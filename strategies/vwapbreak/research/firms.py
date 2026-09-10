"""The firm shortlist, re-priced with the SIZING RULE adopted 2026-09-10.

`FIRMS.md` ranked nine firms by running our own trade series through each
published rule set. Every number there assumes FLAT sizing. The rule adopted
today - size in proportion to the remaining drawdown budget - cut blown accounts
from 29.5% to 16.9% on the shipped firm, and a firm's ranking depends on exactly
that, because a tight daily cap is expensive only if you keep hitting it.

So the ranking has to be recomputed, and it is cheap: the daily series is the
cached blind walk-forward (`daily_traded.json`), and applying a firm's rules to a
fixed series is arithmetic, not a search.

WHAT IS NOT RE-DECIDED HERE. The consistency rule. A 20%-best-day cap is a
disqualifier for this strategy at any size - measured three ways on 2026-09-10 -
and no sizing rule changes that, because it is about the SHAPE of the profit, not
its size. Firms carrying one are marked and stay disqualified.

Every rule set below was read off a comparison page or the firm's own docs on
2026-09-09 and none of it is a signed contract. Verify before paying.

Run: .venv/bin/python strategies/vwapbreak/research/firms.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from core.prop_rules import PropRules                              # noqa: E402
from core.riskladder import run_accounts                           # noqa: E402

CACHE = ROOT / "backtests" / "vwapbreak" / "daily_traded.json"
LEG = "XAUUSD|1h"
RISKS = (0.005, 0.01, 0.015, 0.02, 0.025, 0.03, 0.04)
MAX_DAYS = 120

#: name -> (phases, consistency rule, platform, note)
FIRMS = {
    "Upcomers Ash 1-step 2%": (
        [PropRules(profit_target=0.02, daily_loss=0.03, max_loss=0.06,
                   min_trading_days=0)],
        "20% best day (funded)", "cTrader",
        "fastest to funded and the one place this never gets paid"),
    "Upcomers Thunderbolt 1-step 5%": (
        [PropRules(profit_target=0.05, daily_loss=0.03, max_loss=0.06,
                   min_trading_days=0)],
        "20% best day (funded)", "cTrader", "same consistency rule"),
    "FundingPips 1-Step Flex 10%": (
        [PropRules(profit_target=0.10, daily_loss=0.03, max_loss=0.06,
                   trailing=False, min_trading_days=0)],
        None, "cTrader, MT5", "no consistency rule on the weekly-payout track"),
    "City Traders Imperium 1-step 8%": (
        [PropRules(profit_target=0.08, daily_loss=1.0, max_loss=0.05,
                   trailing=False, min_trading_days=0)],
        None, "MT5, Match-Trader",
        "no daily cap; drawdown measured on closed balance, so this is conservative"),
    "FundingPips 2-Step Pro 6%+6%": (
        [PropRules(profit_target=0.06, daily_loss=0.03, max_loss=0.06,
                   trailing=False, min_trading_days=0)] * 2,
        None, "cTrader, MT5", ""),
    "FTMO 2-step 10%+5%": (
        [PropRules(profit_target=0.10, daily_loss=0.05, max_loss=0.10,
                   trailing=False, min_trading_days=0),
         PropRules(profit_target=0.05, daily_loss=0.05, max_loss=0.10,
                   trailing=False, min_trading_days=0)],
        None, "cTrader, MT5", ""),
}


def series() -> pd.Series:
    v = json.loads(CACHE.read_text())[LEG]
    return pd.Series(v["r"], index=pd.date_range(v["t0"], periods=len(v["r"]),
                                                 freq="D"))


def run_phases(daily: pd.Series, risk: float, phases, sizing: str) -> dict:
    """Every phase in sequence from one start day, with a size schedule.

    A breach in any phase kills the account. Phase n+1 starts the day after
    phase n clears, on the same live series, with fresh equity and a fresh
    drawdown budget - which is how firms reset it.
    """
    d = daily.values
    n = len(d)
    out = []
    for s0 in range(n):
        k, res, total = s0, "OPEN", 0
        for rules in phases:
            eq = peak = 0.0
            day = traded = 0
            res = "OPEN"
            while k < n and total + day < MAX_DAYS:
                day += 1
                dd = min(eq - peak, eq)
                mult = (1.0 if sizing == "flat" else
                        float(np.clip((rules.max_loss + dd) / rules.max_loss, 0.25, 1.0)))
                step = d[k] * risk * mult
                k += 1
                if step != 0.0:
                    traded += 1
                if min(step, 0.0) <= -rules.daily_loss:
                    res = "FAIL_DAILY"
                    break
                low = eq + min(step, 0.0)
                if (rules.trailing and low - peak <= -rules.max_loss) or \
                   (rules.static and low <= -rules.max_loss):
                    res = "FAIL_MAX"
                    break
                eq += step
                peak = max(peak, eq)
                if eq >= rules.profit_target and traded >= rules.min_trading_days:
                    res = "PASS"
                    break
            total += day
            if res != "PASS":
                break
        out.append((res, total))
    df = pd.DataFrame(out, columns=["outcome", "days"])
    p = df[df.outcome == "PASS"]
    rate = len(p) / len(df) if len(df) else 0.0
    return {"pass_pct": round(rate * 100, 1),
            "blown_pct": round(float(df.outcome.isin(["FAIL_MAX", "FAIL_DAILY"]).mean()) * 100, 1),
            "days": round(float(p.days.median()) / rate, 1) if rate else None,
            "risk_pct": risk * 100}


def best(daily, phases, sizing) -> dict:
    out = None
    for r in RISKS:
        x = run_phases(daily, r, phases, sizing)
        if x["days"] and (out is None or x["days"] < out["days"]):
            out = x
    return out or {"days": None, "pass_pct": 0.0, "blown_pct": 0.0, "risk_pct": None}


def main() -> int:
    daily = series()
    print("H-027 gold 1h, cached blind walk-forward, best risk rung per firm\n")
    print(f"{'firm':32}{'flat days':>11}{'pass%':>7}{'| sized days':>13}{'pass%':>7}"
          f"{'blown%':>8}{'risk':>7}  consistency")
    rows = []
    for name, (phases, consistency, platform, note) in FIRMS.items():
        f = best(daily, phases, "flat")
        s = best(daily, phases, "budget")
        rows.append({"firm": name, "platform": platform, "consistency": consistency,
                     "note": note, "flat": f, "sized": s})
        print(f"{name:32}{(f['days'] or 0):11.1f}{f['pass_pct']:7.1f}"
              f"{(s['days'] or 0):13.1f}{s['pass_pct']:7.1f}{s['blown_pct']:8.1f}"
              f"{(s['risk_pct'] or 0):6.2f}%  "
              f"{consistency or 'none stated'}", flush=True)

    dest = ROOT / "backtests" / "vwapbreak" / "firms.json"
    dest.write_text(json.dumps({"leg": LEG, "rows": rows}, indent=1, default=str))
    ok = [r for r in rows if not r["consistency"]]
    ok.sort(key=lambda r: r["sized"]["days"] or 1e9)
    print("\nEligible (no consistency rule), fastest first with the sizing rule:")
    for r in ok:
        print(f"  {r['firm']:32} {r['sized']['days']:6.1f} days at "
              f"{r['sized']['pass_pct']:.1f}% pass, {r['sized']['risk_pct']:.2f}% risk"
              f"   [{r['platform']}]")
    print(f"\nwrote {dest.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
