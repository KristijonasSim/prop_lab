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
    """One evaluation phase.

    max_loss is enforced BOTH static (from starting balance) and trailing
    (from equity high-water mark) — the stricter reading, because firms differ
    and the spec is not worth guessing generously. min_trading_days and
    consistency_share are placeholders; confirm them against the signed firm.
    """

    profit_target: float = 0.08
    daily_loss: float = 0.04
    max_loss: float = 0.08
    trailing: bool = True
    static: bool = True
    min_trading_days: int = 5          # PLACEHOLDER
    consistency_share: float = 0.40    # PLACEHOLDER — max share of profit from one day


# ---------------------------------------------------------------------------
# Firm structure, chosen 2026-09-01.
#
# TARGET: a two-step evaluation on cTrader.
#
# Why cTrader and not MT5: CLAUDE.md prefers it outright — cTrader Open API is a
# real REST/WebSocket API, while MT5 is GUI-only and its Python package is
# Windows-only. This box is Linux with no working MT5 bridge, which is the exact
# reason `live/paper_trade.py` runs the two XAUUSD legs signal-only off cached
# data. cTrader carries both crypto and XAUUSD, so it is the one choice that
# unblocks the whole book rather than half of it.
#
# Why two-step: HANDOFF recorded that most no-time-limit firms are two-step
# (8% then 5%) while this file modelled a single 8% step, which understates
# time-to-funded. TWO_STEP below is the honest structure.
#
# NOT VERIFIED: the exact numbers per firm. Percentages, min trading days and
# consistency rules change and differ between firms — confirm on the firm's own
# spec page before any money moves. The STRUCTURE is what is modelled here.
# ---------------------------------------------------------------------------

PHASE_1 = PropRules(profit_target=0.08, daily_loss=0.04, max_loss=0.08)
PHASE_2 = PropRules(profit_target=0.05, daily_loss=0.04, max_loss=0.08)
TWO_STEP = (PHASE_1, PHASE_2)

# The old single-step assumption, kept so board numbers stay comparable.
ONE_STEP = (PropRules(),)


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
