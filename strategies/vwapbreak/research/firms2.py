"""The firm shortlist under Kris's EUR 40 budget, re-priced 2026-09-15.

Kris, 2026-09-15: *"i dont want to spend more then 40 euros on challange"*, and
*"add to research the5ers.com"*.

TWO THINGS ARE WRONG WITH `docs/FIRMS.md` AND THIS FIXES BOTH.

  1. **It never carried a price.** It ranked nine firms on expected days and
     said nothing about what each costs, so it cannot answer the question that
     was actually asked.
  2. **The5ers Bootcamp was modelled with a 3% daily cap it does not have.**
     FIRMS.md scored it at 219.9 expected days with `daily_loss=0.03`. The
     firm's own page and two independent write-ups say the 3% daily pause
     applies ONLY at the funded stage, never during the three evaluation steps.
     A daily cap is the single most expensive rule for this strategy - its
     worst day is -3.93% of balance at 2% risk - so modelling one that is not
     there is not a small error.

`run_phases` is IMPORTED from `firms.py`, not re-implemented, so both files
score identically and the only thing that changes here is the rule sets, the
prices, and the budget filter.

EVERY RULE BELOW WAS READ OFF A COMPARISON PAGE OR THE FIRM'S OWN DOCS ON
2026-09-15 AND NONE OF IT IS A SIGNED CONTRACT. The `unverified` field on each
row says which specific line still has to be confirmed before money moves.

Run: .venv/bin/python strategies/vwapbreak/research/firms2.py
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from core.prop_rules import PropRules                              # noqa: E402

_spec = importlib.util.spec_from_file_location(
    "firms", Path(__file__).with_name("firms.py"))
_f = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_f)
run_phases, series, RISKS = _f.run_phases, _f.series, _f.RISKS

BUDGET_EUR = 40.0
#: rough, and only used to put USD prices on one axis with a EUR budget.
USD_EUR = 0.92

#: name -> dict. `phases` is the evaluation only; the funded stage is a separate
#: question and is noted rather than simulated.
FIRMS = {
    "The5ers Bootcamp 3-step": {
        "phases": [PropRules(profit_target=0.06, daily_loss=1.0, max_loss=0.05,
                             trailing=False, min_trading_days=0)] * 3,
        "eur": 19.0, "consistency": None, "platform": "MT5, cTrader",
        "note": ("NO daily cap on any evaluation step - the 3% daily pause is "
                 "funded-stage only. Mandatory stop-loss on every position, max "
                 "2% risk per position, 5 violations terminates. EUR 43 more to "
                 "activate the funded account."),
        "unverified": "static vs trailing on the 5%; any consistency rule at the funded stage",
    },
    "FundingPips 2-Step Flex": {
        "phases": [PropRules(profit_target=0.10, daily_loss=0.04, max_loss=0.12,
                             trailing=False, min_trading_days=0),
                   PropRules(profit_target=0.06, daily_loss=0.04, max_loss=0.12,
                             trailing=False, min_trading_days=0)],
        "eur": 32.0 * USD_EUR, "consistency": None, "platform": "cTrader, MT5",
        "note": ("12% STATIC max loss - double Thunderbolt's - and a 4% daily "
                 "rather than 3%. No consistency rule, no minimum days at the "
                 "85% split."),
        "unverified": "the $32 price is for the 5K size; 1-Step Flex is $66 and over budget",
    },
    "Maven 3-step": {
        "phases": [PropRules(profit_target=0.03, daily_loss=0.02, max_loss=0.03,
                             trailing=False, min_trading_days=0)] * 3,
        "eur": 17.0 * USD_EUR, "consistency": None, "platform": "unconfirmed",
        "note": "cheapest thing in the list and the tightest drawdown in it.",
        "unverified": "platform; whether the 3% static is balance or equity",
    },
    "Maven 2-step": {
        "phases": [PropRules(profit_target=0.08, daily_loss=0.02, max_loss=0.05,
                             trailing=False, min_trading_days=0),
                   PropRules(profit_target=0.05, daily_loss=0.02, max_loss=0.05,
                             trailing=False, min_trading_days=0)],
        "eur": 22.0 * USD_EUR,
        "consistency": "3 profitable days of 0.5% PER PHASE",
        "platform": "unconfirmed",
        "note": ("DISQUALIFIED. That is the best-day rule wearing a different "
                 "hat - the same rule FIRMS.md rejected The5ers ProGrowth for. "
                 "This strategy takes 0.93 trades a day and one winner in five "
                 "carries it; three separate 0.5% days per phase is a different "
                 "strategy."),
        "unverified": "-",
    },
    "Upcomers Thunderbolt (shipped)": {
        "phases": [PropRules(profit_target=0.06, daily_loss=0.03, max_loss=0.06,
                             min_trading_days=0)],
        "eur": None, "consistency": "20% best day (funded)", "platform": "cTrader",
        "note": "the rule every board number is quoted against, for reference.",
        "unverified": "-",
    },
    "City Traders Imperium 1-step": {
        "phases": [PropRules(profit_target=0.08, daily_loss=1.0, max_loss=0.05,
                             trailing=False, min_trading_days=0)],
        "eur": 59.0 * USD_EUR, "consistency": None, "platform": "MT5, Match-Trader",
        "note": "over budget; kept because it is the other no-daily-cap firm.",
        "unverified": "the $59 entry price",
    },
}


def best(daily, phases, sizing) -> dict:
    out = None
    for r in RISKS:
        x = run_phases(daily, r, phases, sizing)
        if x["days"] and (out is None or x["days"] < out["days"]):
            out = x
    return out or {"days": None, "pass_pct": 0.0, "blown_pct": 0.0, "risk_pct": None}


def main() -> int:
    daily = series()
    print("H-027 gold 1h, cached blind walk-forward, budget-linear sizing.\n"
          "EVALUATION ONLY - the funded stage is a separate question.\n")
    hdr = (f"{'firm':32}{'EUR':>7}{'steps':>7}{'days':>8}{'pass%':>7}"
           f"{'blown%':>8}{'risk':>7}  consistency")
    print(hdr); print("-" * (len(hdr) + 12))
    rows = []
    for name, c in FIRMS.items():
        s = best(daily, c["phases"], "budget")
        row = {"firm": name, **{k: c[k] for k in
               ("eur", "consistency", "platform", "note", "unverified")},
               "steps": len(c["phases"]), "sized": s,
               "in_budget": c["eur"] is not None and c["eur"] <= BUDGET_EUR,
               "eligible": c["consistency"] is None}
        rows.append(row)
        price = "shipped" if c["eur"] is None else f"{c['eur']:.0f}"
        flag = "" if row["eligible"] else "   <- DISQUALIFIED"
        print(f"{name:32}{price:>7}{len(c['phases']):>7}"
              f"{(s['days'] or 0):8.1f}{s['pass_pct']:7.1f}{s['blown_pct']:8.1f}"
              f"{(s['risk_pct'] or 0):6.2f}%  {c['consistency'] or 'none stated'}{flag}",
              flush=True)

    ok = [r for r in rows if r["eligible"] and r["in_budget"] and r["sized"]["days"]]
    ok.sort(key=lambda r: r["sized"]["days"])
    print(f"\nEligible AND under EUR {BUDGET_EUR:.0f}, fastest first:")
    for r in ok:
        print(f"  {r['firm']:32} {r['sized']['days']:6.1f} days   "
              f"{r['sized']['pass_pct']:5.1f}% pass   {r['sized']['blown_pct']:5.1f}% blown   "
              f"EUR {r['eur']:.0f}   [{r['platform']}]")

    dest = ROOT / "backtests" / "vwapbreak" / "firms2.json"
    dest.write_text(json.dumps({"budget_eur": BUDGET_EUR, "rows": rows},
                               indent=1, default=str))
    print(f"\nwrote {dest.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
