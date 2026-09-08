"""Degenerate and adversarial inputs, including the two that produced real bugs.

Both bugs fixed on 2026-09-07 were degenerate-input bugs and both were found by
accident, by porting the kernel to a second engine and chasing a disagreement:

  1. `sd <= 0.0` as a volatility guard. `vwstd = sqrt(p2v/v - vwap^2)` is a
     difference of two nearly equal accumulated sums, so its cancellation floor
     is price*sqrt(eps) - about 3e-5 on gold. A session made entirely of padded
     weekend bars has a TRUE sigma of exactly zero and returned 3.1e-5 of pure
     floating-point noise, which sailed past `<= 0.0`. The kernel then built
     bands out of that noise and traded them.
  2. Trading the padded bars at all. Dukascopy fills the closed FX weekend with
     zero-volume bars carrying the last price as O=H=L=C. 21.5% of the XAUUSD
     series is these. H-002's 1h leg took 25.19R of 54.25R from entries on one.

`hypothesis` generates the inputs rather than us guessing them, which is the
point: every bug this project has found was an input nobody thought to write by
hand.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from tests.kernels import IDS, KERNELS, T_ENTRY_I, T_EXIT_I, T_R

SETTINGS = settings(max_examples=25, deadline=None,
                    suppress_health_check=[HealthCheck.function_scoped_fixture,
                                           HealthCheck.too_slow])


def frame(close: np.ndarray, volume: np.ndarray | None = None,
          spread: float = 0.001) -> pd.DataFrame:
    """A well-formed OHLC frame around a close path. High and low bracket the
    open and close by construction, so any kernel failure is about the kernel."""
    n = len(close)
    idx = pd.date_range("2024-01-01", periods=n, freq="1h", tz="UTC")
    o = np.concatenate(([close[0]], close[:-1]))
    hi = np.maximum(o, close) * (1 + spread)
    lo = np.minimum(o, close) * (1 - spread)
    v = np.ones(n) if volume is None else volume
    return pd.DataFrame({"open": o, "high": hi, "low": lo, "close": close,
                         "volume": v}, index=idx)


# --------------------------------------------------------------------------- #
# the two real bugs, pinned
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("kernel", KERNELS, ids=IDS)
def test_no_trade_touches_a_zero_volume_bar(kernel):
    """CLAUDE.md rule 1: never decide or fill on a bar where nothing traded.

    A 400-bar series with a 120-bar dead block in the middle, shaped exactly like
    Dukascopy's weekend: zero volume, price frozen at the last traded level.
    """
    n, lo, hi = 400, 150, 270
    rng = np.random.default_rng(7)
    close = 2000 + np.cumsum(rng.normal(0, 2.0, n))
    close[lo:hi] = close[lo - 1]                 # price frozen
    df = frame(close, spread=0.002)
    df.iloc[lo:hi, df.columns.get_loc("volume")] = 0.0
    for col in ("open", "high", "low", "close"):  # O=H=L=C, as the pad really is
        df.iloc[lo:hi, df.columns.get_loc(col)] = close[lo - 1]

    tr = kernel.run(df, kernel.cfg, 1.0, 0.5)
    if len(tr) == 0:
        return
    dead = np.zeros(n, dtype=bool)
    dead[lo:hi] = True
    assert not dead[tr[:, T_ENTRY_I].astype(int)].any(), (
        f"{kernel.name} entered on a zero-volume bar")
    assert not dead[tr[:, T_EXIT_I].astype(int)].any(), (
        f"{kernel.name} exited on a zero-volume bar")


@pytest.mark.parametrize("kernel", KERNELS, ids=IDS)
def test_an_entirely_dead_series_produces_no_trades(kernel):
    """The exact shape that defeated `sd <= 0.0`: a whole series of padding, whose
    true volatility is zero and whose computed sigma is floating-point noise."""
    n = 300
    df = frame(np.full(n, 2000.0), volume=np.zeros(n), spread=0.0)
    tr = kernel.run(df, kernel.cfg, 1.0, 0.5)
    assert len(tr) == 0, (
        f"{kernel.name} produced {len(tr)} trades on a market that never traded. "
        f"Check the volatility guard uses a price-relative tolerance "
        f"(sd <= price * 1e-6), not sd <= 0.0.")


@pytest.mark.parametrize("kernel", KERNELS, ids=IDS)
def test_constant_price_with_real_volume_produces_no_trades(kernel):
    """Volume, but no movement. Sigma is genuinely zero and every band collapses
    onto the price. Anything that trades here is trading numerical noise."""
    n = 300
    df = frame(np.full(n, 2000.0), volume=np.full(n, 5.0), spread=0.0)
    tr = kernel.run(df, kernel.cfg, 1.0, 0.5)
    assert len(tr) == 0, f"{kernel.name} traded a market that never moved"


# --------------------------------------------------------------------------- #
# shape edges
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("kernel", KERNELS, ids=IDS)
@pytest.mark.parametrize("n", [0, 1, 2, 3, 10])
def test_tiny_series_does_not_crash(kernel, n):
    """Zero, one and a handful of bars. A kernel that indexes i-1 or reads a
    rolling window unguarded dies here, and the walk-forward hits short windows
    at the start of every fold."""
    df = frame(np.full(max(n, 1), 2000.0)).iloc[:n]
    tr = kernel.run(df, kernel.cfg, 1.0, 0.5)
    assert tr.shape[1] == 8
    assert len(tr) == 0


# --------------------------------------------------------------------------- #
# property-based: hypothesis picks the inputs
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("kernel", KERNELS, ids=IDS)
@SETTINGS
@given(steps=st.lists(st.floats(min_value=-30, max_value=30,
                                allow_nan=False, allow_infinity=False),
                      min_size=60, max_size=400),
       dead=st.lists(st.booleans(), min_size=60, max_size=400))
def test_never_produces_a_non_finite_r(kernel, steps, dead):
    """Whatever the path, every R must be a finite number. A NaN or an inf here
    propagates silently into the profit factor and the risk ladder, where it
    reads as a result rather than as a bug."""
    close = 2000 + np.cumsum(np.array(steps))
    close = np.maximum(close, 1.0)               # a price cannot go to zero
    vol = np.ones(len(close))
    m = min(len(close), len(dead))
    vol[:m] = np.where(np.array(dead[:m]), 0.0, 1.0)
    tr = kernel.run(frame(close, vol), kernel.cfg, 1.0, 0.5)
    if len(tr):
        assert np.isfinite(tr[:, T_R]).all(), f"{kernel.name} produced a non-finite R"
        assert (tr[:, T_EXIT_I] >= tr[:, T_ENTRY_I]).all(), (
            f"{kernel.name} exited before it entered")


@pytest.mark.parametrize("kernel", KERNELS, ids=IDS)
@SETTINGS
@given(flat_run=st.integers(min_value=1, max_value=120))
def test_a_flat_run_of_any_length_is_never_entered(kernel, flat_run):
    """The dead block, at every length hypothesis cares to try. The weekend gap
    is not a fixed size - a holiday closes the market for longer - so a guard
    tuned to one length is not a guard."""
    n = 400
    rng = np.random.default_rng(11)
    close = 2000 + np.cumsum(rng.normal(0, 2.0, n))
    lo = 200
    hi = min(lo + flat_run, n)
    close[lo:hi] = close[lo - 1]
    df = frame(close, spread=0.002)
    for col in ("open", "high", "low", "close"):
        df.iloc[lo:hi, df.columns.get_loc(col)] = close[lo - 1]
    df.iloc[lo:hi, df.columns.get_loc("volume")] = 0.0

    tr = kernel.run(df, kernel.cfg, 1.0, 0.5)
    if len(tr) == 0:
        return
    dead = np.zeros(n, dtype=bool)
    dead[lo:hi] = True
    assert not dead[tr[:, T_ENTRY_I].astype(int)].any()
    assert not dead[tr[:, T_EXIT_I].astype(int)].any()


# --------------------------------------------------------------------------- #
# the exit path - found 2026-09-08, and the 2026-09-07 fix did not cover it
# --------------------------------------------------------------------------- #
def _dead_block_series(n=600, lo=300, hi=420, seed=3, drift=-6.0):
    """A trend that walks hard against a long, then a closed market.

    Shaped to put a stop INSIDE the dead block: price falls into the weekend, the
    padded bars repeat the last traded price, and a stop sitting at that level is
    'touched' by bars on which nothing traded at all.
    """
    rng = np.random.default_rng(seed)
    close = 2000 + np.cumsum(rng.normal(drift, 3.0, n))
    close[lo:hi] = close[lo - 1]
    df = frame(close, spread=0.002)
    for col in ("open", "high", "low", "close"):
        df.iloc[lo:hi, df.columns.get_loc(col)] = close[lo - 1]
    df.iloc[lo:hi, df.columns.get_loc("volume")] = 0.0
    return df, lo, hi


@pytest.mark.parametrize("kernel", KERNELS, ids=IDS)
@pytest.mark.parametrize("cfgname", ["cfg", "cfg_alt"])
def test_no_exit_lands_on_a_zero_volume_bar(kernel, cfgname):
    """CLAUDE.md rule 1 applies to the EXIT as well as the entry.

    The 2026-09-07 fix guarded the decision bar and the fill bar and stopped
    there. Neither kernel guarded the bar a position is CLOSED on, so a stop or a
    target could be 'hit' by Dukascopy's padded weekend - bars with zero volume
    and the last traded price repeated, on which no order could have filled.

    Measured on the real board books before the fix:
      H-016  776 of 3,916 exits (19.8%) on a zero-volume bar
      H-002  1,079 of 17,432 (6.2%), and 119.12R of the 15m leg's 194.19R
    """
    # Several shapes, because one series that happens to produce no trades
    # would SKIP - and a skipped check verifies nothing while looking like a
    # pass. core/verification.py treats a skip as a failure for exactly this
    # reason, so the test has to guarantee it actually exercises something.
    total = 0
    for seed, drift in ((3, -6.0), (5, +6.0), (11, -3.0), (17, +3.0)):
        df, lo, hi = _dead_block_series(seed=seed, drift=drift)
        tr = kernel.run(df, getattr(kernel, cfgname), 1.0, 0.5)
        if len(tr) == 0:
            continue
        total += len(tr)
        dead = np.zeros(len(df), dtype=bool)
        dead[lo:hi] = True
        bad = dead[tr[:, T_EXIT_I].astype(int)]
        assert not bad.any(), (
            f"{kernel.name} [{cfgname}] seed {seed}: {bad.sum()} of {len(tr)} "
            f"trades exit on a bar where nothing traded. No order could have "
            f"filled there.")
    assert total > 0, (
        f"{kernel.name} [{cfgname}]: no series produced a trade, so this check "
        f"verified nothing. Widen _dead_block_series rather than accept it.")


@pytest.mark.parametrize("kernel", KERNELS, ids=IDS)
@pytest.mark.parametrize("cfgname", ["cfg", "cfg_alt"])
def test_a_stop_never_fills_better_than_the_bar_opened(kernel, cfgname):
    """A stop is a stop-MARKET order. If the bar OPENS beyond it, the fill is
    the open, not the level.

    Filling at the level assumes the price walked down to it, which on a gap it
    did not. Measured on H-016's own legs before the guard existed: 168 of 2,027
    stop exits were gapped, median 13.9-27.2bps through, worst 216bps, and the
    overstatement was 53.2R of 148.3 on the 30m leg alone. This matters more
    since the kernels started holding through the closed weekend, which is
    exactly where gold gaps.

    Stated as an inequality rather than by exit reason, because the reason codes
    differ between kernels and the invariant does not: a LONG can never exit
    above the bar's open when that exit was a stop, and no exit of any kind may
    print outside the bar's own range.
    """
    df, _, _ = _dead_block_series(seed=5, drift=+6.0)
    tr = kernel.run(df, getattr(kernel, cfgname), 1.0, 0.5)
    if len(tr) == 0:
        pytest.skip("no trades")
    xi = tr[:, T_EXIT_I].astype(int)
    hi = df.high.values[xi]
    lo = df.low.values[xi]
    px = tr[:, 4]                              # T_EXIT_PX
    # Every fill must be a price the bar actually contained. A gap fill at the
    # open satisfies this; a fill at a stop the bar gapped past does not.
    assert (px <= hi + 1e-9).all() and (px >= lo - 1e-9).all(), (
        f"{kernel.name} [{cfgname}]: an exit printed outside the bar's range")
