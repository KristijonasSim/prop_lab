"""Render the hypothesis board. One page, one tab per hypothesis, one table each.

Reads every `backtests/<sid>/hypothesis.json` written by `core/run_hypothesis.py`
and writes `backtests/board.html`. Deliberately thin: the numbers are computed
upstream and this only lays them out, so the page and the board can never
disagree about what a strategy scored.

WHAT IS ON THE PAGE IS NOW A CHOICE — see `SHOW` below. Nothing is deleted from
disk by this file; it only decides what renders.

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

#: WHAT THE BOARD SHOWS. `None` means everything on disk, which is what this file
#: did until 2026-09-08.
#:
#: **Kris's instruction, 2026-09-08 evening: show H-027 gold and nothing else.**
#: He wants one thing on the page to work on rather than four hypotheses across
#: ten markets. Read it as focus, not as a verdict on the rest.
#:
#: This is a RENDER filter and nothing more. Every `backtests/*/hypothesis.json`
#: stays on disk, every row stays in `STRATEGY_LOG.md` and `RESEARCH_LOG.md`, and
#: setting this back to `None` brings the whole board back with no re-run. That
#: matters because of the standing rule in `README.md` §2 — a rejected hypothesis
#: that is invisible stops being part of the denominator, and this project has
#: re-proposed dead ideas before.
#:
#: Format: `{sid: {symbols to keep}}`. A sid that is absent does not render at
#: all. An empty set keeps every symbol in that sid.
SHOW: dict[str, set[str]] | None = {"vwapbreak": {"XAUUSD"}}


def _filter(h: dict) -> dict | None:
    """Cut a hypothesis record down to what `SHOW` allows, or drop it entirely.

    Filters `rows` (the promoted per-class picks) and `cells` (every market x
    timeframe searched) alike, so the evidence on the page always belongs to the
    markets on the page. Returns None when nothing survives.
    """
    if SHOW is None:
        return h
    keep = SHOW.get(h.get("sid"))
    if keep is None:
        return None
    if not keep:
        return h
    out = dict(h)
    for k in ("rows", "cells"):
        out[k] = [r for r in h.get(k, []) if r.get("sym") in keep]
    if not out["rows"]:
        return None
    out["filtered_to"] = sorted(keep)
    return out


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
    found = [json.loads(p.read_text()) for p in files]
    hyps = [x for x in (_filter(h) for h in found) if x is not None]
    hyps.sort(key=lambda h: h.get("hid", ""))
    if SHOW is not None:
        hidden = len(found) - len(hyps)
        print(f"  SHOW filter active: {hidden} of {len(found)} records hidden "
              f"from the page (all still on disk)")

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
