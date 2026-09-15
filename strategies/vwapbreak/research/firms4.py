"""Forty-four prop-firm products, priced on our own trade series. 2026-09-15.

Kris: *"please do bigger research i know its not best ones"* - the twenty-two in
`firms3.py` came largely off cheap-challenge listicles and missed most of the
established names. This is the wide sweep: every forex/multi-asset firm found in
a 63-firm industry directory plus the firm-by-firm rule pages, filtered to those
that trade gold. Futures-only firms are excluded by construction - we trade
XAUUSD, and a Tradovate firm cannot hold it.

SAME TWO AXES AS firms3, AND AXIS B STILL DECIDES MOST OF IT.

  A. how fast we pass, on our own blind walk-forward. `run_phases` imported
     from `firms.py`, so every firm table in this repo scores identically.
  B. whether a payout is ever possible. One day is 95.5% of a typical month's
     profit here, so any best-day cap at or under 50% takes a firm to ~0%.

WHAT IS NEW BESIDES THE COUNT. Three rule shapes that firms3 never encountered
and that matter more than another 10 rows of the same:

  * **TRAILING drawdown.** firms3 held almost everything static. Blue Guardian,
    Alpha One, ThinkCapital, E8 One and Aqua Pro all trail, and a trailing cap
    is punitive for a rule whose equity swings hundreds of R before resolving.
    `PropRules(trailing=True)` prices it.
  * **No-weekend-holding.** Alpha Capital's qualified Pro accounts forbid it.
    The shipped rule holds up to 384 hours - sixteen days - so it cannot be
    traded there at all. Marked as a hard exclusion, not a slow row.
  * **Very loose caps.** Finotive's 8% daily / 16% max is the widest thing in
    the industry and is the natural test of whether our speed problem is the
    cap or the edge.

Prices and rules are third-party, gathered 2026-09-15, and firms change them
mid-year. `data` on each row says how good the source was.

Run: .venv/bin/python strategies/vwapbreak/research/firms4.py
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
run_phases, series, RISKS = _f.run_phases, _f.series, _f.RISKS

_spec3 = importlib.util.spec_from_file_location(
    "firms3", Path(__file__).with_name("firms3.py"))
_f3 = importlib.util.module_from_spec(_spec3)
_spec3.loader.exec_module(_f3)
best_day_shares = _f3.best_day_shares

BUDGET_EUR = 40.0
USD_EUR = 0.92
NONE = 1.0


def P(t, d, m, trail=False, days=0):
    return PropRules(profit_target=t, daily_loss=d, max_loss=m,
                     trailing=trail, static=not trail, min_trading_days=days)


# firm -> (phases, usd, best_day_cap, platform, data_quality, note)
# best_day_cap: None = no rule found. "excl" in place of phases = hard exclusion.
F = {
 # ---------------------------------------------------------- one step ---- #
 "City Traders Imperium 1-step": ([P(.10, NONE, .05)], 39, None, "MT5, DXtrade",
   "good", "no daily cap at all; drawdown on CLOSED BALANCE"),
 "FundingPips 1-Step Flex": ([P(.10, .04, .12)], 66, None, "cTrader, MT5",
   "good", "12% static - the loosest max in the one-step group"),
 "Goat Funded 1-step": ([P(.10, .03, .06)], 17, 0.50, "MT5, cTrader",
   "good", "no rule to PASS; funded payout needs 4 days of +0.5% each"),
 "FundedNext Stellar 1-step": ([P(.10, .03, .06)], 66, 0.40, "MT4, MT5, cTrader",
   "good", ""),
 "Atlas Funded 1-step": ([P(.11, .04, .07)], 68, 0.40, "MT5, Match-Trader",
   "good", "also a 1%-profit-per-day rule"),
 "PipFarm 1-step": ([P(.12, NONE, .06)], 45, 0.20, "cTrader, TradeLocker",
   "fair", "5 winning days; the daily gate is a consistency score not a loss cap"),
 "Hola Prime 1-Step Prime": ([P(.10, .03, .06)], 45, 0.35, "MT5, cTrader, Match-Trader",
   "good", "40% best-day in evaluation, 35% funded"),
 "Blue Guardian 1-Step Std": ([P(.09, .04, .06, trail=True)], 32, None,
   "MT5, Match-Trader, cTrader", "good", "6% TRAILING off the equity high"),
 "Alpha Capital Alpha One": ([P(.10, .04, .06, trail=True)], 39, None,
   "MT4, MT5, cTrader", "good", "6% TRAILING"),
 "ThinkCapital Lightning": ([P(.10, .03, .06, trail=True)], 45, None, "MT5",
   "fair", "6% TRAILING"),
 "Fintokei SwiftTrader 1-step": ([P(.10, .05, .10)], 45, 0.40, "MT4, MT5, DXtrade",
   "fair", "40% cap stated for multi-phase; assumed to apply"),
 "E8 One (1-step)": ([P(.06, .03, .04, trail=True)], 88, 0.40, "MT5, Match-Trader",
   "fair", "customisable at purchase; modelled at its tightest/cheapest setting"),
 "Upcomers Thunderbolt 1-step": ([P(.05, .03, .06, trail=True)], None, 0.20, "cTrader",
   "good", "the shipped reference rule"),
 "Upcomers Ash 1-step": ([P(.02, .03, .06, trail=True)], None, 0.20, "cTrader",
   "good", "fastest thing ever measured here, and unpayable"),
 "DNA Funded 1-phase": ([P(.10, .05, .06, trail=True)], 49, 0.30, "MT5",
   "fair", "min 3 trading days; trailing"),
 # ---------------------------------------------------------- two step ---- #
 "Aqua Funded 2-Step Std": ([P(.08, .05, .10), P(.05, .05, .10)], 15, None,
   "MT5, cTrader, Match-Trader", "good", "static"),
 "Aqua Funded 2-Step Pro": ([P(.10, .05, .10, trail=True), P(.05, .05, .10, trail=True)],
   20, 0.50, "MT5, cTrader", "good", "TRAILING"),
 "Goat Funded 2-step": ([P(.08, .04, .10), P(.06, .04, .10)], 22, 0.50,
   "MT5, cTrader, Match-Trader", "good", ""),
 "Maven 2-step": ([P(.08, .04, .08), P(.05, .04, .08)], 22, None,
   "MT5, cTrader, TradeLocker", "good",
   "firm page says 'Consistency score: Not required'; shows 'not available in your region'"),
 "FundingPips 2-Step Flex": ([P(.10, .04, .12), P(.06, .04, .12)], 32, None,
   "cTrader, MT5", "good", "12% static"),
 "FundingPips 2-Step Std": ([P(.08, .05, .10), P(.05, .05, .10)], 29, None,
   "cTrader, MT5", "good", ""),
 "FXIFY 2-step": ([P(.08, .04, .08), P(.05, .04, .08)], 39, None,
   "MT4, MT5, cTrader, DXtrade", "good", ""),
 "FundedNext Stellar 2-step": ([P(.10, .03, .06), P(.05, .03, .06)], 32, 0.40,
   "MT4, MT5, cTrader", "good", ""),
 "Alpine Funded Peak 2-step": ([P(.08, .04, .08), P(.05, .04, .08)], 49, None,
   "cTrader", "fair", "carried from FIRMS.md 2026-09-09"),
 "FTMO 2-step": ([P(.10, .05, .10), P(.05, .05, .10)], 155, None, "cTrader, MT5",
   "good", "no numeric cap; a discretionary 'trading style' review instead"),
 "Funded Trading Plus 2-step": ([P(.07, .04, .08), P(.07, .04, .08)], 79, 0.35,
   "MT4, MT5, cTrader", "good", "35% challenge / 50% funded"),
 "Blueberry Funded Prime 2-step": ([P(.08, .04, .10), P(.06, .04, .10)], 97, None,
   "MT4, MT5, TradingView", "good",
   "explicitly NO consistency rule on any plan - rare and stated by the firm"),
 "E8 Markets 2-phase": ([P(.08, .04, .08), P(.05, .04, .08)], 88, 0.35,
   "MT5, Match-Trader, TradeLocker", "fair", "35% best-day on Signature, funded only"),
 "Blue Guardian 2-Step Std": ([P(.08, .04, .06), P(.05, .04, .06)], 32, None,
   "MT5, Match-Trader, cTrader", "fair", ""),
 "Fintokei ProTrader 2-step": ([P(.08, .05, .10), P(.05, .05, .10)], 45, 0.40,
   "MT4, MT5, DXtrade", "fair", ""),
 "Quant Tekel 2-step": ([P(.08, .04, .08), P(.05, .04, .08)], 45, None,
   "MT5, cTrader", "weak", "targets 6-8% quoted; daily/max assumed from peers"),
 "Finotive Funding 2-step": ([P(.075, .08, .16), P(.05, .08, .16)], 45, None,
   "MT4, MT5", "fair",
   "8% DAILY and 16% MAX - the loosest caps in the industry. The natural test "
   "of whether our pace problem is the caps or the edge."),
 # -------------------------------------------------------- three step ---- #
 "The5ers Bootcamp 3-step": ([P(.06, NONE, .05)] * 3, 22, None, "MT5, cTrader",
   "good", "NO daily cap on any step; +EUR 43 to activate funded; "
           "mandatory SL, max 2% risk per position, 5 violations terminates"),
 "Maven 3-step": ([P(.03, .02, .03)] * 3, 17, None, "MT5, cTrader", "good",
   "tightest drawdown in the table"),
 "The5ers Hyper Growth 3-step": ([P(.06, .03, .06)] * 3, 39, None, "MT5",
   "fair", "carries a 3% daily, unlike Bootcamp"),
 "Fintokei StartTrader 3-step": ([P(.02, .05, .10), P(.03, .05, .10),
                                  P(.06, .05, .10)], 39, 0.40, "MT4, MT5, DXtrade",
   "good", "2%/3%/6% - the softest per-step targets anywhere"),
}

#: Excluded before scoring, with the reason. Not slow - untradeable.
EXCLUDED = {
 "Alpha Capital Alpha Pro": "weekend holding PROHIBITED on qualified accounts; "
    "the shipped rule holds up to 384h (16 days), so it cannot run here at all",
 "Breakout Prop": "crypto only (Kraken); every crypto VWAP hypothesis here is dead",
 "HyroTrader": "crypto only (Bybit)",
 "Topstep / Apex / Take Profit / MyFundedFutures / Bulenox / Earn2Trade / "
 "Tradeify / TradeDay / Leeloo / BluSky / Elite Trader / Alpha Futures / "
 "Funded Futures Network / Legends": "futures only - cannot hold XAUUSD spot",
 "Seacrest Funded": "ceased prop operations February 2026",
}

#: Named in the directory, gold-capable, but no rule set obtained. Not modelled
#: rather than guessed - a guessed rule set produces a real-looking number.
NO_RULES = ["SabioTrade", "Audacity Capital", "Lark Funding", "MyFundedFX",
            "EverFunded", "AscendX Capital", "For Traders", "The Trading Pit",
            "FTUK", "Instant Funding (Acello)", "Crypto Fund Trader",
            "Velotrade", "RebelsFunding", "Smart Prop Trader"]


def best_eval(daily, phases) -> dict:
    out = None
    for r in RISKS:
        x = run_phases(daily, r, phases, "budget")
        if x["days"] and (out is None or x["days"] < out["days"]):
            out = x
    return out or {"days": None, "pass_pct": 0.0, "blown_pct": 0.0, "risk_pct": None}


def main() -> int:
    daily = series()
    s30 = best_day_shares(daily, 30)
    print(f"AXIS B: one day is {np.median(s30)*100:.1f}% of a median month's profit. "
          f"A 50% cap pays in {(s30 < .50).mean()*100:.1f}% of months, "
          f"a 20% cap in {(s30 < .20).mean()*100:.1f}%.\n")
    print(f"{len(F)} products scored, {len(NO_RULES)} named without rules, "
          f"{len(EXCLUDED)} excluded outright.\n")

    hdr = (f"{'firm':30}{'EUR':>5}{'st':>3}{'DD':>5}{'days':>7}{'pass%':>7}"
           f"{'blown%':>8}{'risk':>6}{'cap':>6}{'pay%':>7} {'data':<5} platform")
    print(hdr); print("-" * (len(hdr) + 20))
    rows = []
    for name, (phases, usd, cap, plat, qual, note) in F.items():
        e = best_eval(daily, phases)
        eur = None if usd is None else round(usd * USD_EUR)
        pay = 100.0 if cap is None else round(float((s30 < cap).mean()) * 100, 1)
        trail = any(p.trailing for p in phases)
        rows.append({"firm": name, "steps": len(phases), "eur": eur,
                     "trailing": trail, "best_day_cap": cap, "payable_pct": pay,
                     "platform": plat, "data": qual, "note": note, "eval": e,
                     "in_budget": eur is not None and eur <= BUDGET_EUR})
        print(f"{name:30}{(eur or 0):>5}{len(phases):>3}"
              f"{('trail' if trail else 'stat'):>5}{(e['days'] or 0):>7.1f}"
              f"{e['pass_pct']:>7.1f}{e['blown_pct']:>8.1f}{(e['risk_pct'] or 0):>5.2f}%"
              f"{('-' if cap is None else f'{cap*100:.0f}%'):>6}{pay:>6.1f}% {qual:<5} {plat}",
              flush=True)

    ok = [r for r in rows if r["in_budget"] and r["eval"]["days"] and r["payable_pct"] >= 100]
    ok.sort(key=lambda r: r["eval"]["days"])
    print(f"\n=== UNDER EUR {BUDGET_EUR:.0f} AND PAYABLE ===")
    for r in ok:
        print(f"  {r['firm']:30}{r['eval']['days']:>7.1f}d  {r['eval']['pass_pct']:>5.1f}% pass"
              f"  {r['eval']['blown_pct']:>5.1f}% blown  EUR {r['eur']:<4} "
              f"{'TRAILING' if r['trailing'] else 'static':8} [{r['platform']}]")

    any_pay = [r for r in rows if r["eval"]["days"] and r["payable_pct"] >= 100]
    any_pay.sort(key=lambda r: r["eval"]["days"])
    print("\n=== PAYABLE AT ANY PRICE, fastest five ===")
    for r in any_pay[:5]:
        print(f"  {r['firm']:30}{r['eval']['days']:>7.1f}d  EUR {r['eur']}")

    print("\n=== EXCLUDED OUTRIGHT ===")
    for k, v in EXCLUDED.items():
        print(f"  {k}: {v}")
    print(f"\n=== NAMED, GOLD-CAPABLE, NO RULE SET OBTAINED ({len(NO_RULES)}) ===\n  "
          + ", ".join(NO_RULES))

    dest = ROOT / "backtests" / "vwapbreak" / "firms4.json"
    dest.write_text(json.dumps({"budget_eur": BUDGET_EUR, "rows": rows,
                                "excluded": EXCLUDED, "no_rules": NO_RULES,
                                "best_day_30d_median": float(np.median(s30))},
                               indent=1, default=str))
    print(f"\nwrote {dest.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
