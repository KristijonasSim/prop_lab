"""The two levers that flatten the payoff, applied TOGETHER: partial exit + basket.

Neither is enough on its own, and both push the same way:

    gold alone, as traded          best day = 42.1% of net profit, 0/16 payable
    gold alone, partial exit 1R    28.7%   (`exitshape.py`)
    gold + ETH, as traded          29.8%   (`basket.py`)
    nine legs, as traded           20.0%, and still 0 payable

So the obvious question is whether the two compose. If a two- or three-leg basket
of the PARTIAL-EXIT version gets the single best day under 20% of a withdrawal,
this strategy becomes payable at a firm with a consistency rule - which is the
difference between "cannot be traded at most firms" and "can".

WHAT IS RUN: the winning shape from `exitshape.py` - half off at +1R, then trail
3R behind the best close - walk-forwarded blind on identical folds for four legs,
then combined at equal weight exactly as `basket.py` combines the baseline legs,
and finally swept across withdrawal sizes. The daily series are saved so no future
question about the payout policy needs a re-run.

THE ANSWER, so it is not buried: the flattest payoff this project has produced
(best day 12% of net profit on gold, against 42% as traded) still yields ONE
payable withdrawal in two and a half years, and only at a 10-20% withdrawal size.
The 20% best-day rule is not survivable by reshaping the exit.

Run: .venv/bin/python strategies/vwapbreak/research/payable.py
"""
from __future__ import annotations

import json
import sys
from itertools import combinations
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from core.noiseband import band                                    # noqa: E402
from core.prop_rules import PropRules                              # noqa: E402
from core.riskladder import run_accounts                           # noqa: E402
from core.run_hypothesis import run_market, window                 # noqa: E402
from strategies.vwapbreak.research.exits import UNIVERSE           # noqa: E402
from strategies.vwapbreak.research.exitshape import (ShapedExit,   # noqa: E402
                                                     payout_stats)

ASH = PropRules(profit_target=0.02, daily_loss=0.03, max_loss=0.06,
                min_trading_days=0)
RISKS = (0.01, 0.015, 0.02, 0.03)
LEGS = (("XAUUSD", "1h"), ("ETHUSDT", "1h"), ("SOLUSDT", "1h"), ("XAUUSD", "4h"))
#: THE WINNING SHAPE from `exitshape.py`: half off at +1R, then trail 3R behind the
#: best close. On gold 1h it took the win rate 20.3% -> 43.0% and the single best
#: day from 42% of net profit to **12%** - the first arm ever measured under the
#: 20% cap. It is still 0 payable withdrawals at a 1% withdrawal policy, which is
#: why the policy is swept here rather than assumed.
ARM = ShapedExit("vwapbreak_pt", partial_r=1.0, trail_r=3.0)
MINS = (0.01, 0.02, 0.05, 0.10, 0.20, 0.30)


def score(daily: pd.Series, tag: str) -> dict:
    best = None
    for risk in RISKS:
        a = run_accounts(daily, risk, ASH)
        if not a["pass_rate"]:
            continue
        exp = a["median_days"] / a["pass_rate"]
        line = {"risk_pct": risk * 100, "pass_pct": round(a["pass_rate"] * 100, 1),
                "blown_pct": round((a["fail_max"] + a["fail_daily"]) * 100, 1),
                "days": round(exp, 1), "band": band(daily, risk, rules=ASH)}
        if best is None or exp < best["days"]:
            best = line
    return {"tag": tag, **(best or {"days": None}),
            **payout_stats(daily.values * 0.02)}


def sweep(pct, floor: float) -> tuple:
    """Withdrawals taken and how many pass the 20% cap, at one withdrawal size."""
    acc, best, wins, payable = 0.0, 0.0, 0, 0
    for step in pct:
        acc += step
        best = max(best, step)
        if acc < floor:
            continue
        wins += 1
        if best / acc <= 0.20:
            payable += 1
        acc, best = 0.0, 0.0
    return payable, wins


def main() -> int:
    span = window([s for v in UNIVERSE.values() for s in v], ["1h", "4h"])
    series, cache = {}, {}
    for sym, tf in LEGS:
        res = run_market(ARM, sym, tf, pipe_kw={"floors": (30,), "topn": (5,)},
                         null_seeds=0, span=span)
        tr = res["_trades"]
        d = pd.Series(tr.r.values,
                      index=pd.DatetimeIndex(tr.exit_ts)).resample("1D").sum()
        series[f"{sym}|{tf}"] = d
        cache[f"{sym}|{tf}"] = {"t0": str(d.index[0].date()),
                                "r": [round(float(x), 6) for x in d.values]}
        print(f"  {sym} {tf}: {res['trades']} trades, win {res['win_pct']}%, "
              f"PF@2x {res['pf_2x']}", flush=True)

    df = pd.DataFrame(series).fillna(0.0)
    rows = []
    print(f"\n{'book':34}{'days':>7}{'band':>12}{'pass%':>7}{'bestday':>9}{'payable':>9}")
    keys = list(df.columns)
    for n in range(1, len(keys) + 1):
        for combo in combinations(keys, n):
            s = score(df[list(combo)].mean(axis=1), " + ".join(combo))
            rows.append({"legs": list(combo), **s})
            b = s.get("band") or {}
            print(f"{s['tag'][:33]:34}{(s['days'] or 0):7.1f}"
                  f"{('%.0f-%.0f' % (b.get('days_lo', 0), b.get('days_hi', 0))):>12}"
                  f"{(s['pass_pct'] or 0):7.1f}"
                  f"{(s['best_day_share_net'] or 0):9.3f}"
                  f"{('%d/%d' % (s['windows_payable'], s['windows'])):>9}", flush=True)

    print(f"\nPAYABLE WITHDRAWALS under a 20% best-day cap, by withdrawal size")
    books = {"gold 1h": ["XAUUSD|1h"], "gold + ETH": ["XAUUSD|1h", "ETHUSDT|1h"],
             "all four": keys}
    print(f"{'minimum withdrawal':22}" + "".join(f"{b:>14}" for b in books))
    for floor in MINS:
        line = f"{floor:>18.0%}    "
        for name, legs in books.items():
            p, w = sweep(df[legs].mean(axis=1).values * 0.02, floor)
            rows.append({"policy_min_pct": floor * 100, "book": name,
                         "payable": p, "windows": w})
            line += f"{('%d/%d' % (p, w)):>14}"
        print(line, flush=True)

    (ROOT / "backtests" / "vwapbreak" / "daily_partial.json").write_text(
        json.dumps(cache, indent=0, default=str))
    dest = ROOT / "backtests" / "vwapbreak" / "payable.json"
    dest.write_text(json.dumps({"arm": "partial 1R", "rows": rows}, indent=1,
                               default=str))
    print(f"\nwrote {dest.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
