"""Render the hypothesis board. One page, one tab per hypothesis, one table each.

Reads every `backtests/<sid>/hypothesis.json` written by `core/run_hypothesis.py`
and writes `backtests/board.html`. Deliberately thin: the numbers are computed
upstream and this only lays them out, so the page and the board can never
disagree about what a strategy scored.

Run: .venv/bin/python core/build_board.py
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.prop_rules import ONE_STEP                           # noqa: E402

BT = ROOT / "backtests"


def _clean(o):
    """NaN and Infinity out, null in.

    `json.dumps` emits bare `NaN`/`Infinity`, which are valid JavaScript literals
    but not valid JSON - so the page survives them and anything that later reads
    `board_data.json` with a strict parser does not. A metric that could not be
    computed is absent, and `null` is how the page already renders absent.
    """
    if isinstance(o, dict):
        return {k: _clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_clean(v) for v in o]
    if isinstance(o, float) and not math.isfinite(o):
        return None
    return o


def main() -> int:
    files = sorted(BT.glob("*/hypothesis.json"))
    hyps = [json.loads(p.read_text()) for p in files]
    hyps.sort(key=lambda h: h.get("hid", ""))

    r = ONE_STEP[0]
    data = {
        "hypotheses": hyps,
        # so an open tab can always be told apart from a fresh one
        "built": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S"),
        "firm": {"name": "Thunderbolt (1 step)", "target": r.profit_target,
                 "daily": r.daily_loss, "maxloss": r.max_loss},
    }
    tpl = (ROOT / "core" / "board_template.html").read_text()
    out = BT / "board.html"
    payload = json.dumps(_clean(data), default=str)
    out.write_text(tpl.replace("__BOARD_DATA__", payload))
    (BT / "board_data.json").write_text(json.dumps(_clean(data), indent=1,
                                                  default=str))

    print(f"wrote {out.relative_to(ROOT)}  ({len(hyps)} hypothesis page"
          f"{'' if len(hyps) == 1 else 's'})")
    for h in hyps:
        for row in h.get("rows", []):
            print(f"  {h['hid']}  {row['asset_class']:6s} "
                  f"{(row.get('sym') or '—'):8s} {(row.get('tf') or ''):3s}  "
                  f"days {row.get('days_to_pass')}  PF {row.get('pf')}  "
                  f"CAGR {row.get('cagr_pct')}%")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
