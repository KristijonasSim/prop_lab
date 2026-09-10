"""How much of each cell's edge is ONE quarter?

The cross-market investigation kept running into the same shape: a positive total
carried by a handful of days. `bestday.py` measured that at the DAY level, because
that is what a consistency rule tests. This measures it at the QUARTER level,
because that is what decides whether an edge is a strategy or a period.

The test is deliberately blunt and needs no statistics: sum the walk-forward daily
R by calendar quarter, then delete the single best quarter and look at what is
left. An edge that survives its best quarter is a strategy. An edge that does not
is a description of one thing that happened once.

The series are the cached blind walk-forward output (`daily_traded.json`), so
nothing is re-run and nothing is re-selected.

Run: .venv/bin/python strategies/vwapbreak/research/stability.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

CACHE = ROOT / "backtests" / "vwapbreak" / "daily_traded.json"
#: the same four legs traded with the reshaped exit (`payable.py`), when it exists.
#: Run second, so the question "does the fix also fix the concentration" is answered
#: in the same table rather than in a chat message.
PARTIAL = ROOT / "backtests" / "vwapbreak" / "daily_partial.json"
ASSETS = ROOT / "backtests" / "vwapbreak" / "assets.json"


def quarters(v: dict) -> pd.Series:
    s = pd.Series(v["r"], index=pd.date_range(v["t0"], periods=len(v["r"]), freq="D"))
    return s.groupby(s.index.to_period("Q")).sum()


def main() -> int:
    raw = json.loads(CACHE.read_text())
    meta = json.loads(ASSETS.read_text())
    rows = []
    print(f"{'cell':14}{'total R':>9}{'quarters':>10}{'best qtr':>10}"
          f"{'its share':>11}{'without it':>12}{'+ qtrs left':>13}")
    for key, v in raw.items():
        q = quarters(v)
        total, best = float(q.sum()), float(q.max())
        rest = q.drop(q.idxmax())
        row = {"cell": key, "total_r": round(total, 1),
               "quarters": int(len(q)),
               "pos_quarters": int((q > 0).sum()),
               "best_quarter": str(q.idxmax()),
               "best_quarter_r": round(best, 1),
               "best_share": round(best / total, 3) if total > 0 else None,
               "without_best_r": round(float(rest.sum()), 1),
               "pos_without_best": int((rest > 0).sum()),
               "pf_2x": meta.get(key, {}).get("pf_2x"),
               "by_quarter": {str(p): round(float(x), 1) for p, x in q.items()}}
        rows.append(row)
        print(f"{key:14}{total:9.1f}{row['pos_quarters']:>4}/{row['quarters']:<5}"
              f"{best:10.1f}{(row['best_share'] or 0) * 100:10.0f}%"
              f"{row['without_best_r']:12.1f}"
              f"{row['pos_without_best']:>6}/{row['quarters'] - 1:<6}")

    part = []
    if PARTIAL.exists():
        print("\nTHE SAME LEGS WITH THE RESHAPED EXIT (half off at 1R, trail 3R)")
        print(f"{'cell':14}{'total R':>9}{'best qtr':>10}{'its share':>11}"
              f"{'without it':>12}{'+ qtrs left':>13}")
        for key, v in json.loads(PARTIAL.read_text()).items():
            q = quarters(v)
            total, best = float(q.sum()), float(q.max())
            rest = q.drop(q.idxmax())
            part.append({"cell": key, "total_r": round(total, 1),
                         "best_quarter_r": round(best, 1),
                         "best_share": round(best / total, 3) if total > 0 else None,
                         "without_best_r": round(float(rest.sum()), 1),
                         "pos_without_best": int((rest > 0).sum()),
                         "quarters": int(len(q))})
            print(f"{key:14}{total:9.1f}{best:10.1f}"
                  f"{(part[-1]['best_share'] or 0) * 100:10.0f}%"
                  f"{part[-1]['without_best_r']:12.1f}"
                  f"{part[-1]['pos_without_best']:>6}/{len(rest):<6}")

    dest = ROOT / "backtests" / "vwapbreak" / "stability.json"
    dest.write_text(json.dumps({"rows": rows, "reshaped": part}, indent=1,
                               default=str))
    print(f"\nwrote {dest.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
