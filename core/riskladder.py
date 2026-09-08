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

from core.prop_rules import ONE_STEP, PropRules, TWO_STEP   # noqa: E402

RISK_LADDER = (0.0025, 0.005, 0.0075, 0.01, 0.0125, 0.015, 0.0175,
               0.02, 0.025, 0.03, 0.04, 0.05)
MAX_BREACH = 0.05     # a risk level that kills more than 1 account in 20 is out
#: MINIMUM RISK PER TRADE. Kris's instruction, 2026-09-08: "aim at at least 2%
#: per trade."
#:
#: THE RULE THIS REPLACES WAS NOT DOING WHAT IT SAID. `pick` documents itself as
#: "fewest expected days among the risk levels that are actually allowed", but
#: gold's peak drawdown is -14.86% at the LOWEST rung on the ladder, already far
#: past the 6% cap - so no rung ever qualified, `pick` fell through to its
#: `min(abs(max_dd))` fallback every single time, and the board's chosen risk was
#: the smallest number on the ladder rather than any kind of optimum. Every board
#: record this project has published was reported at a fallback.
#:
#: AND THE FALLBACK IS EXPENSIVE. On gold 1h, 0.25% risk needs 38.0 expected days
#: to a funded account; 2% needs 16.6 and 3% needs 13.0. What the higher rung
#: buys is speed and what it costs is accounts: 58% blow instead of 46%, so 2.4
#: accounts are bought instead of 2.0 - EUR 52 against EUR 44 at EUR 21.89 an
#: account. Eight euros for twenty-one days is not a close call, and it is only
#: a close call at all because accounts are cheap. THAT is the trade being made
#: here, and it is a business decision, not a statistical one.
#:
#: Read `max_dd` at these rungs as the drawdown of the CONTINUOUS equity curve at
#: that size, not as what one challenge account loses - an account is dead at 6%
#: and stops. It is why a -118% curve still passes 42% of accounts in a median of
#: seven days: each account starts on its own day and resolves long before it
#: meets the worst stretch.
MIN_RISK = 0.02
# The firm's max drawdown, not a house rule. Thunderbolt (chosen 2026-09-08) caps
# it at 6%; this was 0.08 while the spec was a guess. Both board picks were
# sitting at -7.5% and -7.8% under the old cap and neither fits this one.
DD_CAP = 0.06
MAX_DAYS = 400        # an account still open after this counts as not passed


def _breached(low: float, peak: float, rules: PropRules) -> bool:
    """Has the max-loss cap been breached, under the rules ACTUALLY configured?

    `PropRules` documents `trailing` and `static` as configurable and both call
    sites used to hard-code `low - peak <= -max_loss or low <= -max_loss`,
    reading neither flag. Two consequences, both silent:

      * `trailing=False` did nothing. Every result the board has ever published
        is on a trailing cap whether or not the firm uses one.
      * the static term was dead code. `peak` starts at 0 and only rises, so
        `low - peak <= low` always, and the trailing test fires first or at the
        same moment. It could never be the binding constraint.

    That is not a rounding difference. `NEXT.md` puts it at **17 points of pass
    rate**: a ZERO-EDGE strategy passes 40.2% of the time under a trailing cap
    and 57.1% under a static one. Which of those a firm uses is worth more than
    most edges in this repo, and until 2026-09-07 the code could not express the
    question. Defaults are unchanged - both flags are True - so no published
    number moves; what changes is that `PropRules(trailing=False)` now means
    something.
    """
    if rules.trailing and low - peak <= -rules.max_loss:
        return True
    if rules.static and low <= -rules.max_loss:
        return True
    return False


