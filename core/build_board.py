"""Render the hypothesis board. One page, one tab per hypothesis, one table each.

Reads every `backtests/<sid>/hypothesis.json` written by `core/run_hypothesis.py`
and writes `backtests/board.html`. Deliberately thin: the numbers are computed
upstream and this only lays them out, so the page and the board can never
disagree about what a strategy scored.

Run: .venv/bin/python core/build_board.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.prop_rules import ONE_STEP                           # noqa: E402

BT = ROOT / "backtests"


def main() -> int:
    files = sorted(BT.glob("*/hypothesis.json"))
    hyps = [json.loads(p.read_text()) for p in files]
    hyps.sort(key=lambda h: h.get("hid", ""))

    r = ONE_STEP[0]
    data = {
        "hypotheses": hyps,
        "firm": {"name": "Thunderbolt (1 step)", "target": r.profit_target,
                 "daily": r.daily_loss, "maxloss": r.max_loss},
    }
    tpl = (ROOT / "core" / "board_template.html").read_text()
    out = BT / "board.html"
    out.write_text(tpl.replace("/*__DATA__*/", json.dumps(data, default=str)))
    (BT / "board_data.json").write_text(json.dumps(data, indent=1, default=str))

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
