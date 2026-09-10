"""Does a BASKET of 6-7 markets beat the 20% best-day rule - and is it faster?

Kris, 2026-09-10: "i think later we could even do a basket of assets for example
6-7 assets and we could trade all of them this would increase our chances".

TWO QUESTIONS, and they are not the same question.

  1. SPEED. More uncorrelated legs at a smaller size each should raise the pass
     rate and cut expected days. H-012 measured the opposite on 57 mostly-weak
     legs - equal weighting divides R per day by the leg count while drawdown
     falls by much less - so the leg quality is what decides it. The two-market
     book (gold + ETH) already beat both its legs, which is why this is worth
     asking again at 3, 4, 5, 6, 7.

  2. PAYOUT. `bestday.py` found ZERO payable withdrawals in all twenty cells
     under a 20% best-day cap: one day is 42% of gold's net profit and 85% of
     ETH's. A basket attacks that directly and arithmetically - if the legs fire
     on different days, the biggest day is a smaller share of the total. This is
     the only lever measured so far that could make the strategy PAYABLE without
     changing what it trades.

NO WALK-FORWARD IS RE-RUN. The daily R series per cell were cached by
`bestday.py` (`backtests/vwapbreak/daily_traded.json`), each one already the
output of the blind quarterly selection. Combining them is arithmetic on fixed
series - the same argument that exempts the risk ladder from the noise floor.

WHAT IS AND IS NOT HONEST HERE. Ranking the legs by their own out-of-sample
profit factor and then reporting the top-k book is exactly the selection H-012
punished: the ranking is done on the window the book is scored on. Both readings
are printed for every size - `ranked` (best-k by PF@2x) and `blind` (every leg
that beats its null, no ordering) - and the blind one is the number to believe.

Run: .venv/bin/python strategies/vwapbreak/research/basket.py
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

ASH = PropRules(profit_target=0.02, daily_loss=0.03, max_loss=0.06,
                min_trading_days=0)
RISKS = (0.01, 0.015, 0.02, 0.03)
CAP = 0.20
PAYOUT_MIN = 0.01

CACHE = ROOT / "backtests" / "vwapbreak" / "daily_traded.json"
ASSETS = ROOT / "backtests" / "vwapbreak" / "assets.json"


def load() -> tuple[pd.DataFrame, dict]:
    raw = json.loads(CACHE.read_text())
    meta = json.loads(ASSETS.read_text())
    cols = {}
    for key, v in raw.items():
        idx = pd.date_range(v["t0"], periods=len(v["r"]), freq="D")
        cols[key] = pd.Series(v["r"], index=idx)
    return pd.DataFrame(cols).fillna(0.0), meta


def payout_stats(pct: np.ndarray) -> dict:
    """Withdrawals the series affords, and how many pass a 20% best-day cap."""
    acc, best, wins, payable = 0.0, 0.0, 0, 0
    for step in pct:
        acc += step
        best = max(best, step)
        if acc < PAYOUT_MIN:
            continue
        wins += 1
        if best / acc <= CAP:
            payable += 1
        acc, best = 0.0, 0.0
    total = float(pct.sum())
    return {"windows": wins, "windows_payable": payable,
            "best_day_share_net": round(float(pct.max() / total), 3) if total > 0 else None}


def score(daily: pd.Series, tag: str) -> dict:
    """Fastest rung on the ladder, its band, and the payout picture at 2% risk."""
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
    out = {"tag": tag, **(best or {"days": None})}
    out.update(payout_stats(daily.values * 0.02))
    out["r_per_day"] = round(float(daily.mean()), 4)
    out["trade_days_pct"] = round(float((daily != 0).mean()) * 100, 1)
    return out


def main() -> int:
    df, meta = load()
    live = {k: v for k, v in meta.items() if k in df.columns}

    # the leg pool: every cell that beats its own paired null AND makes money at
    # double cost. Nine of twenty. No ordering is applied to form `blind`.
    pool = sorted([k for k, v in live.items()
                   if v["beats_null"] and v["pf_2x"] > 1.0],
                  key=lambda k: -live[k]["pf_2x"])
    print("leg pool, best PF@2x first:")
    for k in pool:
        print(f"  {k:14} PF@2x {live[k]['pf_2x']:.3f}  pass {live[k]['pass_pct']:5.1f}%  "
              f"days {live[k]['days']:5.1f}")

    rows = []
    for n in range(1, len(pool) + 1):
        legs = pool[:n]
        rows.append({"kind": "ranked", "n": n, "legs": legs,
                     **score(df[legs].mean(axis=1), f"top {n} by PF")})
        r = rows[-1]
        print(f"\n  ranked {n:2}  {r['days']:6.1f} days  pass {r['pass_pct']:5.1f}%  "
              f"best day {r['best_day_share_net'] if r['best_day_share_net'] else '-'}  "
              f"payable {r['windows_payable']}/{r['windows']}")

    rows.append({"kind": "blind", "n": len(pool), "legs": pool,
                 **score(df[pool].mean(axis=1), "every leg that beats its null")})

    # AND THE CONTROL: random baskets of the same size drawn from ALL twenty
    # cells, so "a basket helps" is separated from "these legs were picked".
    rng = np.random.default_rng(20260910)
    cols = list(df.columns)
    for n in (3, 5, 7):
        shares, days = [], []
        for _ in range(40):
            pick = list(rng.choice(cols, size=n, replace=False))
            s = score(df[pick].mean(axis=1), f"random {n}")
            if s["best_day_share_net"]:
                shares.append(s["best_day_share_net"])
            if s["days"]:
                days.append(s["days"])
        rows.append({"kind": "random", "n": n, "legs": [],
                     "tag": f"random {n} of 20, 40 draws",
                     "best_day_share_net": round(float(np.median(shares)), 3) if shares else None,
                     "days": round(float(np.median(days)), 1) if days else None,
                     "profitable_draws": len(shares)})
        print(f"\n  random {n}: median best-day share "
              f"{rows[-1]['best_day_share_net']}, median days {rows[-1]['days']}, "
              f"{len(shares)}/40 draws profitable")

    # the best-day share is the payout question, so find the smallest basket that
    # gets under the cap by ANY combination of the pool
    under = []
    for n in range(2, min(len(pool), 7) + 1):
        for combo in combinations(pool, n):
            s = payout_stats(df[list(combo)].mean(axis=1).values * 0.02)
            if s["best_day_share_net"] and s["best_day_share_net"] <= CAP:
                under.append((n, combo, s))
        if under:
            break
    print(f"\nbaskets whose best day is under the {CAP:.0%} cap: {len(under)}")
    for n, combo, s in under[:5]:
        print(f"  {n} legs {list(combo)} -> {s['best_day_share_net']:.1%}, "
              f"payable {s['windows_payable']}/{s['windows']}")

    dest = ROOT / "backtests" / "vwapbreak" / "basket.json"
    dest.write_text(json.dumps(
        {"cap": CAP, "payout_min_pct": PAYOUT_MIN * 100, "pool": pool, "rows": rows,
         "under_cap": [{"n": n, "legs": list(c), **s} for n, c, s in under[:20]]},
        indent=1, default=str))
    print(f"\nwrote {dest.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
