"""Re-screen every PASS the loop has produced against the two shape gates.

WHY. `core/screen.py` gained two checks on 2026-09-20 — concentration and seat
survival, from `docs/DIAGNOSIS_2026-09-20.md`. The twenty FEED candidates the
loop had already marked PASS were screened without them, so their verdicts were
recorded under a weaker bar and have to be re-read before any of them is built
on.

THIS DOES NOT CHARGE THE LEDGER. Every candidate here is already in it. Running
`run_candidate(dry=True)` re-uses the identical pipeline without writing a row,
because re-reading an old trial under a new gate is not a new trial and charging
it twice would raise the luck bar for work nobody did.

Run: .venv/bin/python -m research.rescore_shape
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from research.propose import Candidate                             # noqa: E402
from research.run import run_candidate                             # noqa: E402

LEDGER = ROOT / "backtests" / "ledger.csv"


def past_passes() -> list[tuple[str, str]]:
    seen, out = set(), []
    for r in csv.DictReader(LEDGER.open()):
        if r.get("verdict") != "PASS":
            continue
        if not (r.get("hypothesis") or "").startswith("FEED-"):
            continue
        k = json.loads(r.get("params") or "{}").get("candidate_key")
        if k and k not in seen:
            seen.add(k)
            out.append((k, r["arm"]))
    return out


def main() -> int:
    rows = past_passes()
    print(f"{len(rows)} distinct FEED PASS candidates in the ledger\n")
    print(f"{'arm':36}{'old':>5}{'new':>6}{'conc':>7}{'fundd':>8}  why")
    kept = 0
    for key, arm in rows:
        feed, tr, win, lag, mkt, hold, d = key.split("|")
        c = Candidate(feed=feed, transform=tr, window=int(win), lag=int(lag),
                      market=mkt, hold=int(hold), direction=int(d),
                      mechanism="rescore under the shape gates",
                      origin="rescore")
        try:
            res = run_candidate(c, dry=True)
        except Exception as exc:                            # noqa: BLE001
            print(f"{arm:36}{'PASS':>5}{'ERR':>6}  "
                  f"{type(exc).__name__}: {exc}")
            continue
        s = res.screen
        cc = "  -" if s.conc is None else f"{s.conc:.2f}"
        fd = ("  -" if s.fund_days is None
              else "never" if s.fund_days == float("inf")
              else f"{s.fund_days:.0f}")
        kept += res.verdict == "PASS"
        print(f"{arm:36}{'PASS':>5}{res.verdict:>6}{cc:>7}{fd:>8}  "
              f"{'; '.join(s.notes)}")
    print(f"\n{kept} of {len(rows)} survive the two new gates")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
