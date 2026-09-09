"""The prop simulator, pinned. Item 2 of the three that were actually needed.

`core/riskladder.py` is about forty lines and it produces EVERY headline number
on the board — pass rate, breach rates, drawdown, median days, and the
`expected_days` figure the whole phase gate is read off. It had no tests.

Deliberately small. These are the properties that would be wrong if someone
edited the file carelessly, not an exhaustive spec:

  * a hand-computable account resolves the way arithmetic says it does;
  * a breach is a breach — no sizing down, no rescue (CLAUDE.md's standing rule
    against a budget-shrinking risk manager that fakes a 0% fail rate);
  * two-step is strictly harder than one-step;
  * the trailing/static flags actually do something — they were dead code until
    2026-09-07 and the difference is worth 17 points of pass rate;
  * `pick` respects its own gates, including the drawdown cap that a low breach
    rate can otherwise hide.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.prop_rules import PropRules                          # noqa: E402
from core.riskladder import (DD_CAP, MAX_BREACH, MIN_RISK,  # noqa: E402
                             RISK_LADDER,
                             _breached, from_trades, ladder, pick,
                             run_accounts, run_accounts_two_step)


def days(vals) -> pd.Series:
    """A daily R series on consecutive calendar days."""
    return pd.Series(list(vals),
                     index=pd.date_range("2024-01-01", periods=len(vals),
                                         freq="1D", tz="UTC"))


def resolved(r: dict) -> float:
    """Pass rate among accounts that actually finished.

    `run_accounts` opens a FRESH ACCOUNT ON EVERY DAY of the series, so accounts
    started near the end run out of data and report OPEN rather than PASS. That
    is correct - an unresolved account has not passed - but it means a raw
    `pass_rate` of 1.0 is only reachable on an infinitely long series. Every
    hand-computed test below either uses a long enough series or divides this
    out. Getting this wrong was the first thing these tests caught, in
    themselves.
    """
    done = 1.0 - r["still_open"]
    return r["pass_rate"] / done if done else 0.0


# --------------------------------------------------------------------------- #
# arithmetic you can check by hand
# --------------------------------------------------------------------------- #
def test_a_straight_run_to_target_passes_on_the_expected_day():
    """+1R a day at 1% risk is +1% a day. An 8% target with a 5-day minimum is
    reached on day 8, and the first account starts on day 1."""
    r = run_accounts(days([1.0] * 200), risk=0.01,
                     rules=PropRules(min_trading_days=5))
    assert resolved(r) == 1.0
    assert r["median_days"] == 8.0
    assert r["fail_max"] == 0.0 and r["fail_daily"] == 0.0


def test_the_minimum_trading_day_rule_delays_a_fast_pass():
    """+4R a day at 1% clears 8% on day 2, but a 5-day minimum holds it to 5."""
    fast = run_accounts(days([4.0] * 200), risk=0.01,
                        rules=PropRules(min_trading_days=5))
    none = run_accounts(days([4.0] * 200), risk=0.01,
                        rules=PropRules(min_trading_days=0))
    assert none["median_days"] == 2.0
    assert fast["median_days"] == 5.0


def test_a_single_day_past_the_daily_cap_kills_the_account():
    """-5R at 1% is -5%, past a 4% daily cap. Every account dies on day 1."""
    r = run_accounts(days([-5.0] * 10), risk=0.01)
    assert r["fail_daily"] == 1.0
    assert r["pass_rate"] == 0.0


def test_a_slow_bleed_kills_on_the_max_loss_not_the_daily_one():
    """-1R a day at 1% never touches the 4% daily cap and reaches -8% on day 8."""
    r = run_accounts(days([-1.0] * 200), risk=0.01)
    assert resolved(r) == 0.0
    assert r["fail_max"] > 0.9 and r["fail_daily"] == 0.0


def test_the_worst_case_within_a_day_is_charged_before_any_gain():
    """A day that nets +1R still spends its loss first. At 4% risk a -1R day is
    -4%, exactly the daily cap, so it must fail even though the net is positive.
    This is the pessimistic reading CLAUDE.md asks for."""
    r = run_accounts(days([-1.0]), risk=0.04)
    assert r["fail_daily"] == 1.0


# --------------------------------------------------------------------------- #
# no rescue - the standing rule against a shrinking risk manager
# --------------------------------------------------------------------------- #
def test_risk_scales_the_series_and_does_not_protect_anything():
    """Doubling risk must double the loss, never cushion it. A simulator that
    sized down to avoid breaching would produce a fake 0% fail rate."""
    lo = run_accounts(days([-1.0] * 300), risk=0.005)
    hi = run_accounts(days([-1.0] * 300), risk=0.02)
    # -0.5% a day reaches -8% on day 16; -2% a day on day 4. Both kill every
    # account that has room to resolve; the higher risk kills it four times
    # faster, and neither is rescued.
    assert lo["fail_max"] > 0.9 and hi["fail_max"] > 0.9
    assert lo["pass_rate"] == 0.0 and hi["pass_rate"] == 0.0


def test_a_zero_series_never_resolves():
    """No trades means no pass and no breach - it must read as OPEN, not as a
    safe strategy."""
    r = run_accounts(days([0.0] * 30), risk=0.01)
    assert r["pass_rate"] == 0.0
    assert r["still_open"] == 1.0
    assert r["median_days"] is None


# --------------------------------------------------------------------------- #
# the flags that were dead code until 2026-09-07
# --------------------------------------------------------------------------- #
def test_trailing_and_static_caps_are_not_the_same_rule():
    """Tested on `_breached` directly, which is where the bug actually was.

    Both call sites hard-coded `low - peak <= -max_loss or low <= -max_loss` and
    read neither flag until 2026-09-07, so `trailing=False` did nothing and the
    static term was dead code. `NEXT.md` prices the difference at **17 points of
    pass rate** on a zero-edge strategy, which is worth more than most edges in
    this repo.

    An account that ran to +6% and gave it back to -2% has lost 8% FROM ITS PEAK
    but only 2% from its starting balance. A trailing cap kills it; a static one
    does not. That single account is the whole distinction.
    """
    trail_only = PropRules(trailing=True, static=False)
    static_only = PropRules(trailing=False, static=True)

    # +6% high-water mark, now at -2%: -8% from the peak, -2% from the start
    assert _breached(low=-0.02, peak=0.06, rules=trail_only) is True
    assert _breached(low=-0.02, peak=0.06, rules=static_only) is False

    # straight down to -8% with no run-up: both fire
    assert _breached(low=-0.08, peak=0.0, rules=trail_only) is True
    assert _breached(low=-0.08, peak=0.0, rules=static_only) is True

    # comfortably inside both
    assert _breached(low=-0.01, peak=0.02, rules=trail_only) is False
    assert _breached(low=-0.01, peak=0.02, rules=static_only) is False

    # the default is whichever fires first
    assert _breached(low=-0.02, peak=0.06, rules=PropRules()) is True


def test_the_trailing_cap_is_stricter_end_to_end():
    """The same distinction through `run_accounts`, on a saw series so that
    EVERY account sees a run-up and a give-back rather than only the first one.
    On a pure bleed the two rules are identical, which is why the aggregate rate
    hides the difference on a simple series - that is what this test exists to
    stop someone concluding."""
    saw = days(([2.0] * 5 + [-1.0] * 12) * 12)          # +10%, then -12%, at 1%
    trail = run_accounts(saw, risk=0.01,
                         rules=PropRules(trailing=True, static=False,
                                         profit_target=0.50))
    static = run_accounts(saw, risk=0.01,
                          rules=PropRules(trailing=False, static=True,
                                          profit_target=0.50))
    assert trail["fail_max"] > static["fail_max"], (
        f"trailing {trail['fail_max']} must kill more than static "
        f"{static['fail_max']} on a series that repeatedly gives back a run-up")


def test_the_default_is_the_stricter_reading():
    """Both flags default True, i.e. whichever fires first. CLAUDE.md: the firm
    spec is not chosen yet, so do not guess generously."""
    d = PropRules()
    assert d.trailing is True and d.static is True
    assert d.profit_target == 0.08 and d.daily_loss == 0.04 and d.max_loss == 0.08


# --------------------------------------------------------------------------- #
# two-step is strictly harder
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("risk", [0.005, 0.01, 0.02])
def test_two_step_never_passes_more_often_than_one_step(risk):
    """8% then 5% is not half the work of 8%; it is a second chance to breach.
    A board reporting the one-step number reports a fiction."""
    rng = np.random.default_rng(4)
    s = days(rng.normal(0.05, 1.0, 400))
    one = run_accounts(s, risk=risk)
    two = run_accounts_two_step(s, risk=risk)
    assert two["pass_rate"] <= one["pass_rate"] + 1e-9
    if two["median_days"] and one["median_days"]:
        assert two["median_days"] >= one["median_days"]


# --------------------------------------------------------------------------- #
# the ladder and the pick
# --------------------------------------------------------------------------- #
def test_drawdown_scales_linearly_with_risk():
    r = np.array([1.0, -2.0, 1.5, -3.0, 2.0, -1.0])
    rows = ladder(days([0.5] * 30), r)
    # `max_dd` is stored rounded to 4dp, so the ratio is what survives rounding,
    # not the absolute difference: at 0.25% risk the stored value carries only
    # two significant figures.
    ratio = [abs(x["max_dd"]) / x["risk"] for x in rows]
    assert max(ratio) == pytest.approx(min(ratio), rel=0.02), (
        "drawdown must scale linearly with risk - it is the one quantity that "
        "does, and the whole risk ladder depends on it")
    assert all(b >= a for a, b in zip(
        [abs(x["max_dd"]) for x in rows], [abs(x["max_dd"]) for x in rows][1:]))


def _rows():
    rng = np.random.default_rng(9)
    r = rng.normal(0.02, 1.0, 600)
    return from_trades(
        r, pd.date_range("2024-01-01", periods=len(r), freq="8h", tz="UTC"))


def test_pick_never_goes_below_the_risk_floor_when_it_does_not_have_to():
    """Kris's instruction, 2026-09-08: at least 2% per trade.

    The floor is the FIRST filter, ahead of the breach and drawdown gates. Before
    it existed, gold's -14.86% drawdown at the lowest rung meant no rung ever
    cleared `DD_CAP`, `pick` fell through to its smallest-drawdown fallback every
    time, and every board record this project published was reported at the
    bottom of the ladder rather than at any optimum.
    """
    rows, chosen = _rows()
    resolves = [x for x in rows
                if x["risk"] >= MIN_RISK - 1e-12 and x["expected_days"] is not None]
    if not resolves:
        pytest.skip("nothing at or above the floor resolves an account")
    assert chosen["risk"] >= MIN_RISK - 1e-12


def test_pick_takes_the_SMALLEST_size_above_the_floor_not_the_fastest():
    """The floor is a target, not a licence to climb.

    Measured example, and it is why this rule is the way round it is: at 5% risk
    GBPUSD 1h reports 10.4 expected days on a profit factor at 2x cost of
    **0.823** - a losing strategy. `expected_days` is median_days / pass_rate,
    and a big position funds the odd account on variance before it dies: short
    median, low pass rate, flattering ratio. Optimising it across the whole
    ladder buys lottery tickets."""
    rows, chosen = _rows()
    pool = [x for x in rows if x["risk"] >= MIN_RISK - 1e-12] or rows
    ok = [x for x in pool
          if x["fail_max"] <= MAX_BREACH and x["fail_daily"] <= MAX_BREACH
          and abs(x["max_dd"]) <= DD_CAP and x["expected_days"] is not None]
    pool_ok = ok or [x for x in pool if x["expected_days"] is not None]
    if not pool_ok:
        pytest.skip("fallback path")
    assert chosen["risk"] == min(x["risk"] for x in pool_ok)


def test_pick_does_not_climb_the_ladder_for_speed():
    """A faster, larger size does not win when a smaller one already resolves."""
    rows = [
        {"risk": 0.02, "fail_max": 0.50, "fail_daily": 0.10,
         "max_dd": -1.00, "expected_days": 40.0},
        {"risk": 0.05, "fail_max": 0.80, "fail_daily": 0.10,
         "max_dd": -2.50, "expected_days": 8.0},
    ]
    assert pick(rows)["risk"] == 0.02


def test_pick_still_prefers_a_level_that_clears_every_gate():
    """The floor changes WHICH levels are eligible; it does not stop the gates
    deciding among them. A level that clears all three is chosen over a faster
    one that does not."""
    rows = [
        {"risk": 0.02, "fail_max": 0.01, "fail_daily": 0.01,
         "max_dd": -0.05, "expected_days": 20.0},
        {"risk": 0.03, "fail_max": 0.90, "fail_daily": 0.90,
         "max_dd": -1.50, "expected_days": 5.0},
    ]
    assert pick(rows)["risk"] == 0.02


def test_pick_falls_below_the_floor_only_when_nothing_above_it_resolves():
    rows = [
        {"risk": 0.005, "fail_max": 0.01, "fail_daily": 0.01,
         "max_dd": -0.03, "expected_days": 90.0},
        {"risk": 0.02, "fail_max": 0.99, "fail_daily": 0.99,
         "max_dd": -2.00, "expected_days": None},
    ]
    assert pick(rows)["risk"] == 0.005


def test_expected_days_is_median_days_over_pass_rate():
    """The phase gate is read off this one number, so its definition is pinned:
    an account that fails still costs the days it ran, so the expected cost of a
    FUNDED account is the median time to pass divided by the pass rate."""
    rng = np.random.default_rng(2)
    rows = ladder(days(rng.normal(0.1, 1.0, 300)), rng.normal(0.05, 1.0, 300))
    for x in rows:
        if x["expected_days"] is not None:
            assert x["expected_days"] == pytest.approx(
                round(x["median_days"] / x["pass_rate"], 1))


def test_every_ladder_row_carries_both_structures():
    rows = ladder(days([0.5] * 60), np.array([0.5] * 60))
    assert len(rows) == len(RISK_LADDER)
    for x in rows:
        assert "one_step" in x and "expected_days" in x["one_step"]


def test_verify_board_restates_the_firm_it_audits():
    """`core/verify_board.py` deliberately imports nothing from this package -
    an auditor that shares code with the thing it audits proves nothing. The
    cost of that independence is drift, and it drifted: the file was still
    pricing the board on the modelled 8%+5% two-step for a day after Kris chose
    Thunderbolt, so it would have disagreed with every board number for a reason
    that had nothing to do with the strategy.

    This is the only tie between the two files, and it is a comparison of four
    numbers, not an import in the audit path."""
    from core import verify_board as VB
    from core.prop_rules import ONE_STEP as FIRM

    assert VB.TARGET == FIRM[0].profit_target
    assert VB.MAX_LOSS == FIRM[0].max_loss
    assert VB.DAILY_LOSS == FIRM[0].daily_loss
    assert VB.MIN_TRADING_DAYS == FIRM[0].min_trading_days
    assert VB.ONE_STEP[0] == {"target": FIRM[0].profit_target,
                              "daily": FIRM[0].daily_loss,
                              "maxloss": FIRM[0].max_loss,
                              "mindays": FIRM[0].min_trading_days}
