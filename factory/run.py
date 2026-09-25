"""THE PIPELINE, STEPS 1 TO 7, IN ONE COMMAND.

    python -m factory.run                    # 20 ideas, everything
    python -m factory.run -n 40 --seeds 10   # a real batch
    python -m factory.run --no-null          # skip step 5 (the slow one)

Each step has its own module, its own tests and its own design note; this only
chains them in the order the diagram draws, and prints one line per idea so a
run is readable without opening a file.

    1  factory/fill.py      the queue tops itself up          docs/WORKFLOW.md
    2  factory/build.py     the idea becomes runnable code     - guard.py
    3  factory/check.py     four questions about TRADES        docs/STEP3.md
    4  factory/repair.py    six fixed tweaks for a near-miss   docs/STEP4.md
    5  factory/null.py      what best-of-30 gives on noise     docs/STEP5.md
    6  factory/recheck.py   the years it has not been on       docs/STEP6.md
    7  factory/evaluate.py  pass %, days, accounts consumed    docs/STEP7.md

WHY STEP 5 IS RUN ONCE PER BATCH AND NOT PER IDEA. It asks a question about the
PROCEDURE - how many survivors does this pipeline produce when there is nothing
to find - so its unit is the batch. Running it per idea would answer a question
step 3's gate 4 already answers, on one cell, for free.

WHY THE ORDER IS 5 THEN 6 AND NOT 6 THEN 5. Step 6 costs one extra backtest per
survivor and step 5 costs a full pipeline pass per seed, so the cheap one would
normally go first. It does not, because step 5's answer changes what a step-6
pass MEANS: if scrambled markets produce as many survivors as the real one,
then a survivor clearing step 6 is a survivor of two coin flips rather than
evidence. The expensive number is the one that frames the cheap one.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core import prop_rules                                          # noqa: E402
from factory import cells, check, evaluate, null, queue, recheck     # noqa: E402
from factory.spec import Strategy                                    # noqa: E402


def _survivors(ideas: list[Strategy], cell_list, control_seeds: int):
    """Steps 3 and 4 over the batch. Returns (strategy, market, tf, repaired)."""
    out, rows = [], []
    from factory import repair

    for s in ideas:
        checks = check.check_all(s, cell_list, control_seeds=control_seeds)
        won = [c for c in checks if c.verdict == "PASS"]
        if won:
            best = max(won, key=lambda c: c.mean_r.get(1.0, 0.0))
            out.append((s, best.market, best.tf, False))
            rows.append((s.label(), f"{best.market} {best.tf}", "step 3", "PASS"))
            queue.keep(s, f"step 3 on {best.market} {best.tf}")
            continue
        attempts, fixed = repair.repair(s, checks, control_seeds=control_seeds)
        if fixed is not None:
            tgt = attempts[0].before
            out.append((fixed, tgt.market, tgt.tf, True))
            rows.append((fixed.label(), f"{tgt.market} {tgt.tf}", "step 4", "PASS"))
            queue.keep(fixed, f"step 4 repair on {tgt.market} {tgt.tf}")
            continue
        why = "; ".join(sorted({repair.failed_gate(c) for c in checks})) or "no cell"
        rows.append((s.label(), "-", "step 3", f"FAIL ({why})"))
        queue.mark_tried(s, "FAIL", why)
    return out, rows


def _main(argv=None) -> int:
    import argparse

    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("-n", "--count", type=int, default=20)
    ap.add_argument("--seeds", type=int, default=5, help="step 5 scrambled markets")
    ap.add_argument("--control-seeds", type=int, default=check.CONTROL_SEEDS)
    ap.add_argument("--market", action="append")
    ap.add_argument("--tf", action="append")
    ap.add_argument("--no-null", action="store_true", help="skip step 5")
    ap.add_argument("--resamples", type=int, default=evaluate.BAND_RESAMPLES)
    a = ap.parse_args(argv)

    ideas = [s for s in (queue.take() for _ in range(a.count)) if s is not None]
    if not ideas:
        print("queue is empty - run `python -m factory.fill` first")
        return 1
    cell_list = cells.all_cells(a.market, tuple(a.tf) if a.tf else None)
    print(f"{len(ideas)} ideas x {len(cell_list)} cells "
          f"({len({c[0] for c in cell_list})} markets)\n")

    # ---------------------------------------------------------- steps 3 and 4
    print("STEPS 3+4 - the quick check, and repairs")
    head = f"{'idea':46}{'cell':14}{'where':8}{'outcome'}"
    print(head); print("-" * 78)
    survivors, rows = _survivors(ideas, cell_list, a.control_seeds)
    for label, cell, where, outcome in rows:
        print(f"{label[:44]:46}{cell:14}{where:8}{outcome}")
    print(f"\n{len(survivors)} of {len(ideas)} survived steps 3+4\n")

    # ------------------------------------------------------------------ step 5
    if not a.no_null:
        print("STEP 5 - the luck check, once for the batch")
        res = null.compare(ideas, seeds=a.seeds, cell_list=cell_list,
                           control_seeds=a.control_seeds)
        h = f"{'market':18}{'ideas':>7}{'step 3':>10}{'repaired':>10}{'survivors':>11}"
        print(h); print("-" * len(h))
        print(res["real"])
        for n in res["nulls"]:
            print(n)
        print(f"\nreal {res['real_survivors']}   scrambled mean "
              f"{res['null_mean']:.1f}, worst {res['null_max']}   "
              f"p = {res['p_value']:.2f}")
        if res["p_value"] > 0.1:
            print("LUCK IS NOT EXCLUDED - a market with no information in it "
                  "produced as many survivors.")
        print()

    if not survivors:
        print("nothing reached step 6")
        return 0

    # ------------------------------------------------------------------ step 6
    print("STEP 6 - the years the idea has not been selected on")
    h = (f"{'idea':42}{'cell':14}{'step 6':8}{'days':>8}{'trades':>8}"
         f"{'holdout':>9}{'5y':>9}  why")
    print(h); print("-" * len(h))
    passed = []
    for s, m, tf, _rep in survivors:
        r = recheck.recheck(s, m, tf, control_seeds=a.control_seeds)
        print(r)
        if r.verdict == "PASS":
            passed.append((s, m, tf))
    print(f"\n{len(passed)} of {len(survivors)} cleared step 6\n")
    if not passed:
        return 0

    # ------------------------------------------------------------------ step 7
    print(f"STEP 7 - HOUSE spec: {prop_rules.HOUSE.profit_target:.0%} target, "
          f"{prop_rules.HOUSE.daily_loss:.0%} daily, "
          f"{prop_rules.HOUSE.max_loss:.0%} max\n")
    for s, m, tf in passed:
        ev = evaluate.evaluate(s, m, tf, frame=evaluate.five_year_frame(m, tf),
                               resamples=a.resamples)
        print(f"{ev.idea}   [{ev.cell}]   {ev.span}")
        print(f"{ev.n_trades} trades, {ev.trades_per_day:.2f}/day")
        print(ev.table())
        print(f"-> {ev.note}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
