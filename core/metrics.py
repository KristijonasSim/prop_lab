"""Backtest metrics. Every field CLAUDE.md marks mandatory is produced here."""

from __future__ import annotations

import math
from dataclasses import dataclass, asdict

import numpy as np
import pandas as pd


@dataclass
class Metrics:
    trades: int
    profit_factor: float
    win_rate: float
    avg_r: float
    trades_per_day: float
    trades_per_week: float
    avg_hold_hours: float
    max_drawdown: float
    sharpe: float
    total_return: float
    expectancy_r: float
    # phase gate — see resolution_estimate()
    days_to_target: float
    days_to_breach: float
    p_target_first: float


def _drawdown(equity: pd.Series) -> float:
    peak = equity.cummax()
    return float(((equity - peak) / peak).min())


def resolution_estimate(
    daily_pnl: pd.Series,
    target: float = 0.08,
    max_loss: float = 0.08,
) -> tuple[float, float, float]:
    """Two-barrier first-passage estimate on daily P&L (fraction of equity).

    Returns (expected days to target, expected days to breach, P(target first)).
    Random-walk approximation: drift mu, step sd sigma, absorbing barriers at
    +target and -max_loss. This is the field that decides whether an idea fits
    the current phase at all. It is an estimate, not a simulation.
    """
    d = pd.Series(daily_pnl).dropna().astype(float)
    if len(d) < 5:
        return (math.inf, math.inf, float("nan"))

    mu = float(d.mean())
    sigma = float(d.std(ddof=1))
    if sigma <= 0:
        if mu > 0:
            return (target / mu, math.inf, 1.0)
        return (math.inf, max_loss / abs(mu) if mu else math.inf, 0.0)

    a, b = float(max_loss), float(target)  # distance down, distance up

    if abs(mu) < 1e-12:
        # driftless: classic gambler's ruin
        p_up = a / (a + b)
        exp_days = (a * b) / (sigma**2)
    else:
        theta = 2.0 * mu / (sigma**2)
        # guard the exponentials
        ea, eb = theta * a, -theta * b
        cap = 500.0
        ea, eb = max(min(ea, cap), -cap), max(min(eb, cap), -cap)
        p_up = (1.0 - math.exp(ea)) / (math.exp(eb) - math.exp(ea))
        p_up = min(max(p_up, 0.0), 1.0)
        exp_days = (b * p_up - a * (1.0 - p_up)) / mu

    exp_days = float(exp_days) if exp_days > 0 and np.isfinite(exp_days) else math.inf
    days_to_target = exp_days / p_up if p_up > 1e-9 else math.inf
    days_to_breach = exp_days / (1 - p_up) if (1 - p_up) > 1e-9 else math.inf
    return (days_to_target, days_to_breach, p_up)


def compute(
    trades: pd.DataFrame,
    equity: pd.Series,
    starting_equity: float,
    target: float = 0.08,
    max_loss: float = 0.08,
) -> Metrics:
    """trades: columns pnl, r_multiple, entry_time, exit_time.
    equity: equity curve indexed by timestamp."""
    t = trades.copy()
    if t.empty:
        raise ValueError("no trades")

    wins = t.loc[t.pnl > 0, "pnl"].sum()
    losses = -t.loc[t.pnl < 0, "pnl"].sum()
    pf = float(wins / losses) if losses > 0 else math.inf

    span_days = max((equity.index[-1] - equity.index[0]).total_seconds() / 86400.0, 1e-9)
    hold_h = (
        pd.to_datetime(t.exit_time) - pd.to_datetime(t.entry_time)
    ).dt.total_seconds().mean() / 3600.0

    daily = equity.resample("1D").last().dropna()
    daily_ret = daily.diff().dropna() / starting_equity  # fraction of START equity, fixed risk
    ann = math.sqrt(365.0)
    sharpe = float(daily_ret.mean() / daily_ret.std(ddof=1) * ann) if daily_ret.std(ddof=1) > 0 else 0.0

    dtt, dtb, p_up = resolution_estimate(daily_ret, target, max_loss)

    return Metrics(
        trades=int(len(t)),
        profit_factor=round(pf, 3),
        win_rate=round(float((t.pnl > 0).mean()), 4),
        avg_r=round(float(t.r_multiple.mean()), 3),
        trades_per_day=round(len(t) / span_days, 3),
        trades_per_week=round(len(t) / span_days * 7.0, 2),
        avg_hold_hours=round(float(hold_h), 2),
        max_drawdown=round(_drawdown(equity), 4),
        sharpe=round(sharpe, 3),
        total_return=round(float(equity.iloc[-1] / starting_equity - 1.0), 4),
        expectancy_r=round(float(t.r_multiple.mean()), 3),
        days_to_target=round(dtt, 1),
        days_to_breach=round(dtb, 1),
        p_target_first=round(p_up, 4),
    )


def as_row(m: Metrics) -> dict:
    return asdict(m)
