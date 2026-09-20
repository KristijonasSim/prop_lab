"""H-052 — daily net buying pressure on gold, held for days.

WHY THIS ONE. Today closed four ideas and each death narrowed the next test:

  * scalping dies on cost - the shipped bot survives a 21 bps spread only
    because it holds for weeks, so the hold must be long;
  * the gold/silver ratio died because three years held three independent
    swings - **rows are not events**, so the signal must fire often;
  * the macro feeds died to their null, so a null is mandatory, not optional;
  * five markets are worse than gold alone, so this is gold only.

A DAILY reading of the order-flow feed satisfies all four: one genuinely new
observation per day, a hold measured in days, on the one market whose costs work.

THE DATA IS NEW TO THIS REPO AND THAT IS THE POINT. Every `volume` figure in
`data/` is the **bid side only** - Dukascopy publishes bid candles, proven to
floating-point exactness on 2026-09-17. The ask side has never been seen by any
study here. `askvol - bidvol` summed over a day is therefore a reading nothing in
this project has used.

THE MECHANISM. A day that closes with persistent net buying is a day on which
someone with size had to keep paying up. Institutional orders are worked across
sessions, so the part not filled today is still there tomorrow. That predicts
CONTINUATION. The opposite read - that one-sided pressure exhausts and reverts -
is equally plausible and both signs are reported; a signal whose sign has to be
chosen after seeing the data is not a signal.

THE HONEST LIMIT, stated before the numbers. Only **225 days** of ticks were
downloaded before Kris stopped the pull, and they sit in two disjoint chunks
(2023-08/09 and 2025-08 onward). That is 225 events, not the 750 a full three
years would give. Both chunks are reported separately, because a signal that
lives in one of them is the H-043 defect again.

Run: .venv/bin/python strategies/goldflow/daily.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from core.gold_flow import load_flow                               # noqa: E402
from core.markets import COSTS, EXEC_MODE                          # noqa: E402

RT = COSTS["XAUUSD"].round_trip(EXEC_MODE)
HOLDS = (1, 2, 3, 5, 10)
BUCKETS = 5
NULL_SEEDS = 200


def daily_flow() -> pd.DataFrame:
    """One row per trading day: price, and the day's net buying pressure."""
    m = load_flow("XAUUSD", "1min")
    m = m[m.vol > 0]
    g = m.resample("1D")
    d = pd.DataFrame({
        "open": g.open.first(), "close": g.close.last(),
        "askvol": g.askvol.sum(), "bidvol": g.bidvol.sum(),
        "bars": g.close.count(),
    }).dropna(subset=["close"])
    d = d[d.bars > 200]                       # drop half-days and holidays
    d["vol"] = d.askvol + d.bidvol
    d["delta"] = d.askvol - d.bidvol
    d["imb"] = d.delta / d.vol
    # normalised against its own recent scale, so a busy week does not dominate
    d["imb_z"] = ((d.imb - d.imb.rolling(30, min_periods=15).mean())
                  / d.imb.rolling(30, min_periods=15).std())
    # the divergence read: price up on falling pressure, or the reverse
    d["ret"] = (d.close / d.open - 1.0) * 1e4
    d["diverge"] = np.sign(d.ret) * -np.sign(d.imb_z) * d.imb_z.abs()
    return d.dropna(subset=["imb_z"])


def response(d: pd.DataFrame, sig: str, hold: int) -> dict | None:
    """Bucket the signal, measure the forward return. Signal is lagged one day."""
    x = pd.DataFrame({"s": d[sig].shift(1),          # decided on the CLOSED day
                      "f": (d.open.shift(-hold) / d.open - 1.0) * 1e4})
    x = x.replace([np.inf, -np.inf], np.nan).dropna()
    if len(x) < 120:
        return None
    try:
        x["b"] = pd.qcut(x.s, BUCKETS, labels=False, duplicates="drop")
    except ValueError:
        return None
    g = x.groupby("b").f
    mean, med = g.mean(), g.median()
    if len(mean) < 3:
        return None
    rho = float(pd.Series(mean.values).corr(pd.Series(range(len(mean))),
                                            method="spearman"))
    return {"n": int(len(x)), "mean_sp": float(mean.iloc[-1] - mean.iloc[0]),
            "med_sp": float(med.iloc[-1] - med.iloc[0]), "rho": rho,
            "cells": [round(v, 1) for v in mean.values]}


def null_p(d: pd.DataFrame, sig: str, hold: int, observed: float) -> float:
    """Block-shuffle the SIGNAL, keep the market. 20-day blocks."""
    vals = d[sig].values
    n, bs = len(vals), 20
    hits = 0
    for seed in range(NULL_SEEDS):
        rng = np.random.default_rng(seed)
        blocks = [vals[i:i + bs] for i in range(0, n, bs)]
        rng.shuffle(blocks)
        sh = d.copy()
        sh[sig] = np.concatenate(blocks)[:n]
        r = response(sh, sig, hold)
        if r and abs(r["mean_sp"]) >= abs(observed):
            hits += 1
    return hits / NULL_SEEDS


def run(d: pd.DataFrame, tag: str, with_null: bool) -> None:
    print(f"\n=== {tag}   {len(d)} days   {d.index[0].date()} -> "
          f"{d.index[-1].date()} " + "=" * 12)
    print(f"{'signal':9}{'hold':>6}{'n':>6}{'quintile means (low->high) bps':>40}"
          f"{'rho':>7}{'meanSp':>9}{'medSp':>9}")
    print("-" * 86)
    hits = []
    for sig in ("imb_z", "diverge"):
        for hold in HOLDS:
            r = response(d, sig, hold)
            if not r:
                continue
            cells = " ".join(f"{v:6.1f}" for v in r["cells"])
            print(f"{sig:9}{hold:>6}{r['n']:>6}{cells:>40}{r['rho']:>7.2f}"
                  f"{r['mean_sp']:>9.1f}{r['med_sp']:>9.1f}", flush=True)
            same_sign = np.sign(r["mean_sp"]) == np.sign(r["med_sp"])
            if abs(r["rho"]) >= 0.8 and abs(r["mean_sp"]) > 2 * RT and same_sign:
                hits.append((sig, hold, r))
    if not hits:
        print("  no cell is monotone AND pays AND agrees between mean and median.")
        return
    if not with_null:
        return
    print("\n  candidates -> block-shuffled null, 200 seeds:")
    for sig, hold, r in hits:
        p = null_p(d, sig, hold, r["mean_sp"])
        v = "BEATS NULL" if p < 0.05 else ("borderline" if p < 0.10
                                           else "INSIDE NOISE")
        print(f"    {sig} hold {hold}d   observed {r['mean_sp']:+.1f} bps   "
              f"p = {p:.3f}   {v}", flush=True)


def main() -> int:
    print("H-052 — daily net buying pressure on gold. The ask side has never")
    print(f"been used in this repo. Cost bar 2x round trip = {2*RT:.2f} bps.")
    d = daily_flow()
    run(d, "XAUUSD daily  ALL", with_null=True)
    early, late = d[d.index < "2024-01-01"], d[d.index >= "2025-08-01"]
    if len(early) > 60:
        run(early, "XAUUSD daily  2023 chunk", with_null=False)
    if len(late) > 60:
        run(late, "XAUUSD daily  2025-26 chunk", with_null=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
