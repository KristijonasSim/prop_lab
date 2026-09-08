"""Engine 2 itself. The runner that decides every future number on the board.

`core/pipeline.py` was written on 2026-09-08 and was, for a few hours, the only
code in the repo with no tests — while being the code every future result would
flow through. These are the invariants that matter, tested on a fake strategy so
they run in under a second and fail for one reason each.

THE FIRST TEST IS THE IMPORTANT ONE. Every number this project has had to
retract came from selection touching data it was later scored on. The pipeline's
whole job is to make that impossible, so the suite proves it directly: the
strategy records every bar range it is handed, and the assertion is that during
SELECTION it never saw a bar at or after the test window opened.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.nulls import (NULLS, null_seed, shuffle_market,      # noqa: E402
                        shuffle_market_paired)
from core.pipeline import Market, Pipeline, gate_counts, pf    # noqa: E402
from core.strategy import N_COLS, T_ENTRY_I, T_EXIT_I          # noqa: E402


def bars(n=26000, start="2022-01-01", freq="1h", seed=0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    idx = pd.date_range(start, periods=n, freq=freq, tz="UTC")
    close = 100 * np.exp(np.cumsum(rng.normal(0, 0.002, n)))
    o = np.concatenate(([close[0]], close[:-1]))
    return pd.DataFrame({"open": o,
                         "high": np.maximum(o, close) * 1.001,
                         "low": np.minimum(o, close) * 0.999,
                         "close": close,
                         "volume": rng.uniform(1, 10, n)}, index=idx)


class FakeStrategy:
    """Trades every `cfg['every']`-th bar, holds `cfg['hold']` bars.

    Deterministic and cheap, and it RECORDS the first and last timestamp of
    every frame it is handed so a test can prove what the pipeline showed it.
    """

    name = "fake"

    def __init__(self):
        self.seen: list[tuple[pd.Timestamp, pd.Timestamp]] = []

    def features(self, df):
        return df.close.values

    def grid(self, tf):
        return [{"every": e, "hold": h} for e in (50, 80) for h in (3, 7)]

    def run(self, df, cfg, fee_bps, slip_bps, feats=None, **kw):
        self.seen.append((df.index[0], df.index[-1]))
        n = len(df)
        ent = np.arange(1, max(n - cfg["hold"] - 1, 1), cfg["every"])
        ext = np.minimum(ent + cfg["hold"], n - 1)
        out = np.zeros((len(ent), N_COLS))
        out[:, T_ENTRY_I] = ent
        out[:, T_EXIT_I] = ext
        out[:, 2] = 1.0
        out[:, 3] = df.open.values[ent]
        out[:, 4] = df.close.values[ext]
        px = df.close.values
        gross = (px[ext] - px[ent]) / px[ent]
        out[:, 5] = gross * 100 - (fee_bps + slip_bps) / 100.0
        return out


@pytest.fixture
def market():
    return Market(sym="TEST", tf="1h", df=bars(), fee_bps=1.0, slip_bps=0.5,
                  pad_bars=100)


@pytest.fixture
def pipe():
    return Pipeline(FakeStrategy(), train_months=12, test_months=3)


# --------------------------------------------------------------------------- #
# the one that matters
# --------------------------------------------------------------------------- #
def test_selection_never_sees_the_test_window(market):
    """No leakage, proved rather than asserted.

    Every fold runs the whole grid on TRAIN before it touches TEST. If any of
    those selection calls were handed bars from at or after the fold boundary,
    the configuration would have been chosen on data it is then scored on -
    which is the single failure mode that has cost this project the most.
    """
    s = FakeStrategy()
    p = Pipeline(s, train_months=12, test_months=3)
    res = p.walk_forward(market)
    assert len(res.folds), "the fixture produced no folds; the test proves nothing"

    n_cfgs = len(s.grid("1h"))
    quarters = sorted(pd.Timestamp(q, tz="UTC") for q in set(res.folds.quarter))
    # Calls arrive in fold order: n_cfgs selection calls on TRAIN, then the test
    # calls. Each selection block must end strictly before its fold boundary.
    i = 0
    for q in quarters:
        block = s.seen[i:i + n_cfgs]
        assert len(block) == n_cfgs
        for lo, hi in block:
            assert hi < q, (
                f"selection for the quarter starting {q} was shown bars up to "
                f"{hi} - the configuration was chosen on data it is scored on")
        i += n_cfgs
        # skip however many distinct test-slice calls this fold made
        while i < len(s.seen) and s.seen[i][1] >= q:
            i += 1


def test_every_trade_falls_inside_a_test_window(market, pipe):
    """A trade entered inside the warm-up pad is the pad's, not the fold's, and
    must be dropped - otherwise the same bars are counted in two folds."""
    res = pipe.walk_forward(market)
    assert len(res.trades)
    for q, g in res.trades.groupby("quarter"):
        q0 = pd.Timestamp(q, tz="UTC")
        assert (g.entry_ts >= q0).all(), (
            f"quarter {q}: a trade was entered before the window opened")


def test_trades_are_ordered_and_have_both_cost_levels(market, pipe):
    res = pipe.walk_forward(market)
    for _, g in res.trades.groupby(["quarter", "floor", "topn"]):
        assert g.exit_ts.is_monotonic_increasing
    assert res.trades.r_2x.notna().all(), "2x cost missing on some trades"
    # 2x cost must be worse on every trade - it is the same trades, charged more
    assert (res.trades.r_2x <= res.trades.r + 1e-12).all()


def test_the_null_is_a_different_market_but_the_same_procedure(market, pipe):
    real = pipe.walk_forward(market)
    null = pipe.walk_forward(market, shuffled="paired", tag="t")
    assert len(null.folds), "the null produced nothing to compare against"
    # same shape of search, different outcome
    assert set(real.folds.quarter) == set(null.folds.quarter)
    assert not np.allclose(sorted(real.trades.r.values[:50]),
                           sorted(null.trades.r.values[:50]))


def test_it_is_deterministic(market):
    a = Pipeline(FakeStrategy()).walk_forward(market)
    b = Pipeline(FakeStrategy()).walk_forward(market)
    pd.testing.assert_frame_equal(a.folds, b.folds)
    pd.testing.assert_frame_equal(a.trades, b.trades)


def test_a_kernel_that_breaks_the_contract_is_refused(market):
    """The pipeline runs `conforms` on every kernel output. A strategy that
    returns overlapping positions or an out-of-range bar index must stop the run,
    not quietly produce a board number."""
    class Broken(FakeStrategy):
        def run(self, df, cfg, fee_bps, slip_bps, feats=None, **kw):
            out = super().run(df, cfg, fee_bps, slip_bps, feats)
            if len(out):
                out[0, T_EXIT_I] = len(df) + 500      # exits past the series
            return out

    with pytest.raises(ValueError, match="contract"):
        Pipeline(Broken()).walk_forward(market)


def test_a_strategy_that_never_trades_produces_empty_frames(market):
    class Silent(FakeStrategy):
        def run(self, df, cfg, fee_bps, slip_bps, feats=None, **kw):
            return np.zeros((0, N_COLS))

    res = Pipeline(Silent()).walk_forward(market)
    assert len(res.trades) == 0
    assert gate_counts(res.folds) == (0, 0)


def test_the_per_slice_cache_is_shared_across_configs(market):
    """`new_cache` exists so an expensive config-independent computation is done
    once per slice. If the pipeline handed out a fresh cache per config, vwap's
    anchored VWAP would be rebuilt 12,960 times per fold."""
    seen = []

    class Cached(FakeStrategy):
        def new_cache(self):
            d = {"box": {}}
            seen.append(d["box"])
            return d

        def run(self, df, cfg, fee_bps, slip_bps, feats=None, box=None, **kw):
            box[len(box)] = 1
            return super().run(df, cfg, fee_bps, slip_bps, feats)

    Pipeline(Cached()).walk_forward(market)
    assert seen, "new_cache was never called"
    assert max(len(b) for b in seen) > 1, (
        "each config got a fresh cache - the whole point is that they share one")


# --------------------------------------------------------------------------- #
# the nulls
# --------------------------------------------------------------------------- #
def test_null_seed_is_stable_across_processes():
    """Seeds used to come from `hash()`, which Python randomises per process, so
    no null result could be reproduced - H-007's verdict flipped between two runs
    of identical code."""
    assert null_seed("BTC", "1h", "x") == null_seed("BTC", "1h", "x")
    assert null_seed("BTC", "1h", "x") != null_seed("BTC", "4h", "x")


@pytest.mark.parametrize("kind", sorted(NULLS))
def test_a_null_keeps_the_returns_and_destroys_their_order(kind):
    df = bars(4000)
    out = NULLS[kind](df, 7)
    assert len(out) == len(df)
    a = np.sort(np.diff(np.log(df.close.values)))
    b = np.sort(np.diff(np.log(out.close.values)))
    np.testing.assert_allclose(a, b, atol=1e-12)
    assert not np.allclose(df.close.values, out.close.values)
    # bars stay self-consistent or the kernel is trading impossible candles
    assert (out.high >= out.low).all()
    assert (out.high >= out[["open", "close"]].max(axis=1) - 1e-12).all()
    assert (out.low <= out[["open", "close"]].min(axis=1) + 1e-12).all()


def test_the_paired_null_keeps_each_bar_with_its_own_volume():
    """`shuffle_market` permutes volume independently, which quietly hands any
    participation filter a free win. The paired null moves (return, volume)
    together so only the SEQUENCE is destroyed."""
    df = bars(4000)
    plain = shuffle_market(df, 3)
    paired = shuffle_market_paired(df, 3)
    np.testing.assert_allclose(np.sort(df.volume.values),
                               np.sort(paired.volume.values), atol=1e-12)
    assert not np.allclose(plain.volume.values, paired.volume.values)