def run_accounts(daily_r: pd.Series, risk: float, rules: PropRules = ONE_STEP[0],
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
            if _breached(low, peak, rules):
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
                if _breached(low, peak, rules):
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

    The headline keys (`pass_rate`, `median_days`, `expected_days`, the two
    breach rates) are the **firm's own structure** — Thunderbolt, one step, 6%
    target, 3% daily, 6% max, chosen by Kris 2026-09-08 and the first real spec
    this project has had. Until then the headline was a modelled 8%+5% two-step,
    which was an honest guess and is now simply wrong.

    The two-step numbers are kept alongside under `two_step`, because Kris will
    run SEVERAL firms and the next one may well be two-step. Keeping both is what
    makes the structure question answerable instead of re-litigated.
    """
    eq = np.concatenate(([0.0], np.cumsum(r_series)))
    dd_r = float((eq - np.maximum.accumulate(eq)).min())
    rows = []
    for risk in levels:
        one = run_accounts(daily_r, risk)          # the firm: one step, 6%
        two = run_accounts_two_step(daily_r, risk)  # kept for the next firm
        rows.append({
            "risk": risk, **one,
            "expected_days": _expected(one),
            "max_dd": round(dd_r * risk, 4),
            "two_step": {**two, "expected_days": _expected(two)},
            # the old key name, so nothing that reads it breaks while the board
            # pages are updated; same values as the headline now
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

    THE FLOOR COMES FIRST. `MIN_RISK` is Kris's instruction and it is applied
    before anything else, because the alternative - which is what this function
    did until 2026-09-08 - is to fall through to the smallest number on the
    ladder whenever the drawdown cap cannot be met, which on this data is always.

    AND IT IS A TARGET, NOT A LICENCE TO CLIMB. Among the rungs that clear the
    floor, this takes the LOWEST one that resolves accounts - not the fastest.
    Chasing speed above the floor is a trap with a measured example: at 5% risk
    GBPUSD 1h reports 10.4 expected days while its profit factor at 2x cost is
    **0.823**, a losing strategy. `expected_days` is `median_days / pass_rate`,
    and at a large position size a losing book still funds the occasional account
    on variance alone before it dies - short median, low pass rate, flattering
    ratio. Optimising that number across the whole ladder buys lottery tickets,
    and README.md is explicit that passing is not the goal: "What matters is the
    lift over that line, and keeping the account afterwards."

    So: clear the floor, then take the smallest size that works. Speed above the
    floor has to be argued for per strategy, from the ladder, by a person.

    If nothing at or above the floor resolves any account, fall back below it
    rather than returning nothing, and only then to the smallest drawdown."""
    at_floor = [x for x in rows if x["risk"] >= MIN_RISK - 1e-12]
    pool = at_floor or rows
    ok = [x for x in pool
          if x["fail_max"] <= MAX_BREACH and x["fail_daily"] <= MAX_BREACH
          and abs(x["max_dd"]) <= DD_CAP and x["expected_days"] is not None]
    if ok:
        return min(ok, key=lambda x: (x["risk"], x["expected_days"]))
    # Nothing clears the firm's caps - which on this data is every cell, because
    # gold already draws -14.86% at the bottom rung against a 6% cap. The caps
    # cannot arbitrate, so the floor does: smallest size that resolves anything.
    resolving = [x for x in pool if x["expected_days"] is not None]
    if resolving:
        return min(resolving, key=lambda x: (x["risk"], x["expected_days"]))
    if pool is not rows:
        resolving = [x for x in rows if x["expected_days"] is not None]
        if resolving:
            return min(resolving, key=lambda x: (x["risk"], x["expected_days"]))
    return min(rows, key=lambda x: abs(x["max_dd"]))


#: How a stored board ladder names the same quantities `pick` works in. The
#: board writes percentages because a page renders them; `pick` works in
#: fractions. Kept here, next to `pick`, so the two can never drift.
_STORED = {"risk": ("risk_pct", 100.0), "max_dd": ("max_dd_pct", 100.0),
           "fail_max": ("fail_max_pct", 100.0),
           "fail_daily": ("fail_daily_pct", 100.0),
           "expected_days": ("days_to_pass", None)}


def pick_stored(ladder_rows: list[dict]) -> dict | None:
    """Re-run `pick` over a ladder already written into a board record.

    THE POINT: a board record can be re-priced at a new risk POLICY without
    re-running the walk-forward. The ladder is a fixed trade series simulated at
    twelve position sizes, so changing `MIN_RISK` changes which row to read, not
    what the rows say. When Kris moved the floor to 2% this is what let every
    record move with him in a second rather than in half an hour.

    Returns the chosen row IN ITS STORED FORM, or None if the ladder is empty.
    """
    if not ladder_rows:
        return None
    conv = []
    for row in ladder_rows:
        c = {}
        for k, (src, scale) in _STORED.items():
            v = row.get(src)
            c[k] = v if (v is None or scale is None) else v / scale
        c["_stored"] = row
        conv.append(c)
    return pick(conv)["_stored"]


def from_trades(r: np.ndarray, exit_ts) -> tuple[list[dict], dict]:
    """The usual entry point: trade R multiples plus their exit timestamps."""
    daily = pd.Series(r, index=pd.DatetimeIndex(exit_ts)).resample("1D").sum()
    rows = ladder(daily, r)
    return rows, pick(rows)
