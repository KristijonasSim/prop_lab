"""=== CORE BACKTEST MATH - OWNER: kris. Strategy code must not modify. ===

Prop-firm evaluation rules, checked INSIDE the backtest run - not bolted on
afterwards. A profitable strategy that breaches any hard rule is a FAIL.

Two classes of rule:
  HARD BREACH  -> account is dead the moment it happens (daily loss, max DD,
                  trailing DD). We record the first breach timestamp; equity
                  after that point is fiction, and is reported as such.
  QUALIFICATION-> you can still pass later (profit target, min trading days,
                  consistency, no-martingale sizing).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from ..config import PropFirmRules
from .types import BacktestResult


def check(result: BacktestResult, rules: PropFirmRules) -> dict:
    eq = result.equity
    low = result.equity_low if len(result.equity_low) == len(eq) else eq
    start = rules.starting_balance
    trades = result.trades_df()

    # Which curve the firm measures against: intraday equity (harsh) or closes.
    basis = pd.concat([eq, low], axis=1).min(axis=1) if rules.intraday_equity_basis else eq
    basis = basis.copy()
    basis.name = "basis"

    checks: dict[str, dict] = {}
    breaches: list[tuple[pd.Timestamp, str]] = []

    # ---- 1. daily loss limit ------------------------------------------------
    day = basis.index.tz_convert(rules.day_boundary_tz).date
    day_close = eq.groupby(day).last()
    day_min = basis.groupby(day).min()
    prev_close = day_close.shift(1)
    prev_close.iloc[0] = start
    day_loss = prev_close - day_min                       # worst loss within each day
    limit_amt = start * rules.daily_loss_limit_pct / 100
    daily_bad = day_loss[day_loss > limit_amt]
    checks["daily_loss_limit"] = {
        "hard": True,
        "limit": round(limit_amt, 2),
        "worst_day_loss": round(float(day_loss.max()), 2) if len(day_loss) else 0.0,
        "worst_day": str(day_loss.idxmax()) if len(day_loss) else None,
        "n_breach_days": int(len(daily_bad)),
        "passed": bool(len(daily_bad) == 0),
    }
    if len(daily_bad):
        breaches.append((pd.Timestamp(str(daily_bad.index[0]), tz="UTC"), "daily_loss_limit"))

    # ---- 2. static max drawdown (from starting balance) ---------------------
    floor_static = start * (1 - rules.max_drawdown_pct / 100)
    below = basis[basis < floor_static]
    checks["max_drawdown_static"] = {
        "hard": True,
        "floor": round(floor_static, 2),
        "lowest_equity": round(float(basis.min()), 2),
        "worst_dd_from_start_pct": round(100 * (1 - float(basis.min()) / start), 3),
        "passed": bool(below.empty),
    }
    if not below.empty:
        breaches.append((below.index[0], "max_drawdown_static"))

    # ---- 3. trailing drawdown (from equity high-water mark) -----------------
    trail_amt = start * rules.trailing_drawdown_pct / 100
    hwm = eq.cummax()
    floor_trail = hwm - trail_amt
    if rules.trailing_locks_at_start:
        # The floor trails the high-water mark upward but STOPS at the starting
        # balance: once the account is trail_amt in profit, the worst case is a
        # flat account, not a loss. (Topstep/Apex style "locks at breakeven".)
        floor_trail = pd.Series(np.minimum(floor_trail, start), index=eq.index)
    trail_hit = basis[basis < floor_trail]
    checks["trailing_drawdown"] = {
        "hard": True,
        "trail_amount": round(trail_amt, 2),
        "locks_at_start": rules.trailing_locks_at_start,
        "min_headroom": round(float((basis - floor_trail).min()), 2),
        "passed": bool(trail_hit.empty),
    }
    if not trail_hit.empty:
        breaches.append((trail_hit.index[0], "trailing_drawdown"))

    # ---- 4. profit target ---------------------------------------------------
    target_amt = start * rules.profit_target_pct / 100
    reached = eq[eq >= start + target_amt]
    checks["profit_target"] = {
        "hard": False,
        "target_balance": round(start + target_amt, 2),
        "reached": bool(not reached.empty),
        "reached_at": str(reached.index[0]) if not reached.empty else None,
        "days_to_target": round((reached.index[0] - eq.index[0]).total_seconds() / 86400, 1)
        if not reached.empty else None,
        "passed": bool(not reached.empty),
    }

    # ---- 5. minimum trading days -------------------------------------------
    if trades.empty:
        n_days = 0
    else:
        n_days = int(pd.to_datetime(trades["exit_time"], utc=True).dt.date.nunique())
    checks["min_trading_days"] = {
        "hard": False,
        "required": rules.min_trading_days,
        "actual": n_days,
        "passed": bool(n_days >= rules.min_trading_days),
    }

    # ---- 6. consistency: no single day dominating the profit ----------------
    daily_pnl = day_close.diff()
    daily_pnl.iloc[0] = day_close.iloc[0] - start
    profit_days = daily_pnl[daily_pnl > 0]
    total_profit = float(eq.iloc[-1] - start)
    if total_profit > 0 and len(profit_days):
        share = float(profit_days.max()) / total_profit
    else:
        share = float("nan")
    checks["consistency"] = {
        "hard": False,
        "max_allowed_share": rules.max_single_day_profit_share,
        "best_day_share_of_profit": round(share, 4) if share == share else None,
        "best_day_pnl": round(float(profit_days.max()), 2) if len(profit_days) else 0.0,
        "passed": bool(share == share and share <= rules.max_single_day_profit_share),
        "note": ("no net profit over the period, so consistency cannot be "
                 "assessed - the binding failure is profit_target"
                 if total_profit <= 0 else
                 "one day carried too much of the total profit"),
    }

    # ---- 7. no martingale sizing -------------------------------------------
    checks["no_martingale"] = _martingale_check(trades, rules)

    # ---- verdict ------------------------------------------------------------
    breaches.sort(key=lambda x: x[0])
    first_breach = breaches[0] if breaches else None
    hard_ok = all(c["passed"] for c in checks.values() if c["hard"])
    soft_ok = all(c["passed"] for c in checks.values() if not c["hard"])

    survived_days = (
        round((first_breach[0] - eq.index[0]).total_seconds() / 86400, 1)
        if first_breach else None
    )
    return {
        "passed": bool(hard_ok and soft_ok),
        "hard_rules_passed": bool(hard_ok),
        "qualification_passed": bool(soft_ok),
        "first_breach_rule": first_breach[1] if first_breach else None,
        "first_breach_time": str(first_breach[0]) if first_breach else None,
        "days_survived_before_breach": survived_days,
        "failed_rules": [k for k, v in checks.items() if not v["passed"]],
        "checks": checks,
        "rules_used": rules.to_dict(),
        "note": (
            "Equity after a hard breach is not tradeable - the account would be "
            "closed. Metrics covering the full period are shown for diagnosis only."
        ) if first_breach else "",
    }


def _martingale_check(trades: pd.DataFrame, rules: PropFirmRules) -> dict:
    """Flag size-ups after losses (bet-doubling), which firms ban outright."""
    if trades.empty or len(trades) < 3:
        return {"hard": False, "passed": True, "n_size_ups_after_loss": 0,
                "max_size_ratio_after_loss": None, "note": "too few trades to judge"}

    notional = (trades["qty"] * trades["entry_price"]).to_numpy(float)
    prev_pnl = trades["net_pnl"].shift(1).to_numpy(float)
    ratio = np.divide(notional[1:], notional[:-1],
                      out=np.ones(len(notional) - 1), where=notional[:-1] > 0)
    after_loss = prev_pnl[1:] <= 0
    flagged = (ratio > rules.martingale_size_ratio) & after_loss
    n_flag = int(flagged.sum())
    n_after_loss = int(after_loss.sum())
    # Occasional size-ups happen when stop distance shrinks; a systematic
    # pattern is what matters.
    share = n_flag / n_after_loss if n_after_loss else 0.0
    return {
        "hard": False,
        "n_size_ups_after_loss": n_flag,
        "share_of_post_loss_trades": round(share, 3),
        "max_size_ratio_after_loss": round(float(ratio[after_loss].max()), 3) if n_after_loss else None,
        "passed": bool(not rules.forbid_martingale or share < 0.20),
        "note": "flags trades sized >%.1fx the previous trade after a loss"
                % rules.martingale_size_ratio,
    }
