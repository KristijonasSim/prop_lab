"""=== CORE BACKTEST MATH - OWNER: kris. Strategy code must not modify. ===

Performance statistics computed from the equity curve and trade list.
Crypto is 24/7, so annualisation uses 365 days.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

from ..data.timeframes import parse_timeframe
from .types import LONG, BacktestResult

SECONDS_PER_YEAR = 365 * 24 * 3600


def bars_per_year(timeframe: str) -> float:
    return SECONDS_PER_YEAR / parse_timeframe(timeframe).total_seconds()


def resolution_estimate(equity: pd.Series, rules, timeframe: str) -> dict:
    """How many trading days until this account resolves - target or breach.

    An evaluation is a race between two barriers: +profit_target and
    -max_drawdown. Total return says nothing about how long that race takes,
    and a strategy that needs two years to clear 8% is useless for an
    evaluation however good its Sharpe is.

    Models daily P&L as a random walk with drift and applies the classic
    two-barrier first-passage result, then reports both the drift-only
    estimate and the probability of reaching the target first. Assumes daily
    P&L is i.i.d., which it is not - treat these as order-of-magnitude
    figures, not promises.
    """
    daily = equity.resample("1D").last().dropna().diff().dropna()
    start = rules.starting_balance
    up = start * rules.profit_target_pct / 100          # distance to target
    down = start * rules.max_drawdown_pct / 100         # distance to breach

    out = {
        "target_amount": round(up, 2),
        "breach_amount": round(down, 2),
        "daily_pnl_mean": round(float(daily.mean()), 2) if len(daily) else None,
        "daily_pnl_std": round(float(daily.std(ddof=1)), 2) if len(daily) > 1 else None,
        "observed_trading_days": int(len(daily)),
    }
    if len(daily) < 5:
        out["verdict"] = "not enough daily observations to estimate"
        return out

    mu = float(daily.mean())
    sigma2 = float(daily.var(ddof=1))

    out["days_to_target_at_current_rate"] = round(up / mu, 1) if mu > 0 else None
    out["days_to_breach_at_current_rate"] = round(down / -mu, 1) if mu < 0 else None

    # Zero variance is deterministic, not unknowable - it is only "no
    # information" when the account also has no drift.
    if sigma2 == 0:
        if abs(mu) < 1e-12:
            out["p_target_before_breach"] = None
            out["expected_days_to_resolution"] = None
            out["verdict"] = "equity never moves - never resolves"
            return out
        p_up = 1.0 if mu > 0 else 0.0
        expected_days = (up / mu) if mu > 0 else (down / -mu)
    # Two-barrier first passage for a drifting random walk.
    elif abs(mu) < 1e-9:
        p_up = down / (up + down)                       # driftless: distance ratio
        expected_days = (up * down) / sigma2
    else:
        theta = 2 * mu / sigma2
        # guard the exponentials: large |theta*barrier| saturates to 0/1
        ea, eb = -theta * up, theta * down
        if ea > 700 or eb > 700:
            p_up = 1.0 if mu > 0 else 0.0
        else:
            p_up = (math.exp(eb) - 1) / (math.exp(eb) - math.exp(ea))
        p_up = min(max(p_up, 0.0), 1.0)
        expected_days = (p_up * up - (1 - p_up) * down) / mu

    out["p_target_before_breach"] = round(p_up, 3)
    out["expected_days_to_resolution"] = (round(expected_days, 1)
                                          if expected_days == expected_days
                                          and expected_days > 0 else None)
    days = out["expected_days_to_resolution"]
    if days is None:
        out["verdict"] = "no finite estimate"
    elif days <= 14:
        out["verdict"] = f"resolves in ~{days:.0f} trading days (fits a 1-2 week phase)"
    elif days <= 60:
        out["verdict"] = f"~{days:.0f} trading days - too slow for a 1-2 week phase"
    else:
        out["verdict"] = f"~{days:.0f} trading days - far too slow to be practical"
    return out


def compute(result: BacktestResult, timeframe: str, starting_balance: float,
            rules=None) -> dict:
    eq = result.equity
    trades = result.trades_df()
    out: dict = {}

    rets = eq.pct_change().fillna(0.0)
    ann = bars_per_year(timeframe)
    days = max((eq.index[-1] - eq.index[0]).total_seconds() / 86400, 1e-9)
    years = days / 365

    final = float(eq.iloc[-1])
    out["starting_balance"] = starting_balance
    out["final_balance"] = round(final, 2)
    out["net_profit"] = round(final - starting_balance, 2)
    out["total_return_pct"] = round(100 * (final / starting_balance - 1), 3)
    out["cagr_pct"] = round(100 * ((final / starting_balance) ** (1 / years) - 1), 3) \
        if years > 0 and final > 0 else float("nan")

    sd = float(rets.std(ddof=1)) if len(rets) > 2 else 0.0
    out["ann_volatility_pct"] = round(100 * sd * np.sqrt(ann), 3)
    out["sharpe"] = round(float(rets.mean() / sd * np.sqrt(ann)), 3) if sd > 0 else 0.0
    downside = rets[rets < 0]
    dsd = float(downside.std(ddof=1)) if len(downside) > 2 else 0.0
    out["sortino"] = round(float(rets.mean() / dsd * np.sqrt(ann)), 3) if dsd > 0 else 0.0

    # drawdown on the pessimistic (intrabar) curve when available
    low = result.equity_low if len(result.equity_low) == len(eq) else eq
    dd_ref = pd.concat([eq, low], axis=1).min(axis=1)
    peak = eq.cummax()
    dd = (dd_ref - peak) / peak
    out["max_drawdown_pct"] = round(float(-dd.min() * 100), 3)
    out["max_drawdown_abs"] = round(float((peak - dd_ref).max()), 2)
    out["calmar"] = round(out["cagr_pct"] / out["max_drawdown_pct"], 3) \
        if out["max_drawdown_pct"] > 0 else float("nan")

    daily = eq.resample("1D").last().dropna()
    daily_pnl = daily.diff().dropna()
    out["days_tested"] = round(days, 1)
    out["best_day"] = round(float(daily_pnl.max()), 2) if len(daily_pnl) else 0.0
    out["worst_day"] = round(float(daily_pnl.min()), 2) if len(daily_pnl) else 0.0

    if trades.empty:
        out.update({
            "n_trades": 0, "win_rate_pct": float("nan"), "profit_factor": float("nan"),
            "expectancy_r": float("nan"), "avg_r": float("nan"), "t_stat": float("nan"),
            "trades_per_week": 0.0, "trades_per_day": 0.0, "exposure_pct": 0.0,
            "avg_hold_hours": None, "avg_hold_days": None, "total_fees": 0.0,
            "total_funding": 0.0, "gross_profit": 0.0,
        })
        if rules is not None:
            out["resolution"] = resolution_estimate(eq, rules, timeframe)
        return out

    pnl = trades["net_pnl"]
    wins, losses = pnl[pnl > 0], pnl[pnl <= 0]
    out["n_trades"] = int(len(trades))
    out["n_long"] = int((trades["direction"] == LONG).sum())
    out["n_short"] = int(out["n_trades"] - out["n_long"])
    out["win_rate_pct"] = round(100 * len(wins) / len(trades), 2)
    out["avg_win"] = round(float(wins.mean()), 2) if len(wins) else 0.0
    out["avg_loss"] = round(float(losses.mean()), 2) if len(losses) else 0.0
    out["largest_win"] = round(float(pnl.max()), 2)
    out["largest_loss"] = round(float(pnl.min()), 2)
    gp, gl = float(wins.sum()), float(-losses.sum())
    out["gross_profit"] = round(gp, 2)
    out["gross_loss"] = round(gl, 2)
    out["profit_factor"] = round(gp / gl, 3) if gl > 0 else float("inf")
    out["total_fees"] = round(float(trades["fees"].sum()), 2)
    out["total_funding"] = round(float(trades["funding"].sum()), 2)
    # Costs as a share of gross PROFIT (not net gross, which sits near zero and
    # makes the ratio explode). Also as a share of the account, which is stable.
    gross_win = float(trades.loc[trades["gross_pnl"] > 0, "gross_pnl"].sum())
    total_cost = out["total_fees"] + out["total_funding"]
    out["total_costs"] = round(total_cost, 2)
    out["cost_pct_of_gross_profit"] = round(100 * total_cost / gross_win, 2) if gross_win > 0 else None
    out["cost_pct_of_start_balance"] = round(100 * total_cost / starting_balance, 2)

    r = trades["r_multiple"].replace([np.inf, -np.inf], np.nan).dropna()
    if len(r) > 1:
        out["avg_r"] = round(float(r.mean()), 4)
        out["expectancy_r"] = out["avg_r"]
        out["r_std"] = round(float(r.std(ddof=1)), 4)
        out["t_stat"] = round(float(r.mean() / (r.std(ddof=1) / np.sqrt(len(r)))), 3) \
            if r.std(ddof=1) > 0 else float("nan")
    else:
        out["avg_r"] = out["expectancy_r"] = out["r_std"] = out["t_stat"] = float("nan")

    # Concentration: trend-following results are routinely one trade wide.
    # If the best trade IS the edge, the effective sample size is ~1.
    ranked = pnl.sort_values(ascending=False)
    total = float(pnl.sum())
    if total > 0:
        out["best_trade_pct_of_profit"] = round(100 * float(ranked.iloc[0]) / total, 1)
        out["top3_trades_pct_of_profit"] = round(100 * float(ranked.head(3).sum()) / total, 1)
        out["net_profit_excluding_best"] = round(total - float(ranked.iloc[0]), 2)
    else:
        out["best_trade_pct_of_profit"] = None
        out["top3_trades_pct_of_profit"] = None
        out["net_profit_excluding_best"] = None

    bar_hours = parse_timeframe(timeframe).total_seconds() / 3600
    out["avg_bars_held"] = round(float(trades["bars_held"].mean()), 2)
    out["avg_hold_hours"] = round(float(trades["bars_held"].mean()) * bar_hours, 2)
    out["avg_hold_days"] = round(out["avg_hold_hours"] / 24, 2)
    out["median_hold_hours"] = round(float(trades["bars_held"].median()) * bar_hours, 2)
    out["max_hold_days"] = round(float(trades["bars_held"].max()) * bar_hours / 24, 2)
    out["exposure_pct"] = round(100 * float(trades["bars_held"].sum()) / len(eq), 2)
    out["trades_per_day"] = round(len(trades) / days, 3)
    out["trades_per_week"] = round(len(trades) / (days / 7), 2)
    out["exit_reasons"] = trades["exit_reason"].value_counts().to_dict()

    eq_after = trades["equity_after"].to_numpy()
    out["max_consecutive_losses"] = _max_streak(pnl.to_numpy() <= 0)
    out["max_consecutive_wins"] = _max_streak(pnl.to_numpy() > 0)
    out["final_from_trades_check"] = round(float(eq_after[-1]), 2)

    if rules is not None:
        out["resolution"] = resolution_estimate(eq, rules, timeframe)
    return out


def _max_streak(flags: np.ndarray) -> int:
    best = cur = 0
    for f in flags:
        cur = cur + 1 if f else 0
        best = max(best, cur)
    return int(best)
