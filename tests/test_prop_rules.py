"""Prop-firm rule checks, driven by hand-built equity curves."""
from __future__ import annotations

import numpy as np
import pandas as pd

from proplab.config import PropFirmRules
from proplab.core import prop_rules
from proplab.core.types import BacktestResult, Trade

RULES = PropFirmRules(starting_balance=100_000.0, daily_loss_limit_pct=5.0,
                      max_drawdown_pct=10.0, trailing_drawdown_pct=10.0,
                      profit_target_pct=10.0, min_trading_days=5,
                      max_single_day_profit_share=0.40)


def result_from(values, freq="1h", start="2024-01-01", lows=None, trades=None):
    idx = pd.date_range(start, periods=len(values), freq=freq, tz="UTC")
    eq = pd.Series(np.asarray(values, dtype=float), index=idx)
    lo = pd.Series(np.asarray(lows if lows is not None else values, dtype=float), index=idx)
    return BacktestResult(trades=trades or [], equity=eq, equity_low=lo)


def fake_trades(n_days=6, pnl=100.0, qty=1.0, price=100.0):
    out = []
    for d in range(n_days):
        ts = pd.Timestamp("2024-01-01", tz="UTC") + pd.Timedelta(days=d)
        out.append(Trade(ts, ts + pd.Timedelta(hours=1), 1, qty, price, price + pnl,
                         pnl, 0.0, 0.0, pnl, 1.0, 1, "target", "t", 0.0, 0.0,
                         100_000, 100_000 + pnl))
    return out


def test_clean_pass():
    # steady climb to +10% over 24 days, no big single day
    vals = np.linspace(100_000, 110_000, 24 * 24)
    r = result_from(vals, trades=fake_trades(8, pnl=1250))
    p = prop_rules.check(r, RULES)
    assert p["passed"], p["failed_rules"]


def test_daily_loss_limit_breach_is_detected():
    vals = [100_000] * 12 + [94_000] * 12      # -6% inside day 1
    r = result_from(vals, trades=fake_trades(6))
    p = prop_rules.check(r, RULES)
    assert not p["checks"]["daily_loss_limit"]["passed"]
    assert p["first_breach_rule"] == "daily_loss_limit"
    assert not p["passed"]


def test_daily_loss_uses_intraday_low_not_just_close():
    """A day that dips -6% and closes flat still kills the account."""
    vals = [100_000] * 24
    lows = [100_000] * 10 + [93_500] + [100_000] * 13
    r = result_from(vals, lows=lows, trades=fake_trades(6))
    p = prop_rules.check(r, RULES)
    assert not p["checks"]["daily_loss_limit"]["passed"]


def test_static_max_drawdown_breach():
    vals = list(np.linspace(100_000, 89_000, 240))   # -11% from start
    r = result_from(vals, trades=fake_trades(6))
    p = prop_rules.check(r, RULES)
    assert not p["checks"]["max_drawdown_static"]["passed"]


def test_trailing_drawdown_breach_while_still_above_start():
    """Up 9%, then down 10% from the peak - still above the start balance, but
    the trailing rule is what kills evaluation accounts."""
    up = list(np.linspace(100_000, 109_000, 120))
    down = list(np.linspace(109_000, 98_500, 120))
    r = result_from(up + down, trades=fake_trades(6))
    p = prop_rules.check(r, RULES)
    assert not p["checks"]["trailing_drawdown"]["passed"]
    assert p["checks"]["max_drawdown_static"]["passed"]   # static rule never fired


def test_trailing_floor_locks_at_start_balance():
    """Once +10% is banked, the floor stops trailing at the start balance."""
    up = list(np.linspace(100_000, 112_000, 120))
    down = list(np.linspace(112_000, 101_000, 120))
    r = result_from(up + down, trades=fake_trades(6))
    p = prop_rules.check(r, RULES)
    assert p["checks"]["trailing_drawdown"]["passed"]


def test_consistency_rule_catches_one_lucky_day():
    # flat for 9 days, then one day makes the entire profit
    vals = [100_000] * (24 * 9) + [111_000] * 24
    r = result_from(vals, trades=fake_trades(10))
    p = prop_rules.check(r, RULES)
    assert not p["checks"]["consistency"]["passed"]
    assert p["checks"]["consistency"]["best_day_share_of_profit"] > 0.4
    assert not p["passed"]        # profitable, target hit, still a FAIL


def test_min_trading_days_enforced():
    vals = list(np.linspace(100_000, 111_000, 24 * 20))
    r = result_from(vals, trades=fake_trades(3))       # only 3 days traded
    p = prop_rules.check(r, RULES)
    assert not p["checks"]["min_trading_days"]["passed"]


def test_martingale_sizing_is_flagged():
    trades = []
    ts = pd.Timestamp("2024-01-01", tz="UTC")
    qty = 1.0
    for i in range(12):
        pnl = -100.0 if i % 2 == 0 else 50.0
        trades.append(Trade(ts + pd.Timedelta(days=i), ts + pd.Timedelta(days=i, hours=1),
                            1, qty, 100.0, 101.0, pnl, 0.0, 0.0, pnl, 1.0, 1,
                            "stop", "t", 0.0, 0.0, 100_000, 100_000))
        qty = qty * 2 if pnl < 0 else 1.0          # double after every loss
    r = result_from([100_000] * 48, trades=trades)
    p = prop_rules.check(r, RULES)
    assert not p["checks"]["no_martingale"]["passed"]


def test_fixed_fractional_sizing_is_not_flagged():
    trades = fake_trades(10, pnl=-50.0)
    r = result_from([100_000] * 48, trades=trades)
    p = prop_rules.check(r, RULES)
    assert p["checks"]["no_martingale"]["passed"]


def test_profit_target_not_reached_is_not_a_pass():
    vals = list(np.linspace(100_000, 103_000, 240))
    r = result_from(vals, trades=fake_trades(8))
    p = prop_rules.check(r, RULES)
    assert not p["checks"]["profit_target"]["passed"]
    assert not p["passed"]
    assert p["hard_rules_passed"]          # nothing was breached, just not enough


def test_configured_defaults_match_the_targets_kris_set():
    """4% daily loss, 8% max loss (both static and trailing), 8% target.
    If these drift, every logged pass/fail becomes incomparable."""
    d = PropFirmRules()
    assert d.daily_loss_limit_pct == 4.0
    assert d.max_drawdown_pct == 8.0
    assert d.trailing_drawdown_pct == 8.0
    assert d.profit_target_pct == 8.0


def test_eight_percent_loss_is_enforced_both_ways():
    """A curve that never breaches static 8% but does breach trailing 8% must
    still fail, because "max loss" was not specified as one or the other."""
    rules = PropFirmRules()
    up = list(np.linspace(100_000, 107_000, 120))
    down = list(np.linspace(107_000, 98_600, 120))   # -7.85% from peak
    r = result_from(up + down, trades=fake_trades(6))
    p = prop_rules.check(r, rules)
    assert p["checks"]["max_drawdown_static"]["passed"]
    assert not p["checks"]["trailing_drawdown"]["passed"]
    assert not p["passed"]
