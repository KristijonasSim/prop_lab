"""What does a 14-day book actually need? The arithmetic, before any search.

Kris's goal is a funded account in ~7 days, 14 worst case, against H-009's 48.7.
Searching for "something better" without knowing the shape of the answer wastes
the search. This inverts the project's own simulator to say what has to be true.

The binding constraint in `riskladder.pick` is that peak drawdown must fit the
8% cap, so risk per trade is pinned at `risk = 0.08 / |maxDD_R|`. At that risk,
clearing phase 1 (+8%) needs exactly `|maxDD_R|` in R, and phase 2 (+5%) needs
another 0.625x of it. So:

    days_to_funded  ~=  1.625 * |maxDD_R| / R_per_day  =  1.625 / K

    where K = R_per_day / |maxDD_R|

**K is the only number that matters.** Not profit factor, not Sharpe, not win
rate - those move K but none of them is it. A book with PF 3.0 and K of 0.01 is
slower than a book with PF 1.3 and K of 0.05.

Output: backtests/xpos/stage0_arithmetic.csv
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

BT = ROOT / "backtests"
OUT = BT / "xpos"


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    rows = []
    print("WHERE THE EXISTING BOOKS SIT\n")
    print(f"  {'id':7s} {'name':30s} {'R/day':>8s} {'maxDD_R':>9s} "
          f"{'K':>8s} {'expected d':>11s} {'trades/day':>11s}")
    for p in sorted(BT.glob("*/board.json")):
        b = json.loads(p.read_text())
        f = b["fields"]
        rpd, dd = f.get("r_per_day"), f.get("max_dd_r")
        if not rpd or not dd:
            continue
        k = rpd / abs(dd)
        print(f"  {b['hid']:7s} {b['name'][:30]:30s} {rpd:>8.4f} {dd:>9.2f} "
              f"{k:>8.4f} {str(b['pick'].get('expected_days')):>11s} "
              f"{f['trades_per_day']:>11.3f}")
        rows.append({"hid": b["hid"], "name": b["name"], "r_per_day": rpd,
                     "max_dd_r": dd, "K": round(k, 5),
                     "expected_days": b["pick"].get("expected_days"),
                     "trades_per_day": f["trades_per_day"],
                     "avg_r": f["avg_r"], "pf": f["pf"]})

    print("\n\nWHAT THE GOAL REQUIRES\n")
    print(f"  {'target days':>12s} {'K needed':>10s} {'vs H-009':>10s}")
    for d in (7, 14, 21, 30, 48.7):
        k = 1.625 / d
        rows.append({"hid": "TARGET", "name": f"{d} days", "K": round(k, 5),
                     "expected_days": d})
        print(f"  {d:>12} {k:>10.4f}")

    h009 = [r for r in rows if r["hid"] == "H-009"]
    if h009:
        k9 = h009[0]["K"]
        print(f"\n  H-009's K is {k9:.4f}. "
              f"7 days needs {1.625/7/k9:.1f}x it; 14 days needs {1.625/14/k9:.1f}x.")

        print("\n\nHOW K CAN BE REACHED\n")
        print("  K = R_per_day / |maxDD_R|, and R_per_day = avg_R x trades/day.")
        print("  For a book whose per-trade R is roughly independent, drawdown")
        print("  grows like sqrt(total trades), so over a FIXED test window")
        print("  K grows like sqrt(trades per day). That is the hard part:\n")
        n9 = h009[0]["trades_per_day"]
        print(f"  {'multiple of K':>14s} {'=> trades/day needed':>22s}")
        for mult in (2, 3.5, 7):
            print(f"  {mult:>13.1f}x {n9 * mult**2:>22.1f}   "
                  f"(H-009 runs {n9:.2f})")
        print("\n  So frequency alone cannot do it: 14 days would need roughly")
        print(f"  {n9 * (1.625/14/k9)**2:.0f} trades a day at H-009's per-trade edge.")
        print("  The other route is a SMALLER drawdown per unit of return -")
        print("  which is what market-neutrality buys, and what no book here has.")

    pd.DataFrame(rows).to_csv(OUT / "stage0_arithmetic.csv", index=False)
    print(f"\nwrote {OUT / 'stage0_arithmetic.csv'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
