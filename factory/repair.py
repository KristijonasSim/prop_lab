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


#: THE LIST. First fixed 2026-09-22 at twelve; WIDENED 2026-09-24 on Kris's
#: word: *"i dont care how many repairs you will do it can be 1k repairs"*.
#: Every attempt is still logged and the first pass still wins, so the width is
#: a known number of extra draws - and step 6 is what prices them.
#:
#: Exits: every stop x target x hold on the grid below (answers "either").
#: Filters: sessions, trend, vwap, volatility regime (answer "edge" - a filter
#: spends trades, so a thin idea is never handed one).
STOPS = (1.0, 1.5, 2.0, 3.0, 4.0)
TARGETS = (1.5, 2.0, 3.0, 4.0, 6.0)
HOLDS = (12, 24, 48, 96)
#: What an idea carries when step 2 builds it. A grid point's name lists only
#: what differs from this, so the one-lever repairs read "hold 24", "stop 3".
BASE = (2.0, 3.0, 48)
ASIA = (-0.5, 6.5)
FAST_EMA = 50


def _exit(stop: float, target: float, hold: int) -> Repair:
    parts = [f"stop {stop:g}" if stop != BASE[0] else "",
             f"target {target:g}" if target != BASE[1] else "",
             f"hold {hold}" if hold != BASE[2] else ""]
    tag = " ".join(p for p in parts if p)
    return Repair(tag, "either",
                  _set(tag, stop_atr=stop, target_atr=target, max_hold=hold),
                  "exit grid")


def _ema_trend(n: int):
    def f(s: Strategy) -> Strategy:
        return _add(s, Condition(Term("price"),
                                 "above" if s.side == "long" else "below",
                                 Term("ema", n)), tag=f"with ema{n}")
    return f


def _quiet():
    def f(s: Strategy) -> Strategy:
        return _add(s, Condition(Term("atr", FAST_ATR), "below",
                                 Term("atr", SLOW_ATR)), tag="quiet")
    return f


FILTERS: tuple[Repair, ...] = (
    Repair("London+NY", "edge", _session(*LONDON_NY, tag="London+NY"), "liquid hours"),
    Repair("NY only", "edge", _session(*NY, tag="NY only"), "busiest window"),
    Repair("Asia only", "edge", _session(*ASIA, tag="Asia only"), "quiet hours"),
    Repair("with trend", "edge", _trend(True), "price on the trade's side of EMA200"),
    Repair("against trend", "edge", _trend(False), "control for the line above"),
    Repair(f"with ema{FAST_EMA}", "edge", _ema_trend(FAST_EMA), "shorter trend"),
    Repair("price past vwap", "edge", _vwap_side(), "rolling vwap side"),
    Repair("busy", "edge", _fast_vol(), "short-term vol above long-term"),
    Repair("quiet", "edge", _quiet(), "short-term vol below long-term"),
)

EXITS: tuple[Repair, ...] = tuple(
    _exit(st, tg, h) for st in STOPS for tg in TARGETS for h in HOLDS
    if (st, tg, h) != BASE)

REPAIRS: tuple[Repair, ...] = FILTERS + EXITS


def _levers(r: Repair) -> int:
    """How many things a repair changes. Smallest changes are tried first."""
    return 1 if r.answers == "edge" else len(r.name.split()) // 2


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
    return sorted((r for r in REPAIRS if r.answers in (kind, "either")),
                  key=_levers)


def _same(a: Strategy, b: Strategy) -> bool:
    """A grid point that is the idea's own exit is not a repair."""
    return (a.entry == b.entry and a.stop_atr == b.stop_atr
            and a.target_atr == b.target_atr and a.max_hold == b.max_hold)


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
        if _same(cand, strategy):
            continue
        after = check.check(cand, frame, market=target.market, tf=target.tf,
                            days=days, control_seeds=control_seeds)
        attempts.append(Attempt(repair=r.name, before=target, after=after))
        if after.verdict == "PASS" and fixed is None:
            fixed = cand
    return attempts, fixed


def repair_holdout(strategy: Strategy, holdout: Check, market: str, tf: str, *,
                   control_seeds: int = check.CONTROL_SEEDS
                   ) -> tuple[list[Attempt], Strategy | None]:
    """Step 4's fixed list, applied to a near-miss at STEP 6.

    Kris, 2026-09-23: *"if we miss one of our goals by tiny margin we enter
    step 4 which is repair and try to upgrade it - so first of all this didint
    even happened."* He is right: step 4 only ever ran on a step-3 failure, so
    an idea that cleared step 3 and then missed the holdout by a hair was
    deleted with nothing offered. His first translated script missed the pace
    flag there by 17%.

    **THE COST, AND IT IS REAL: THIS SPENDS THE HOLDOUT.** Step 6 is worth
    what it is worth because the idea was never selected on those years. Try
    twelve repairs against them and it has been, so the repaired rule no
    longer has an independent test anywhere - which is why the survivor is
    flagged `repaired_at_6` and why the bar is BOTH windows, not just the one
    it failed. With the 2026-09-24 grid this is ~100 draws on the holdout, so a
    step-6 repair is effectively fitted on all five years - flagged, not hidden.

    A repaired rule must pass the holdout AND still pass the window it already
    passed. A change that fixes the old years by breaking the recent ones is
    not a repair.
    """
    if not near_miss(holdout):
        return [], None

    hold_frame = cells.holdout(market, tf)
    recent = cells.load(market, tf)
    if not len(hold_frame) or not len(recent):
        return [], None
    hold_days = check.trading_days(cells.holdout(market, "1h")) or None
    recent_days = cells.trading_days(market)

    attempts: list[Attempt] = []
    fixed: Strategy | None = None
    for rp in repairs_for(failed_gate(holdout)):
        cand = rp.apply(strategy)
        if _same(cand, strategy):
            continue
        after = check.check(cand, hold_frame, market=market, tf=tf,
                            days=hold_days, control_seeds=control_seeds)
        attempts.append(Attempt(repair=rp.name, before=holdout, after=after))
        if after.verdict != "PASS" or fixed is not None:
            continue
        still = check.check(cand, recent, market=market, tf=tf,
                            days=recent_days, control_seeds=control_seeds)
        if still.verdict == "PASS":
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
