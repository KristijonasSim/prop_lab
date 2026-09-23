"""THE UNATTENDED RUN. One pass: top the queue up, test, record, report.

    python -m factory.nightly                 # one pass, default sizes
    python -m factory.nightly --no-agent      # enumerator only, zero tokens
    python -m factory.nightly --status        # what the last runs did

WHAT ONE PASS DOES

    1  top the queue up      the model proposes, the enumerator backfills
    3  the quick check       four questions about trades, all 24 cells
    4  repair near-misses    six fixed tweaks, once each
    5  the luck check        the same batch on scrambled markets
    6  the re-check          the years the idea was not selected on
    7  the evaluation        pass %, days, accounts consumed

Steps 2 to 7 never call a model. Only step 1 does, and it is allowed to fail:
`sources.agent.fill` reports and returns zero, and `sources.invent` backfills,
because a loop that stops when the model is unreachable is not unattended.

WHY THE RESULT IS A JSON LINE AND NOT A LOG. `backtests/factory/runs.jsonl` is
one object per pass, so "is the model's source better than the enumerator's"
is answerable by reading a file rather than by remembering. That comparison is
the only thing that says whether paying for a model is worth it, and it needs
the counts to be recorded from the first run, not added later.

TOKENS. Step 1 only, roughly 10-15k per pass at the default of 20 ideas. Once a
night is about 450k a month. Hourly is about 11M a month and will compete with
an interactive Claude session on the same account - see `--no-agent`, which
runs the whole pipeline for nothing when the queue is already full.
"""
from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from factory import (cells, check, evaluate, live, null, queue,      # noqa: E402
                     recheck, repair)
from factory.sources import agent, invent                              # noqa: E402

RUNS = queue.DIR / "runs.jsonl"
#: Ideas proposed per pass, and how far below this the queue must fall before
#: the enumerator is asked to backfill.
BATCH = 20
QUEUE_FLOOR = 40


def top_up(n: int = BATCH, *, use_agent: bool = True) -> dict:
    """Step 1. The model first, the enumerator as the floor under it."""
    out = {"agent": {"added": 0}, "invent": {"added": 0}}
    if use_agent:
        out["agent"] = agent.fill(n)
    waiting = queue.status()["waiting"]
    if waiting < QUEUE_FLOOR:
        out["invent"] = queue.add(invent.generate(limit=QUEUE_FLOOR - waiting),
                                  quiet=True)
    return out


