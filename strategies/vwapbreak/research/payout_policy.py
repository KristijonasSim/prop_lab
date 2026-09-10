"""How big does a withdrawal have to be before a 20% best-day rule allows it?

`bestday.py` asked whether the strategy is ever payout eligible under a 20%
best-day cap and got ZERO payable withdrawals in twenty of twenty cells. That was
measured at ONE withdrawal policy: take the money as soon as it is worth 1% of the
account. The policy is not the firm's rule - it is our choice - so it is a lever,
and it was never swept.

THE ARITHMETIC THAT MAKES IT A LEVER. The rule tests one day against the whole
withdrawal. Withdraw early and the withdrawal is often ONE day, which is 100% of
itself and always fails. Wait, and the same big day is divided by a larger total.
So the question is not "does it pass" but "how long do you have to leave the
money in before it passes" - and whether the account survives that long, since
profit left in the account is still exposed to the drawdown rules.

WHAT IS SWEPT: the minimum withdrawal, 1% to 30% of the account, against basket
size (1, 2, 3 and every leg that beats its null). Both are ours to choose; the
20% cap is not.

Nothing is re-run: the daily series per cell are the cached walk-forward output
(`daily_traded.json`), and combining them is arithmetic on fixed series.

Run: .venv/bin/python strategies/vwapbreak/research/payout_policy.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

CAP = 0.20
RISK = 0.02
MINS = (0.01, 0.02, 0.03, 0.05, 0.08, 0.10, 0.15, 0.20, 0.30)

CACHE = ROOT / "backtests" / "vwapbreak" / "daily_traded.json"
ASSETS = ROOT / "backtests" / "vwapbreak" / "assets.json"


def series() -> tuple[pd.DataFrame, list[str]]:
    raw = json.loads(CACHE.read_text())
    meta = json.loads(ASSETS.read_text())
    cols = {k: pd.Series(v["r"], index=pd.date_range(v["t0"], periods=len(v["r"]),
                                                     freq="D"))
            for k, v in raw.items()}
    df = pd.DataFrame(cols).fillna(0.0)
    pool = sorted([k for k, v in meta.items()
                   if k in df.columns and v["beats_null"] and v["pf_2x"] > 1.0],
                  key=lambda k: -meta[k]["pf_2x"])
    return df, pool


def walk(pct: np.ndarray, floor: float) -> dict:
    """Withdraw whenever profit since the last withdrawal reaches `floor`."""
    acc, best, wins, payable, waits, since = 0.0, 0.0, 0, 0, [], 0
    for step in pct:
        acc += step
        since += 1
        best = max(best, step)
        if acc < floor:
            continue
        wins += 1
        if best / acc <= CAP:
            payable += 1
            waits.append(since)
        acc, best, since = 0.0, 0.0, 0
    return {"windows": wins, "payable": payable,
            "median_wait_days": int(np.median(waits)) if waits else None}


def main() -> int:
    df, pool = series()
    books = {"gold 1h alone": pool[:1], "gold + ETH": pool[:2],
             "top 3": pool[:3], f"all {len(pool)} legs": pool}
    print(f"cap {CAP:.0%}, risk {RISK:.0%}. payable withdrawals / withdrawals taken\n")
    print(f"{'minimum withdrawal':22}" + "".join(f"{b:>16}" for b in books))
    rows = []
    for floor in MINS:
        line = f"{floor:>18.0%}    "
        for name, legs in books.items():
            pct = df[legs].mean(axis=1).values * RISK
            w = walk(pct, floor)
            rows.append({"min_pct": floor * 100, "book": name, "legs": legs, **w})
            line += f"{('%d/%d' % (w['payable'], w['windows'])):>16}"
        print(line, flush=True)

    print("\nmedian days between PAYABLE withdrawals (blank = never payable)")
    print(f"{'minimum withdrawal':22}" + "".join(f"{b:>16}" for b in books))
    for floor in MINS:
        line = f"{floor:>18.0%}    "
        for name in books:
            r = next(x for x in rows if x["min_pct"] == floor * 100 and x["book"] == name)
            line += f"{(str(r['median_wait_days']) if r['median_wait_days'] else '-'):>16}"
        print(line)

    dest = ROOT / "backtests" / "vwapbreak" / "payout_policy.json"
    dest.write_text(json.dumps({"cap": CAP, "risk_pct": RISK * 100, "rows": rows},
                               indent=1, default=str))
    print(f"\nwrote {dest.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
