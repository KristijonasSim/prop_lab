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

import numpy as np                                                   # noqa: E402
import pandas as pd                                                  # noqa: E402

from core import riskladder                                          # noqa: E402
from factory import (build, cells, check, evaluate, live, null,      # noqa: E402
                     queue, recheck, repair)
from factory.sources import agent, invent                              # noqa: E402

RUNS = queue.DIR / "runs.jsonl"
#: ONE RECORD PER IDEA, with every gate and every repair attempt on it.
#: Kris, 2026-09-23: *"i dont see no repairs here, nothing, i dont understand."*
#: The run record held totals and the board showed "0 fixed" while eight
#: repairs had just been tried and reported nowhere. Aggregates cannot answer
#: "what happened to THIS idea", and that is the question being asked.
IDEAS = queue.DIR / "ideas.jsonl"
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
    stories: list[dict] = []
    # A repaired rule has a new label (a filter adds a condition), so each
    # fixed rule remembers which idea's story it belongs to. Without this the
    # step 6/7 outcome was written nowhere and the page kept saying
    # "repaired at step 4" for ideas that went on to be scored (2026-09-24).
    origin: dict[str, str] = {}
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
        best_any = _headline_cell(s, checks)
        story = {"idea": s.label(), "name": s.name, "side": s.side,
                 "source": s.source, "note": s.note,
                 "score": (scorecard(s, best_any.market, best_any.tf)
                           if best_any else {}),
                 "ladder": (ladder_rows(s, best_any.market) if best_any else []),
                 "when": rec["started"], "stop_atr": s.stop_atr,
                 "target_atr": s.target_atr, "max_hold": s.max_hold,
                 "cells": [_cell_row(c) for c in checks], "repairs": [],
                 "outcome": "", "cell": ""}
        stories.append(story)
        won = [c for c in checks if c.verdict == "PASS"]
        if won:
            best = max(won, key=lambda c: c.mean_r.get(1.0, 0.0))
            survivors.append((s, best.market, best.tf, False))
            queue.keep(s, f"step 3 on {best.market} {best.tf}", reached=3)
            story["outcome"] = "passed step 3"
            story["cell"] = f"{best.market} {best.tf}"
            s3 += 1
            continue
        live.beat(4, "repair", idea=s.label(), done=i, total=len(ideas),
                  detail="six fixed tweaks on the best near-miss")
        atts, fixed = repair.repair(s, checks, control_seeds=control_seeds)
        story["repairs"] += [{"step": 3, "name": a.repair,
                              "verdict": a.after.verdict,
                              "cell": f"{a.after.market} {a.after.tf}",
                              "reasons": list(a.after.reasons)} for a in atts]
        if fixed is not None:
            tgt = repair.best_near_miss(checks)
            survivors.append((fixed, tgt.market, tgt.tf, True))
            origin[fixed.label()] = s.label()
            queue.keep(fixed, f"step 4 repair on {tgt.market} {tgt.tf}", reached=4)
            story["outcome"] = "repaired at step 4"
            story["cell"] = f"{tgt.market} {tgt.tf}"
            s4 += 1
        else:
            # The gate recorded is the one the BEST cell died on, not a set
            # union of all 24 - "trades; cost; drift" says nothing about what
            # to fix, and a source breakdown built on it cannot add up.
            best_cell = max(checks, key=repair.closeness, default=None)
            gate = repair.failed_gate(best_cell) if best_cell else "other"
            queue.mark_tried(s, "FAIL", f"best cell died on {gate}",
                             step=3, gate=gate)
            story["outcome"] = f"stopped at step 3 ({gate})"
            if best_cell:
                story["cell"] = f"{best_cell.market} {best_cell.tf}"
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

    by_label = {st["idea"]: st for st in stories}

    cleared = []
    for i, (s, m, tf, _rep) in enumerate(survivors, 1):
        st = (by_label.get(origin.get(s.label(), s.label()))
              or {"repairs": [], "cells": []})
        live.beat(6, "re-check", idea=s.label(), cell=f"{m} {tf}",
                  done=i, total=len(survivors),
                  detail="years the idea was not selected on")
        r = recheck.recheck(s, m, tf, control_seeds=control_seeds)
        if r.verdict == "PASS":
            cleared.append((s, m, tf))
            live.beat(6, "re-check", idea=s.label(), cell=f"{m} {tf}",
                      done=i, total=len(survivors),
                      counts={"step6_pass": len(cleared)})
            st["outcome"] = "held at step 6"
        else:
            # A NEAR-MISS AT STEP 6 GETS THE SAME SIX TRIES STEP 4 GIVES A
            # NEAR-MISS AT STEP 3. Nothing was offered here before, so an idea
            # that cleared step 3 and missed the holdout by a hair was deleted
            # in silence. It spends the holdout - see `repair.repair_holdout`.
            attempts, fixed6 = ([], None)
            if r.holdout is not None:
                st["holdout"] = _cell_row(r.holdout)
                st["holdout_span"] = r.holdout_span
            # THE FACTS THE BOARD QUOTES. Kris, 2026-09-24: say "last 3 years
            # PF, win %, R ... last 5 years was ..." instead of explaining
            # what a holdout is. Recent = the step-3 window, full = 5 years.
            st["recent"] = _cell_row(check.check(
                s, cells.load(m, tf), market=m, tf=tf,
                control_seeds=control_seeds))
            if r.full is not None:
                st["full"] = _cell_row(r.full)
                attempts, fixed6 = repair.repair_holdout(
                    s, r.holdout, m, tf, control_seeds=control_seeds)
            st["repairs"] += [{"step": 6, "name": a.repair,
                               "verdict": a.after.verdict,
                               "cell": f"{a.after.market} {a.after.tf}",
                               "reasons": list(a.after.reasons)} for a in attempts]
            rec["repair6_attempts"] = rec.get("repair6_attempts", 0) + len(attempts)
            if fixed6 is not None:
                cleared.append((fixed6, m, tf))
                origin[fixed6.label()] = origin.get(s.label(), s.label())
                queue.keep(fixed6, f"step 6 repair on {m} {tf} "
                                   f"(NOT holdout-clean)", reached=6)
                st["outcome"] = "repaired at step 6 (NOT holdout-clean)"
                rec["repaired_at_6"] = rec.get("repaired_at_6", 0) + 1
                continue
            # THE GATE, NOT THE STEP. This recorded a hardcoded "holdout" and
            # the board therefore told Kris his script "fell apart on the years
            # it was not selected on" - when it had in fact failed the TRADE
            # COUNT floor on that window and its edge was never measured there
            # at all. Two different facts, and the wrong one was displayed.
            g = repair.failed_gate(r.holdout) if r.holdout else "other"
            why = "; ".join(r.holdout.reasons) if r.holdout else "no holdout data"
            queue.mark_tried(s, "FAIL", f"step 6: {why}", step=6,
                             gate=g or "other")
            st["outcome"] = f"stopped at step 6 ({g or 'other'})"
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
        stx = by_label.get(origin.get(s.label(), s.label()))
        if stx is not None:
            stx["outcome"] = ("scored at step 7 (repaired at step 6, NOT holdout-clean)"
                              if "NOT holdout-clean" in stx.get("outcome", "")
                              else "scored at step 7")
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
    for st in stories:
        record_idea(st)
    rec["seconds"] = round(time.time() - t0, 1)
    # The last beat keeps the uptime clock alive between passes - the sleep
    # between them is longer than a step, and without this the dashboard would
    # call the factory dead every time it rested.
    live.beat(0, "resting", detail=f"pass finished in {rec['seconds']:.0f}s",
              counts={"step3_pass": s3, "step4_repaired": s4, "gates": gates})
    return rec


