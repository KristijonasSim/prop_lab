"""Seed the trial ledger from the 250 rows already written in STRATEGY_LOG.md.

WHY BACKFILL RATHER THAN START AT ZERO. A trial count that begins today says the
search is cheap, and the search is not cheap - it is 250 recorded variations
across 48 hypotheses over 18 days. Starting the count at zero would hand the next
result the lowest bar this project has ever had, at the exact moment the evidence
says the bar should be highest.

WHAT IS AND IS NOT RECOVERABLE. The markdown table carries a date, an idea, a
variation, an asset, a profit factor, a Sharpe and a verdict. It does NOT carry
per-trial daily returns, so `pbo_cscv` cannot be run on the history and the
effective-trial discount falls back to the Sharpe column wherever it exists.

Rows are matched loosely on purpose: the table was written by hand over three
weeks and its formatting drifts. A row that cannot be parsed is counted and
reported rather than silently dropped, because an undercounted search is the
failure mode this whole file exists to prevent.

    python -m core.backfill_ledger --dry-run     # what it would write
    python -m core.backfill_ledger               # write it
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core import ledger as L  # noqa: E402

SRC = ROOT / "STRATEGY_LOG.md"
HYP = re.compile(r"\b(H-\d{3})\b")
NUM = re.compile(r"-?\d+\.?\d*")
VERDICTS = ("WITHDRAWN", "INCONCLUSIVE", "PASS", "FAIL", "MAYBE", "NULL",
            "DEAD", "OPEN")


def _num(cell: str) -> float:
    """First number in a cell, or NaN. Cells hold things like 'best 1.045',
    '1.669', '0.61-0.78', 'IS 1.907 -> OOS 0.671' - the first number is the one
    the row is about in every case checked."""
    m = NUM.search(cell.replace(",", ""))
    if not m:
        return float("nan")
    try:
        return float(m.group())
    except ValueError:
        return float("nan")


def _num_strict(cell: str) -> float:
    """A number only when the cell is ESSENTIALLY a number.

    The table's later rows put prose in numeric columns - the days column of the
    top-N row reads "real speed-up 1.53-3.85". Parsing that as 1.53 days puts a
    fabricated figure in the ledger, which is worse than an empty one. So: at
    most two words of decoration, and no arrows or ranges.
    """
    c = cell.strip().strip("*").replace("~", "").replace("≈", "")
    if not c or c in {"-", "—", "?"}:
        return float("nan")
    if any(t in c for t in ("→", "->", "vs", "–", " to ")):
        return float("nan")
    if len(c.split()) > 2:
        return float("nan")
    return _num(c)


def _verdict(cell: str) -> str:
    """The verdict word that appears EARLIEST in the cell.

    Scanning a fixed list in order got this wrong: "FAIL on 6 of 6 markets - the
    top-N claim is withdrawn" was logged as WITHDRAWN because WITHDRAWN came
    first in the list. The row's own word order is the author's intent.
    """
    up = cell.upper()
    hits = [(up.index(v), v) for v in VERDICTS if v in up]
    return min(hits)[1] if hits else "?"


def parse(text: str) -> tuple[list[dict], int]:
    rows, skipped = [], 0
    for line in text.splitlines():
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 14 or not re.match(r"^20\d\d-\d\d-\d\d", cells[0]):
            continue
        date, idea, variation, asset = cells[0], cells[1], cells[2], cells[3]
        m = HYP.search(idea) or HYP.search(variation)
        if not m:
            skipped += 1
            continue
        parts = asset.rsplit(" ", 1)
        market = parts[0] if len(parts) == 2 else asset
        tf = parts[1] if len(parts) == 2 else ""
        rows.append(dict(
            ts=date,
            hypothesis=m.group(1),
            arm=re.sub(r"\s+", " ", variation)[:120],
            market=market[:40],
            tf=tf[:8],
            pf=_num_strict(cells[5]),
            sharpe=_num_strict(cells[11]),
            expected_days=_num_strict(cells[12]),
            verdict=_verdict(cells[13]),
            prereg="",
            note=re.sub(r"\s+", " ", cells[14] if len(cells) > 14 else "")[:200],
            source="STRATEGY_LOG.md backfill",
        ))
    return rows, skipped


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)

    rows, skipped = parse(SRC.read_text())
    print(f"parsed {len(rows)} trials from {SRC.name}, {skipped} rows had no H-id")
    if L.LEDGER.exists() and not a.dry_run:
        print(f"refusing to append: {L.LEDGER.relative_to(ROOT)} already exists")
        return 1
    if a.dry_run:
        for r in rows[:5]:
            print("  ", r["ts"], r["hypothesis"], r["market"], r["verdict"],
                  r["arm"][:50])
        print("   ...")
        return 0
    for r in rows:
        L.log(**r)
    print(L.budget())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
