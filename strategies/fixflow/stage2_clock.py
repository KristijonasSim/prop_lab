"""H-046 stage 2 - the clock axis, with the SEARCH priced. Read `PREREG.md`.

Stage 1 killed the fix itself: 1 of 5 markets clears the cost bar, the pooled
statistic does not beat its hour-matched null (p=0.418) and the fix anchor ranks
11th of 24 on its own placebo clock. This stage answers the only question that
leaves open - **is any hour of the day a tradeable object on FX and metals, or
is the whole axis noise?** - and prices the search that asking it costs.

H-038's LESSON 1 is the whole design here. 96 tests at a 95th percentile expect
4.8 false passes and 7 were seen; the correction was written down and then not
applied three days later. So the benchmark is not a per-cell p-value: it is the
**maximum over every cell of a null draw**, which is what "the best of N" has to
beat. H-028's two numbers - p=0.0000 in one slot against p=0.187 best-of-48 -
are the same point.

TWO SHAPES, both fixed before the run and both a coin flip a priori:
  fade    - the drift into the anchor reverses after it        (stage 1's shape)
  follow  - the anchor bar's own move continues                (the drift shape)

THE STATISTIC IS COST-FREE. Stage 1 pooled `edge / cost`, which hands the market
with the smallest spread the largest weight: EURUSD's round trip is 0.19bps
against gold's 1.06, so a 4.7bps EURUSD spread scored 6.35 and carried a pooled
number that nothing else in the table supported. Here every cell is standardised
by its OWN forward-return dispersion, and the cost bar is applied afterwards and
separately.

Run:  .venv/bin/python strategies/fixflow/stage2_clock.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from core.markets import COSTS, EXEC_MODE, load                 # noqa: E402
from core.run_hypothesis import window                          # noqa: E402
from strategies.fixflow.stage1_response import (BAR_MIN, CONTROL, FIX_HOUR,
                                                FIX_MARKETS, HORIZONS, TF,
                                                events, round_trip)

OUT = ROOT / "backtests" / "fixflow"
PRIMARY_H = 60
NQ = 5
N_NULL = 2000
SEED = 20260915


def qsplit(n: int, nq: int = NQ) -> tuple[int, int]:
    """Sizes of the bottom and top quantile groups, matching `pd.qcut`."""
    k = n // nq
    return k, k


def spread_bps(order: np.ndarray, post: np.ndarray) -> float:
    """Bottom-group minus top-group forward return, in bps, given a ranking.

    `order` is the argsort of whatever the cell ranks on. Splitting a ranking
    rather than calling `qcut` is what makes the 2,000-seed null affordable: a
    permutation null is exactly a random ranking, so the null needs no qcut at
    all - it needs a shuffled index.
    """
    k, _ = qsplit(len(order))
    return float(post[order[:k]].mean() - post[order[-k:]].mean()) * 1e4


def cell(pre: np.ndarray, post: np.ndarray, shape: str) -> dict:
    """One (market, hour, shape) cell: the real statistic and its null.

    `fade` ranks on the pre-drift and buys the bottom, which is stage 1's rule.
    `follow` ranks on MINUS the pre-drift, so the same code reads the other sign.
    """
    n = len(post)
    if n < 200:
        return {}
    sgn = 1.0 if shape == "fade" else -1.0
    order = np.argsort(sgn * pre, kind="stable")
    real = spread_bps(order, post)
    sd = float(post.std()) * 1e4
    rng = np.random.default_rng(SEED)
    idx = np.argsort(rng.random((N_NULL, n)), axis=1, kind="stable")
    k, _ = qsplit(n)
    draws = (post[idx[:, :k]].mean(1) - post[idx[:, -k:]].mean(1)) * 1e4
    return {"n": n, "spread": real, "sd": sd, "t": real / sd if sd else np.nan,
            "null": draws, "p": float((draws >= real).mean())}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    syms = list(FIX_MARKETS) + [CONTROL]
    t0, t1 = window(syms, ["1h"])
    bars = {}
    for s in syms:
        d = load(s, TF[s])
        bars[s] = d[(d.index >= t0) & (d.index <= t1)]

    # Every (market, hour) event table once. The two shapes and every horizon
    # read the same table, so the clock is built five times, not 240.
    ev: dict[tuple[str, int], pd.DataFrame] = {}
    for s in syms:
        for hr in range(24):
            e = events(bars[s], hr, BAR_MIN[s])
            if len(e) >= 200:
                ev[(s, hr)] = e

    hours = sorted({h for (_, h) in ev if all((m, h) in ev for m in FIX_MARKETS)})
    print(f"window {t0.date()} -> {t1.date()}")
    print(f"{len(hours)} usable London anchors (of 24): {hours}")
    print("the other anchors lose too many days to the FX weekend and the "
          "22:00 London close\n")

    rows, nulls = [], []
    for s in FIX_MARKETS:
        for hr in hours:
            e = ev[(s, hr)]
            for shape in ("fade", "follow"):
                c = cell(e.pre.to_numpy(), e[f"post{PRIMARY_H}"].to_numpy(), shape)
                if not c:
                    continue
                rt2 = 2.0 * round_trip(s)
                rows.append({"sym": s, "hour": hr, "side": shape,
                             "n": c["n"], "spread": round(c["spread"], 3),
                             "t": round(c["t"], 4), "p": c["p"],
                             "edge": round(c["spread"] / 2.0, 3),
                             "rt_2x": round(rt2, 3),
                             "edge_over_rt2x": round(c["spread"] / 2.0 / rt2, 3)})
                nulls.append(c["null"] / c["sd"])

    tbl = pd.DataFrame(rows)
    # THE SEARCH CORRECTION. Every cell's null draw is standardised the same way
    # the real statistic is, so seed i gives one draw of "the best cell you get
    # from a market that carries nothing". `fade` and `follow` are the same
    # ranking read from both ends, so a cell and its mirror are not two
    # independent tests - the max is taken over all of them anyway, which is the
    # pessimistic read.
    nullmat = np.vstack(nulls)                      # (cells, seeds)
    best_null = nullmat.max(axis=0)
    ncell = len(tbl)
    thresh95 = float(np.percentile(best_null, 95))

    tbl = tbl.sort_values("t", ascending=False)
    print(f"=== {ncell} cells ({len(FIX_MARKETS)} markets x {len(hours)} anchors "
          f"x 2 shapes), h={PRIMARY_H}m ===")
    print(f"best-of-{ncell} null: 95th pctile t = {thresh95:.4f}, "
          f"max over {N_NULL} seeds = {best_null.max():.4f}")
    print(f"\n{'sym':8s}{'hr':>4s}{'side':>8s}{'n':>6s}{'spread':>9s}"
          f"{'t':>8s}{'p_cell':>8s}{'p_search':>10s}{'edge/RT2x':>11s}")
    for _, r in tbl.head(12).iterrows():
        ps = float((best_null >= r.t).mean())
        print(f"{r.sym:8s}{r.hour:4d}{r.side:>8s}{r.n:6d}{r.spread:9.2f}"
              f"{r.t:8.4f}{r.p:8.3f}{ps:10.3f}{r.edge_over_rt2x:11.2f}")

    top = tbl.iloc[0]
    p_search = float((best_null >= top.t).mean())
    exp_false = ncell * 0.05

    # Sign consistency of the best cell's ANCHOR across the five markets: an
    # effect that is real at an hour should not flip sign market by market.
    same = tbl[(tbl.hour == top.hour) & (tbl.side == top.side)]
    print(f"\n=== the best cell's anchor across all five markets "
          f"({top.hour:02d}:00 London, {top.side}) ===")
    for _, r in same.iterrows():
        print(f"  {r.sym:8s} spread {r.spread:+7.2f}bps   t {r.t:+.4f}   "
              f"edge/RT2x {r.edge_over_rt2x:+.2f}")
    pos = int((same.spread > 0).sum())

    print(f"\n=== VERDICT, against PREREG.md's search rule ===")
    print(f"  cells searched                  {ncell}")
    print(f"  false passes expected at p<0.05 {exp_false:.1f}")
    print(f"  observed at p<0.05              {int((tbl.p < 0.05).sum())}")
    print(f"  best cell                       {top.sym} {top.hour:02d}:00 "
          f"{top.side}, t={top.t:.4f}, cell p={top.p:.3f}")
    print(f"  best cell vs the BEST-OF-{ncell} null   p={p_search:.3f}")
    print(f"  its anchor's sign across markets {pos}/5 positive")
    alive = p_search < 0.05 and pos >= 4
    print(f"\nCLOCK AXIS: {'A CELL SURVIVES' if alive else 'NOTHING SURVIVES THE SEARCH'}")

    rec = {"window": [str(t0.date()), str(t1.date())], "hours": hours,
           "n_cells": ncell, "n_null": N_NULL, "horizon": PRIMARY_H,
           "best_of_n_null_p95_t": round(thresh95, 4),
           "expected_false_passes": round(exp_false, 1),
           "observed_p05": int((tbl.p < 0.05).sum()),
           "best": {k: (float(v) if isinstance(v, (int, float, np.floating)) else v)
                    for k, v in top.items()},
           "best_p_search": p_search,
           "best_anchor_across_markets": same.to_dict("records"),
           "alive": bool(alive),
           "cells": tbl.to_dict("records")}
    (OUT / "stage2.json").write_text(json.dumps(rec, indent=1, default=float))
    print(f"wrote {OUT / 'stage2.json'}")


if __name__ == "__main__":
    main()
