"""The traded H-027 rule's blind walk-forward trades, cached for the gate study.

Same call as `strategies/vwapbreak/research/tier1.py`: the wide-stop exit grid,
floor 30 / top 5, the 3-year window aligned across the exits study's universe.
Nothing about the rule is re-chosen here; this only writes the trade list the
COT gates are scored on.

Run: .venv/bin/python strategies/goldfeed/baseline.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from core.run_hypothesis import run_market, window                 # noqa: E402
from strategies.vwapbreak.research.exits import (UNIVERSE, WIDE_SIGMA,  # noqa: E402
                                                 ExitVariant)

OUT = ROOT / "backtests" / "goldfeed" / "baseline_trades.parquet"


def main() -> int:
    span = window([s for v in UNIVERSE.values() for s in v], ["1h", "4h"])
    res = run_market(ExitVariant("wide", stops=WIDE_SIGMA), "XAUUSD", "1h",
                     pipe_kw={"floors": (30,), "topn": (5,)},
                     null_seeds=0, span=span)
    tr = res["_trades"]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    tr.to_parquet(OUT)
    print(f"span {span[0]} -> {span[1]}")
    print(f"{len(tr)} trades  PF {res['pf']}  PF@2x {res['pf_2x']}  columns {list(tr.columns)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
