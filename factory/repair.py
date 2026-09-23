"""STEP 4 — REPAIR THE NEAR-MISSES. A fixed list, not a hunt.

    docs/WORKFLOW.drawio   the picture
    docs/STEP4.md          the design, the risk, and what it is measured against

Kris, 2026-09-22: *"if it fails 3rd step but not that far off try to tweak and
play with it, if no then move on."*

THE LINE THIS FILE WALKS. Taking a failing idea and tweaking it until it passes
is how a pipeline manufactures results - 19 of 45 generated ideas already clear
the cost gate, so poking at one long enough will get it through the rest by
luck. What makes a repair stage honest is that it is **a fixed list applied
identically to every near-miss**, decided before any of them were seen, with
every attempt logged. Then the number of extra trials is known instead of
unbounded, and steps 5 and 6 still have to be beaten afterwards.

So: no adaptive search, no second round, no repair of a repair. An idea gets
its matching subset of `REPAIRS` once, on the one cell it came closest on, and
whatever happens it then moves on.

WHY THE LIST IS SPLIT BY WHAT FAILED - and this is the finding that shaped it.
`CLAUDE.md`, 2026-09-08: 25 entry filters were screened on H-027 gold and **24
of 25 raised profit factor while LOWERING R per day**, which makes an
evaluation slower; every session window was worse on both timeframes; the one
survivor lost to its own shuffled control. A filter buys quality by spending
trades. Step 3's commonest failure is *too few trades* - most generated ideas
sit at 0.15-0.5 a day against a 0.4 floor - so handing a thin idea a filter
makes its actual problem worse.

    failed on TRADES  ->  repairs that free the slot sooner
    failed on EDGE    ->  filters, which spend trades to buy quality
    either            ->  the stop and target widenings

WHY REPAIRS ARE TRIED ON ONE CELL AND NOT ON ALL 24. Step 3 already searched 24
cells; re-searching them for every repair would multiply the search by 24 again
and is exactly the move `NEXT.md` records being withdrawn over. The repair is
applied to the cell the idea came closest on, and a survivor's identity is
(idea + repair, that cell).

WHAT IS NOT DONE HERE. No walk-forward. Every idea the factory makes has a
FIXED stop, target and hold (`sources/invent.py`), so nothing is fitted inside
a training window and a train/test split would protect against nothing. What
protects this stage is the paired null (step 5) and the five-year re-check
(step 6), and `repaired=True` is carried through so we can measure whether
repaired survivors die at step 6 more often than first-try ones.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Callable

import numpy as np

from factory import cells, check
from factory.check import Check
from factory.spec import Condition, Strategy, Term

#: How close to a gate still counts as "not that far off".
#:
#: On the COUNT gates the shortfall is a ratio, so a quarter is a quarter:
#: 0.30 trades/day against the 0.4 floor, or 75 trades against 100.
NEAR_RATIO = 0.75
#: On the EDGE gates the threshold is zero and a ratio means nothing, so the
#: scale used is the result's own standard error. Within one standard error of
#: breakeven is a result that noise alone could have flipped - which is the
#: honest reading of "not far off". Further than that and a tweak is not
#: repairing anything, it is drawing again.
NEAR_SIGMA = 1.0

#: Session windows, in UTC hours. `above`/`below` are strict, so the half-hour
#: offsets make the ends inclusive: 6.5 < hour < 16.5 is 07:00-16:00.
LONDON_NY = (6.5, 16.5)
NY = (12.5, 20.5)
#: Lengths used by the filter repairs. Fixed, so they are not a search.
TREND_LEN = 200
VWAP_LEN = 20
FAST_ATR, SLOW_ATR = 14, 100


@dataclass(frozen=True)
class Repair:
    """One named change, and which kind of failure it is allowed to answer."""
    name: str
    answers: str                      # "trades" | "edge" | "either"
    apply: Callable[[Strategy], Strategy]
    why: str


def _add(s: Strategy, *conds: Condition, tag: str) -> Strategy:
    """Append conditions. Every condition must hold, so this narrows entry."""
    return replace(s, entry=s.entry + conds, name=f"{s.name} [{tag}]")


def _session(lo: float, hi: float, tag: str):
    def f(s: Strategy) -> Strategy:
        return _add(s,
                    Condition(Term("hour"), "above", Term("const", value=lo)),
                    Condition(Term("hour"), "below", Term("const", value=hi)),
                    tag=tag)
    return f


def _trend(with_it: bool):
    """Only take the signal when price agrees (or disagrees) with EMA200.

    The sense is flipped for a short, so "with the trend" means the same thing
    on both sides rather than meaning "long-biased".
    """
    def f(s: Strategy) -> Strategy:
        up = (s.side == "long") == with_it
        return _add(s, Condition(Term("price"), "above" if up else "below",
                                 Term("ema", TREND_LEN)),
                    tag="with trend" if with_it else "against trend")
    return f


def _vwap_side():
    def f(s: Strategy) -> Strategy:
        up = s.side == "long"
        return _add(s, Condition(Term("price"), "above" if up else "below",
                                 Term("vwap", VWAP_LEN)),
                    tag="price past vwap")
    return f


def _fast_vol():
    """Short-term volatility above long-term - a regime filter the grammar can
    state without needing "above its own median", which it cannot express."""
    def f(s: Strategy) -> Strategy:
        return _add(s, Condition(Term("atr", FAST_ATR), "above",
                                 Term("atr", SLOW_ATR)), tag="busy")
    return f


def _set(tag: str, **kw):
    def f(s: Strategy) -> Strategy:
        return replace(s, name=f"{s.name} [{tag}]", **kw)
    return f


#: THE LIST. Fixed on 2026-09-22, before any near-miss was looked at.
#: Adding to it later is a new search and has to be logged as one.
REPAIRS: tuple[Repair, ...] = (
    # --- the idea does not trade enough: let the slot come free sooner ------
    Repair("hold 24", "trades", _set("hold 24", max_hold=24),
           "one position at a time, so a shorter hold is the direct lever"),
    Repair("hold 12", "trades", _set("hold 12", max_hold=12),
           "same lever, harder"),
    Repair("target 2", "trades", _set("target 2", target_atr=2.0),
           "a nearer target is hit sooner and frees the slot"),
    Repair("stop 1.5", "trades", _set("stop 1.5", stop_atr=1.5),
           "a nearer stop does the same, at the cost of being hit more often"),

    # --- the idea trades enough but the edge is weak: spend trades ---------
    Repair("London+NY", "edge", _session(*LONDON_NY, tag="London+NY"),
           "the liquid hours. Measured WORSE on H-027; kept because that was "
           "one strategy and this list is applied to all of them"),
    Repair("NY only", "edge", _session(*NY, tag="NY only"),
           "the single busiest window"),
    Repair("with trend", "edge", _trend(True),
           "the one H-027 filter that survived screening, before it lost to "
           "its own shuffled control"),
    Repair("against trend", "edge", _trend(False),
           "the control for the line above. If both directions 'help', the "
           "help is the filter cutting trades, not the trend"),
    Repair("price past vwap", "edge", _vwap_side(),
           "a rolling volume-weighted reference, not H-027's session anchor"),
    Repair("busy", "edge", _fast_vol(),
           "short-term vol above long-term. A breakout wants a live market"),

    # --- either -----------------------------------------------------------
    Repair("stop 3", "either", _set("stop 3", stop_atr=3.0),
           "more room, fewer stop-outs, a smaller R on each win"),
    Repair("target 5", "either", _set("target 5", target_atr=5.0),
           "let the winners run, at a lower hit rate"),
)


def failed_gate(c: Check) -> str:
    """Which gate this cell died on: trades, cost, concentration, drift, or "".

    Gates short-circuit, so a Check carries only its FIRST failure - which is
    the one worth repairing.
    """
    if c.verdict == "PASS":
        return ""
    r = " ".join(c.reasons)
    if "trades" in r and "random" not in r:
        return "trades"
    if "at 1x cost" in r:
        return "cost"
    if "without its best" in r:
        return "concentration"
    if "random entry" in r:
        return "drift"
    return "other"


def near_miss(c: Check) -> bool:
    """Is this cell close enough to the gate it failed to be worth a tweak?

    On the edge gates closeness is measured in the result's own standard
    errors, not as a percentage: the threshold there is zero and a percentage
    of zero says nothing. `check.Check` carries those errors for this.
    """
    gate = failed_gate(c)
    if gate == "":
        return False
    if gate == "trades":
        return (c.trades_per_day >= NEAR_RATIO * check.MIN_TRADES_PER_DAY
                and c.n_trades >= NEAR_RATIO * check.MIN_TRADES)
    if gate == "cost":
        se = c.mean_r_se
        return bool(se == se and c.mean_r[1.0] > -NEAR_SIGMA * se)
    if gate == "concentration":
        se = c.mean_r_drop_best_se
        return bool(se == se and c.mean_r_drop_best > -NEAR_SIGMA * se)
    if gate == "drift":
        # It beat the middle of its own control but not the 90th percentile.
        return c.mean_r[1.0] > c.control_median
    return False


def closeness(c: Check) -> float:
    """How close this cell came to the gate it failed, on a 0-1 scale.

    ONE SCALE FOR FOUR GATES, so the near-misses of an idea can be ranked
    against each other. A cell that failed on trade count has no mean R at all
    (the gates short-circuit), so ranking near-misses by mean R silently put
    every count-failure at the bottom and picked between them arbitrarily.
    Each gate is scored as "what fraction of the way there did it get":

        trades          the worse of tpd/floor and n/100
        cost            1 + meanR/se     -> 1.0 at breakeven, 0.0 at -1 se
        concentration   the same, on the trimmed mean
        drift           meanR / the control's p90
    """
    gate = failed_gate(c)
    if gate == "trades":
        return min(c.trades_per_day / check.MIN_TRADES_PER_DAY,
                   c.n_trades / check.MIN_TRADES)
    if gate == "cost" and c.mean_r_se == c.mean_r_se and c.mean_r_se:
        return 1.0 + c.mean_r[1.0] / (NEAR_SIGMA * c.mean_r_se)
    if gate == "concentration" and c.mean_r_drop_best_se:
        return 1.0 + c.mean_r_drop_best / (NEAR_SIGMA * c.mean_r_drop_best_se)
    if gate == "drift" and c.control_p90:
        return c.mean_r[1.0] / c.control_p90
    return 0.0


def repairs_for(gate: str) -> list[Repair]:
    """The subset of the fixed list that answers this failure. Never all of it."""
    kind = "trades" if gate == "trades" else "edge"
    return [r for r in REPAIRS if r.answers in (kind, "either")]


@dataclass
class Attempt:
    """One repair, tried once, on one cell."""
    repair: str
    before: Check
    after: Check

    @property
    def fixed(self) -> bool:
        return self.after.verdict == "PASS"


def best_near_miss(checks: list[Check]) -> Check | None:
    """The one cell worth repairing: the near-miss with the strongest mean R.

    One cell, not several. Repairing every near-miss cell of an idea would
    re-open the 24-way search the repair stage is explicitly not allowed to
    re-open.
    """
    near = [c for c in checks if near_miss(c)]
    if not near:
        return None
    return max(near, key=closeness)


def repair(strategy: Strategy, checks: list[Check], *,
           control_seeds: int = check.CONTROL_SEEDS, loader=None
           ) -> tuple[list[Attempt], Strategy | None]:
    """Try the matching repairs on the idea's best near-miss cell.

    Returns every attempt - the failures are the denominator - and the first
    repaired strategy that passes, or None. First, not best: picking the best
    of several passing repairs would be a selection on the test data, which is
    the thing this whole stage is built to avoid.
    """
    target = best_near_miss(checks)
    if target is None:
        return [], None

    frame = (loader or cells.load)(target.market, target.tf)
    days = check.trading_days(frame)
    attempts: list[Attempt] = []
    fixed: Strategy | None = None
    for r in repairs_for(failed_gate(target)):
        cand = r.apply(strategy)
        after = check.check(cand, frame, market=target.market, tf=target.tf,
                            days=days, control_seeds=control_seeds)
        attempts.append(Attempt(repair=r.name, before=target, after=after))
        if after.verdict == "PASS" and fixed is None:
            fixed = cand
    return attempts, fixed


def _main(argv=None) -> int:
    """Steps 3 and 4 end to end: check an idea, repair it if it came close."""
    import argparse

    from factory import queue

    ap = argparse.ArgumentParser(description=_main.__doc__)
    ap.add_argument("-n", "--count", type=int, default=5)
    ap.add_argument("--market", action="append")
    ap.add_argument("--tf", action="append")
    ap.add_argument("--seeds", type=int, default=check.CONTROL_SEEDS)
    a = ap.parse_args(argv)

    cell_list = cells.all_cells(a.market, tuple(a.tf) if a.tf else None)
    print(f"steps 3+4 on {len(cell_list)} cells\n")
    head = (f"{'idea':46}{'cell':14}{'step':6}{'trades':>7}{'tpd':>7}"
            f"{'mean R':>9}  outcome")
    print(head); print("-" * len(head))

    for _ in range(a.count):
        s = queue.take()
        if s is None:
            print("queue empty - run `python -m factory.fill`")
            break
        checks = check.check_all(s, cell_list, control_seeds=a.seeds)
        verdict, shown = check.verdict_of(checks)
        best = shown[0]
        print(f"{s.label()[:44]:46}{best.cell:14}{'3':6}{best.n_trades:>7}"
              f"{best.trades_per_day:>7.2f}{best.mean_r.get(1.0, float('nan')):>+9.3f}"
              f"  {verdict}: {'; '.join(best.reasons) or 'passed'}")

        note = f"step3 {verdict}"
        if verdict == "FAIL":
            attempts, fixed = repair(s, checks, control_seeds=a.seeds)
            if not attempts:
                print(f"{'':46}{'':14}{'4':6}{'':>7}{'':>7}{'':>9}"
                      f"  not close enough to repair")
            elif attempts:
                b = attempts[0].before
                print(f"{'  repairing on its closest cell':46}{b.cell:14}{'4':6}"
                      f"{b.n_trades:>7}{b.trades_per_day:>7.2f}"
                      f"{b.mean_r.get(1.0, float('nan')):>+9.3f}"
                      f"  baseline: {'; '.join(b.reasons)}")
            for at in attempts:
                print(f"{('  + ' + at.repair)[:44]:46}{at.after.cell:14}{'4':6}"
                      f"{at.after.n_trades:>7}{at.after.trades_per_day:>7.2f}"
                      f"{at.after.mean_r.get(1.0, float('nan')):>+9.3f}"
                      f"  {at.after.verdict}: "
                      f"{'; '.join(at.after.reasons) or 'REPAIRED'}")
            if fixed is not None:
                tag = fixed.name.split("[")[-1].rstrip("]")
                queue.keep(fixed, note=f"repaired via {tag}")
                note = f"step4 REPAIRED via {tag}"
            elif attempts:
                note = f"step4 {len(attempts)} repairs, none worked"
        queue.mark_tried(s, verdict=verdict, note=note)
        print()
    return 0


if __name__ == "__main__":
    import sys as _sys
    _sys.exit(_main())
