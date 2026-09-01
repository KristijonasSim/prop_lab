"""Paired-lift study: does a lever move the MEDIAN, across everything?

The rule this project learned the hard way: score a filter as a paired lift on
the median, never by whether it produced a new best. Run the identical
configuration family with the lever off and on and compare the distributions. A
lever that only raises the maximum has shrunk the sample, not found signal.

Both levers under test here come from findings already established elsewhere in
the repo, not from a fresh search:

  * **participation (rvol)** - the only filter family that has ever lifted a
    median here. It lifted ORB's 29-filter study, and H-002's walk-forward chose
    `rvol > 1.5` in 22 of 30 folds with nothing forcing it.
  * **time of day** - H-001 established the NY cash open as the only session
    anchor carrying anything and Asia as the worst region. Never tested on
    H-002 or H-003.

Configurations are subsampled with a fixed seed: a few hundred per combination
estimates a median shift precisely enough, and the full grid times the lever
count would cost hours for no extra confidence.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

SUBSAMPLE = 400
SEED = 20260901
MIN_TRADES = 30

# name -> config overrides. `None` is the paired baseline.
LEVERS = {
    "base": {},
    "rvol>1.0": {"min_rvol": 1.0},
    "rvol>1.25": {"min_rvol": 1.25},
    "rvol>1.5": {"min_rvol": 1.5},
    "rvol>2.0": {"min_rvol": 2.0},
    "rvol>2.5": {"min_rvol": 2.5},
    "NY 13-20": {"hour_lo": 13, "hour_hi": 20},
    "NY open 13-17": {"hour_lo": 13, "hour_hi": 17},
    "London 07-16": {"hour_lo": 7, "hour_hi": 16},
    "no Asia 07-22": {"hour_lo": 7, "hour_hi": 22},
    "Asia only 00-07": {"hour_lo": 0, "hour_hi": 7},   # control: should be worst
    "long only": {"dir_mode": 1},
    "short only": {"dir_mode": 2},
    "rvol1.5 + NY": {"min_rvol": 1.5, "hour_lo": 13, "hour_hi": 20},
    # H-003's mechanic used as CONFIRMATION rather than as a trigger, which is
    # how the literature actually uses the pair and the one form H-003 never
    # tested. `with` requires the EMA on the same side of VWAP as the trade;
    # `against` requires the opposite, i.e. fade an over-extended regime.
    "EMA with VWAP": {"ema_regime": 1},
    "EMA against VWAP": {"ema_regime": 2},
    "rvol2.5 + EMA against": {"min_rvol": 2.5, "ema_regime": 2},
}


def subsample(cfgs: list[dict]) -> list[dict]:
    if len(cfgs) <= SUBSAMPLE:
        return cfgs
    rng = np.random.default_rng(SEED)
    idx = rng.choice(len(cfgs), SUBSAMPLE, replace=False)
    return [cfgs[i] for i in sorted(idx)]


def summarise(frames: list[pd.DataFrame]) -> pd.DataFrame:
    """`frames` each carry columns lever, pf, trades, plus a `cfg_id` that pairs
    a configuration across levers."""
    d = pd.concat(frames, ignore_index=True)
    d = d[d.trades >= MIN_TRADES]
    base = d[d.lever == "base"].set_index(["combo", "cfg_id"]).pf
    rows = []
    for lever, g in d.groupby("lever"):
        s = g.set_index(["combo", "cfg_id"]).pf
        j = pd.concat([base.rename("off"), s.rename("on")], axis=1).dropna()
        if not len(j):
            continue
        rows.append({
            "lever": lever, "paired": len(j),
            "median_off": round(float(j.off.median()), 3),
            "median_on": round(float(j.on.median()), 3),
            "lift": round(float(j.on.median() - j.off.median()), 4),
            "improved": round(float((j.on > j.off).mean()), 4),
            "best_on": round(float(s.max()), 3),
            "kept": round(len(j) / max(len(base), 1), 3),
        })
    out = pd.DataFrame(rows).sort_values("lift", ascending=False)
    return out.reset_index(drop=True)
