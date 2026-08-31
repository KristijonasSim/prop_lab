"""H-002 VWAP stage 2 — close the three gaps stage 1 left.

1. **The paper's trend variant has no stop.** Stage 1 always carried one, which
   is not what Zarattini & Aziz tested: their only exit is the VWAP cross. A
   very wide stop reproduces that, and profit factor is scale-invariant in the
   stop distance, so it is a fair stand-in.
2. **Rolling VWAP.** Stage 1 only anchored to sessions. A trailing-window VWAP
   is the other way the line is used, and the only version that means anything
   on a market with no session at all.
3. **The filters that survived H-001.** Relative volume and the volatility
   regime were the only two families that lifted a median on ORB. Scored the
   same way here: paired, on the median, never on a new best.

Honest fills only. Stage 1 established that every configuration clearing the
gate did so on a resting-limit assumption, so the limit variant is dropped.
"""
from __future__ import annotations

import sys, time
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from strategies.vwap.sweep import sweep, features, DEFAULTS      # noqa: E402
from strategies.vwap.stage1_grid import ASSETS, load, OUT        # noqa: E402

# (anchor_hour, anchor_minute); -1 selects a rolling window of `minute` bars
ANCHORS = [(0, 0), (8, 0), (13, 30), (-1, 96), (-1, 192), (-1, 384)]
NO_STOP = [(0, 6.0), (0, 12.0), (1, 6.0), (1, 12.0)]   # effectively unstopped
FILTERS = {
    "none": {},
    "rvol > 1.2": {"min_rvol": 1.2},
    "rvol > 1.5": {"min_rvol": 1.5},
    "rvol > 2.0": {"min_rvol": 2.0},
    "ATR rank > 0.5": {"min_atr_rank": 0.5},
    "ATR rank > 0.7": {"min_atr_rank": 0.7},
    "ATR rank < 0.5": {"max_atr_rank": 0.5},
}


def build_grid() -> list[dict]:
    cfgs = []
    for ah, am in ANCHORS:
        for mode in (0, 1, 2, 3, 4):
            band_ks = [2.0] if mode in (0, 4) else [1.5, 2.0, 2.5]
            targets = [0, 3] if mode in (0, 3, 4) else [0, 1, 2, 3]
            stops = NO_STOP if mode == 0 else [(0, 0.5), (0, 1.0), (1, 1.0), (1, 2.0)]
            for bk in band_ks:
                for sm, sk in stops:
                    for tm in targets:
                        for rr in ([1.0, 2.0, 3.0] if tm == 3 else [0.0]):
                            for hold in (0, 32):
                                for fname, fover in FILTERS.items():
                                    c = dict(DEFAULTS)
                                    c.update(anchor_hour=ah, anchor_minute=am,
                                             mode=mode, fill_mode=1, band_k=bk,
                                             stop_mode=sm, stop_k=sk,
                                             target_mode=tm, rr=rr,
                                             max_hold_bars=hold)
                                    c.update(fover)
                                    c["filter"] = fname
                                    cfgs.append(c)
    return cfgs


def main():
    cfgs = build_grid()
    print(f"{len(cfgs)} configs per market", flush=True)
    frames = []
    for sym, (fee, slip, minrisk) in ASSETS.items():
        try:
            df = load(sym)
        except FileNotFoundError:
            continue
        for c in cfgs:
            c["min_risk_bps"] = minrisk
        feats = features(df)
        t = time.time()
        for mult in (0.0, 1.0, 2.0):
            r = sweep(df, cfgs, fee * mult, slip * mult, feats=feats)
            r["symbol"], r["cost_mult"] = sym, mult
            frames.append(r)
        k = frames[-2]
        k = k[k.trades >= 100]
        print(f"{sym}: best {k.pf.max():.3f}  median {k.pf.median():.3f}  "
              f"clear1.2 {int((k.pf>=1.2).sum())}  [{time.time()-t:.0f}s]", flush=True)
    out = pd.concat(frames, ignore_index=True)
    out.to_csv(OUT / "stage2_paper.csv", index=False)
    print("saved", len(out), "rows", flush=True)


if __name__ == "__main__":
    main()
