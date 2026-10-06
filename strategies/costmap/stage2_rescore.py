"""H-049 stage 2 — re-score H-024's 935 cells at the corrected cost.

THE POINT OF THE WHOLE EXERCISE, AND ITS KILL CRITERION.

H-024 measured book-depth imbalance across 11 coins and 935 cells. It found
something real: monotone, beating its null, stable across years. It died on one
number - **0 of 935 cells cleared a 14bps taker round trip, best honest cell
7.9bps.** Stage 1 has now shown that 14bps was wrong: BTC's half-spread was
charged at 2.0bps/side against a measured 0.027, ETH at 2.0 against 0.070.

So the fair question, and it is the only reason stage 1 was worth running:
**does a corrected cost bar bring any of those 935 cells back?**

KILL CRITERION, WRITTEN BEFORE THE RUN. If **0 cells clear the corrected bar
while also passing H-024's own quality gates**, the cost side is exhausted, and
the 2.7-10.9bps band that six signals in this repo occupy is structural rather
than an artefact of a bad cost model. That is a real result and it closes the
direction rather than inviting another attempt.

WHAT IS AND IS NOT ALLOWED TO COUNT.

  * **A cell is not a finding.** 935 cells at a 95th-percentile null produce
    about 47 passes from noise alone. `core/search_cost.py` exists because this
    repo has already been fooled by exactly that (H-038 LESSON 1, the retracted
    `size_z` at 14.6bps). So cells are reported, and **families** - a feature at
    a horizon, counted across the 11 coins - are what the verdict rests on.
  * **The quality gates come from H-024, not from here.** `beats_null`,
    `monotone`, and year-sign stability were all computed in stage 1, before
    anybody knew what the corrected cost would be. Nothing is re-fitted.
  * **Nothing is re-measured.** `abs_spread` is H-024's own number. This file
    changes the right-hand side of the inequality and only that.

THE FOUR BARS, now per-coin instead of one constant for the whole panel:

    taker1x   round_trip("taker")        cross both ways
    taker2x   2x that                    the stress case board numbers quote
    mixed     round_trip("mixed")        limit in, market out - the repo default
    maker1x   round_trip("maker")        both sides passive - H-048's target,
                                         and the fill H-023 validated on ticks
    maker2x   2x maker                   maker, stressed

Run:  .venv/bin/python strategies/costmap/stage2_rescore.py
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, REPO)

from core.markets import COSTS                                   # noqa: E402
from core.search_cost import expected_false, verdict             # noqa: E402

SRC = os.path.join(REPO, "backtests", "depth", "stage1_response.csv")
OUT = os.path.join(REPO, "backtests", "depth", "stage3_rescore.csv")

#: H-024's own quality gates, computed in stage 1 before this cost was known
MONO_MIN = 0.75

#: what the panel used to be charged, per coin, before 2026-09-16
OLD = {c: (14.0 if c in ("BTCUSDT", "ETHUSDT") else 16.0)
       for c in ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT",
                 "ADAUSDT", "AVAXUSDT", "DOGEUSDT", "DOTUSDT", "LINKUSDT",
                 "LTCUSDT")}


def bars(sym: str) -> dict[str, float]:
    c = COSTS[sym]
    return {"taker1x": c.round_trip("taker"),
            "taker2x": 2 * c.round_trip("taker"),
            "mixed": c.round_trip("mixed"),
            "maker1x": c.round_trip("maker"),
            "maker2x": 2 * c.round_trip("maker")}


def main() -> None:
    d = pd.read_csv(SRC)
    print(f"H-024 stage 1: {len(d):,} cells, {d.sym.nunique()} coins, "
          f"{d.feature.nunique()} features, {d.horizon.nunique()} horizons")

    missing = sorted(set(d.sym) - set(COSTS))
    if missing:
        raise SystemExit(f"no cost entry for {missing}")

    names = ["taker1x", "taker2x", "mixed", "maker1x", "maker2x"]
    for k in names:
        d[f"bar_{k}"] = d.sym.map(lambda s: bars(s)[k])
        d[f"new_{k}"] = d.abs_spread > d[f"bar_{k}"]
    d["bar_old"] = d.sym.map(OLD)
    d["old_taker1x"] = d.abs_spread > d["bar_old"]

    # H-024's own quality gates, fixed before this cost was known
    d["quality"] = d.beats_null & (d.monotone >= MONO_MIN)
    d["quality_stable"] = d.quality & (d.years_same_sign >= 3)

    d.to_csv(OUT, index=False)

    print(f"\n{'=' * 78}\nCELLS CLEARING EACH BAR (of {len(d):,})\n{'=' * 78}")
    print(f"{'bar':10} {'median bar':>11} {'clears':>8} "
          f"{'+ beats null':>13} {'+ monotone':>11} {'+ 3/4 years':>12}")
    print(f"{'OLD 14/16':10} {np.median(d.bar_old):11.2f} "
          f"{int(d.old_taker1x.sum()):8d} "
          f"{int((d.old_taker1x & d.beats_null).sum()):13d} "
          f"{int((d.old_taker1x & d.quality).sum()):11d} "
          f"{int((d.old_taker1x & d.quality_stable).sum()):12d}")
    for k in names:
        c = d[f"new_{k}"]
        print(f"{k:10} {d[f'bar_{k}'].median():11.2f} {int(c.sum()):8d} "
              f"{int((c & d.beats_null).sum()):13d} "
              f"{int((c & d.quality).sum()):11d} "
              f"{int((c & d.quality_stable).sum()):12d}")

    print(f"\n-- the price of the search --")
    print(f"  {verdict(len(d), 95.0, 200)}")
    print(f"  at a 95th-percentile null, {len(d):,} cells produce about "
          f"{expected_false(len(d), 95.0):.0f} passes from noise alone.")
    print(f"  observed beating their null: {int(d.beats_null.sum())}. "
          f"**A CELL IS NOT A FINDING - read the families below.**")

    print(f"\n{'=' * 78}\nFAMILIES — a feature at a horizon, across the 11 "
          f"coins\n{'=' * 78}")
    print("a real effect shows up on many coins at once. noise shows up on one.")
    for k in ("maker1x", "mixed", "taker1x"):
        g = (d[d[f"new_{k}"] & d.quality]
             .groupby(["feature", "horizon"])
             .agg(coins=("sym", "nunique"),
                  med_bps=("abs_spread", "median"),
                  stable=("quality_stable", "sum"))
             .sort_values("coins", ascending=False))
        print(f"\n-- at {k} (median bar {d[f'bar_{k}'].median():.2f}bps), "
              f"passing beats_null AND monotone >= {MONO_MIN} --")
        if g.empty:
            print("   NOTHING")
            continue
        print(f"   {'feature':16} {'horizon':>8} {'coins':>6} {'med bps':>9} "
              f"{'of which 3/4yr':>15}")
        for (f_, h), r in g.head(8).iterrows():
            print(f"   {f_:16} {h:>8} {int(r.coins):6d} {r.med_bps:9.2f} "
                  f"{int(r.stable):15d}")
        print(f"   ({len(g)} families in total, "
              f"{int((g.coins >= 3).sum())} on 3+ coins)")

    print(f"\n{'=' * 78}\nTHE SURVIVORS — every cell clearing the MIXED bar "
          f"with both quality gates\n{'=' * 78}")
    s = d[d["new_mixed"] & d.quality].sort_values("abs_spread", ascending=False)
    if s.empty:
        print("NONE.")
    else:
        print(f"{'sym':9} {'feature':16} {'h':>5} {'bps':>7} {'bar':>7} "
              f"{'mono':>5} {'null':>7} {'yrs':>5}")
        for _, r in s.head(20).iterrows():
            print(f"{r.sym:9} {r.feature:16} {r.horizon:>5} "
                  f"{r.abs_spread:7.2f} {r.bar_mixed:7.2f} {r.monotone:5.2f} "
                  f"{r.null_best:7.2f} {int(r.years_same_sign)}/{int(r.years)}")
        print(f"\n{len(s)} cells. On {s.sym.nunique()} coins, "
              f"{s.feature.nunique()} features.")

    print(f"\n-- the kill criterion, written before the run --")
    n = int((d["new_mixed"] & d.quality).sum())
    nt = int((d["new_taker1x"] & d.quality).sum())
    print(f"  cells clearing the corrected MIXED bar with quality: {n}")
    print(f"  cells clearing the corrected TAKER bar with quality: {nt}")
    if n == 0 and nt == 0:
        print("  **ZERO. The cost side is exhausted. The 2.7-10.9bps band is\n"
              "  structural, not an artefact of a bad cost model.**")
    else:
        print("  **NON-ZERO. Survivors above; they owe a full-kernel run with\n"
              "  stops, sizing and the prop rules before any of it is a trade.**")
    print(f"\nwritten: {OUT}")


if __name__ == "__main__":
    main()


# ---------------------------------------------------------------- family test
def family_signs() -> None:
    """THE RIGHT UNIT, AND THE RIGHT DENOMINATOR.

    935 cells expect ~47 false passes, so no cell survives its own search. But
    the cells are not 935 independent questions - they are **17 features x 5
    horizons = 85 families**, each asked of the same 11 coins. A real effect
    has the SAME SIGN on most of the coins; noise splits them evenly.

    That converts the whole panel into 85 binomial tests with a known null
    (p = 0.5 per coin), which 200 resamples do not need to resolve, and prices
    the search honestly against 85 rather than 935.
    """
    from math import comb

    d = pd.read_csv(OUT)
    rows = []
    for (f_, h), g in d.groupby(["feature", "horizon"]):
        sign = np.sign(g["spread"].to_numpy())
        sign = sign[sign != 0]
        n = len(sign)
        if n < 8:
            continue
        k = int(max((sign > 0).sum(), (sign < 0).sum()))
        p = sum(comb(n, i) for i in range(k, n + 1)) / 2 ** (n - 1)  # two-sided
        rows.append({"feature": f_, "horizon": h, "coins": n, "agree": k,
                     "p": min(p, 1.0),
                     "dir": "+" if (sign > 0).sum() == k else "-",
                     "med_bps": float(g["abs_spread"].median()),
                     "clears_maker1x": int((g["abs_spread"] > 4.0).sum())})
    r = pd.DataFrame(rows).sort_values("p")

    print(f"\n{'=' * 78}\nFAMILY SIGN AGREEMENT — {len(r)} families, 11 coins "
          f"each\n{'=' * 78}")
    print("does the effect point the SAME WAY on the whole panel? noise splits "
          "6/5.")
    alpha = 0.05 / len(r)
    print(f"\nBonferroni over {len(r)} families: a family needs p < {alpha:.5f}\n")
    print(f"{'feature':16} {'horizon':>8} {'agree':>7} {'dir':>4} {'p':>9} "
          f"{'med bps':>9} {'>4bps':>6}  verdict")
    for _, x in r.head(12).iterrows():
        v = "**SURVIVES**" if x.p < alpha else ("nominal" if x.p < 0.05 else "-")
        print(f"{x.feature:16} {x.horizon:>8} {int(x.agree):3d}/{int(x.coins):<3d} "
              f"{x.dir:>4} {x.p:9.5f} {x.med_bps:9.2f} {int(x.clears_maker1x):6d}"
              f"  {v}")
    surv = r[r.p < alpha]
    print(f"\nfamilies surviving Bonferroni: {len(surv)} of {len(r)}")
    print(f"families nominal at 0.05: {int((r.p < 0.05).sum())}, "
          f"against {0.05 * len(r):.1f} expected")
    r.to_csv(os.path.join(REPO, "backtests", "depth", "stage3_families.csv"),
             index=False)


if __name__ == "__main__":
    family_signs()
