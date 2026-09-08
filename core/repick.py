"""Re-price every board record at the CURRENT risk policy, without re-running.

WHY THIS CAN EXIST AT ALL. A risk ladder is one fixed trade series simulated at
twelve position sizes. Changing `riskladder.MIN_RISK` changes which rung to read;
it cannot change what the rungs say. So a policy change is a re-read, not a
re-search - half a second instead of half an hour, and with no chance of the new
numbers differing from the old ones for any reason other than the policy.

WHY IT WRITES THE RECORD RATHER THAN THE PAGE. `core/build_board.py` is
deliberately thin: it lays out numbers computed upstream so the page and the
record can never disagree. Re-pricing inside the renderer would break exactly
that. So this rewrites `backtests/*/hypothesis.json` in place and the renderer
stays dumb.

WHAT IT TOUCHES: the headline keys of every cell and every promoted row, plus the
`picked` flag on each ladder rung. It does NOT touch trades, profit factors,
nulls or fingerprints - none of those depend on position size.

Run: .venv/bin/python core/repick.py [--dry-run]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.riskladder import MIN_RISK, pick_stored                  # noqa: E402

BT = ROOT / "backtests"
#: The headline keys a record copies out of its chosen ladder rung.
HEADLINE = ("risk_pct", "pass_pct", "max_dd_pct", "days_to_pass", "median_days",
            "fail_max_pct", "fail_daily_pct", "cagr_pct")


def repick(node: dict) -> tuple[bool, str | None]:
    """Re-read one cell/row against the current policy. True if it moved."""
    lad = node.get("ladder")
    if not lad:
        return False, None
    chosen = pick_stored(lad)
    if chosen is None:
        return False, None
    before = (node.get("risk_pct"), node.get("days_to_pass"))
    for k in HEADLINE:
        if k in chosen:
            node[k] = chosen[k]
    for rung in lad:
        rung["picked"] = rung is chosen
    after = (node.get("risk_pct"), node.get("days_to_pass"))
    if before == after:
        return False, None
    return True, (f"{before[0]}% / {before[1]}d -> {after[0]}% / {after[1]}d")


def main(argv: list[str]) -> int:
    dry = "--dry-run" in argv
    print(f"risk floor {MIN_RISK:.2%} per trade"
          f"{'   (dry run)' if dry else ''}\n")
    total = 0
    for p in sorted(BT.glob("*/hypothesis.json")):
        d = json.loads(p.read_text())
        moved = []
        for key in ("cells", "rows"):
            for node in d.get(key, []):
                did, msg = repick(node)
                if did:
                    moved.append(f"    {key[:-1]:5s} {str(node.get('sym'))[:28]:28s} "
                                 f"{node.get('tf') or '':3s}  {msg}")
                # per-rule ladders too, where they exist
                for rule in node.get("rules", []):
                    repick(rule)
        if moved:
            print(f"  {d.get('hid')} {p.parent.name}")
            print("\n".join(moved))
            total += len(moved)
        if not dry:
            p.write_text(json.dumps(d, indent=1, default=str))
    print(f"\n{total} headline{'' if total == 1 else 's'} moved"
          f"{'' if dry else '; records rewritten'}")
    if not dry:
        print("now rebuild the page: .venv/bin/python core/build_board.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
