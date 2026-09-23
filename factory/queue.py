"""STEP 1 — THE IDEA QUEUE. Closed with Kris 2026-09-21.

His words: *"i dont want to generate new ideas it must happen automatically ...
it needs to happen automatically on VM or on something"*, and the order he set:

    1. TRADINGVIEW        start here, until it is exhausted
    2. THE BOT INVENTS    when TradingView runs dry, keep going alone
    3. KRIS INJECTS       any time he likes. Optional, never required.

**No human input is needed for the loop to run.** The old step 1 waited for
Kris to have an idea, and that was the bottleneck the whole project ran into.

DEDUPE IS THE WHOLE VALUE. A queue that re-tests the same idea in a new costume
is worse than no queue, because each test costs the same whether or not it was
informative. `Strategy.fingerprint()` is built from WHAT A RULE DOES - side,
conditions, stop, target, hold - and deliberately ignores its name, its author
and its source. Two hundred TradingView scripts that are all a 50/200 moving
average cross collapse to one entry here.

Kris: *"200 scripts that are all RSI are ONE idea, not 200."*

THE QUEUE IS A FILE, NOT MEMORY. `backtests/factory/queue.jsonl` for what is
waiting and `tried.jsonl` for what has been done. The loop is meant to run for
days on a VM and survive a reboot, so nothing important lives in RAM.
"""
from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from factory.sources import catalogue
from factory.spec import Condition, Strategy, Term

ROOT = Path(__file__).resolve().parents[1]
DIR = ROOT / "backtests" / "factory"
QUEUE = DIR / "queue.jsonl"
TRIED = DIR / "tried.jsonl"
SURVIVORS = DIR / "survivors.jsonl"

#: The order sources are drained in, DERIVED from the catalogue so the two
#: cannot disagree. Kris set the first version:
#: TradingView, then the bot inventing its own, then Kris injecting one.
#:
#: `agent` ADDED 2026-09-23, AND ITS POSITION IS THE POINT. A source missing
#: from this tuple sorts LAST (`rank.get(source, len(rank))`), so the first
#: nightly run queued eight model-written ideas and then tested eight
#: enumerated ones instead - the model's ideas sat behind 48 enumerated ones
#: and would not have been reached for days. Found by reading the run record's
#: `by_source`, which is exactly what that field is for.
#:
#: It goes ABOVE `invent` because the enumerator is the FLOOR, not a peer: its
#: job is to keep the queue non-empty when the thinking sources run dry, and a
#: floor that is drained first is not a floor. See `factory/nightly.top_up`.
SOURCE_ORDER = catalogue.ORDER


def _to_json(s: Strategy) -> str:
    return json.dumps(asdict(s), separators=(",", ":"), sort_keys=True)


#: Keys `mark_tried` and `keep` add to a row that are NOT part of a Strategy.
_EXTRA = ("verdict", "note_result", "died_at", "gate", "reached",
          "carried")


def _from_json(line: str) -> Strategy:
    """One row back into a Strategy, ignoring the outcome keys written beside it.

    FIXED 2026-09-23. `mark_tried` writes `verdict` and `note_result` into the
    row and `keep` writes `note_result`; `Strategy(**d)` then raised
    `TypeError: unexpected keyword argument 'note_result'` on the first read of
    `tried.jsonl`. That is worse than it looks: `fingerprints()` reads TRIED, so
    the dedupe silently stopped working the moment anything had been tried, and
    `take()` could not run at all. The queue's one job is not to test the same
    idea twice.
    """
    d = json.loads(line)
    d["entry"] = tuple(
        Condition(Term(**c["left"]), c["op"], Term(**c["right"])) for c in d["entry"])
    for k in _EXTRA:
        d.pop(k, None)
    return Strategy(**d)


def rows(path: Path) -> list[dict]:
    """The raw records, outcome fields and all.

    `_read` returns Strategy objects and drops `verdict`, `died_at` and `gate`,
    which is exactly what the per-source breakdown needs. Both exist.
    """
    if not path.exists():
        return []
    out = []
    for line in path.read_text().splitlines():
        if line.strip():
            try:
                out.append(json.loads(line))
            except ValueError:
                continue                  # a torn last line is not a crash
    return out


