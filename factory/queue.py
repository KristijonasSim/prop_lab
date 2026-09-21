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

from factory.spec import Condition, Strategy, Term

ROOT = Path(__file__).resolve().parents[1]
DIR = ROOT / "backtests" / "factory"
QUEUE = DIR / "queue.jsonl"
TRIED = DIR / "tried.jsonl"

#: The order sources are drained in. Kris set this.
SOURCE_ORDER = ("tradingview", "invent", "kris")


def _to_json(s: Strategy) -> str:
    return json.dumps(asdict(s), separators=(",", ":"), sort_keys=True)


def _from_json(line: str) -> Strategy:
    d = json.loads(line)
    d["entry"] = tuple(
        Condition(Term(**c["left"]), c["op"], Term(**c["right"])) for c in d["entry"])
    return Strategy(**d)


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


def mark_tried(s: Strategy, verdict: str, note: str = "") -> None:
    """Record that it has been through the pipeline, so it is never re-offered."""
    DIR.mkdir(parents=True, exist_ok=True)
    d = asdict(s)
    d["verdict"], d["note_result"] = verdict, note
    with TRIED.open("a") as fh:
        fh.write(json.dumps(d, separators=(",", ":"), sort_keys=True) + "\n")


def status() -> dict:
    q, t = _read(QUEUE), _read(TRIED)
    by = {}
    for s in q:
        by[s.source] = by.get(s.source, 0) + 1
    return {"waiting": len(q), "tried": len(t), "waiting_by_source": by}


if __name__ == "__main__":
    print(json.dumps(status(), indent=2))