def _cell_row(c) -> dict:
    """One cell's four gates, whatever they said. Nothing short-circuits now,
    so every number here is real rather than "not reached"."""
    return {"cell": f"{c.market} {c.tf}", "verdict": c.verdict,
            "trades": c.n_trades, "per_day": round(c.trades_per_day, 3),
            "mean_r": (None if c.mean_r.get(1.0) is None
                       else round(c.mean_r.get(1.0, float("nan")), 4)),
            "drop_best": (None if c.mean_r_drop_best != c.mean_r_drop_best
                          else round(c.mean_r_drop_best, 4)),
            "control_p90": (None if c.control_p90 != c.control_p90
                            else round(c.control_p90, 4)),
            "pf": (None if c.pf != c.pf or c.pf == float("inf")
                   else round(c.pf, 3)),
            "win_pct": None if c.win_pct != c.win_pct else round(c.win_pct, 1),
            "reasons": list(c.reasons), "flags": list(c.flags)}


def scorecard(strategy, market: str, tf: str) -> dict:
    """The numbers Kris reads a strategy by, on the 2023-2026 window.

    *"i want to see in table this strategy together with upcoming strategies
    like its PF, DD, evaluation time etc, from 2023 to 2026 always."*

    Computed for EVERY idea that produced a usable cell, not only for the ones
    that reach step 7. An idea that stopped at step 6 still has a profit
    factor and a drawdown on the recent window, and refusing to show them is
    what made the board feel like a bin rather than a workbench.
    """
    frame = cells.load(market, tf)
    if not len(frame):
        return {}
    rt = cells.cost_bps(market)
    trades = build.run(strategy, frame.reset_index(drop=True), cost_bps=rt)
    if len(trades) < 2:
        return {}
    r = np.array([t.r for t in trades], dtype=float)
    wins, losses = r[r > 0], r[r <= 0]
    gross_w, gross_l = float(wins.sum()), float(-losses.sum())
    eq = np.concatenate(([0.0], np.cumsum(r)))
    dd_r = float((eq - np.maximum.accumulate(eq)).min())
    days = check.trading_days(frame)

    out = {
        "cell": f"{market} {tf}", "market": market, "tf": tf,
        "trades": len(r),
        "per_day": round(len(r) / days, 3) if days else None,
        "pf": round(gross_w / gross_l, 3) if gross_l else None,
        "win_pct": round(100 * len(wins) / len(r), 1),
        "mean_r": round(float(r.mean()), 4),
        "total_r": round(float(r.sum()), 1),
        "max_dd_r": round(dd_r, 1),
        "hold_days": round(check.mean_hold_days(trades, frame, days), 2),
    }
    # Evaluation pace: the risk ladder is arithmetic on a fixed trade series,
    # so it selects nothing and is always allowed. The rung reported is the
    # fastest one the project's own constraints permit.
    try:
        exit_ts = frame.index[[t.exit_bar for t in trades]]
        daily = pd.Series(r, index=pd.DatetimeIndex(exit_ts)).resample("1D").sum()
        rows = riskladder.ladder(daily, r)
        best = min((x for x in rows if x.get("expected_days")),
                   key=lambda x: x["expected_days"], default=None)
        if best:
            out.update(risk_pct=round(best["risk"] * 100, 2),
                       pass_pct=round(best["pass_rate"] * 100, 1),
                       eval_days=round(best["expected_days"], 1),
                       median_days=best["median_days"],
                       accounts=round(1 / best["pass_rate"], 2))
    except Exception:                       # a pace number is never worth a crash
        pass
    return out


