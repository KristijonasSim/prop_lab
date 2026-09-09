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

from core import noiseband as NB                               # noqa: E402
from core import pine as PINE                                  # noqa: E402
from core import studies as STUDIES                            # noqa: E402
from core.chosen import CHOSEN                                 # noqa: E402
from core.prop_rules import ONE_STEP                           # noqa: E402
from core.scorecard import rank_tiers                          # noqa: E402

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
    # How many cells the RUN has finished, before this filter cuts them down.
    # The page's progress bar reads it, and without this a complete twenty-cell
    # run showing one market read as "2/20 done" - the filter looking like a
    # half-finished run.
    out["cells_done"] = len(h.get("cells", []))
    for k in ("rows", "cells"):
        out[k] = [r for r in h.get(k, []) if r.get("sym") in keep]
    if not out["rows"]:
        return None
    out["filtered_to"] = sorted(keep)
    return out


def _tiers(h: dict) -> dict:
    """Stamp a TIER on every row the page ranks, and rank nothing inside one.

    `core/scorecard.rank_tiers` groups rows whose sampling bands overlap; this
    only writes the group number onto the record so the page can show it. The
    page must not do the grouping itself - the rule about what may be called
    faster than what belongs next to the score, not in a template.

    Two rankings are stamped, because the board answers two questions:
      * `tier`   - over every market x timeframe in the hypothesis, on the
                   headline expected days and its band;
      * `tier60` - over the selection rules of one promoted market, on the "60%
                   in" number and ITS band, which is the column Kris reads
                   against his goal.
    """
    cells = [c for c in h.get("cells", [])]
    for i, tier in enumerate(rank_tiers(cells), start=1):
        for c in tier:
            # a row with no number was never compared with anything, and
            # `rank_tiers` puts each of those in a tier of its own. Stamping
            # that would print a ranking of absences.
            if c.get("days_to_pass") is not None:
                c["tier"] = i
    for row in h.get("rows", []):
        rules = row.get("rules") or []
        for i, tier in enumerate(rank_tiers(rules, band_key="band60",
                                            value_key="days60"), start=1):
            for r in tier:
                if r.get("days60") is not None:
                    r["tier60"] = i
    return h


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
    hyps = [_tiers(x) for x in (_filter(h) for h in found) if x is not None]
    # THE PINE INDICATOR EACH HYPOTHESIS SHIPS, filled in from its own folds.
    # Kris's request, 2026-09-09: a button on every hypothesis that copies a
    # TradingView INDICATOR - not a strategy - so the rule can be eyeballed on a
    # chart. See core/pine.py for why it is deliberately not a strategy.
    for h in hyps:
        h["pine"] = PINE.for_record(h)
        # The research arms that decide what this hypothesis becomes. They lived
        # in JSON files and a log nobody opens; Kris reads the board.
        h["studies"] = STUDIES.for_sid(h.get("sid", ""))
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
        # THE MEASURED NOISE FLOOR, on the page rather than in a markdown file.
        # Every per-cell band is read against this line: a headline sitting
        # inside it has not been shown to differ from a gate that knows nothing.
        "noise_floor": {"days": list(NB.FLOOR_DAYS), "pf_2x": list(NB.FLOOR_PF_2X),
                        "note": NB.FLOOR_NOTE},
        # WHAT KRIS TRADES, at the top of the page. Chosen 2026-09-09 and pinned
        # in core/chosen.py, because the pipeline's own pick optimises profit
        # factor and a prop evaluation does not pay for profit factor.
        "chosen": CHOSEN,
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
