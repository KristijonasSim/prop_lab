"""What produced a board record, so the board can notice when it stops being true.

Item 1 of `STEPS_1_2_4.md`. The problem it solves, stated once:

    `SUPERSEDED - SCORED ON A BROKEN KERNEL` is a note a human typed by hand,
    after noticing. H-009 held board score 8.9 on a kernel that had already been
    found to look ahead. Nothing in the system said so.

A board record now carries a fingerprint of everything it depends on - the
kernel files, the data files, the cost assumption - and `build_scoreboard`
recomputes that fingerprint at render time. If the kernel has changed, the
record marks itself stale. Nobody has to remember.

Three decisions worth knowing before changing this file:

* **Content hashes, never mtime.** A fresh `git clone` rewrites every mtime and
  would cry stale on a repo where nothing moved.
* **The git SHA is provenance, not the gate.** Code moves for a hundred reasons
  that cannot touch a result. Only the declared kernel files gate a record.
  `dirty` is recorded because a result produced from an uncommitted tree cannot
  be reproduced from the repo alone, and that is worth saying out loud.
* **Appending to a feed is not the same as rewriting one.** The feeds grow every
  day by design. A file that got longer at the same start, with the same history,
  is a note. A file whose history changed is a hard stale - it is a different
  input wearing the same filename.

Two tiers of source file, because they fail differently and a flag that is always
on gets ignored:

* `kernels` - the arithmetic that produced the TRADES. If one of these changed,
  the trade list itself is no longer what the record describes. **Hard stale.**
* `scoring` - the layer that turned those trades into the stored summary
  (`core/board.py`, `core/riskladder.py`). The trades still stand; the numbers on
  the card were computed by code that has moved. **A note, and rerun the board
  stage.**

The score itself is NOT fingerprinted: `core/scorecard.py` runs at render time,
so a change there re-scores every record on the spot and cannot go stale.
"""
from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]

SCHEMA = 1

# 1 MiB. Files here run to 12 MB; this keeps peak memory flat without making the
# hash of a small file cost anything measurable.
_CHUNK = 1 << 20


# --------------------------------------------------------------------------- #
# primitives
# --------------------------------------------------------------------------- #
def _rel(p: Path | str) -> str:
    """Repo-relative, forward slashes. The key must not depend on where the repo
    is checked out or the fingerprint is not portable between machines."""
    p = Path(p)
    try:
        return p.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return p.as_posix()


def file_sha(path: Path | str) -> str | None:
    """sha256 of the bytes, or None if the file is gone. Missing is a real state
    and must survive into the record - a result whose kernel was deleted is not
    the same thing as a result whose kernel matches."""
    p = Path(path)
    if not p.is_file():
        return None
    h = hashlib.sha256()
    with p.open("rb") as fh:
        for chunk in iter(lambda: fh.read(_CHUNK), b""):
            h.update(chunk)
    return h.hexdigest()


def hash_files(paths) -> dict:
    """{repo-relative path: sha256}, sorted. Sorted because the combined hash
    below must not depend on the order the caller happened to list them in."""
    return {_rel(p): file_sha(p) for p in sorted(paths, key=lambda x: _rel(x))}


def combine(shas: dict) -> str:
    """One hash over a {path: sha} map, so a record can be compared in one line.
    The path is folded in as well as the hash: renaming a kernel is a change."""
    h = hashlib.sha256()
    for k in sorted(shas):
        h.update(k.encode())
        h.update(b"\0")
        h.update((shas[k] or "MISSING").encode())
        h.update(b"\n")
    return h.hexdigest()


def git_state() -> dict:
    """HEAD plus whether the tree was dirty. Provenance only - see the module
    docstring. A dirty tree is recorded, not punished."""
    def _run(*args) -> str | None:
        try:
            out = subprocess.run(args, cwd=ROOT, capture_output=True,
                                 text=True, timeout=10)
        except (OSError, subprocess.SubprocessError):
            return None
        return out.stdout.strip() if out.returncode == 0 else None

    sha = _run("git", "rev-parse", "HEAD")
    status = _run("git", "status", "--porcelain")
    return {
        "sha": sha,
        "short": (sha[:7] if sha else None),
        # None, not False, when git itself did not answer. "we did not look" and
        # "we looked and it was clean" are different claims.
        "dirty": (bool(status) if status is not None else None),
    }


def data_state(paths) -> dict:
    """Per data file: content hash, row count, and the first and last timestamp.

    The hash alone would be enough to detect a change. The rows and the range are
    what let `check` tell an append apart from a rewrite, and they are also the
    thing a human wants to read on the card - a result scored on eighteen months
    of gold is not the result scored on three years of it.
    """
    out = {}
    for p in sorted(paths, key=lambda x: _rel(x)):
        path = Path(p)
        rec: dict = {"sha": file_sha(path)}
        if rec["sha"] is None:
            out[_rel(path)] = rec | {"rows": None, "first": None, "last": None}
            continue
        rec["bytes"] = path.stat().st_size
        try:
            # columns=[] reads the index and nothing else: 10ms on a 22k-row
            # file against 5ms for the whole thing, and flat as files grow.
            idx = pd.read_parquet(path, columns=[]).index
            rec["rows"] = int(len(idx))
            if len(idx):
                rec["first"] = str(idx[0])
                rec["last"] = str(idx[-1])
        except Exception as exc:                       # noqa: BLE001
            # A file we cannot read is still fingerprinted by its bytes. Losing
            # the range is a smaller loss than refusing to write the record.
            rec["read_error"] = f"{type(exc).__name__}: {exc}"
            rec.setdefault("rows", None)
        out[_rel(path)] = rec
    return out


