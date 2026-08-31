"""Prop-firm evaluation rules. Clean PASS/FAIL, fixed risk, real breaches.

No budget-shrinking risk manager — sizing down to avoid ever breaching produces
a fake 0% fail rate and a bucket of accounts that never resolve. If it fails,
it fails. See CLAUDE.md.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

import pandas as pd


class Outcome(str, Enum):
    PASS = "PASS"
    FAIL_DAILY = "FAIL_DAILY"
    FAIL_MAX = "FAIL_MAX"
    OPEN = "OPEN"  # ran out of data without resolving


@dataclass(frozen=True)
class PropRules:
    """Kris's targets. No firm chosen yet.

    max_loss is enforced BOTH static (from starting balance) and trailing
    (from equity high-water mark) at 8% — the stricter reading, because the
    firm's spec is unknown. min_trading_days and consistency_share are
    placeholders; confirm them when a firm is picked.
    """

    profit_target: float = 0.08
    daily_loss: float = 0.04
    max_loss: float = 0.08
    trailing: bool = True
    static: bool = True
    min_trading_days: int = 5          # PLACEHOLDER
    consistency_share: float = 0.40    # PLACEHOLDER — max share of profit from one day


@dataclass
class EvalResult:
    outcome: Outcome
    day: int | None
    final_equity: float
    peak_equity: float
    trading_days: int
    best_day_share: float
    consistency_ok: bool


def evaluate(
    equity: pd.Series,
    starting_equity: float,
    rules: PropRules = PropRules(),
) -> EvalResult:
    """Walk the equity curve day by day and return the first resolution.

    equity: intraday equity curve indexed by timestamp. Daily loss is checked
    against the intraday LOW of each day, not the close — a firm breaches you
    the moment the line is crossed.
    """
    eq = pd.Series(equity).dropna().astype(float)
    daily = eq.resample("1D")
    day_low, day_close = daily.min().dropna(), daily.last().dropna()
    day_open = daily.first().dropna()

    peak = starting_equity
    outcome, hit_day = Outcome.OPEN, None
    pnl_by_day: list[float] = []

    for i, (ts, close) in enumerate(day_close.items(), start=1):
        low, opn = day_low[ts], day_open[ts]
        start_of_day = starting_equity if i == 1 else prev_close

        # daily loss — measured from the day's starting balance, intraday low
        if (low - start_of_day) / starting_equity <= -rules.daily_loss:
            outcome, hit_day = Outcome.FAIL_DAILY, i
            break

        # max loss — static from start, and trailing from high-water mark
        if rules.static and (low - starting_equity) / starting_equity <= -rules.max_loss:
            outcome, hit_day = Outcome.FAIL_MAX, i
            break
        if rules.trailing and (low - peak) / starting_equity <= -rules.max_loss:
            outcome, hit_day = Outcome.FAIL_MAX, i
            break

        peak = max(peak, eq[eq.index.date == ts.date()].max())
        pnl_by_day.append(close - start_of_day)
        prev_close = close

        if (close - starting_equity) / starting_equity >= rules.profit_target:
            outcome, hit_day = Outcome.PASS, i
            break
    else:
        prev_close = day_close.iloc[-1] if len(day_close) else starting_equity

    traded = [p for p in pnl_by_day if abs(p) > 1e-9]
    total_profit = sum(p for p in pnl_by_day if p > 0)
    best_share = (max(pnl_by_day) / total_profit) if total_profit > 0 and pnl_by_day else 0.0

    if outcome is Outcome.PASS and len(traded) < rules.min_trading_days:
        outcome = Outcome.OPEN  # target hit too early to satisfy min trading days

    return EvalResult(
        outcome=outcome,
        day=hit_day,
        final_equity=float(day_close.iloc[hit_day - 1] if hit_day else day_close.iloc[-1]),
        peak_equity=float(peak),
        trading_days=len(traded),
        best_day_share=round(float(best_share), 4),
        consistency_ok=bool(best_share <= rules.consistency_share),
    )
