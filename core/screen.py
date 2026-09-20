"""ONE screen, five checks, in the order that kills cheapest first.

WHY THIS EXISTS. On 2026-09-17 six hypotheses were tested and five died. They
died in four DIFFERENT ways, and every one of those ways was knowable in under a
minute:

    H-051 gold/silver   3 independent swings in 794 rows      -> EVENTS
    H-046 footprint     2 bps effect against a 5.5 bps spread -> COST
    H-046c long holds   mean +16.73, median -2.10             -> SKEW
    H-049 macro feeds   real 17.8, shuffled signal 9.6-41.6   -> NULL
    H-035 (earlier)     96 tests, 4.8 false passes expected   -> SEARCH

Each was found after building the whole study. **The checks are cheap and the
studies are expensive**, so the order is inverted here: a signal must survive
counting, costing, and the median before anything is built around it.

HOW TO USE IT. Hand it a signal and a price series. Adding a candidate should be
five lines, not a new file - that is the point. The intended shape is a BATCH:
twenty signals through one identical pipeline, so the output is a distribution
that can be compared against the null distribution, instead of twenty separate
studies each re-deriving its own machinery and each quietly running its own
search.

TWO MORE CHECKS, ADDED 2026-09-20, and they are the ones H-027 fails.
`docs/DIAGNOSIS_2026-09-20.md` measured that the project's only survivor earns
188.4 R over 634 days of which **two days are 65%** — drop the largest ten and
the total goes to **-24.7 R**. The five checks above all pass that series. They
see the size of an effect and the shape of its response; neither of them can see
that the effect lives on a handful of days.

That shape is what makes a strategy unpayable (one day is 95.5% of a typical
month, so any consistency rule rejects it) and what kills a funded seat (19.4 R
of drawdown against a 6% cap, which buys 3 R at the traded risk). So:

    CONCENTRATION  drop the best few decisions. If more than half the profit
                   goes with them, the edge is a handful of episodes.
    SURVIVAL       the README's own formula, run forward:
                   days = maxDD / return_per_day x (target / cap).
                   A seat that cannot be funded inside a quarter at the risk
                   that survives its own worst stretch is not a product.

Both are O(n) and both run BEFORE the null, which is 200 shuffles.

WHAT IT DOES NOT DO. It does not prove anything. Passing all seven means the
idea has earned a real study with a walk-forward and honest fills - nothing more.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

#: An effect must clear this multiple of the round trip to be worth building on.
COST_MULT = 2.0
#: Below this many INDEPENDENT events the result is a story about a few episodes.
MIN_EVENTS = 40
#: Spearman of bucket index against bucket mean.
MIN_RHO = 0.8
NULL_SEEDS = 200
BLOCK = 20
#: Drop this many of the best decisions when testing concentration.
CONC_K = 5
#: If those few carry more than this share of the profit, the edge is episodes.
MAX_CONC = 0.50
#: Days to a funded seat, at the risk that survives the worst stretch. The pace
#: target in README.md is 5-14; this bar is a whole quarter and deliberately
#: generous, because the screen is a filter and not the study.
MAX_FUND_DAYS = 90.0
#: FundingPips 1-Step Flex - the row docs/FIRMS.md picked. Target over cap is
#: what the formula needs, and 10/6 is the same for every firm on the shortlist.
PROFIT_TARGET, MAX_LOSS = 0.10, 0.06


@dataclass
class Screen:
    name: str
    verdict: str = "?"
    events: int = 0
    rows: int = 0
    effect: float = 0.0
    median_effect: float = 0.0
    rho: float = 0.0
    cost_bar: float = 0.0
    #: None until the gate actually runs. A check that was never reached must
    #: not print as 0.00, which is the best possible score.
    conc: float | None = None
    fund_days: float | None = None
    p_null: float | None = None
    notes: list[str] = field(default_factory=list)

    def __str__(self) -> str:
        p = f"{self.p_null:.3f}" if self.p_null is not None else "  -  "
        cc = "      -" if self.conc is None else f"{self.conc:>7.2f}"
        if self.fund_days is None:
            fd = "      -"
        elif not np.isfinite(self.fund_days):
            fd = "  never"
        else:
            fd = f"{self.fund_days:>7.0f}"
        return (f"{self.name:22}{self.verdict:6}{self.events:>7}{self.rows:>7}"
                f"{self.effect:>9.1f}{self.median_effect:>9.1f}{self.rho:>7.2f}"
                f"{self.cost_bar:>7.2f}{cc}{fd}{p:>8}"
                f"  {'; '.join(self.notes)}")


HEADER = (f"{'signal':22}{'verd':6}{'events':>7}{'rows':>7}{'effect':>9}"
          f"{'median':>9}{'rho':>7}{'bar':>7}{'conc':>7}{'fundd':>7}"
          f"{'p':>8}  why")


def independent_events(sig: pd.Series, hold: int) -> int:
    """Rows are not events.

    Two corrections, both learned the expensive way. A hold of `h` bars means
    overlapping trades, so `rows/h` is the non-overlapping count. And a signal
    that only changes sign a few times across the sample carries only that many
    independent episodes however many rows it has - the defect that killed H-051
    (794 daily rows, three swings) and H-043 (48 days, 17 episodes, two of them
    half the sample). The smaller of the two is the honest count.

    **CROSSINGS ARE COUNTED AROUND THE MEDIAN, NOT AROUND ZERO.** The first
    version used `np.sign`, which silently assumed every signal is centred. A
    strictly positive series - a percentile rank, a VIX level, a spread, a tick
    count - never changes sign, so it scored ONE episode however long it ran and
    was killed at the first gate for a property of its units rather than of its
    information. Measured 2026-09-18: 12 of 219 loop trials died this way, and
    every `level` and `pctile` candidate in the registry was affected.

    The median is the honest centre: it is what the bucket response splits on
    anyway, and it makes the count invariant to shifting or rescaling a feed.
    """
    if not len(sig):
        return 0
    v = sig.dropna().values
    if not len(v):
        return 0
    non_overlap = int(len(sig) / max(1, hold))
    s = np.sign(v - np.median(v))
    s = s[s != 0]                      # ties sit on the fence, they are not a side
    if len(s) < 2:
        return min(non_overlap, 1)
    flips = int(np.sum(s[1:] != s[:-1])) + 1
    return min(non_overlap, flips)


def bucket_response(sig: pd.Series, fwd: pd.Series, n_buckets: int = 5) -> dict | None:
    x = pd.DataFrame({"s": sig, "f": fwd}).replace(
        [np.inf, -np.inf], np.nan).dropna()
    if len(x) < 100 or x.s.nunique() < n_buckets:
        return None
    try:
        x["b"] = pd.qcut(x.s, n_buckets, labels=False, duplicates="drop")
    except ValueError:
        return None
    g = x.groupby("b").f
    mean, med = g.mean(), g.median()
    if len(mean) < 3:
        return None
    rho = float(pd.Series(mean.values).corr(pd.Series(range(len(mean))),
                                            method="spearman"))
    return {"rows": int(len(x)), "effect": float(mean.iloc[-1] - mean.iloc[0]),
            "median": float(med.iloc[-1] - med.iloc[0]), "rho": rho}



def implied_pnl(sig: pd.Series, fwd: pd.Series, hold: int = 1,
                n_buckets: int = 5) -> np.ndarray:
    """The per-decision PnL the bucket response is really describing.

    Long the top bucket, short the bottom, flat in between. That is the trade
    the monotonicity check implies, and until now nothing ever built it - the
    screen scored the *response* and never the *series*, which is why a result
    carried by three days looked identical to one carried by three hundred.

    **Sampled every `hold` rows.** A signal held five days produces five
    overlapping copies of the same decision; counting them all understates
    drawdown and flatters concentration, for the same reason
    `independent_events` divides by the hold.
    """
    x = pd.DataFrame({"s": sig, "f": fwd}).replace(
        [np.inf, -np.inf], np.nan).dropna()
    if len(x) < 100 or x.s.nunique() < n_buckets:
        return np.empty(0)
    try:
        b = pd.qcut(x.s, n_buckets, labels=False, duplicates="drop")
    except ValueError:
        return np.empty(0)
    top = int(b.max())
    pos = np.where(b == top, 1.0, np.where(b == 0, -1.0, 0.0))
    pnl = pos * x.f.values
    return pnl[::max(1, hold)]


def concentration(pnl: np.ndarray, k: int = CONC_K) -> float:
    """Share of the total that goes with the `k` best decisions.

    1.0 means the edge is entirely those few. A series that never made money
    scores 1.0 too, which is correct: there is nothing to concentrate.
    """
    if len(pnl) <= k:
        return 1.0
    total = float(pnl.sum())
    if total <= 0.0:
        return 1.0
    return float(np.sort(pnl)[-k:].sum() / total)


def fund_days(pnl: np.ndarray, hold: int = 1,
              profit_target: float = PROFIT_TARGET,
              max_loss: float = MAX_LOSS) -> float:
    """README.md's own formula: days = maxDD / return_per_day x (target/cap).

    The risk per trade cancels. A seat has to survive its worst stretch, which
    caps the risk at `max_loss / maxDD`; at that risk the target is
    `profit_target / max_loss` multiples of the drawdown away. What is left is
    a number of days and it does not depend on the size traded.

    `inf` when the series never makes money - the seat is never funded. **Zero
    when it never draws down**, which is the opposite case and was returned as
    `inf` in the first draft: no drawdown means the risk is not capped by the
    worst stretch at all, so the seat funds immediately. That sign error would
    have rejected every cleanly trending candidate the loop could find, and
    `test_a_clean_signal_still_passes_all_seven` is what caught it.
    """
    if not len(pnl):
        return float("inf")
    per_day = float(pnl.sum()) / (len(pnl) * max(1, hold))
    if per_day <= 0.0:
        return float("inf")
    eq = np.cumsum(pnl)
    dd = float((eq - np.maximum.accumulate(eq)).min())
    if dd == 0.0:
        return 0.0
    return abs(dd) / per_day * (profit_target / max_loss)


def screen(name: str, sig: pd.Series, fwd: pd.Series, round_trip_bps: float,
           hold: int = 1, run_null: bool = True) -> Screen:
    """Five checks, cheapest first. Stops at the first failure."""
    out = Screen(name=name, cost_bar=round_trip_bps * COST_MULT)

    ev = independent_events(sig, hold)
    out.events = ev
    if ev < MIN_EVENTS:
        out.verdict = "DEAD"
        out.notes.append(f"{ev} independent events, under {MIN_EVENTS}")
        return out

    r = bucket_response(sig, fwd)
    if not r:
        out.verdict = "DEAD"
        out.notes.append("no usable response")
        return out
    out.rows, out.effect = r["rows"], r["effect"]
    out.median_effect, out.rho = r["median"], r["rho"]

    if abs(r["effect"]) < out.cost_bar:
        out.verdict = "DEAD"
        out.notes.append(f"effect {abs(r['effect']):.1f} under the "
                         f"{out.cost_bar:.1f} bar")
        return out

    if np.sign(r["effect"]) != np.sign(r["median"]):
        out.verdict = "DEAD"
        out.notes.append("mean and median disagree in sign - skew trap")
        return out

    if abs(r["rho"]) < MIN_RHO:
        out.verdict = "DEAD"
        out.notes.append(f"response not monotone, rho {r['rho']:.2f}")
        return out

    pnl = implied_pnl(sig, fwd, hold)
    out.conc = concentration(pnl)
    out.fund_days = fund_days(pnl, hold)

    if out.conc > MAX_CONC:
        out.verdict = "DEAD"
        out.notes.append(f"{CONC_K} best decisions carry "
                         f"{out.conc:.0%} of the profit")
        return out

    if out.fund_days > MAX_FUND_DAYS:
        d = ("never" if not np.isfinite(out.fund_days)
             else f"{out.fund_days:.0f}d")
        out.notes.append(f"seat funded in {d}, over the "
                         f"{MAX_FUND_DAYS:.0f}d bar")
        out.verdict = "DEAD"
        return out

    if not run_null:
        out.verdict = "WORK"
        out.notes.append("clears without a null")
        return out

    vals = sig.values
    n = len(vals)
    hits = 0
    for seed in range(NULL_SEEDS):
        rng = np.random.default_rng(seed)
        blocks = [vals[i:i + BLOCK] for i in range(0, n, BLOCK)]
        rng.shuffle(blocks)
        sh = pd.Series(np.concatenate(blocks)[:n], index=sig.index)
        rr = bucket_response(sh, fwd)
        if rr and abs(rr["effect"]) >= abs(r["effect"]):
            hits += 1
    out.p_null = hits / NULL_SEEDS
    if out.p_null >= 0.05:
        out.verdict = "DEAD"
        out.notes.append(f"loses to its own shuffle, p={out.p_null:.3f}")
        return out

    out.verdict = "WORK"
    out.notes.append("earned a real study")
    return out


def price_the_search(results: list[Screen], alpha: float = 0.05) -> str:
    """The H-035 correction, applied automatically instead of being forgotten.

    N tests at a threshold of alpha expect N*alpha false passes. A count of
    survivors is meaningless until it is compared against that expectation -
    this was written down for H-028 and rebuilt without it three days later.
    """
    n = len(results)
    passed = sum(1 for r in results if r.verdict == "WORK")
    expected = n * alpha
    verdict = ("more than chance" if passed > expected * 2
               else "INDISTINGUISHABLE FROM CHANCE")
    return (f"{n} signals screened, {passed} survived. "
            f"At alpha={alpha} chance alone gives {expected:.1f}. -> {verdict}")
