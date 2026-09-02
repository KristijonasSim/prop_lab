"""Risk-per-trade ladder and prop simulation, shared by every hypothesis.

Risk per trade is the only lever left once a configuration has been chosen
blind, and it moves speed and survival in opposite directions. Reporting one
arbitrary level hides that trade-off - and hides the fact that the arbitrary
level may not even be the best one, which is exactly what happened when the VWAP
board inherited 0.75% from an earlier stage and nobody checked.

So every strategy produces the whole ladder plus an explicitly-stated pick, and
the board lets the trader choose. Because this lives in one place, a new
hypothesis gets the same simulation, the same constraints and the same
comparable numbers the moment it can hand over a trade series.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.prop_rules import PropRules, TWO_STEP        # noqa: E402

RISK_LADDER = (0.0025, 0.005, 0.0075, 0.01, 0.0125, 0.015, 0.0175,
               0.02, 0.025, 0.03, 0.04, 0.05)
MAX_BREACH = 0.05     # a risk level that kills more than 1 account in 20 is out
DD_CAP = 0.08         # and its equity curve must stay inside the prop max-loss cap
MAX_DAYS = 400        # an account still open after this counts as not passed


def run_accounts(daily_r: pd.Series, risk: float, rules: PropRules = PropRules(),
                 max_days: int = MAX_DAYS) -> dict:
    """Fresh account every trading day, fixed risk, real breaches, no size
    shrinking. Worst case within a day: the whole day's loss lands before any of
    its gain."""
    d = daily_r.values * risk
    n = len(d)
    out = []
    for s in range(n):
        eq, peak, day, traded, res = 0.0, 0.0, 0, 0, "OPEN"
        for k in range(s, min(s + max_days, n)):
            day += 1
            step = d[k]
            if step != 0.0:
                traded += 1
            if min(step, 0.0) <= -rules.daily_loss:
                res = "FAIL_DAILY"; break
            low = eq + min(step, 0.0)
            if low - peak <= -rules.max_loss or low <= -rules.max_loss:
                res = "FAIL_MAX"; break
            eq += step
            peak = max(peak, eq)
            if eq >= rules.profit_target and traded >= rules.min_trading_days:
                res = "PASS"; break
        out.append((res, day))
    res = pd.DataFrame(out, columns=["outcome", "days"])
    p = res[res.outcome == "PASS"]
    return {
        "pass_rate": round(len(p) / len(res), 4) if len(res) else 0.0,
        "fail_max": round(float((res.outcome == "FAIL_MAX").mean()), 4),
        "fail_daily": round(float((res.outcome == "FAIL_DAILY").mean()), 4),
        "still_open": round(float((res.outcome == "OPEN").mean()), 4),
        "median_days": float(p.days.median()) if len(p) else None,
        "p25_days": float(p.days.quantile(0.25)) if len(p) else None,
    }


def run_accounts_two_step(daily_r: pd.Series, risk: float,
                          phases=TWO_STEP, max_days: int = MAX_DAYS) -> dict:
    """The same simulation, but an account must clear EVERY phase in sequence.

    Phase 2 starts the day after phase 1 is cleared, on the same live series, and
    gets a fresh equity, peak and drawdown budget — which is how firms reset it.
    A breach in any phase kills the account outright; there is no retry.

    This exists because the one-step number flatters every hypothesis here: the
    second 5% step is not half the work of the first 8% one, it is a whole
    second chance to breach, and the drawdown that has to be survived is paid
    twice."""
    d = daily_r.values * risk
    n = len(d)
    out = []
    for s0 in range(n):
        k, res, total_days = s0, "OPEN", 0
        for rules in phases:
            eq, peak, day, traded, res = 0.0, 0.0, 0, 0, "OPEN"
            while k < n and total_days + day < max_days:
                day += 1
                step = d[k]; k += 1
                if step != 0.0:
                    traded += 1
                if min(step, 0.0) <= -rules.daily_loss:
                    res = "FAIL_DAILY"; break
                low = eq + min(step, 0.0)
                if low - peak <= -rules.max_loss or low <= -rules.max_loss:
                    res = "FAIL_MAX"; break
                eq += step
                peak = max(peak, eq)
                if eq >= rules.profit_target and traded >= rules.min_trading_days:
                    res = "PASS"; break
            total_days += day
            if res != "PASS":
                break
        out.append((res, total_days))
    res = pd.DataFrame(out, columns=["outcome", "days"])
    p = res[res.outcome == "PASS"]
    return {
        "pass_rate": round(len(p) / len(res), 4) if len(res) else 0.0,
        "fail_max": round(float((res.outcome == "FAIL_MAX").mean()), 4),
        "fail_daily": round(float((res.outcome == "FAIL_DAILY").mean()), 4),
        "still_open": round(float((res.outcome == "OPEN").mean()), 4),
        "median_days": float(p.days.median()) if len(p) else None,
        "p25_days": float(p.days.quantile(0.25)) if len(p) else None,
    }


def _expected(a: dict) -> float | None:
    md, pr = a["median_days"], a["pass_rate"]
    return None if (md is None or not pr) else round(md / pr, 1)


def ladder(daily_r: pd.Series, r_series: np.ndarray,
           levels=RISK_LADDER) -> list[dict]:
    """One row per risk level. `r_series` is the trade-by-trade R used for the
    drawdown, which is the one quantity that scales linearly with risk.

    Every row carries BOTH structures. The headline keys (`pass_rate`,
    `median_days`, `expected_days`, the two breach rates) are the **two-step**
    evaluation, because that is the structure the project decided to trade on
    2026-09-01 and a board that reports the one-step number reports a fiction.
    The one-step values are kept alongside under a `one_step` sub-dict so older
    board figures stay comparable and the gap between the two stays visible.
    """
    eq = np.concatenate(([0.0], np.cumsum(r_series)))
    dd_r = float((eq - np.maximum.accumulate(eq)).min())
    rows = []
    for risk in levels:
        one = run_accounts(daily_r, risk)
        two = run_accounts_two_step(daily_r, risk)
        rows.append({
            "risk": risk, **two,
            "expected_days": _expected(two),
            "max_dd": round(dd_r * risk, 4),
            "one_step": {**one, "expected_days": _expected(one)},
        })
    return rows


def pick(rows: list[dict]) -> dict:
    """Fewest expected days per funded account, among the risk levels that are
    actually allowed.

    Three constraints, all from the project's own gates: the two breach rates
    each under MAX_BREACH, and **peak drawdown inside the 8% cap at the risk
    used**. That last one matters more than it looks. Without it the rule picks
    a level whose equity curve draws down past the cap it is meant to respect,
    while the simulation still reports a low breach rate - because each account
    starts on its own day and stops at a pass or a breach, so most are finished
    before they ever meet the worst stretch of the curve. A low breach rate on
    short-lived accounts is not evidence that the drawdown fits.

    Read on the two-step structure, which is what `ladder` now puts in the
    headline keys: an account has to clear 8% and then 5%, and a level that only
    looks affordable across one phase is not affordable.

    If nothing qualifies, fall back to the level with the smallest drawdown."""
    ok = [x for x in rows
          if x["fail_max"] <= MAX_BREACH and x["fail_daily"] <= MAX_BREACH
          and abs(x["max_dd"]) <= DD_CAP and x["expected_days"] is not None]
    if not ok:
        return min(rows, key=lambda x: abs(x["max_dd"]))
    return min(ok, key=lambda x: x["expected_days"])


def from_trades(r: np.ndarray, exit_ts) -> tuple[list[dict], dict]:
    """The usual entry point: trade R multiples plus their exit timestamps."""
    daily = pd.Series(r, index=pd.DatetimeIndex(exit_ts)).resample("1D").sum()
    rows = ladder(daily, r)
    return rows, pick(rows)
