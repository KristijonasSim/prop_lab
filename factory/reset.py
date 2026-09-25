"""CLEAR THE BOARD — archive what has been run, start the next source clean.

Kris, 2026-09-23: *"clean all UI from data, we will start with tradingview."*

IT ARCHIVES, IT DOES NOT DELETE. `CLAUDE.md`: *"Log every variation tested,
pass or fail. The failures are the denominator."* And `core/searchcost.py`
prices the search - 228 trials are already charged against a budget of 13, and
a trial does not become uncharged because the page stopped showing it. Every
file is moved to `backtests/factory/archive/<timestamp>/` and the path is
printed.

THE DEDUPE IS THE ONE THING THAT MAY NOT BE LOST. `tried.jsonl` is what stops
an idea being tested twice, so by default its fingerprints are CARRIED FORWARD
into the fresh file as bare records - no verdicts, no step, nothing the page
will count - while the full rows go to the archive. `--forget` drops them, and
says what that costs.

    python -m factory.reset                # clear the board, keep the dedupe
    python -m factory.reset --forget       # clear everything, allow re-tests
    python -m factory.reset --dry-run      # say what it would do
"""
from __future__ import annotations

import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from factory import live, queue                                      # noqa: E402

#: Everything the dashboard reads. `live.json` is a heartbeat, not a record,
#: so it is removed rather than archived.
RECORDS = ("queue.jsonl", "tried.jsonl", "survivors.jsonl", "runs.jsonl")
ARCHIVE = queue.DIR / "archive"

#: The fields kept when carrying a fingerprint forward. Just enough for
#: `queue.fingerprints()` to recognise the idea, and nothing the page counts.
_KEEP = ("name", "side", "entry", "stop_atr", "target_atr", "max_hold",
         "source", "note")
#: Marks a row that is here only for dedupe. The page ignores these.
CARRIED = "carried"


def plan() -> dict:
    """What is on the board right now, without touching anything."""
    return {f: len(queue.rows(queue.DIR / f)) for f in RECORDS
            if (queue.DIR / f).exists()}


def reset(*, forget: bool = False, dry_run: bool = False) -> dict:
    """Move the records aside. Returns what happened."""
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    dest = ARCHIVE / stamp
    before = plan()
    if dry_run:
        return {"dry_run": True, "would_archive": before, "to": str(dest),
                "dedupe_kept": 0 if forget else before.get("tried.jsonl", 0)}

    dest.mkdir(parents=True, exist_ok=True)
    carried = []
    for name in RECORDS:
        src = queue.DIR / name
        if not src.exists():
            continue
        if name == "tried.jsonl" and not forget:
            # FLAGGED, and the flag is the whole point. A carried row exists so
            # the idea is not tested twice; it is NOT a result of this board.
            # Without the flag `dashboard.per_source` counted 158 archived
            # ideas as "tested" on a board that was just cleared, which is the
            # opposite of what clearing it means.
            carried = [{**{k: r[k] for k in _KEEP if k in r}, "carried": 1}
                       for r in queue.rows(src)]
        shutil.move(str(src), str(dest / name))

    if carried:
        with (queue.DIR / "tried.jsonl").open("w") as fh:
            for r in carried:
                fh.write(json.dumps(r, separators=(",", ":"), sort_keys=True) + "\n")

    # The heartbeat is removed, not rewritten. A beat - even an idle one -
    # carries an `updated` timestamp, and the page read that as a factory that
    # had been running for two seconds on a board with nothing on it.
    beat = queue.DIR / "live.json"
    if beat.exists():
        beat.unlink()
    _ = live

    return {"archived_to": str(dest), "archived": before,
            "dedupe_kept": len(carried),
            "note": ("fingerprints dropped - ideas may be re-tested and "
                     "re-charged to the search budget" if forget else
                     "fingerprints carried forward, so nothing is re-tested")}


def _main(argv=None) -> int:
    import argparse

    ap = argparse.ArgumentParser(description="Clear the board for a new source.")
    ap.add_argument("--forget", action="store_true",
                    help="drop the dedupe fingerprints too")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    print(json.dumps(reset(forget=a.forget, dry_run=a.dry_run), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