def _read(path: Path) -> list[Strategy]:
    if not path.exists():
        return []
    return [_from_json(l) for l in path.read_text().splitlines() if l.strip()]


def fingerprints() -> set[str]:
    """Everything already queued or already tested. Nothing here is offered twice."""
    return {s.fingerprint() for s in _read(QUEUE)} | {s.fingerprint() for s in _read(TRIED)}


def add(strategies, *, quiet: bool = False) -> dict:
    """Queue what is new. Returns a count of what happened, by source.

    Deduping happens against the queue AND the tried log, so an idea that was
    tested and killed three weeks ago is not silently offered again.
    """
    DIR.mkdir(parents=True, exist_ok=True)
    seen = fingerprints()
    added, dup = [], 0
    for s in strategies:
        fp = s.fingerprint()
        if fp in seen:
            dup += 1
            continue
        seen.add(fp)
        added.append(s)
    if added:
        with QUEUE.open("a") as fh:
            for s in added:
                fh.write(_to_json(s) + "\n")
    out = {"added": len(added), "duplicates": dup, "queued": len(_read(QUEUE))}
    if not quiet:
        print(f"queued {out['added']}, skipped {out['duplicates']} duplicates, "
              f"{out['queued']} waiting")
    return out


def take() -> Strategy | None:
    """The next idea, in the order Kris set. Removes it from the queue.

    Returns None when the queue is empty, which is the honest signal that the
    current source is exhausted and the next one should be asked to top it up.
    """
    q = _read(QUEUE)
    if not q:
        return None
    rank = {s: i for i, s in enumerate(SOURCE_ORDER)}
    q.sort(key=lambda s: rank.get(s.source, len(rank)))
    nxt, rest = q[0], q[1:]
    QUEUE.write_text("".join(_to_json(s) + "\n" for s in rest))
    return nxt


def mark_tried(s: Strategy, verdict: str, note: str = "",
               step: int = 0, gate: str = "") -> None:
    """Record that it has been through the pipeline, so it is never re-offered.

    `step` AND `gate` ADDED 2026-09-23. Kris: *"its not really possible to see
    how many strategies were found in tradingview, how many tested, how many
    passed / failed."* The row already carried the source and the verdict, so
    "how many did TradingView give us" was answerable and "where did they die"
    was not - the note was free text assembled differently at each call site.
    Recording the step and the gate as fields is what lets the page break a
    source down without parsing prose.
    """
    DIR.mkdir(parents=True, exist_ok=True)
    d = asdict(s)
    d["verdict"], d["note_result"] = verdict, note
    d["died_at"], d["gate"] = int(step), gate
    with TRIED.open("a") as fh:
        fh.write(json.dumps(d, separators=(",", ":"), sort_keys=True) + "\n")


def keep(s: Strategy, note: str = "", reached: int = 3) -> None:
    """A survivor. It has passed step 3 (possibly after a step 4 repair) and is
    waiting for step 5.

    IT DOES NOT GO BACK ON THE QUEUE. Re-queueing a repaired idea would send it
    through step 3's 24-cell search a second time, which is the search
    multiplication step 4 exists not to do. Its cell is already decided.
    """
    DIR.mkdir(parents=True, exist_ok=True)
    d = asdict(s)
    d["note_result"], d["reached"] = note, int(reached)
    with SURVIVORS.open("a") as fh:
        fh.write(json.dumps(d, separators=(",", ":"), sort_keys=True) + "\n")


def status() -> dict:
    q, t = _read(QUEUE), _read(TRIED)
    by = {}
    for s in q:
        by[s.source] = by.get(s.source, 0) + 1
    return {"waiting": len(q), "tried": len(t), "waiting_by_source": by}


if __name__ == "__main__":
    print(json.dumps(status(), indent=2))