def _headline_cell(strategy, checks):
    """Which of the 24 cells the scoreboard should show for this idea.

    NOT the highest profit per trade, which is what a first version used and
    which is wrong for this project. Kris, 2026-09-23, on seeing 0.156
    trades/day: *"we were talking about 0.33 tpd, now you added 1.56? i dont
    get it."* The cell had silently moved from gold 1h to gold 4h because 4h
    earns more per trade - and on this rule the whole timeframe ladder is
    monotone in exactly that way:

        15m  1.59/day  PF 0.99  7.5 eval days   3.76 accounts
        1h   0.47/day  PF 1.29  18.1            3.62
        4h   0.16/day  PF 1.80  37.7            2.35
        1d   0.04/day  PF 3.23  71.2            1.78

    Sorting on profit per trade always lands on the slowest chart, and the
    pace target is 5-14 days. So the headline is the FASTEST cell that still
    makes money, and the drill-down shows the whole ladder - the trade-off is
    the finding, not a number to hide.
    """
    usable = [c for c in checks if c.mean_r.get(1.0, -9e9) > 0]
    if not usable:
        return max(checks, key=lambda c: c.mean_r.get(1.0, -9e9), default=None)

    paced = []
    for c in usable:
        k = scorecard(strategy, c.market, c.tf)
        if k.get("eval_days"):
            paced.append((k["eval_days"], c))
    if paced:
        return min(paced, key=lambda x: x[0])[1]
    return max(usable, key=lambda c: c.mean_r.get(1.0, -9e9))


def ladder_rows(strategy, market: str) -> list[dict]:
    """The same rule on all four timeframes of one market.

    The trade-off Kris found by asking about one number: slower charts earn
    more per trade and take far longer to resolve an evaluation. Showing it
    beside the headline is the difference between a number and a choice.
    """
    out = []
    for tf in cells.TIMEFRAMES:
        k = scorecard(strategy, market, tf)
        if k:
            out.append(k)
    return out


def record_idea(rec: dict) -> None:
    IDEAS.parent.mkdir(parents=True, exist_ok=True)
    with IDEAS.open("a") as fh:
        fh.write(json.dumps(rec, separators=(",", ":")) + "\n")


def ideas(limit: int = 500) -> list[dict]:
    if not IDEAS.exists():
        return []
    out = []
    for line in IDEAS.read_text().splitlines():
        if line.strip():
            try:
                out.append(json.loads(line))
            except ValueError:
                continue
    return out[-limit:]


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
