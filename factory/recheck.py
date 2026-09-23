"""STEP 6 — THE RE-CHECK ON LONGER HISTORY. Kris's rule, and what makes 4 safe.

    docs/WORKFLOW.drawio   the picture
    docs/STEP6.md          the design, the coverage table, and the correction

WHAT KRIS ASKED, 2026-09-23: *"step 6 is only same check as step 3 just on 5
years?"* Same four gates, yes. On a different window, and the difference is not
cosmetic.

**IT TESTS THE YEARS BEFORE THE STEP-3 WINDOW, NOT ALL FIVE.** The five-year
window CONTAINS the three the idea has already been selected on, so a rule that
did well there is carried by its own training data into the longer number. Two
thirds of a "five-year re-check" would be a re-read of the exam paper. The
holdout is the prefix: `cells.holdout` returns [end - 5y, start of the step-3
window), which the idea has never touched. The full five years is computed as
well and printed, as context, never as the gate.

**WHAT IT IS FOR.** Step 3 tests 24 cells and step 4 hands the near-miss up to
twelve more tries, so a survivor is the best of about thirty draws. The
2026-09-21 simulation put junk reaching the desk at 31 per 1,000 on three years
alone and 0.5 per 1,000 once this stage runs. That 98% is the reason steps 3
and 4 are allowed to be as wide as they are.

**AND THE 98% IS OPTIMISTIC, WHICH IS WHY THIS FILE SAYS SO.** That simulation
drew the two windows independently. Real history is one path: the holdout and
the step-3 window are adjacent stretches of the same market, share its regime
and its drift, and a rule that is long gold will look similar on both for a
reason that has nothing to do with edge. Read a step-6 pass as "it did not fall
apart", not as "it replicated".

**COVERAGE IS NOT THE SAME ON EVERY MARKET.** Gold has eleven years of raw
1-minute files on disk and BTC nine, so both get the full two extra years. The
other four were cached from 2023-09 only; `scripts/build_5y.py` pulls the rest.
A cell with no holdout is reported as NO DATA and is NOT counted as a pass -
the alternative, treating a missing test as a passed one, is how a pipeline
quietly stops testing.

    python -m factory.recheck            # re-check whatever steps 3+4 produced
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from factory import cells, check                                     # noqa: E402
from factory.check import Check                                      # noqa: E402
from factory.spec import Strategy                                    # noqa: E402

#: A holdout shorter than this cannot carry the 100-trade floor and is reported
#: as NO DATA rather than as a failure. One year of the two is the minimum that
#: leaves the trade gate meaning what it means in step 3.
MIN_HOLDOUT_DAYS = 250.0


@dataclass
class Recheck:
    """One survivor, re-tested on bars it has never seen."""
    idea: str
    market: str
    tf: str
    verdict: str = "NO DATA"            # PASS | FAIL | NO DATA
    holdout: Check | None = None
    full: Check | None = None
    holdout_days: float = float("nan")
    holdout_span: str = ""

    @property
    def cell(self) -> str:
        return f"{self.market} {self.tf}"

    def __str__(self) -> str:
        h, f = self.holdout, self.full
        hm = h.mean_r.get(1.0, float("nan")) if h else float("nan")
        fm = f.mean_r.get(1.0, float("nan")) if f else float("nan")
        why = "; ".join(h.reasons) if h and h.reasons else ""
        return (f"{self.idea[:40]:42}{self.cell:14}{self.verdict:8}"
                f"{self.holdout_days:>8.0f}"
                f"{(h.n_trades if h else 0):>8}{hm:>+9.3f}{fm:>+9.3f}  {why}")


def recheck(strategy: Strategy, market: str, tf: str, *,
            control_seeds: int = check.CONTROL_SEEDS) -> Recheck:
    """The four step-3 gates on the holdout, and again on the full five years.

    The gate is the HOLDOUT. `full` is reported beside it because a rule that
    passes the holdout and fails the five-year window is telling us something
    (the two halves disagree) that neither number says alone.
    """
    out = Recheck(idea=strategy.label(), market=market, tf=tf)
    hold = cells.holdout(market, tf)
    if not len(hold):
        return out
    out.holdout_days = check.trading_days(hold)
    out.holdout_span = f"{hold.index[0]:%Y-%m-%d}..{hold.index[-1]:%Y-%m-%d}"
    if not (out.holdout_days >= MIN_HOLDOUT_DAYS):
        return out

    days = check.trading_days(cells.holdout(market, "1h")) or out.holdout_days
    out.holdout = check.check(strategy, hold, market=market, tf=tf,
                              days=days, control_seeds=control_seeds)

    recent = cells.load(market, tf)
    full = pd.concat([hold, recent])
    full = full[~full.index.duplicated(keep="last")].sort_index()
    out.full = check.check(strategy, full, market=market, tf=tf,
                           days=check.trading_days(full),
                           control_seeds=control_seeds)

    out.verdict = out.holdout.verdict
    return out


def recheck_all(survivors, *, control_seeds: int = check.CONTROL_SEEDS
                ) -> list[Recheck]:
    """Re-check a list of `(strategy, market, tf)`, one row each."""
    return [recheck(s, m, t, control_seeds=control_seeds)
            for s, m, t in survivors]


def coverage() -> pd.DataFrame:
    """What holdout each of the 24 cells actually has. Prints as a table.

    Exists because "step 6 ran" and "step 6 could run" are different claims and
    the repo has confused them before.
    """
    rows = []
    for sym, tf in cells.all_cells():
        h = cells.holdout(sym, tf)
        d = check.trading_days(h) if len(h) else 0.0
        rows.append({
            "market": sym, "tf": tf, "bars": len(h),
            "days": round(d, 0) if d == d else 0.0,
            "from": f"{h.index[0]:%Y-%m-%d}" if len(h) else "-",
            "to": f"{h.index[-1]:%Y-%m-%d}" if len(h) else "-",
            "usable": bool(len(h) and d == d and d >= MIN_HOLDOUT_DAYS),
        })
    return pd.DataFrame(rows)


def _main(argv=None) -> int:
    """Step 6 on the survivors of steps 3+4, or a coverage report."""
    import argparse

    from factory import null, queue

    ap = argparse.ArgumentParser(description=_main.__doc__)
    ap.add_argument("--coverage", action="store_true",
                    help="what holdout each cell has, and run nothing")
    ap.add_argument("-n", "--count", type=int, default=20)
    ap.add_argument("--market", action="append")
    ap.add_argument("--tf", action="append")
    a = ap.parse_args(argv)

    if a.coverage:
        df = coverage()
        print(df.to_string(index=False))
        print(f"\n{int(df.usable.sum())} of {len(df)} cells can be re-checked")
        return 0

    ideas = [s for s in (queue.take() for _ in range(a.count)) if s is not None]
    cell_list = cells.all_cells(a.market, tuple(a.tf) if a.tf else None)
    survivors = []
    for s in ideas:
        checks = check.check_all(s, cell_list)
        for c in checks:
            if c.verdict == "PASS":
                survivors.append((s, c.market, c.tf))
    if not survivors:
        print(f"{len(ideas)} ideas, no step-3 survivors to re-check")
        return 0

    head = (f"{'idea':42}{'cell':14}{'step 6':8}{'days':>8}{'trades':>8}"
            f"{'holdout':>9}{'5y':>9}  why")
    print(head); print("-" * len(head))
    for r in recheck_all(survivors):
        print(r)
    _ = null  # imported so `-m factory.recheck` documents the step order
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
