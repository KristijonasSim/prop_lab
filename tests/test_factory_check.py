"""STEP 3 — the four gates. Each test pins one gate against a planted case.

The design and the measurements behind the constants are in `docs/STEP3.md`.
These tests pin the BEHAVIOUR: that each gate fires on the shape it was built
for, that it does not fire on the shape it was not, and that the two
denominators the gates divide by - trading days and the 1R risk - mean what the
docstrings say they mean.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from factory import build, check
from factory.spec import Condition, Strategy, Term


def _bars(close: np.ndarray, *, start="2024-01-01", freq="1h", wick=0.002,
          volume: np.ndarray | None = None) -> pd.DataFrame:
    """Bars around a close path. `wick` sets the range, and so sets the ATR."""
    idx = pd.date_range(start, periods=len(close), freq=freq, tz="UTC")
    v = np.ones(len(close)) if volume is None else volume
    return pd.DataFrame({"open": close, "high": close * (1 + wick),
                         "low": close * (1 - wick), "close": close, "volume": v},
                        index=idx)


@pytest.fixture
def drifting_up():
    """A market that only goes up. Random entry makes money here."""
    n = 6000
    rng = np.random.default_rng(7)
    r = rng.standard_normal(n) * 0.002 + 0.0004      # positive drift
    return _bars(100 * np.exp(np.cumsum(r)))


def always_long(max_hold: int = 24) -> Strategy:
    """Fires on every bar: price above a 1-bar high is true nearly always."""
    return Strategy(name="always", side="long",
                    entry=(Condition(Term("price"), "above", Term("const", value=0.0)),),
                    stop_atr=2.0, target_atr=3.0, max_hold=max_hold)


# ------------------------------------------------------------ the denominators
def test_trading_days_is_the_same_whatever_the_bar_size():
    """The whole point of counting sessions rather than bar-days.

    A trades/day figure has to be comparable across a market's four cells, so
    the denominator must not depend on the timeframe it is measured through.
    """
    n = 24 * 400
    close = np.full(n, 100.0)
    hourly = _bars(close)
    four_hourly = (hourly.resample("4h")
                   .agg({"open": "first", "high": "max", "low": "min",
                         "close": "last", "volume": "sum"}))
    assert check.trading_days(hourly) == pytest.approx(400, rel=0.02)
    assert (check.trading_days(four_hourly)
            == pytest.approx(check.trading_days(hourly), rel=0.05))


def test_dead_bars_do_not_count_as_trading_days():
    """21.5% of the gold series is a padded weekend at a frozen price."""
    n = 24 * 100
    vol = np.ones(n)
    vol[: 24 * 40] = 0.0                       # the first 40 days never traded
    frame = _bars(np.full(n, 100.0), volume=vol)
    assert check.trading_days(frame) == pytest.approx(60, rel=0.05)


def test_risk_is_stored_so_a_trade_can_be_repriced_exactly():
    """Gate 2 reports 1x/2x/3x by arithmetic, not by re-running the rule.

    Re-running at a higher cost would also re-open `build`'s min-risk guard and
    change WHICH trades exist, so the multiples would stop being like-for-like.
    """
    frame = _bars(100 * np.exp(np.cumsum(
        np.random.default_rng(3).standard_normal(3000) * 0.003)))
    s = always_long()
    sig = build.series(s, frame.reset_index(drop=True))
    one = build.run(s, frame.reset_index(drop=True), cost_bps=10.0, signals=sig)
    two = build.run(s, frame.reset_index(drop=True), cost_bps=20.0, signals=sig)
    assert len(one) == len(two)
    for a, b in zip(one, two):
        repriced = a.r - a.entry_px * 10.0 / 1e4 / a.risk
        assert repriced == pytest.approx(b.r, abs=1e-9)


# ------------------------------------------------------------------ the gates
def test_gate_1_rejects_a_rule_that_does_not_trade_enough(drifting_up):
    s = Strategy(name="rare", side="long",
                 entry=(Condition(Term("rsi", length=14), "cross_above",
                                  Term("const", value=95.0)),),
                 max_hold=24)
    c = check.check(s, drifting_up, market="XAUUSD", tf="1h",
                    round_trip_bps=1.0, control_seeds=2)
    assert c.verdict == "FAIL"
    assert any("trades" in r for r in c.reasons)


def test_a_long_hold_is_reported_next_to_a_low_trade_rate(drifting_up):
    """`max_hold` is NOT a rate ceiling, and an earlier version claimed it was.

    That version computed `bars_per_day / max_hold` and labelled any cell below
    the floor CELL IMPOSSIBLE. It is wrong: almost every trade exits early on
    its stop or target, so a rule with `max_hold=5000` still traded 254 times in
    250 days. The real bound is one trade per bar. What step 3 reports instead
    is the MEASURED mean hold, which explains a low rate without overclaiming.
    """
    s = always_long(max_hold=5000)
    c = check.check(s, drifting_up, market="XAUUSD", tf="1h",
                    round_trip_bps=1.0, control_seeds=2)
    assert c.trades_per_day > 1.0 / (5000 / 24), "max_hold does not cap the rate"
    assert 0 < c.mean_hold_days < 5000 / 24


def test_gate_2_rejects_a_rule_that_loses_to_its_own_costs():
    """The same rule passes cheap and fails expensive. Only the cost changes.

    A WIDE-RANGE frame, deliberately. `build`'s min-risk guard refuses any bar
    whose 2-ATR stop is not at least twice the round trip, so on a quiet series
    a large cost empties the trade list and the cell dies on gate 1 instead -
    a different finding. Wide bars keep the trades and let the cost do the work.
    """
    n = 6000
    rng = np.random.default_rng(7)
    close = 100 * np.exp(np.cumsum(rng.standard_normal(n) * 0.002 + 0.0004))
    frame = _bars(close, wick=0.02)
    s = always_long()
    cheap = check.check(s, frame, market="XAUUSD", tf="1h",
                        round_trip_bps=0.1, control_seeds=2)
    dear = check.check(s, frame, market="XAUUSD", tf="1h",
                       round_trip_bps=400.0, control_seeds=2)
    assert dear.n_trades >= check.MIN_TRADES, "the guard must not empty the cell"
    assert dear.verdict == "FAIL"
    assert any("at 1x cost" in r for r in dear.reasons)
    assert cheap.mean_r[1.0] > dear.mean_r[1.0]


def test_gate_2_reports_three_cost_multiples_and_they_fall(drifting_up):
    c = check.check(always_long(), drifting_up, market="XAUUSD", tf="1h",
                    round_trip_bps=5.0, control_seeds=2)
    assert set(c.mean_r) == set(check.COST_MULTIPLES)
    assert c.mean_r[1.0] > c.mean_r[2.0] > c.mean_r[3.0]


def test_gate_3_rejects_a_rule_carried_by_a_handful_of_trades():
    """The check that replaces `core/screen.py`'s median gate.

    A median gate cannot be used on trades: a stop at 1R makes the median about
    -1R whenever the win rate is under 50%, which is the normal shape of a
    breakout. Concentration is the question that gate was really asking.
    """
    rng = np.random.default_rng(11)
    r = np.full(300, -0.10)
    r[:4] = 40.0                               # four trades carry everything
    rng.shuffle(r)
    assert r.mean() > 0                        # profitable overall...
    assert np.sort(r)[:-check.DROP_BEST].mean() < 0   # ...and only just, on 4
    assert np.median(r) < 0                    # and the median says nothing


def test_gate_4_rejects_a_rule_that_loses_to_random_entry(drifting_up):
    """Gold rose 123% in the cached window; 14 of 19 "winners" were that.

    An always-fires rule on a rising market has, by construction, no entry
    information at all - it is the drift and nothing else. Its own random-entry
    control must therefore match it, and the gate must refuse it.
    """
    s = always_long()
    c = check.check(s, drifting_up, market="XAUUSD", tf="1h",
                    round_trip_bps=0.5, control_seeds=12)
    assert c.mean_r[1.0] > 0, "the drift alone should look profitable"
    assert c.verdict == "FAIL"
    assert any("random entry" in r for r in c.reasons)


def test_the_control_changes_the_entries_and_nothing_else(drifting_up):
    """What makes gate 4 a PAIRED comparison rather than a second study.

    A SPARSE rule, deliberately. `always_long` fires on nearly every bar, so
    shuffling its entries reproduces them and the control becomes the real run -
    which is worth knowing: the control has no power against a rule that is
    always in the market, and such a rule is pure drift by definition.
    """
    s = Strategy(name="sparse", side="long",
                 entry=(Condition(Term("rsi", length=14), "cross_above",
                                  Term("const", value=70.0)),),
                 stop_atr=2.0, target_atr=3.0, max_hold=24)
    frame = drifting_up.reset_index(drop=True)
    fire, atr = build.series(s, frame)
    rng = np.random.default_rng(0)
    shuffled = np.zeros_like(fire)
    shuffled[rng.choice(len(fire), size=int(fire.sum()), replace=False)] = True

    real = build.run(s, frame, cost_bps=1.0, signals=(fire, atr))
    ctrl = build.run(s, frame, cost_bps=1.0, signals=(shuffled, atr))
    assert {t.side for t in ctrl} == {t.side for t in real} == {"long"}
    assert max(t.exit_bar - t.entry_bar for t in ctrl) <= s.max_hold
    assert [t.entry_bar for t in ctrl] != [t.entry_bar for t in real]


# ------------------------------------------------------------------- plumbing
def test_nothing_short_circuits_so_every_failure_is_recorded(drifting_up):
    """CHANGED 2026-09-23, and the reason is a real misreading it caused.

    The gates used to return on the first failure, so a Check said which gate
    fired FIRST rather than what was true. Kris's first translated script was
    reported as "too few trades" on its holdout when it ALSO lost money there
    and scored worse than random - the two facts that decide whether the idea
    is worth repairing, hidden behind the cheapest one.

    Everything is measured now. It costs milliseconds and a rule with one
    failing gate reads differently from a rule with three.
    """
    s = Strategy(name="rare", side="long",
                 entry=(Condition(Term("rsi", length=14), "cross_above",
                                  Term("const", value=99.0)),),
                 max_hold=24)
    c = check.check(s, drifting_up, market="XAUUSD", tf="1h",
                    round_trip_bps=1.0, control_seeds=2)
    assert c.verdict == "FAIL"
    assert c.mean_r, "cost was never priced"
    assert not np.isnan(c.control_p90), "the control was never run"


def test_a_slow_rule_is_flagged_not_killed(drifting_up):
    """Kris, 2026-09-23: *"if this strategy is 0.33 a day but its PF is 3 and
    very low dd, you would just say its unusable... why?"*

    Trades/day is a PACE preference and `core/riskladder` already prices pace
    as expected days. The hundred-trade floor is different - it is whether the
    mean can be measured at all - and that one still kills.
    """
    s = Strategy(name="rare", side="long",
                 entry=(Condition(Term("rsi", length=14), "cross_above",
                                  Term("const", value=99.0)),),
                 max_hold=24)
    c = check.check(s, drifting_up, market="XAUUSD", tf="1h",
                    round_trip_bps=1.0, control_seeds=2)
    assert any("slow" in f for f in c.flags)
    assert not any("trades/day" in r for r in c.reasons)
    assert any("under 100" in r for r in c.reasons)


def test_an_idea_survives_if_any_one_cell_passes():
    """Kris, 2026-09-21: "If only ONE of the 24 works, that is fine.\""""
    good = check.Check(idea="x", market="XAUUSD", tf="1h", verdict="PASS")
    good.mean_r[1.0] = 0.2
    bad = check.Check(idea="x", market="BTCUSDT", tf="1h", verdict="FAIL")
    verdict, shown = check.verdict_of([bad, good])
    assert verdict == "PASS"
    assert shown == [good]


def test_a_failing_idea_reports_its_closest_cells():
    checks = []
    for i, sym in enumerate(("XAUUSD", "BTCUSDT", "EURUSD", "GBPUSD")):
        c = check.Check(idea="x", market=sym, tf="1h", verdict="FAIL")
        c.mean_r[1.0] = -0.1 * i
        checks.append(c)
    verdict, shown = check.verdict_of(checks)
    assert verdict == "FAIL"
    assert len(shown) == 3
    assert shown[0].market == "XAUUSD"       # least bad first
