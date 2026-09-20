"""Every trial this project has ever run, in one append-only file.

WHY. Kris, 2026-09-18: *"everything happens random, we do little bit of this
little bit of that."* He is describing a real structural fact, not a mood.

There are 48 hypotheses in `STRATEGY_LOG.md` and 325 result files in
`backtests/`, and they live in a 191 KB markdown table that is written by hand,
read by nobody, and cannot be counted by a machine. So:

  * **the search cannot be priced** - `core/searchcost.py` needs a trial count
    and there was nothing to count;
  * **a dead idea gets re-proposed** - it happened on 2026-09-14, when a stale
    sentence in `CLAUDE.md` led to proposing an exit study that had already run
    four days earlier, and the correction is still sitting in that file;
  * **nothing knows what yesterday cost**, so every morning starts a fresh
    search that believes it is the first.

WHAT THIS IS NOT. It is not a replacement for `STRATEGY_LOG.md`, which is the
human narrative and is worth keeping. It is the machine-readable shadow of it:
one row per trial, fixed columns, appended by the code that runs the trial
rather than by a person afterwards.

THE ONE RULE. **A trial that is not logged did not happen, and a trial that is
logged is charged.** `log()` is the single entry point, so the count is complete
by construction. That is the only way a trial count can be trusted - a ledger
that anything can bypass undercounts exactly the trials somebody wished had not
happened.

USE

    from core.ledger import log
    log(hypothesis="H-053", arm="dfii10_gate", market="XAUUSD", tf="1h",
        n_trades=412, pf=1.31, sharpe=0.62, verdict="FAIL",
        prereg="docs/prereg/H-053.md", note="beaten by its own null")

    python -m core.ledger            # the budget, and what has been spent
    python -m core.ledger --tail 20  # the last 20 trials
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from dataclasses import asdict, dataclass, field, fields
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.searchcost import (  # noqa: E402
    expected_max_z, min_backtest_years, trials_affordable,
)

LEDGER = ROOT / "backtests" / "ledger.csv"

#: The test-window rule (CLAUDE.md, 2026-09-15): 3 years ideal, 5 the ceiling.
#: The budget is quoted against BOTH because which one applies depends on the
#: study, and the gap between them is a factor of three in affordable trials.
YEARS_IDEAL = 3.0
YEARS_MAX = 5.0


@dataclass
class Trial:
    """One configuration measured once. Columns are fixed on purpose."""
    ts: str = ""
    hypothesis: str = ""          # H-027, H-053 ...
    arm: str = ""                 # what was varied, in words
    market: str = ""
    tf: str = ""
    n_trades: int = 0
    pf: float = float("nan")      # at 2x cost, the repo's standard
    sharpe: float = float("nan")  # per-observation, for searchcost
    expected_days: float = float("nan")
    pass_rate: float = float("nan")
    null_margin: float = float("nan")   # real / null median, >1 is good
    verdict: str = "?"            # PASS / FAIL / WITHDRAWN / INCONCLUSIVE
    prereg: str = ""              # path to the pre-registration, or "" if none
    params: str = ""              # json
    note: str = ""

    def row(self) -> dict:
        d = asdict(self)
        return d


COLUMNS = [f.name for f in fields(Trial)]


def log(**kw) -> Trial:
    """Append one trial. The single entry point - nothing else writes the file.

    Unknown keyword arguments are folded into `params` rather than dropped, so a
    caller can pass a strategy's own configuration without this file having to
    know about it.
    """
    known = {k: v for k, v in kw.items() if k in COLUMNS}
    extra = {k: v for k, v in kw.items() if k not in COLUMNS}
    if extra:
        merged = json.loads(known.get("params") or "{}")
        merged.update(extra)
        known["params"] = json.dumps(merged, sort_keys=True, default=str)
    known.setdefault("ts", datetime.now(timezone.utc).isoformat(timespec="seconds"))

    t = Trial(**known)
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    new = not LEDGER.exists()
    with LEDGER.open("a", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=COLUMNS)
        if new:
            w.writeheader()
        w.writerow(t.row())
    return t


def read() -> list[Trial]:
    if not LEDGER.exists():
        return []
    out: list[Trial] = []
    with LEDGER.open(newline="") as fh:
        for r in csv.DictReader(fh):
            clean = {k: r.get(k, "") for k in COLUMNS}
            for k in ("n_trades",):
                clean[k] = int(float(clean[k])) if clean[k] else 0
            for k in ("pf", "sharpe", "expected_days", "pass_rate", "null_margin"):
                try:
                    clean[k] = float(clean[k])
                except (TypeError, ValueError):
                    clean[k] = float("nan")
            out.append(Trial(**clean))
    return out


@dataclass
class Budget:
    """What the search has spent against what the history buys."""
    raw: int = 0
    effective: float = 0.0
    prereg: int = 0
    affordable_3y: int = 0
    affordable_5y: int = 0
    years_needed: float = 0.0
    bar_z: float = 0.0
    by_verdict: dict = field(default_factory=dict)

    def __str__(self) -> str:
        over3 = "OVER BUDGET" if self.effective > self.affordable_3y else "ok"
        over5 = "OVER BUDGET" if self.effective > self.affordable_5y else "ok"
        v = "  ".join(f"{k} {n}" for k, n in sorted(self.by_verdict.items()))
        return (
            f"trials        {self.raw} charged, "
            f"{self.prereg} pre-registered\n"
            f"budget        3y buys {self.affordable_3y} ({over3}), "
            f"5y buys {self.affordable_5y} ({over5})\n"
            f"this search   needs {self.years_needed:.1f}y of history; "
            f"luck alone reaches {self.bar_z:.2f} sigma\n"
            f"verdicts      {v}"
        )


def budget(trials: list[Trial] | None = None) -> Budget:
    """Price the whole search to date.

    **The raw count is what is charged.** `core/searchcost.effective_trials`
    can discount trials that moved together, but it needs each trial's return
    series on a shared axis and the ledger stores summary rows, not series. The
    discount is therefore available to a single study that keeps its own returns
    and is deliberately NOT applied to the project-wide count, because guessing
    it from summary columns understates the search - the direction that flatters
    every result.
    """
    ts = read() if trials is None else trials
    eff = float(len(ts))
    verd: dict[str, int] = {}
    for t in ts:
        verd[t.verdict or "?"] = verd.get(t.verdict or "?", 0) + 1
    return Budget(
        raw=len(ts),
        effective=eff,
        prereg=sum(1 for t in ts if t.prereg),
        affordable_3y=trials_affordable(YEARS_IDEAL),
        affordable_5y=trials_affordable(YEARS_MAX),
        years_needed=min_backtest_years(max(1, round(eff))),
        bar_z=expected_max_z(max(1, round(eff))),
        by_verdict=verd,
    )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--tail", type=int, default=0, help="show the last N trials")
    a = ap.parse_args(argv)

    ts = read()
    if not ts:
        print(f"no ledger yet at {LEDGER.relative_to(ROOT)}")
        return 0
    print(budget(ts))
    if a.tail:
        print()
        print(f"{'date':11}{'hyp':8}{'arm':24}{'mkt':9}{'tf':5}"
              f"{'n':>7}{'pf':>7}{'days':>8}  verdict")
        for t in ts[-a.tail:]:
            days = f"{t.expected_days:.1f}" if t.expected_days == t.expected_days else "-"
            pf = f"{t.pf:.3f}" if t.pf == t.pf else "-"
            print(f"{t.ts[:10]:11}{t.hypothesis:8}{t.arm[:23]:24}{t.market:9}"
                  f"{t.tf:5}{t.n_trades:>7}{pf:>7}{days:>8}  {t.verdict}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
