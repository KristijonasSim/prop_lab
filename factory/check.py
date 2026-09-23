"""STEP 3 — THE QUICK CHECK. Four questions, seconds, cheapest kill first.

    docs/WORKFLOW.drawio   the picture
    docs/STEP3.md          the design and the measurements behind every number

THE UNIT IS A TRADE (Kris, 2026-09-21). Step 7 counts money in trades and step 2
produces trades, so nothing is translated in between and nothing is lost.

    1  ENOUGH TRADES?    >= 0.4 trades/day AND >= 100 trades
    2  BEATS COSTS?      mean R > 0 at 1x the crossing cost; 1x/2x/3x reported
    3  ONE LUCKY RUN?    mean R still > 0 after deleting the best 5 trades
    4  IDEA, OR DRIFT?   beats the p90 of its own random-entry control

THIS IS A FLOOR, NOT A SCORE. Passing means an idea has earned the hours step 4
costs. No number produced here is quotable as a result.

WHY NOT `core/screen.py`. That screen reads a SIGNAL against forward BAR
returns, and its third gate - "the median moves, not just the mean" - cannot be
carried over. A trade with a stop at 1R has a median of about -1R whenever the
win rate is under 50%, which is the ordinary shape of a breakout. Measured on 40
generated ideas on gold 1h: 39 of 40 had a median between -1.00 and -1.05, and
the one exception was the only rule that won more than half its trades. A median
gate here would reject H-027's own family. `core/screen.py` stays, for signals.

WHAT EACH GATE COST WHEN IT WAS MEASURED, 45 ideas, gold 1h (`docs/STEP3.md`):

    all ideas                                             45
    ...makes money at 1x cost                             19
    ...and survives deleting its best 5 trades            19
    ...and beats its own random-entry control              5

Gate 3 removed NOTHING on that sample and gate 4 removed fourteen. Both are
kept: gate 3 is nearly free and it is the check that catches the shape gate 4
cannot (one enormous trade inside a rule that does beat random), and on the same
sample it did remove `short when price below lowest200`, which held 22.3% of its
total R in a single trade out of 83.

WHY THE COST GATE IS AT 1x AND NOT 2x. Kris, 2026-09-22: *"if we charge normal
fees and it survives just a bit, we could make improvements... with double fees
we already exclude some that would pass single fees."* He is right and it was
measured: at 2x the survivor count went 19 -> 17, and once gate 4 was applied
BOTH multiples left exactly 5. The 2x gate bought nothing and cost precisely
what he said it costs. Cost sensitivity moves to step 7, where the rule is fixed
and the fills are honest. 1x here means 1x the round trip in `core/markets.py`,
which on gold is measured and on USDJPY is an assumption.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from factory import build, cells
from factory.spec import Strategy

#: THE TWO NUMBERS DO DIFFERENT JOBS, AND ONLY ONE OF THEM IS A KILL.
#: Split 2026-09-23 after Kris: *"if this strategy is 0.33 a day but its PF is
#: 3 and very low dd, you would just say its unusable... why?"*
#:
#: `MIN_TRADES` is a STATISTICAL floor. Under a hundred trades the mean is a
#: story about a few episodes and no amount of patience fixes it. It kills.
#:
#: `MIN_TRADES_PER_DAY` is a PACE preference - Kris, 2026-09-21, "this is day
#: trading". A rule with 500 trades at 0.3/day is perfectly measurable; it is
#: only slower to resolve an evaluation, and `core/riskladder` already prices
#: exactly that as expected days. So it is now a FLAG carried to step 7, not a
#: delete. Killing on it threw away the answer along with the idea: Kris's
#: first translated script was reported as "too few trades" on the holdout
#: when what was true is that it LOSES MONEY there and scores worse than
#: random - the gate fired first and hid the finding.
MIN_TRADES_PER_DAY = 0.4
MIN_TRADES = 100
#: Gate 3 deletes this many of the best trades and asks for a profit anyway.
DROP_BEST = 5
#: Gate 4. Seeds of the random-entry control, and the percentile it must beat.
CONTROL_SEEDS = 20
CONTROL_PCTILE = 90.0
#: Cost multiples reported. The GATE is the first one.
COST_MULTIPLES = (1.0, 2.0, 3.0)


@dataclass
class Check:
    """What step 3 saw. `verdict` is PASS or FAIL and `reasons` says why."""
    idea: str
    market: str
    tf: str
    verdict: str = "FAIL"
    n_trades: int = 0
    trades_per_day: float = 0.0
    mean_r: dict[float, float] = field(default_factory=dict)   # cost mult -> mean R
    mean_r_drop_best: float = float("nan")
    #: Standard error of each mean above. Step 4 needs a SCALE to decide what
    #: "not far off" means on a gate whose threshold is zero, and a percentage
    #: of zero is not one. See `repair.NEAR_SIGMA`.
    mean_r_se: float = float("nan")
    mean_r_drop_best_se: float = float("nan")
    mean_hold_days: float = float("nan")
    control_p90: float = float("nan")
    control_median: float = float("nan")
    round_trip_bps: float = float("nan")
    reasons: list[str] = field(default_factory=list)
    #: Things worth knowing that are NOT reasons to reject. `slow` means it
    #: trades under the pace preference; step 7 prices that as expected days.
    flags: list[str] = field(default_factory=list)

    @property
    def cell(self) -> str:
        return f"{self.market} {self.tf}"

    def __str__(self) -> str:
        m1 = self.mean_r.get(1.0, float("nan"))
        return (f"{self.idea[:40]:42}{self.cell:14}{self.verdict:6}"
                f"{self.n_trades:>7}{self.trades_per_day:>7.2f}"
                f"{self.mean_hold_days:>7.1f}{m1:>+9.3f}"
                f"{self.mean_r_drop_best:>+9.3f}{self.control_p90:>+9.3f}"
                f"  {'; '.join(self.reasons + self.flags)}")


#: A day holding at least this share of a full session's bars is not "a day".
#: Used to define what a full session is; see `trading_days`.
FULL_DAY_PCTILE = 90.0


def trading_days(frame: pd.DataFrame) -> float:
    """FULL SESSIONS the market was open. Not calendar days, not bar-days.

    Three definitions were available and only this one is stable:

    * **Calendar days** overstates by 7/5 - the weekend is not a trading day and
      Kris's 0.4 floor is a rule about days he could trade.
    * **Days that contain at least one live bar** is what a first version used
      and it is wrong at the edges. Gold's week opens at 22:00 UTC on a Sunday,
      so 155 two-hour Sundays were each counted as a full day, inflating the
      denominator by 20% and understating trades/day by the same.
    * **Live bars divided by the bars in a full session** is what this returns.
      It handles the Sunday open, the daily CME break and half-days by itself,
      and - the property that matters - it gives the SAME number of days for a
      market whatever timeframe it is measured on, so a trades/day figure is
      comparable across the 24 cells.

    Dead bars are excluded, for the same reason every other calculation here
    excludes them: `CLAUDE.md` records that 21.5% of the gold series is padded
    weekend at a frozen price.
    """
    if not isinstance(frame.index, pd.DatetimeIndex):
        raise TypeError("trading_days needs a DatetimeIndex")
    live = frame[frame["volume"] > 0] if "volume" in frame else frame
    if not len(live):
        return float("nan")
    per_day = live.groupby(live.index.normalize()).size()
    full_session = float(np.percentile(per_day, FULL_DAY_PCTILE))
    return len(live) / full_session if full_session else float("nan")


def mean_hold_days(trades, frame: pd.DataFrame, days: float) -> float:
    """Average time a position is held, in days. Reported beside trades/day.

    WHY IT IS HERE, AND WHAT IT REPLACES. A first version of this file reported
    a "ceiling" of `bars_per_day / max_hold` and labelled any cell below the
    0.4 floor CELL IMPOSSIBLE, on the reasoning that one position at a time for
    `max_hold` bars caps the rate. **That was wrong and a test caught it.**
    `max_hold` is a maximum, not the hold: almost every trade exits earlier on
    its stop or target, so the real bound is one trade per BAR, which is 6/day
    on 4h and 1/day on 1d - above the floor in both cases. No cell is
    structurally impossible.

    What is true is milder and worth reporting: a low trade rate on 4h and 1d
    comes from the hold, not from the entry rule being fussy. Saying so with the
    measured mean hold states it without overclaiming.
    """
    live = int((frame["volume"] > 0).sum()) if "volume" in frame else len(frame)
    if not trades or not days or not live:
        return float("nan")
    bars_per_day = live / days
    held = float(np.mean([t.exit_bar - t.entry_bar for t in trades]))
    return held / bars_per_day


def _stderr(x: np.ndarray) -> float:
    """Standard error of the mean. nan on a single observation, by definition."""
    return float(np.std(x, ddof=1) / np.sqrt(len(x))) if len(x) > 1 else float("nan")


def _r(trades) -> np.ndarray:
    return np.array([t.r for t in trades], dtype=float)


def control_means(strategy: Strategy, frame: pd.DataFrame, cost_bps: float,
                  fire: np.ndarray, atr: np.ndarray,
                  seeds: int = CONTROL_SEEDS) -> np.ndarray:
    """Mean R of the same rule entered at RANDOM bars, once per seed.

    Same side, same stop, same target, same hold, same NUMBER of entries - only
    the bars change. So the difference between this and the real run is the
    entry rule and nothing else.

    WHAT IT IS FOR. Gold rose 123% over the cached window. On 45 generated ideas
    every rule with a positive mean was long, and the control's own median was
    +0.05 to +0.09 R per trade - random long entries on gold, with a 2-ATR stop
    and a 3-ATR target, made money. Fourteen of the nineteen "profitable" ideas
    scored below that. Without this gate step 3 passes 42% of a randomly
    generated idea list and hands step 4 the gold uptrend, fourteen times over.

    It does NOT forbid trading with a trend: all five survivors on that sample
    were long gold too. It forbids trading one WORSE THAN RANDOM.
    """
    n_entries = int(fire.sum())
    if n_entries == 0:
        return np.array([])
    out = []
    for seed in range(seeds):
        rng = np.random.default_rng(seed)
        shuffled = np.zeros_like(fire)
        shuffled[rng.choice(len(fire), size=n_entries, replace=False)] = True
        tr = build.run(strategy, frame, cost_bps=cost_bps, signals=(shuffled, atr))
        out.append(_r(tr).mean() if tr else np.nan)
    return np.asarray(out, dtype=float)


def check(strategy: Strategy, frame: pd.DataFrame, *, market: str, tf: str,
          round_trip_bps: float | None = None, days: float | None = None,
          control_seeds: int = CONTROL_SEEDS) -> Check:
    """Run the four gates on one cell, cheapest first, short-circuiting.

    `days` is the trades/day denominator. Left out, it is measured from THIS
    frame. `check_all` passes the market-level number instead, so that all four
    of a market's cells divide by the same thing and their trades/day figures
    are comparable - see `cells.trading_days`.
    """
    rt = cells.cost_bps(market) if round_trip_bps is None else round_trip_bps
    c = Check(idea=strategy.label(), market=market, tf=tf, round_trip_bps=rt)

    days = trading_days(frame) if days is None else days
    frame = frame.reset_index(drop=True)
    sig = build.series(strategy, frame)

    trades = build.run(strategy, frame, cost_bps=rt, signals=sig)
    c.n_trades = len(trades)
    c.trades_per_day = c.n_trades / days if days else 0.0

    # --- 1. enough trades to measure? ----------------------------------------
    #
    # NOTHING SHORT-CIRCUITS FROM HERE ON. Every check is computed and every
    # failure recorded, because a gate that returns early tells you which gate
    # fired FIRST and not what is true. Kris's first translated script was
    # reported as "too few trades" when it also lost money and scored worse
    # than random on the same window - the useful facts, hidden behind the
    # cheap one. Measuring all four costs milliseconds.
    #
    # The HOLD is reported beside the rate, because on 4h and 1d a rate under
    # the floor is usually a long hold rather than a fussy entry rule, and the
    # two call for different fixes.
    c.mean_hold_days = mean_hold_days(trades, frame, days)
    if c.n_trades < MIN_TRADES:
        c.reasons.append(f"{c.n_trades} trades, under {MIN_TRADES}")
    if c.trades_per_day < MIN_TRADES_PER_DAY:
        c.flags.append(f"slow: {c.trades_per_day:.2f} trades/day, under "
                       f"{MIN_TRADES_PER_DAY} (mean hold "
                       f"{c.mean_hold_days:.1f} days)")
    if not trades:
        c.reasons.append("no trades")
        return c

    r = _r(trades)
    c.mean_r[1.0] = float(r.mean())
    c.mean_r_se = _stderr(r)
    # Re-pricing is exact arithmetic, not a re-run. Cost enters R linearly, so
    # the same trade at multiple m simply loses (m-1) x entry x bps / risk more.
    # Re-running at a higher cost would also re-open `build`'s min-risk guard
    # and change WHICH trades exist, so the multiples would no longer be
    # like-for-like. H-023 stage 14 priced a whole book this way for the same
    # reason. This is arithmetic on a fixed series and selects nothing.
    charged = np.array([t.entry_px * rt / 1e4 / t.risk for t in trades])
    for m in COST_MULTIPLES[1:]:
        c.mean_r[m] = float((r - (m - 1.0) * charged).mean())

    # --- 2. beats costs? -----------------------------------------------------
    if c.mean_r[1.0] <= 0:
        c.reasons.append(f"mean {c.mean_r[1.0]:+.3f} R at 1x cost ({rt:.2f} bps)")

    # --- 3. one lucky run? ---------------------------------------------------
    if len(r) > DROP_BEST:
        trimmed = np.sort(r)[:-DROP_BEST]
        c.mean_r_drop_best = float(trimmed.mean())
        c.mean_r_drop_best_se = _stderr(trimmed)
        if c.mean_r_drop_best <= 0:
            c.reasons.append(f"{c.mean_r_drop_best:+.3f} R without its best "
                             f"{DROP_BEST} trades")

    # --- 4. the idea, or the drift? -----------------------------------------
    ctrl = control_means(strategy, frame, rt, *sig, seeds=control_seeds)
    ctrl = ctrl[~np.isnan(ctrl)]
    if not len(ctrl):
        c.reasons.append("control produced no trades")
    else:
        c.control_median = float(np.median(ctrl))
        c.control_p90 = float(np.percentile(ctrl, CONTROL_PCTILE))
        if c.mean_r[1.0] <= c.control_p90:
            c.reasons.append(f"random entry scores {c.control_p90:+.3f} at p90")

    c.verdict = "FAIL" if c.reasons else "PASS"
    return c


def market_days(sym: str, loader=None) -> float:
    """Full sessions this MARKET was open, measured once on its 1h series.

    All four of a market's cells must divide by the SAME denominator or their
    trades/day figures are not comparable - `cells.trading_days` has the
    measurement. This wrapper is what keeps that true when the bars come from
    somewhere other than the default cache: step 5's scrambled market has to be
    measured through its own loader, not through the real one.
    """
    if loader is None:
        return cells.trading_days(sym)
    return trading_days(loader(sym, "1h"))


def check_all(strategy: Strategy, cell_list=None, *,
              control_seeds: int = CONTROL_SEEDS, loader=None) -> list[Check]:
    """The four gates on every cell. An idea survives if ANY cell passes.

    Kris, 2026-09-21: *"If only ONE of the 24 works, that is fine. Keep it."*
    The cell is part of the survivor's identity and step 4 carries it forward
    rather than searching for it again.

    `loader(sym, tf)` overrides where the bars come from, and exists so that
    step 5 can run this exact function over scrambled markets. Nothing else in
    the gates changes, which is what makes the two counts comparable.
    """
    out = []
    for sym, tf in (cell_list or cells.all_cells()):
        frame = (loader or cells.load)(sym, tf)
        if not len(frame):
            continue
        out.append(check(strategy, frame, market=sym, tf=tf,
                         days=market_days(sym, loader),
                         control_seeds=control_seeds))
    return out


def verdict_of(checks: list[Check]) -> tuple[str, list[Check]]:
    """PASS plus the passing cells, or FAIL plus the cells that came closest."""
    passed = [c for c in checks if c.verdict == "PASS"]
    if passed:
        return "PASS", sorted(passed, key=lambda c: -c.mean_r.get(1.0, 0.0))
    return "FAIL", sorted(checks, key=lambda c: -c.mean_r.get(1.0, -1e9))[:3]


def _main(argv=None) -> int:
    """Take ideas off the queue, run step 3 on all 24 cells, log the verdict."""
    import argparse

    from factory import queue

    ap = argparse.ArgumentParser(description=_main.__doc__)
    ap.add_argument("-n", "--count", type=int, default=5)
    ap.add_argument("--market", action="append",
                    help="restrict markets; repeatable. Default: all six.")
    ap.add_argument("--tf", action="append",
                    help="restrict timeframes; repeatable. Default: 15m 1h 4h 1d")
    ap.add_argument("--seeds", type=int, default=CONTROL_SEEDS)
    ap.add_argument("-v", "--verbose", action="store_true",
                    help="print every cell, not just the verdict")
    a = ap.parse_args(argv)

    cell_list = cells.all_cells(a.market, tuple(a.tf) if a.tf else None)
    print(f"step 3 on {len(cell_list)} cells: "
          f"{', '.join(f'{s} {t}' for s, t in cell_list[:6])}"
          f"{' ...' if len(cell_list) > 6 else ''}\n")
    header = (f"{'idea':42}{'cell':14}{'verdict':6}{'trades':>7}{'tpd':>7}"
              f"{'hold d':>7}{'mean R':>9}{'-best5':>9}{'ctrl p90':>9}  why")
    print(header)
    print("-" * len(header))

    for _ in range(a.count):
        s = queue.take()
        if s is None:
            print("queue empty - run `python -m factory.fill`")
            break
        checks = check_all(s, cell_list, control_seeds=a.seeds)
        verdict, shown = verdict_of(checks)
        for c in (checks if a.verbose else shown):
            print(c)
        n_pass = sum(c.verdict == "PASS" for c in checks)
        queue.mark_tried(s, verdict=verdict,
                         note=f"step3: {n_pass}/{len(checks)} cells passed")
        print()
    return 0


if __name__ == "__main__":
    import sys as _sys
    _sys.exit(_main())