# --------------------------------------------------------------------------- #
# make / check
# --------------------------------------------------------------------------- #
def make(*, kernels, scoring=(), data=(), costs=None,
         note: str | None = None) -> dict:
    """Assemble the fingerprint that gets written into a board record.

    `kernels` - every source file whose arithmetic produced the trades. Be
    generous: the kernel, its sweep, the timeframe loader, the walk-forward
    stage, the board stage. Listing too little is the exact failure this item
    exists to prevent, and there is no cost to listing one file too many.
    """
    kern = hash_files(kernels)
    score = hash_files(scoring)
    return {
        "v": SCHEMA,
        "written": pd.Timestamp.utcnow().isoformat(),
        "git": git_state(),
        "kernels": kern,
        "kernel_hash": combine(kern),
        "scoring": score,
        "scoring_hash": combine(score),
        "data": data_state(data),
        "costs": costs,
        "note": note,
    }


def check(fp: dict | None) -> dict:
    """Recompute a stored fingerprint against the files on disk now.

    Returns a verdict the board can render directly:

        state   'ok' | 'stale' | 'note' | 'unfingerprinted'
        stale   bool - the hard one. Kernel or cost changed, or a file vanished.
        reasons list[str] - the hard reasons, in words
        notes   list[str] - benign drift, chiefly feeds that grew
    """
    if not fp:
        # Every record written before this item existed. Say so plainly rather
        # than inventing a fingerprint that would claim more than we know.
        return {"state": "unfingerprinted", "stale": False,
                "reasons": [], "notes": ["written before fingerprinting existed"],
                "detail": "no fingerprint"}

    reasons: list[str] = []
    notes: list[str] = []

    if fp.get("v") != SCHEMA:
        notes.append(f"fingerprint schema v{fp.get('v')} against v{SCHEMA}")

    # --- kernels: the gate ---------------------------------------------------
    for rel, was in (fp.get("kernels") or {}).items():
        now = file_sha(ROOT / rel)
        if now is None:
            reasons.append(f"{rel} is gone")
        elif was is None:
            reasons.append(f"{rel} did not exist when this was scored")
        elif now != was:
            reasons.append(f"{rel} changed")

    # --- scoring: the trades stand, the summary was recomputed elsewhere -----
    for rel, was in (fp.get("scoring") or {}).items():
        now = file_sha(ROOT / rel)
        if now != was:
            notes.append(f"{rel} changed - rerun the board stage to refresh")

    # --- data: append is a note, rewrite is a reason -------------------------
    for rel, was in (fp.get("data") or {}).items():
        path = ROOT / rel
        now_sha = file_sha(path)
        if now_sha is None:
            reasons.append(f"data {rel} is gone")
            continue
        if now_sha == was.get("sha"):
            continue
        now = data_state([path])[_rel(path)]
        grew = (
            was.get("rows") is not None and now.get("rows") is not None
            and now["rows"] >= was["rows"]
            and now.get("first") == was.get("first")
            and (was.get("last") is None or now.get("last") is None
                 or str(now["last"]) >= str(was["last"]))
        )
        if grew:
            notes.append(f"data {rel} grew {was['rows']}→{now['rows']} rows")
        else:
            # Same name, different history. This is the case that quietly
            # changes a result and the one worth being loud about.
            reasons.append(
                f"data {rel} rewritten "
                f"({was.get('rows')}→{now.get('rows')} rows, "
                f"{was.get('first')}→{now.get('first')})")

    state = "stale" if reasons else ("note" if notes else "ok")
    detail = "; ".join(reasons) if reasons else "; ".join(notes)
    return {"state": state, "stale": bool(reasons),
            "reasons": reasons, "notes": notes, "detail": detail}


def costs_changed(fp: dict | None, costs) -> bool:
    """Separate from `check` because the cost assumption lives with the caller,
    not on disk. A record scored at 1.83bps is not a record scored at 3.00."""
    if not fp or costs is None:
        return False
    return fp.get("costs") != costs


if __name__ == "__main__":                                       # pragma: no cover
    import json
    fp = make(kernels=[ROOT / "core" / "fingerprint.py"],
              scoring=[ROOT / "core" / "board.py"],
              data=[ROOT / "data" / "XAUUSD_dukascopy_1h.parquet"],
              costs={"rt_bps": 1.83})
    print(json.dumps(fp, indent=1))
    print(json.dumps(check(fp), indent=1))
