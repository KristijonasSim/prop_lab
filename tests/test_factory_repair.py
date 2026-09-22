"""STEP 4 — the repair stage, and the two grammar terms it needed.

The design is in `docs/STEP4.md`. What these pin is the thing that separates a
repair stage from a fishing expedition: the list is FIXED, each near-miss gets
the matching subset ONCE, and "not far off" is a number rather than a feeling.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from factory import build, check, repair
from factory.guard import LookAheadError, Window
from factory.spec import Condition, Strategy, Term


def _bars(n=3000, *, drift=0.0004, seed=7, start="2024-01-01"):
    rng = np.random.default_rng(seed)
    close = 100 * np.exp(np.cumsum(rng.standard_normal(n) * 0.002 + drift))
    idx = pd.date_range(start, periods=n, freq="1h", tz="UTC")
    return pd.DataFrame({"open": close, "high": close * 1.002,
                         "low": close * 0.998, "close": close,
                         "volume": np.ones(n), "hour": idx.hour.astype(float)},
                        index=idx)


def _check(verdict="FAIL", **kw):
    c = check.Check(idea="x", market="XAUUSD", tf="1h", verdict=verdict)
    for k, v in kw.items():
        if k == "mean_r":
            c.mean_r.update(v)
        else:
            setattr(c, k, v)
    return c


def _simple(side="long", **kw) -> Strategy:
    return Strategy(name="s", side=side,
                    entry=(Condition(Term("price"), "above",
                                     Term("const", value=0.0)),), **kw)


# ------------------------------------------------------- the grammar additions
def test_the_clock_is_readable_and_still_cannot_reach_forward():
    """`hour` is a property of bar t, so it cannot leak - but the guard still
    has to hold for it, or it becomes a hole in the one structural guarantee."""
    f = _bars(200)
    w = Window(f, t=100)
    assert w.hour[-1] == pytest.approx(f["hour"].iloc[100])
    for bad in (lambda: w.hour[101], lambda: w.hour[0], lambda: w.hour[-5:200]):
        with pytest.raises(LookAheadError):
            bad()


def test_a_frame_without_a_clock_makes_every_hour_condition_false():
    """The safe direction. A session filter that silently matched every bar
    would look like a working filter and quietly be nothing."""
    from factory.spec import INDICATORS
    f = _bars(200).drop(columns=["hour"])
    assert INDICATORS["hour"][0](Window(f, t=100)) == 0.0
    s = repair._session(*repair.LONDON_NY, tag="t")(_simple())
    fire, _ = build.series(s, f.reset_index(drop=True))
    assert not fire.any()


def test_vwap_is_volume_weighted_and_survives_a_dead_stretch():
    from factory.spec import INDICATORS
    n = 100
    close = np.full(n, 100.0)
    close[-5:] = 200.0
    vol = np.ones(n)
    vol[-5:] = 99.0                            # the expensive bars carry the volume
    f = _bars(n)
    f = f.assign(open=close, high=close, low=close, close=close, volume=vol)
    v = INDICATORS["vwap"][0](Window(f, t=n - 1), 10)
    assert v > 150, "a volume-weighted mean must follow the volume"

    dead = f.assign(volume=np.zeros(n))
    v0 = INDICATORS["vwap"][0](Window(dead, t=n - 1), 10)
    assert np.isfinite(v0), "a padded weekend must not divide by zero"


# ---------------------------------------------------------------- the list
def test_every_repair_produces_a_runnable_strategy():
    f = _bars()
    for r in repair.REPAIRS:
        out = r.apply(_simple())
        assert isinstance(out, Strategy)
        assert r.name in out.name
        build.series(out, f.reset_index(drop=True))     # must not raise


def test_a_thin_idea_is_never_handed_a_filter():
    """The finding the list is built around: 24 of 25 entry filters on H-027
    raised profit factor and LOWERED R per day. A filter spends trades, and the
    commonest step 3 failure is not having enough of them."""
    names = {r.name for r in repair.repairs_for("trades")}
    assert not (names & {"London+NY", "NY only", "with trend",
                         "against trend", "price past vwap", "busy"})
    assert "hold 24" in names


def test_the_trend_filter_means_the_same_thing_on_both_sides():
    """"With the trend" must not quietly mean "long only"."""
    long_ = repair._trend(True)(_simple("long"))
    short = repair._trend(True)(_simple("short"))
    assert long_.entry[-1].op == "above"
    assert short.entry[-1].op == "below"
    assert repair._trend(False)(_simple("long")).entry[-1].op == "below"


def test_a_session_repair_really_restricts_the_hours():
    f = _bars(3000)
    s = repair._session(*repair.LONDON_NY, tag="t")(_simple())
    fire, _ = build.series(s, f.reset_index(drop=True))
    hours = set(f["hour"].values[fire])
    assert hours <= set(range(7, 17)), f"fired outside the window: {sorted(hours)}"
    assert hours, "the window fired on nothing at all"


# ------------------------------------------------------------- "not far off"
def test_a_count_near_miss_is_a_quarter_short_at_most():
    floor = check.MIN_TRADES_PER_DAY
    near = _check(trades_per_day=floor * 0.8, n_trades=90,
                  reasons=["0.32 trades/day, under 0.4 (mean hold 1.0 days)"])
    far = _check(trades_per_day=floor * 0.5, n_trades=90,
                 reasons=["0.20 trades/day, under 0.4 (mean hold 1.0 days)"])
    assert repair.near_miss(near)
    assert not repair.near_miss(far)


def test_an_edge_near_miss_is_measured_in_standard_errors_not_percent():
    """The threshold on the edge gates is ZERO, and a percentage of zero says
    nothing. Within one standard error of breakeven is a result noise could
    have flipped, which is the honest reading of "not far off"."""
    near = _check(mean_r={1.0: -0.01}, mean_r_se=0.02,
                  reasons=["mean -0.010 R at 1x cost (1.83 bps)"])
    far = _check(mean_r={1.0: -0.30}, mean_r_se=0.02,
                 reasons=["mean -0.300 R at 1x cost (1.83 bps)"])
    assert repair.near_miss(near)
    assert not repair.near_miss(far)


def test_a_passing_cell_is_not_a_near_miss():
    assert not repair.near_miss(_check(verdict="PASS"))


def test_closeness_puts_the_four_gates_on_one_scale():
    """Without it, a cell that died on trade count has no mean R at all and
    every count-failure sorted to the bottom, so the choice between them was
    arbitrary. Found while running the queue, 2026-09-22."""
    counted = _check(trades_per_day=0.38, n_trades=200,
                     reasons=["0.38 trades/day, under 0.4 (mean hold 1.0 days)"])
    barely = _check(trades_per_day=0.31, n_trades=200,
                    reasons=["0.31 trades/day, under 0.4 (mean hold 1.0 days)"])
    costly = _check(mean_r={1.0: -0.019}, mean_r_se=0.02,
                    reasons=["mean -0.019 R at 1x cost (1.83 bps)"])
    assert repair.closeness(counted) > repair.closeness(barely)
    assert repair.closeness(counted) > repair.closeness(costly)
    assert repair.best_near_miss([barely, costly, counted]) is counted


# ------------------------------------------------------------------ the loop
def test_each_matching_repair_is_tried_exactly_once(monkeypatch):
    """No adaptive search, no second round, no repair of a repair. The count of
    extra trials an idea costs has to be knowable in advance."""
    f = _bars()
    target = _check(trades_per_day=0.38, n_trades=200,
                    reasons=["0.38 trades/day, under 0.4 (mean hold 1.0 days)"])
    monkeypatch.setattr(repair.cells, "load", lambda *_: f)
    monkeypatch.setattr(repair.cells, "trading_days", lambda *_: 125.0)

    seen = []
    real = check.check

    def spy(strategy, frame, **kw):
        seen.append(strategy.name)
        return real(strategy, frame, **kw)

    monkeypatch.setattr(repair.check, "check", spy)
    attempts, _ = repair.repair(_simple(), [target], control_seeds=2)
    expected = [r.name for r in repair.repairs_for("trades")]
    assert [a.repair for a in attempts] == expected
    assert len(seen) == len(expected), "a repair was tried twice"


def test_nothing_is_attempted_when_nothing_came_close():
    far = _check(trades_per_day=0.05, n_trades=10,
                 reasons=["10 trades, under 100; 0.05 trades/day, under 0.4"])
    attempts, fixed = repair.repair(_simple(), [far], control_seeds=2)
    assert attempts == [] and fixed is None


def test_the_first_passing_repair_is_taken_not_the_best(monkeypatch):
    """Picking the BEST of several passing repairs would be a selection made on
    the test data - the exact move the stage exists to avoid."""
    f = _bars()
    target = _check(trades_per_day=0.38, n_trades=200,
                    reasons=["0.38 trades/day, under 0.4 (mean hold 1.0 days)"])
    monkeypatch.setattr(repair.cells, "load", lambda *_: f)
    monkeypatch.setattr(repair.cells, "trading_days", lambda *_: 125.0)

    order = [r.name for r in repair.repairs_for("trades")]
    scores = {n: 0.5 if n in (order[1], order[2]) else -1.0 for n in order}

    def fake(strategy, frame, **kw):
        tag = strategy.name.split("[")[-1].rstrip("]")
        c = _check(verdict="PASS" if scores[tag] > 0 else "FAIL")
        c.mean_r[1.0] = scores[tag]
        return c

    monkeypatch.setattr(repair.check, "check", fake)
    _, fixed = repair.repair(_simple(), [target], control_seeds=2)
    assert fixed is not None
    assert fixed.name.endswith(f"[{order[1]}]"), "took a later repair over the first"
