"""Twenty-two prop firms, priced on our own trade series. 2026-09-15.

Kris: *"please do research of at least 20 best prop firms and give me table of
results what would suit best"*.

TWO AXES, AND THE SECOND ONE IS THE ONE EVERY COMPARISON SITE MISSES.

  A. **Can we pass the evaluation, and how fast?**  Arithmetic on a fixed trade
     series under each firm's published phase rules. `run_phases` is imported
     from `firms.py` so this scores identically to every earlier firm table.

  B. **Can we ever be PAID?**  Almost every firm caps the share of a payout that
     may come from a single trading day. `docs/FIRMS.md` measured this strategy's
     profit shape on 2026-09-10: one day is 76-95% of all profit at any
     accumulation length. That is not a tuning problem - the lumpiness IS the
     edge. So a firm can be the fastest in the table to pass and still never pay,
     and the two columns must be read together or the ranking is nonsense.

Axis B is re-measured here rather than quoted, because the threshold differs by
firm (20%, 35%, 40%, 50%) and a single quoted range cannot answer per-firm.

EVERY RULE AND PRICE BELOW IS THIRD-PARTY, read off firm help-centre pages and
comparison sites on 2026-09-15. Rows carry what is unconfirmed. None of it is a
signed contract and several firms changed rules mid-2026 (Goat's 1-step daily
went 4% -> 3% in August; its funded payout gained a 4-day 0.5% requirement in
July), so the date on this file matters.

Run: .venv/bin/python strategies/vwapbreak/research/firms3.py
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

BUDGET_EUR = 40.0
USD_EUR = 0.92
NONE = 1.0          # `daily_loss=1.0` is how this engine spells "no daily cap"


def P(t, d, m, trailing=False, days=0):
    return PropRules(profit_target=t, daily_loss=d, max_loss=m,
                     trailing=trailing, min_trading_days=days)


#: firm -> (phases, usd, best_day_cap_at_payout, platform, note, unverified)
#: best_day_cap: None = no rule found; a float = max share of a payout that may
#: come from one day; "days" rules are expressed as their equivalent share where
#: the firm states one, and noted where they are a different shape.
FIRMS = {
    # ---- one-step ---------------------------------------------------- #
    "Goat Funded 1-step": ([P(.10, .03, .06)], 17, 0.50, "MT5, cTrader",
        "no consistency rule to PASS; funded payout needs 4 days of +0.5% each",
        "the 4-day payout rule is dated 2026-07-27 and may not apply to older accounts"),
    "City Traders Imperium 1-step": ([P(.10, NONE, .05)], 39, None, "MT5, Match-Trader",
        "no daily cap at all; drawdown on CLOSED BALANCE, so this is conservative",
        "price $39 from a comparison table; FIRMS.md had $59 and an 8% target"),
    "Upcomers Thunderbolt 1-step": ([P(.05, .03, .06, trailing=True)], None, 0.20, "cTrader",
        "the shipped reference rule", "-"),
    "Upcomers Ash 1-step": ([P(.02, .03, .06, trailing=True)], None, 0.20, "cTrader",
        "fastest to funded of anything ever measured here", "-"),
    "FundedNext 1-step": ([P(.10, .03, .06)], 66, 0.40, "MT4, MT5, cTrader", "", "-"),
    "Atlas Funded 1-step": ([P(.11, .04, .07)], 68, 0.40, "MT5, TradeLocker, Match-Trader",
        "also a 1%-profit-per-day rule", "-"),
    "PipFarm 1-step": ([P(.12, NONE, .06)], 45, 0.20, "cTrader",
        "5 winning days required; the 25% 'consistency score' is a separate gate",
        "the daily rule is a consistency score, not a loss cap - modelled as no daily cap"),
    "FundingPips 1-Step Flex": ([P(.10, .04, .12)], 66, None, "cTrader, MT5",
        "12% static max loss", "price is for the 5K size"),
    # ---- two-step ---------------------------------------------------- #
    "Aqua Funded 2-Step Std": ([P(.08, .05, .10), P(.05, .05, .10)], 15,
        None, "MT5, cTrader, Match-Trader, TradeLocker", "static drawdown", "-"),
    "Aqua Funded 2-Step Pro": ([P(.10, .05, .10, trailing=True),
                                P(.05, .05, .10, trailing=True)], 20, 0.50,
        "MT5, cTrader", "TRAILING drawdown", "-"),
    "Goat Funded 2-step": ([P(.08, .04, .10), P(.06, .04, .10)], 22, 0.50,
        "MT5, cTrader, DXtrade, Match-Trader", "", "-"),
    "Maven 2-step": ([P(.08, .04, .08), P(.05, .04, .08)], 22, None, "MT5, Match-Trader",
        "firm's page says 'Consistency score: Not required'",
        "two review sites claim 3 profitable days of 0.5% per phase; also shows "
        "'not available in your region'"),
    "FundingPips 2-Step Flex": ([P(.10, .04, .12), P(.06, .04, .12)], 32, None,
        "cTrader, MT5", "12% static; no consistency rule at the 85% split", "-"),
    "FundingPips 2-Step Std": ([P(.08, .05, .10), P(.05, .05, .10)], 29, None,
        "cTrader, MT5", "", "-"),
    "FXIFY 2-step": ([P(.08, .04, .08), P(.05, .04, .08)], 39, None,
        "MT5, DXtrade, TradingView", "no cTrader", "-"),
    "FundedNext 2-step": ([P(.10, .03, .06), P(.05, .03, .06)], 32, 0.40,
        "MT4, MT5, cTrader", "", "-"),
    "Alpine Funded Peak 2-step": ([P(.08, .04, .08), P(.05, .04, .08)], 49, None,
        "cTrader", "", "rules carried over from FIRMS.md 2026-09-09"),
    "FTMO 2-step": ([P(.10, .05, .10), P(.05, .05, .10)], 155, None, "cTrader, MT5",
        "no numeric consistency rule; a discretionary 'trading style' review", "-"),
    "Funded Trading Plus 2-step": ([P(.07, .04, .08), P(.07, .04, .08)], 79, 0.50,
        "MT4, MT5, cTrader, DXtrade", "35% in challenge, 50% funded", "-"),
    # ---- three-step -------------------------------------------------- #
    "The5ers Bootcamp 3-step": ([P(.06, NONE, .05)] * 3, 22, None, "MT5, cTrader",
        "NO daily cap on any step - the 3% pause is funded-stage only. Mandatory "
        "stop-loss, max 2% risk per position, 5 violations terminates. "
        "+EUR 43 to activate funded.",
        "static vs trailing on the 5%; funded-stage consistency rule"),
    "Maven 3-step": ([P(.03, .02, .03)] * 3, 17, None, "MT5, Match-Trader",
        "tightest drawdown in the table", "-"),
    "The5ers Hyper Growth 3-step": ([P(.06, .03, .06)] * 3, 39, None, "MT5, cTrader",
        "carries a 3% daily cap, unlike Bootcamp", "rules from a comparison table"),
}


def best_eval(daily, phases) -> dict:
    out = None
    for r in RISKS:
        x = run_phases(daily, r, phases, "budget")
        if x["days"] and (out is None or x["days"] < out["days"]):
            out = x
    return out or {"days": None, "pass_pct": 0.0, "blown_pct": 0.0, "risk_pct": None}


def best_day_shares(daily: pd.Series, window: int = 30) -> np.ndarray:
    """Share of a payout window's profit contributed by its single best day.

    This is axis B. A firm capping the best day at `c` can only pay us when this
    number is below `c`, so the distribution of this quantity - not its average -
    decides whether a funded account ever produces money.

    Windows that end up unprofitable are dropped: there is no payout to request,
    so no consistency rule applies to them.
    """
    v = daily.values
    out = []
    for i in range(0, len(v) - window):
        w = v[i:i + window]
        tot = w.sum()
        if tot <= 0:
            continue
        out.append(max(w.max(), 0.0) / tot)
    return np.asarray(out)


def main() -> int:
    daily = series()

    # ---- axis B, measured once; it is a property of the series ---------- #
    print("AXIS B - the profit shape, and it does not depend on the firm\n")
    print(f"{'payout window':>16}{'windows':>9}{'median best-day share':>24}"
          f"{'% of windows under 20%':>24}{'under 50%':>12}")
    shares = {}
    for w in (14, 30, 60, 90):
        s = best_day_shares(daily, w)
        shares[w] = s
        print(f"{w:>13}d{len(s):>9}{np.median(s)*100:>23.1f}%"
              f"{(s < 0.20).mean()*100:>23.1f}%{(s < 0.50).mean()*100:>11.1f}%")
    s30 = shares[30]
    print("\n   One day is the median share above of an entire month's profit.\n"
          "   A firm capping the best day at 20% can pay us in "
          f"{(s30 < 0.20).mean()*100:.1f}% of months; at 50%, {(s30 < 0.50).mean()*100:.1f}%.\n")

    # ---- axis A, per firm ---------------------------------------------- #
    print("AXIS A - the evaluation, on our own blind walk-forward, "
          "budget-linear sizing\n")
    hdr = (f"{'firm':30}{'EUR':>6}{'st':>4}{'days':>7}{'pass%':>7}{'blown%':>8}"
           f"{'risk':>7}{'bestday':>9}{'payable%':>10}  platform")
    print(hdr); print("-" * (len(hdr) + 18))
    rows = []
    for name, (phases, usd, cap, platform, note, unver) in FIRMS.items():
        e = best_eval(daily, phases)
        eur = None if usd is None else round(usd * USD_EUR, 1)
        payable = 100.0 if cap is None else round(float((s30 < cap).mean()) * 100, 1)
        rows.append({"firm": name, "steps": len(phases), "eur": eur,
                     "best_day_cap": cap, "payable_pct": payable,
                     "platform": platform, "note": note, "unverified": unver,
                     "eval": e,
                     "in_budget": eur is not None and eur <= BUDGET_EUR})
        print(f"{name:30}{(eur if eur is not None else 0):>6.0f}{len(phases):>4}"
              f"{(e['days'] or 0):>7.1f}{e['pass_pct']:>7.1f}{e['blown_pct']:>8.1f}"
              f"{(e['risk_pct'] or 0):>6.2f}%"
              f"{('none' if cap is None else f'{cap*100:.0f}%'):>9}{payable:>9.1f}%"
              f"  {platform}", flush=True)

    ok = [r for r in rows if r["in_budget"] and r["eval"]["days"]
          and r["payable_pct"] >= 100.0]
    ok.sort(key=lambda r: r["eval"]["days"])
    print(f"\nUNDER EUR {BUDGET_EUR:.0f}, AND NO BEST-DAY RULE TO BLOCK THE PAYOUT:")
    for r in ok:
        print(f"  {r['firm']:30}{r['eval']['days']:>7.1f}d  "
              f"{r['eval']['pass_pct']:>5.1f}% pass  {r['eval']['blown_pct']:>5.1f}% blown  "
              f"EUR {r['eur']:.0f}  [{r['platform']}]")

    dest = ROOT / "backtests" / "vwapbreak" / "firms3.json"
    dest.write_text(json.dumps(
        {"budget_eur": BUDGET_EUR, "best_day_share_30d_median": float(np.median(s30)),
         "rows": rows}, indent=1, default=str))
    print(f"\nwrote {dest.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
