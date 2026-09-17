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

WHAT IT DOES NOT DO. It does not prove anything. Passing all five means the idea
has earned a real study with a walk-forward and honest fills - nothing more.
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
    p_null: float | None = None
    notes: list[str] = field(default_factory=list)

    def __str__(self) -> str:
        p = f"{self.p_null:.3f}" if self.p_null is not None else "  -  "
        return (f"{self.name:22}{self.verdict:6}{self.events:>7}{self.rows:>7}"
                f"{self.effect:>9.1f}{self.median_effect:>9.1f}{self.rho:>7.2f}"
                f"{self.cost_bar:>7.2f}{p:>8}  {'; '.join(self.notes)}")


HEADER = (f"{'signal':22}{'verd':6}{'events':>7}{'rows':>7}{'effect':>9}"
          f"{'median':>9}{'rho':>7}{'bar':>7}{'p':>8}  why")


def independent_events(sig: pd.Series, hold: int) -> int:
    """Rows are not events.

    Two corrections, both learned the expensive way. A hold of `h` bars means
    overlapping trades, so `rows/h` is the non-overlapping count. And a signal
    that only changes sign a few times across the sample carries only that many
    independent episodes however many rows it has - the defect that killed H-051
    (794 daily rows, three swings) and H-043 (48 days, 17 episodes, two of them
    half the sample). The smaller of the two is the honest count.
    """
    if not len(sig):
        return 0
    non_overlap = int(len(sig) / max(1, hold))
    s = np.sign(sig.dropna().values)
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