def run_once(*, batch: int = BATCH, seeds: int = 5, use_agent: bool = True,
             cell_list=None, control_seeds: int = check.CONTROL_SEEDS,
             resamples: int = evaluate.BAND_RESAMPLES) -> dict:
    """One full pass. Returns the record that is appended to `runs.jsonl`."""
    t0 = time.time()
    rec: dict = {"started": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    live.clear_counts()
    live.beat(1, "ideas", detail="the model proposes, the enumerator backfills")
    rec["top_up"] = top_up(batch, use_agent=use_agent)

    ideas = [s for s in (queue.take() for _ in range(batch)) if s is not None]
    rec["ideas"] = len(ideas)
    # BY SOURCE, from the first run. The comparison this file exists to make -
    # does the model's source survive at a better rate than the enumerator's -
    # is impossible to reconstruct later if only the total is kept.
    rec["by_source"] = {}
    for s in ideas:
        rec["by_source"][s.source] = rec["by_source"].get(s.source, 0) + 1
    if not ideas:
        rec["note"] = "queue empty"
        return rec

    cl = cell_list or cells.all_cells()
    live.beat(2, "build", detail=f"{len(ideas)} ideas into runnable code",
              total=len(ideas), counts={"ideas": len(ideas)})
    survivors, s3, s4 = [], 0, 0
    # WHY THE GATE COUNTS ARE TALLIED HERE. 87% of everything dies on trade
    # count and the dashboard is the first place that has ever been visible
    # while it happens. A funnel that only shows "20 in, 1 out" hides which
    # gate is doing the killing, which is the whole diagnosis.
    gates = {"trades": 0, "cost": 0, "concentration": 0, "drift": 0, "other": 0}
    for i, s in enumerate(ideas, 1):
        live.beat(3, "quick check", idea=s.label(), done=i, total=len(ideas),
                  detail=f"{len(cl)} cells", counts={"step3_pass": s3,
                                                     "step4_repaired": s4,
                                                     "gates": gates})
        checks = check.check_all(s, cl, control_seeds=control_seeds)
        for c in checks:
            g = repair.failed_gate(c)
            if g in gates:
                gates[g] += 1
        won = [c for c in checks if c.verdict == "PASS"]
        if won:
            best = max(won, key=lambda c: c.mean_r.get(1.0, 0.0))
            survivors.append((s, best.market, best.tf, False))
            queue.keep(s, f"step 3 on {best.market} {best.tf}", reached=3)
            s3 += 1
            continue
        live.beat(4, "repair", idea=s.label(), done=i, total=len(ideas),
                  detail="six fixed tweaks on the best near-miss")
        _, fixed = repair.repair(s, checks, control_seeds=control_seeds)
        if fixed is not None:
            tgt = repair.best_near_miss(checks)
            survivors.append((fixed, tgt.market, tgt.tf, True))
            queue.keep(fixed, f"step 4 repair on {tgt.market} {tgt.tf}", reached=4)
            s4 += 1
        else:
            # The gate recorded is the one the BEST cell died on, not a set
            # union of all 24 - "trades; cost; drift" says nothing about what
            # to fix, and a source breakdown built on it cannot add up.
            best_cell = max(checks, key=repair.closeness, default=None)
            gate = repair.failed_gate(best_cell) if best_cell else "other"
            queue.mark_tried(s, "FAIL", f"best cell died on {gate}",
                             step=3, gate=gate)
    rec["gates"] = dict(gates)
    rec["step3_pass"] = s3
    rec["step4_repaired"] = s4
    rec["survivors"] = [{"idea": s.label(), "cell": f"{m} {tf}",
                         "source": s.source, "repaired": rep}
                        for s, m, tf, rep in survivors]

    if seeds:
        live.beat(5, "luck check", total=seeds,
                  detail=f"the same {len(ideas)} ideas on {seeds} scrambled markets",
                  counts={"step3_pass": s3, "step4_repaired": s4, "gates": gates})
        res = null.compare(ideas, seeds=seeds, cell_list=cl,
                           control_seeds=control_seeds)
        rec["step5"] = {"real": res["real_survivors"],
                        "null_mean": round(res["null_mean"], 2),
                        "null_max": res["null_max"],
                        "seeds": seeds, "p_value": round(res["p_value"], 3)}

    cleared = []
    for i, (s, m, tf, _rep) in enumerate(survivors, 1):
        live.beat(6, "re-check", idea=s.label(), cell=f"{m} {tf}",
                  done=i, total=len(survivors),
                  detail="years the idea was not selected on")
        r = recheck.recheck(s, m, tf, control_seeds=control_seeds)
        if r.verdict == "PASS":
            cleared.append((s, m, tf))
            live.beat(6, "re-check", idea=s.label(), cell=f"{m} {tf}",
                      done=i, total=len(survivors),
                      counts={"step6_pass": len(cleared)})
        else:
            # THE GATE, NOT THE STEP. This recorded a hardcoded "holdout" and
            # the board therefore told Kris his script "fell apart on the years
            # it was not selected on" - when it had in fact failed the TRADE
            # COUNT floor on that window and its edge was never measured there
            # at all. Two different facts, and the wrong one was displayed.
            g = repair.failed_gate(r.holdout) if r.holdout else "other"
            why = "; ".join(r.holdout.reasons) if r.holdout else "no holdout data"
            queue.mark_tried(s, "FAIL", f"step 6: {why}", step=6,
                             gate=g or "other")
    rec["step6_pass"] = len(cleared)

    rec["step7"] = []
    for i, (s, m, tf) in enumerate(cleared, 1):
        live.beat(7, "evaluation", idea=s.label(), cell=f"{m} {tf}",
                  done=i, total=len(cleared),
                  detail="pass %, days, accounts consumed",
                  counts={"step7": i})
        ev = evaluate.evaluate(s, m, tf, frame=evaluate.five_year_frame(m, tf),
                               resamples=resamples)
        f = ev.fastest()
        queue.keep(s, f"step 7 on {m} {tf}", reached=7)
        rec["step7"].append({
            "idea": ev.idea, "cell": ev.cell, "trades": ev.n_trades,
            "trades_per_day": round(ev.trades_per_day, 2),
            "risk": f.risk if f else None,
            "pass_pct": f.pass_pct if f else None,
            "expected_days": f.expected_days if f else None,
            "band": [f.band.get("days_lo"), f.band.get("days_hi")]
                    if f and f.band else None,
            "accounts": round(f.accounts, 2) if f and f.accounts else None,
            "note": ev.note,
        })
    rec["seconds"] = round(time.time() - t0, 1)
    # The last beat keeps the uptime clock alive between passes - the sleep
    # between them is longer than a step, and without this the dashboard would
    # call the factory dead every time it rested.
    live.beat(0, "resting", detail=f"pass finished in {rec['seconds']:.0f}s",
              counts={"step3_pass": s3, "step4_repaired": s4, "gates": gates})
    return rec


def record(rec: dict) -> None:
    RUNS.parent.mkdir(parents=True, exist_ok=True)
    with RUNS.open("a") as fh:
        fh.write(json.dumps(rec, separators=(",", ":")) + "\n")


def history(limit: int = 20) -> list[dict]:
    if not RUNS.exists():
        return []
    return [json.loads(l) for l in RUNS.read_text().splitlines() if l.strip()][-limit:]


def by_source() -> dict:
    """Ideas tested and survivors, split by where the idea came from.

    THE NUMBER THAT SAYS WHETHER THE MODEL IS WORTH PAYING FOR. If the agent's
    ideas do not survive at a better rate than the enumerator's, the model is
    not thinking to any effect and this table says so in one line.
    """
    out: dict[str, dict] = {}
    for r in history(10_000):
        for src, n in (r.get("by_source") or {}).items():
            out.setdefault(src, {"tested": 0, "survived": 0})["tested"] += n
        for s in (r.get("survivors") or []):
            out.setdefault(s.get("source", "?"),
                           {"tested": 0, "survived": 0})["survived"] += 1
    for v in out.values():
        v["rate_pct"] = round(100 * v["survived"] / v["tested"], 1) if v["tested"] else None
    return out


def _main(argv=None) -> int:
    import argparse

    ap = argparse.ArgumentParser(description="One unattended pass of the factory.")
    ap.add_argument("-n", "--batch", type=int, default=BATCH)
    ap.add_argument("--seeds", type=int, default=5, help="step 5 seeds; 0 skips it")
    ap.add_argument("--no-agent", action="store_true",
                    help="enumerator only - the whole pass costs zero tokens")
    ap.add_argument("--market", action="append")
    ap.add_argument("--tf", action="append")
    ap.add_argument("--control-seeds", type=int, default=check.CONTROL_SEEDS)
    ap.add_argument("--resamples", type=int, default=evaluate.BAND_RESAMPLES)
    ap.add_argument("--status", action="store_true")
    a = ap.parse_args(argv)

    if a.status:
        print(json.dumps({"queue": queue.status(), "by_source": by_source(),
                          "last_runs": history(5)}, indent=2))
        return 0

    cl = cells.all_cells(a.market, tuple(a.tf) if a.tf else None)
    rec = run_once(batch=a.batch, seeds=a.seeds, use_agent=not a.no_agent,
                   cell_list=cl, control_seeds=a.control_seeds,
                   resamples=a.resamples)
    record(rec)
    print(json.dumps(rec, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
