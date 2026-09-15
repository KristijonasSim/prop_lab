"""H-047 stage 1 - does participation decide whether a move reverses?

READ `PREREG.md` FIRST. No strategy, no stop, no target, no fitting: bucket the
forward return by the size of the move and by how much volume the move carried,
and print the answer in basis points against what a round trip costs.

THE SHAPE THAT WOULD MAKE IT REAL. Within each participation tercile, rank bars
by their own standardised return and take the bottom quintile minus the top. A
positive number is a reversal. The hypothesis is not "the number is positive" -
it is that the number **falls as participation rises**, because a move on volume
is information and a move without it is inventory. A fade that works equally at
every volume is a different, already-dead hypothesis (H-005, H-011).

WHY THE NULL IS A BLOCK PERMUTATION. The forward return at h > 1 overlaps its
neighbours, so independent shuffling would compare an overlapped statistic
against a non-overlapped population and make everything look significant. Blocks
of length h keep the overlap and destroy only the pairing between the signal and
what follows it.

Run:  .venv/bin/python strategies/partrev/stage1_response.py
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
from core.universe import STANDARD                              # noqa: E402

OUT = ROOT / "backtests" / "partrev"
TF = "15m"
LOOKBACK = 96          # 24h of 15m bars, for both the sd and the volume median
HORIZONS = (1, 3, 6, 12)
NQ = 5                 # return quintiles
NT = 3                 # participation terciles
N_NULL = 500
SEED = 20260915


def rt_bps(sym: str) -> float:
    return COSTS[sym].round_trip(EXEC_MODE)


def table(df: pd.DataFrame, h: int) -> pd.DataFrame:
    """One row per usable signal bar: the move, its participation, what followed.

    Timing is the kernel contract's. The signal bar's own return and volume are
    known at its close; the entry is the NEXT bar's open; the exit is the open h
    bars after that. Nothing reads a bar that had not finished.
    """
    o, c, v = df.open, df.close, df.volume
    ret = np.log(c / c.shift(1))
    sd = ret.rolling(LOOKBACK).std()
    vmed = v.rolling(LOOKBACK).median()
    ent = o.shift(-1)
    ex = o.shift(-1 - h)
    live = (v > 0) & (v.shift(-1) > 0) & (v.shift(-1 - h) > 0)
    t = pd.DataFrame({"z": ret / sd, "rv": v / vmed,
                      "fwd": (ex / ent - 1.0) * 1e4, "live": live})
    return t[t.live & np.isfinite(t.z) & np.isfinite(t.rv)
             & np.isfinite(t.fwd)].drop(columns="live")


def spread(z: np.ndarray, fwd: np.ndarray) -> float:
    """Bottom return-quintile minus top, in bps. Positive = the move reverses."""
    k = len(z) // NQ
    if k < 20:
        return float("nan")
    o = np.argsort(z, kind="stable")
    return float(fwd[o[:k]].mean() - fwd[o[-k:]].mean())


def block_null(z: np.ndarray, fwd: np.ndarray, h: int,
               seeds: int = N_NULL) -> np.ndarray:
    """The same statistic with `fwd` re-ordered in blocks of length h.

    Reshape-and-permute rather than `array_split`: the first version rebuilt a
    27,000-element list of one-bar blocks on every seed and 72 cells of that did
    not finish. Same null, same blocks, two orders of magnitude cheaper.
    """
    n = len(fwd)
    L = max(h, 1)
    nb = n // L
    if nb < 10:
        return np.full(seeds, np.nan)
    trim = nb * L
    base = fwd[:trim].reshape(nb, L)
    tail = fwd[trim:]
    o = np.argsort(z, kind="stable")
    k = n // NQ
    lo, hi = o[:k], o[-k:]
    rng = np.random.default_rng(SEED)
    out = np.empty(seeds)
    for i in range(seeds):
        f = np.concatenate([base[rng.permutation(nb)].ravel(), tail])
        out[i] = f[lo].mean() - f[hi].mean()
    return out


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    t0, t1 = window(STANDARD, [TF])
    print(f"window {t0.date()} -> {t1.date()}   bars {TF}   "
          f"lookback {LOOKBACK} ({LOOKBACK / 4:.0f}h)\n")

    rec: dict = {"window": [str(t0.date()), str(t1.date())], "tf": TF,
                 "lookback": LOOKBACK, "horizons": list(HORIZONS),
                 "n_null": N_NULL, "cells": [], "monotone": {}}
    rows, nulls = [], []

    for sym in STANDARD:
        d = load(sym, TF)
        d = d[(d.index >= t0) & (d.index <= t1)]
        rt2 = 2.0 * rt_bps(sym)
        print(f"=== {sym}  {len(d):,} bars  round trip {rt_bps(sym):.2f}bps  "
              f"2x bar on the per-trade edge {rt2:.2f}bps ===")
        print(f"{'h':>3s}{'tercile':>9s}{'n':>8s}{'spread':>9s}{'edge':>8s}"
              f"{'edge/RT2x':>11s}{'p_cell':>8s}")
        for h in HORIZONS:
            t = table(d, h)
            # terciles of participation, cut on the whole sample - this is a
            # DIAGNOSTIC, not a tradeable rule; gate 2 cuts them inside the fold.
            ter = pd.qcut(t.rv.rank(method="first"), NT, labels=False)
            sp_by_ter = []
            for g in range(NT):
                m = ter == g
                z, f = t.z[m].to_numpy(), t.fwd[m].to_numpy()
                sp = spread(z, f)
                sp_by_ter.append(sp)
                nd = block_null(z, f, h)
                p = float((nd >= sp).mean())
                sd_null = float(nd.std())
                rows.append({"sym": sym, "h": h, "ter": g, "n": int(m.sum()),
                             "spread": round(sp, 3), "edge": round(sp / 2, 3),
                             "rt_2x": round(rt2, 3),
                             "edge_over_rt2x": round(sp / 2 / rt2, 3),
                             "p": p, "t": round(sp / sd_null, 3) if sd_null else None})
                nulls.append(nd / sd_null if sd_null else nd)
                print(f"{h:3d}{['thin', 'mid', 'heavy'][g]:>9s}{int(m.sum()):8d}"
                      f"{sp:9.2f}{sp / 2:8.2f}{sp / 2 / rt2:11.2f}{p:8.3f}")
            mono = sp_by_ter[0] > sp_by_ter[1] > sp_by_ter[2]
            rec["monotone"][f"{sym}_h{h}"] = bool(mono)
            print(f"    thin>mid>heavy: {'YES' if mono else 'no'}   "
                  f"({sp_by_ter[0]:.2f} / {sp_by_ter[1]:.2f} / {sp_by_ter[2]:.2f})")
        print()

    tbl = pd.DataFrame(rows)
    nullmat = np.vstack(nulls)
    best_null = nullmat.max(axis=0)
    ncell = len(tbl)

    # --- criterion 1: the interaction, per horizon, across markets ---------
    print("=== CRITERION 1 - is the response monotone in participation? ===")
    best_h, best_cnt = None, -1
    for h in HORIZONS:
        cnt = sum(rec["monotone"][f"{s}_h{h}"] for s in STANDARD)
        print(f"  h={h:2d} bars: monotone on {cnt}/6 markets")
        if cnt > best_cnt:
            best_h, best_cnt = h, cnt
    c1 = best_cnt >= 4

    # --- criterion 2: does the thin tercile clear cost --------------------
    thin = tbl[(tbl.ter == 0) & (tbl.h == best_h)]
    c2n = int((thin.edge_over_rt2x > 1.0).sum())
    print(f"\n=== CRITERION 2 - thin-participation cell against 2x cost, "
          f"h={best_h} ===")
    for _, r in thin.iterrows():
        print(f"  {r.sym:9s} spread {r.spread:+8.2f}bps  edge/RT2x "
              f"{r.edge_over_rt2x:+7.2f}  p={r.p:.3f}")
    c2 = c2n >= 4

    # --- criterion 3: the priced search -----------------------------------
    top = tbl.sort_values("t", ascending=False).iloc[0]
    p_search = float((best_null >= top.t).mean())
    print(f"\n=== CRITERION 3 - the search, priced ===")
    print(f"  cells                      {ncell}")
    print(f"  false passes expected p<.05 {ncell * 0.05:.1f}")
    print(f"  observed p<.05              {int((tbl.p < 0.05).sum())}")
    print(f"  best cell                   {top.sym} h={int(top.h)} "
          f"tercile={['thin', 'mid', 'heavy'][int(top.ter)]}, t={top.t:.2f}")
    print(f"  vs the best-of-{ncell} null       p={p_search:.3f}")
    c3 = p_search < 0.05

    print(f"\n=== GATE 1 ===")
    for k, ok, why in (("1 interaction", c1, f"monotone on {best_cnt}/6 at h={best_h}"),
                       ("2 clears cost", c2, f"{c2n}/6 markets"),
                       ("3 beats search", c3, f"p={p_search:.3f}")):
        print(f"  {'PASS' if ok else 'FAIL'}  {k:16s} {why}")
    alive = c1 and c2 and c3
    print(f"\nH-047 GATE 1: {'PASS' if alive else 'FAIL'}")

    rec |= {"cells": tbl.to_dict("records"), "best_h": int(best_h),
            "criteria": {"1_interaction": bool(c1), "2_cost": bool(c2),
                         "3_search": bool(c3)},
            "monotone_count": int(best_cnt), "cost_count": int(c2n),
            "p_search": p_search, "gate1": bool(alive)}
    (OUT / "stage1.json").write_text(json.dumps(rec, indent=1, default=float))
    print(f"wrote {OUT / 'stage1.json'}")


if __name__ == "__main__":
    main()
