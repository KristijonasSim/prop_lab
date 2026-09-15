"""What a consistency rule does INSIDE the challenge, not just at payout.

Kris sent Blue Guardian's own pricing page on 2026-09-15 and asked: *"is there
any succees rule in this company where it would be rule of 20% where one trade
cant be bigger and etc etc i think its important for us"*.

IT IS, AND firms4.py HAD BLUE GUARDIAN WRONG. It scored the firm with
`best_day_cap=None` on the strength of a comparison table that said "no
consistency rule". The firm's own page says **Consistency 50%** and lists it
under BOTH "Challenge Rules" and "Funded & Reward Rules". That is the single
worst kind of error this repo makes - a third-party summary preferred over the
primary source - and it promoted Blue Guardian to the top of the shortlist.

WHY THE CHALLENGE-STAGE VERSION NEEDED NEW CODE. Every firm table here has
treated a consistency rule as a PAYOUT gate: pass the evaluation, then discover
you cannot withdraw. A cap that sits in the Challenge Rules is a different
object - it gates PASSING. Reaching the profit target is no longer sufficient;
the account must reach it AND have its best day be under the cap share of total
profit. An account that hits +10% on one enormous day has not passed, and must
keep trading - at risk - until the ratio comes down or the drawdown kills it.

That is a strictly harsher rule for this strategy than the payout version,
because it converts "we passed but cannot withdraw" into "we cannot pass".

Run: .venv/bin/python strategies/vwapbreak/research/consistency.py
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from core.prop_rules import PropRules                              # noqa: E402

_spec = importlib.util.spec_from_file_location(
    "firms", Path(__file__).with_name("firms.py"))
_f = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_f)
series, RISKS = _f.series, _f.RISKS
MAX_DAYS = _f.MAX_DAYS


def run_phase_consistency(daily: pd.Series, risk: float, rules: PropRules,
                          cap: float | None) -> dict:
    """One phase, with an optional consistency cap that gates PASSING.

    Identical to `firms.run_phases` for a single phase when `cap is None`. When a
    cap is set, hitting the profit target is necessary but not sufficient: the
    largest single POSITIVE day must be at or under `cap` x the total profit, or
    the account keeps trading and keeps risking the drawdown caps.
    """
    d = daily.values
    n = len(d)
    out = []
    for s0 in range(n):
        eq = peak = 0.0
        best_day = 0.0
        k, day, res = s0, 0, "OPEN"
        while k < n and day < MAX_DAYS:
            day += 1
            dd = min(eq - peak, eq)
            mult = float(np.clip((rules.max_loss + dd) / rules.max_loss, 0.25, 1.0))
            step = d[k] * risk * mult
            k += 1
            if min(step, 0.0) <= -rules.daily_loss:
                res = "FAIL_DAILY"
                break
            low = eq + min(step, 0.0)
            if (rules.trailing and low - peak <= -rules.max_loss) or \
               (rules.static and low <= -rules.max_loss):
                res = "FAIL_MAX"
                break
            eq += step
            best_day = max(best_day, step)
            peak = max(peak, eq)
            if eq >= rules.profit_target:
                # THE CONSISTENCY GATE. Target reached - but is the profit
                # spread widely enough for the firm to accept it?
                if cap is None or (eq > 0 and best_day <= cap * eq):
                    res = "PASS"
                    break
                # else: keep trading. Nothing is booked, the caps still apply.
        out.append((res, day))
    df = pd.DataFrame(out, columns=["outcome", "days"])
    p = df[df.outcome == "PASS"]
    rate = len(p) / len(df) if len(df) else 0.0
    return {"pass_pct": round(rate * 100, 1),
            "blown_pct": round(float(df.outcome.isin(["FAIL_MAX", "FAIL_DAILY"]).mean()) * 100, 1),
            "stuck_pct": round(float((df.outcome == "OPEN").mean()) * 100, 1),
            "days": round(float(p.days.median()) / rate, 1) if rate else None,
            "risk_pct": risk * 100}


def best(daily, rules, cap):
    out = None
    for r in RISKS:
        x = run_phase_consistency(daily, r, rules, cap)
        if x["days"] and (out is None or x["days"] < out["days"]):
            out = x
    return out or {"days": None, "pass_pct": 0.0, "blown_pct": 0.0,
                   "stuck_pct": 100.0, "risk_pct": None}


def main() -> int:
    daily = series()
    # Blue Guardian 1 Step Nano, read off the firm's own pricing page:
    # 10% target, 4% max daily loss, 6% TRAILING drawdown, Consistency 50%,
    # min trading days none, EAs yes, weekend + overnight holding yes,
    # news trading yes in the challenge and NO once funded.
    BG = PropRules(profit_target=0.10, daily_loss=0.04, max_loss=0.06,
                   trailing=True, static=False, min_trading_days=0)

    print("BLUE GUARDIAN 1 STEP NANO - the firm's own page, not a review\n")
    hdr = f"{'consistency cap':>16}{'days':>8}{'pass%':>8}{'blown%':>9}{'never passed%':>15}{'risk':>7}"
    print(hdr); print("-" * len(hdr))
    rows = {}
    for cap in (None, 0.50, 0.40, 0.30, 0.20):
        b = best(daily, BG, cap)
        rows["none" if cap is None else f"{cap:.2f}"] = b
        print(f"{('none' if cap is None else f'{cap*100:.0f}%'):>16}"
              f"{(b['days'] or 0):>8.1f}{b['pass_pct']:>8.1f}{b['blown_pct']:>9.1f}"
              f"{b['stuck_pct']:>14.1f}%{(b['risk_pct'] or 0):>6.2f}%", flush=True)

    n, c = rows["none"], rows["0.50"]
    print(f"\n   The 50% cap Blue Guardian actually applies takes the pass rate\n"
          f"   {n['pass_pct']:.1f}% -> {c['pass_pct']:.1f}% and expected days "
          f"{n['days']:.1f} -> {c['days'] if c['days'] else float('nan'):.1f}.")

    # The same cap on the other shortlisted structures, so the comparison is fair.
    print("\nTHE SAME 50% GATE ON THE OTHER SHORTLISTED ONE-STEP STRUCTURES\n")
    others = {
        "City Traders Imperium (static, no daily)":
            PropRules(profit_target=.10, daily_loss=1.0, max_loss=.05,
                      trailing=False, static=True, min_trading_days=0),
        "Alpha Capital Alpha One (trailing)":
            PropRules(profit_target=.10, daily_loss=.04, max_loss=.06,
                      trailing=True, static=False, min_trading_days=0),
        "FundingPips 1-Step Flex (static 12%)":
            PropRules(profit_target=.10, daily_loss=.04, max_loss=.12,
                      trailing=False, static=True, min_trading_days=0),
    }
    hdr = f"{'structure':44}{'no cap days':>13}{'pass%':>7}{'| 50% cap days':>16}{'pass%':>7}"
    print(hdr); print("-" * len(hdr))
    for name, r in others.items():
        a, b = best(daily, r, None), best(daily, r, 0.50)
        rows[name] = {"no_cap": a, "cap50": b}
        print(f"{name:44}{(a['days'] or 0):>13.1f}{a['pass_pct']:>7.1f}"
              f"{(b['days'] or 0):>16.1f}{b['pass_pct']:>7.1f}", flush=True)

    dest = ROOT / "backtests" / "vwapbreak" / "consistency.json"
    dest.write_text(json.dumps(rows, indent=1, default=str))
    print(f"\nwrote {dest.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
