"""Bring the VM's work home, and merge it without losing either side.

THE GAP THIS CLOSES. The loop moved to the VM on 2026-09-18 so it survives the
desktop being switched off. That immediately created a worse problem than the
one it solved: **two ledgers**. The VM appends its trials there, the desktop
keeps its own, and within a day neither machine knows what the other spent.

That is not a filing inconvenience. `core/searchcost.py` prices every result
against the trial count, and the whole point of the ledger is that the count is
complete. Two half-counts mean the bar is understated on both machines - the
exact direction that flatters a result.

HOW THE MERGE WORKS. Rows are unioned on a natural key: timestamp, hypothesis,
arm, market. Both files are append-only and neither rewrites history, so a union
is safe and idempotent - running this twice changes nothing. The merged file
goes back to BOTH sides, so the VM stops re-proposing what the desktop paid for
and vice versa.

WHY NOT JUST COPY THE VM'S FILE DOWN. Because the desktop is not read-only: it
is where the walk-forwards run, and those are trials too. A copy in either
direction silently deletes the other machine's work.

    python -m research.sync_vm            # pull, merge, push back, rebuild
    python -m research.sync_vm --dry-run
"""
from __future__ import annotations

import argparse
import csv
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.ledger import COLUMNS, LEDGER                        # noqa: E402

KEY_ENV = "PROP_LAB_VM_KEY"
HOST_ENV = "PROP_LAB_VM_HOST"
DEFAULT_KEY = Path.home() / "trading-bots/bybit_bot/deploy/ssh/oracle_bots"
DEFAULT_HOST = "ubuntu@89.168.78.138"
REMOTE = "/home/ubuntu/prop_lab"


def _ssh_opts() -> tuple[str, str]:
    import os
    key = os.environ.get(KEY_ENV, str(DEFAULT_KEY))
    host = os.environ.get(HOST_ENV, DEFAULT_HOST)
    return key, host


def _rsync(src: str, dst: str, key: str) -> bool:
    cmd = ["rsync", "-az", "-e",
           f"ssh -i {key} -o StrictHostKeyChecking=no -o ConnectTimeout=15",
           src, dst]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if r.returncode:
        print(f"  rsync failed: {r.stderr.strip()[:200]}", file=sys.stderr)
    return r.returncode == 0


def _rows(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(newline="") as fh:
        return [dict(r) for r in csv.DictReader(fh)]


def _key(r: dict) -> tuple:
    return (r.get("ts", ""), r.get("hypothesis", ""), r.get("arm", ""),
            r.get("market", ""))


def merge(local: list[dict], remote: list[dict]) -> tuple[list[dict], int, int]:
    """Union on the natural key, ordered by timestamp. Idempotent."""
    seen = {_key(r): r for r in local}
    added = 0
    for r in remote:
        k = _key(r)
        if k not in seen:
            seen[k] = r
            added += 1
    out = sorted(seen.values(), key=lambda r: (r.get("ts", ""),
                                               r.get("hypothesis", "")))
    return out, added, len(local)


def write(rows: list[dict], path: Path) -> None:
    """Write via a temp file and replace, so an interrupted sync cannot leave a
    half-written ledger - the one file this project cannot afford to corrupt."""
    tmp = path.with_suffix(".tmp")
    with tmp.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=COLUMNS)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in COLUMNS})
    shutil.move(tmp, path)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    key, host = _ssh_opts()

    with tempfile.TemporaryDirectory() as td:
        got = Path(td) / "ledger.csv"
        print("→ pulling the VM's ledger")
        if not _rsync(f"{host}:{REMOTE}/backtests/ledger.csv", str(got), key):
            return 1

        local, remote = _rows(LEDGER), _rows(got)
        merged, added, had = merge(local, remote)
        print(f"  desktop {had}, vm {len(remote)}, merged {len(merged)} "
              f"(+{added} new from the vm)")

        print("→ pulling pre-registrations and the log")
        _rsync(f"{host}:{REMOTE}/docs/prereg/", str(ROOT / "docs/prereg/"), key)
        _rsync(f"{host}:{REMOTE}/backtests/loop.log",
               str(ROOT / "backtests/loop.log"), key)
        _rsync(f"{host}:{REMOTE}/backtests/loop_state.json",
               str(ROOT / "backtests/loop_state.json"), key)

        if a.dry_run:
            print("dry run — nothing written")
            return 0

        write(merged, LEDGER)
        print(f"→ wrote {LEDGER.relative_to(ROOT)}")

        # Back to the VM, so it stops re-proposing what the desktop paid for.
        print("→ pushing the merged ledger back")
        _rsync(str(LEDGER), f"{host}:{REMOTE}/backtests/ledger.csv", key)

        # And the model-written queue, which is the whole reason the VM can
        # propose like the model without having one (`research/backlog.py`).
        q = ROOT / "backtests" / "proposals.jsonl"
        if q.exists():
            from research import backlog
            print(f"→ pushing {backlog.depth()} queued proposals")
            _rsync(str(q), f"{host}:{REMOTE}/backtests/proposals.jsonl", key)
        else:
            print("→ no proposal queue to push "
                  "(python -m research.backlog --fill 60)")

    from research import dashboard
    dashboard.OUT.write_text(dashboard.build())
    print(f"→ rebuilt {dashboard.OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
