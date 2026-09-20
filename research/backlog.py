"""A queue of model-written candidates, so the VM can run them without a model.

THE GAP THIS CLOSES. The loop runs on the VM so it survives the desktop being
switched off. But the model-driven proposer shells out to the `claude` CLI, and
that is not installed there — so the VM fell back to the library proposer, which
is mechanical enumeration and the weakest part of the search space. Kris picked
"C target with B machinery" and the B half was only running when he was at his
desk, which is the same problem the VM move was meant to solve.

THE FIX IS A QUEUE, NOT A CLI ON THE VM. Installing and authenticating Claude on
a 952 MB box, to have it call out per cycle, buys latency and a second place for
credentials to live. Instead the desktop writes candidates ahead of time and the
VM eats them:

    desktop    python -m research.backlog --fill 60      (model writes 60)
               python -m research.sync_vm                (ships them)
    VM         consumes one per screen, falls back to the library when empty

So a single fill at the desk keeps the VM proposing like the model for days,
and when the queue drains the loop degrades to the library rather than stopping.

WHY A FILE AND NOT A DATABASE. Two machines, one direction, append-and-consume.
A JSONL file rsyncs cleanly, merges by line, and can be read with `cat` when
something looks wrong. Each line is a validated candidate — validation happens
at FILL time, on the desktop, so the VM never has to trust the file.

DUPLICATES ARE CHECKED TWICE, DELIBERATELY. Once when filling (against the
ledger as it stands) and again when popping (against the ledger as it is by
then). The gap between the two can be days, and the VM will have screened
hundreds of candidates in between.
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from research.propose import (                                  # noqa: E402
    Candidate, ProposalError, propose_llm, tried_keys, validate)

QUEUE = ROOT / "backtests" / "proposals.jsonl"


def read() -> list[Candidate]:
    """Every queued candidate that still validates. A line that no longer does
    - because the registry changed under it - is dropped, not crashed on."""
    if not QUEUE.exists():
        return []
    out: list[Candidate] = []
    for line in QUEUE.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(validate(json.loads(line)))
        except (ValueError, ProposalError):
            continue
    return out


def write(cands: list[Candidate]) -> None:
    QUEUE.parent.mkdir(parents=True, exist_ok=True)
    tmp = QUEUE.with_suffix(".tmp")
    tmp.write_text("".join(json.dumps(asdict(c), sort_keys=True) + "\n"
                           for c in cands))
    tmp.replace(QUEUE)


def depth() -> int:
    return len(read())


def pop(n: int = 1) -> list[Candidate]:
    """Take up to `n` off the front, skipping anything since screened.

    Re-checked against the ledger here as well as at fill time: a queue filled
    on Monday and drained on Thursday has had hundreds of candidates screened
    underneath it.
    """
    done = tried_keys()
    queued = read()
    take, keep = [], []
    for c in queued:
        if len(take) < n and c.key not in done and c.key not in {t.key for t in take}:
            take.append(c)
        elif c.key not in done:
            keep.append(c)
    if take:
        write(keep)
    return take


def fill(n: int = 40, batch: int = 8) -> tuple[int, int]:
    """Ask the model for `n` candidates, in batches, and queue the new ones.

    Batched because one prompt asking for forty proposals returns a list where
    the last twenty are near-duplicates of the first twenty - the model runs out
    of distinct mechanisms long before it runs out of output. Smaller batches,
    each seeing an updated "already queued" set, stay varied.
    """
    have = {c.key for c in read()}
    done = tried_keys()
    added: list[Candidate] = []
    asked = 0

    while len(added) < n:
        want = min(batch, n - len(added))
        asked += want
        try:
            got = propose_llm(want)
        except ProposalError as exc:
            print(f"  model call failed: {exc}", file=sys.stderr)
            break
        if not got:
            print("  model returned nothing usable, stopping", file=sys.stderr)
            break
        fresh = [c for c in got if c.key not in have and c.key not in done]
        if not fresh:
            print("  batch was all duplicates, stopping", file=sys.stderr)
            break
        for c in fresh:
            have.add(c.key)
        added.extend(fresh)
        print(f"  +{len(fresh)} (queue now {len(have)})")

    if added:
        write(read() + added)
    return len(added), asked


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--fill", type=int, metavar="N",
                    help="ask the model for N candidates and queue them")
    ap.add_argument("--show", action="store_true", help="list the queue")
    ap.add_argument("--clear", action="store_true")
    a = ap.parse_args(argv)

    if a.clear:
        write([])
        print("queue cleared")
        return 0
    if a.fill:
        n, asked = fill(a.fill)
        print(f"queued {n} new candidates ({asked} asked for); "
              f"depth now {depth()}")
        return 0

    q = read()
    print(f"{len(q)} queued in {QUEUE.relative_to(ROOT)}")
    if a.show:
        for c in q:
            print(f"  {c.name:38}{c.origin:6}dir {c.direction:+d}")
            print(f"      {c.mechanism[:100]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
