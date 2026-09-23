"""THE HEARTBEAT. What the factory is doing RIGHT NOW, for the dashboard.

Kris, 2026-09-23: *"i would love to see live what is happening, for example 1st
step gathering info from tradingview, AI agent working, then 2nd step, then 3rd
how many live, 4th, 5th etc... i want to launch that page and understand
everything what is going on there."*

A run record (`nightly.runs.jsonl`) is written when a pass FINISHES, which is
nineteen minutes after it starts. For most of that time a dashboard reading
only run records has nothing to say, and a factory floor with nothing moving on
it looks broken rather than busy. This file is the difference: one small JSON
written as the pass moves, so the page can show the line running.

WHY A FILE AND NOT A SOCKET. The pass runs on the VM, under systemd, with no
network path back to a desktop that may be switched off. A file is rsynced by
`deploy_vm.sh --pull` like everything else, survives a restart, and costs
nothing to write. The dashboard polls it.

UPTIME IS "WITHOUT INTERRUPTION", NOT "SINCE FIRST EVER RUN". Kris asked for
the long unbroken stretch. `started` is carried forward while the beats keep
coming and is RESET when the gap between two beats exceeds `STALE_AFTER` -
because a factory that was down for a day and came back has not been running
for a week, and a counter that says it has is worse than no counter.
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / "backtests" / "factory" / "live.json"

#: A gap longer than this means the run stopped, so the uptime clock restarts.
#: Generous, because one pass of 20 ideas is ~19 minutes on the desktop and
#: about an hour on the VM, and a step can be quiet for a while inside that.
STALE_AFTER = 3600.0

#: The line, in order. The dashboard draws one station per entry and this is
#: the single place the order and the names live.
STEPS = (
    (1, "ideas", "TradingView, the model, the enumerator"),
    (2, "build", "into code that cannot read a future bar"),
    (3, "quick check", "four questions about trades, 24 cells"),
    (4, "repair", "six fixed tweaks on a near-miss"),
    (5, "luck check", "the same batch on scrambled markets"),
    (6, "re-check", "years the idea was not selected on"),
    (7, "evaluation", "pass %, days, accounts consumed"),
)


@dataclass
class Beat:
    """One snapshot of the floor."""
    step: int = 0
    label: str = "idle"
    detail: str = ""
    idea: str = ""
    cell: str = ""
    done: int = 0
    total: int = 0
    started: float = 0.0          # this unbroken stretch began
    updated: float = 0.0
    counts: dict = field(default_factory=dict)   # per-step tallies this pass

    def to_dict(self) -> dict:
        return {"step": self.step, "label": self.label, "detail": self.detail,
                "idea": self.idea, "cell": self.cell, "done": self.done,
                "total": self.total, "started": self.started,
                "updated": self.updated, "counts": self.counts}


def read(path: Path | None = None) -> Beat:
    p = path or STATE
    if not p.exists():
        return Beat()
    try:
        d = json.loads(p.read_text())
    except (ValueError, OSError):
        return Beat()
    b = Beat()
    for k, v in d.items():
        if hasattr(b, k):
            setattr(b, k, v)
    return b


def beat(step: int = 0, label: str = "", *, detail: str = "", idea: str = "",
         cell: str = "", done: int = 0, total: int = 0,
         counts: dict | None = None, path: Path | None = None) -> Beat:
    """Write where the pass is. Carries the uptime clock forward itself.

    ATOMIC, because the dashboard reads this file on a timer and a half-written
    JSON read as truncated is a dashboard that blinks 'idle' at random.
    """
    p = path or STATE
    now = time.time()
    prev = read(p)
    started = prev.started
    if not started or (prev.updated and now - prev.updated > STALE_AFTER):
        started = now
    b = Beat(step=step, label=label or "idle", detail=detail, idea=idea,
             cell=cell, done=done, total=total, started=started, updated=now,
             counts={**prev.counts, **(counts or {})} if counts is not None
                    else prev.counts)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(b.to_dict(), separators=(",", ":")))
    os.replace(tmp, p)
    return b


def clear_counts(path: Path | None = None) -> None:
    """Start a pass with an empty tally, keeping the uptime clock."""
    b = read(path or STATE)
    beat(0, "starting", counts={}, path=path)
    _ = b


def uptime(b: Beat | None = None) -> float:
    """Seconds of unbroken running, 0 when it is not running."""
    b = b or read()
    if not b.updated or time.time() - b.updated > STALE_AFTER:
        return 0.0
    return max(0.0, b.updated - b.started)


def is_live(b: Beat | None = None) -> bool:
    b = b or read()
    return bool(b.updated) and (time.time() - b.updated) <= STALE_AFTER
