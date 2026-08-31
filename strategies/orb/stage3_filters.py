"""ORB stage 3 — the variants the literature says carry the edge.

Stage 1 tests the price pattern on its own. The Zarattini/Barbon/Aziz result is
that the pattern alone is worth almost nothing (Sharpe 0.48) and that the
relative-volume "stocks in play" filter is what produced Sharpe 2.81. This stage
tests that claim on BTC, plus the QQQ paper's first-candle-direction entry and
its 10%-of-daily-ATR stop with a far target.
"""
from __future__ import annotations

import sys, time
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from core import data                                    # noqa: E402
from strategies.orb.sweep import sweep, DEFAULTS, features  # noqa: E402
from strategies.orb.deep_test import FEE_BPS, SLIP_BPS, IS_START, IS_END, OOS_START, OOS_END, OUT  # noqa: E402

HOURS = [0, 7, 13]
OR_BARS = [1, 2, 4]                 # 15m / 30m / 1h
RVOL = [0.0, 1.2, 1.5, 2.0, 3.0]    # 0 = no filter
DATR_MULT = [0.05, 0.10, 0.20]      # fraction of the 14-day ATR
RR = [0.0, 3.0, 5.0, 10.0]          # 0 = hold to session end
ENTRY = [0, 2]                      # breakout touch | first-candle direction
TREND = [0, 1]                      # none | only with the 200-bar EMA


def build_grid() -> list[dict]:
    cfgs = []
    for hour in HOURS:
        for ob in OR_BARS:
            for rv in RVOL:
                for dm in DATR_MULT:
                    for rr in RR:
                        for em in ENTRY:
                            for tm in TREND:
                                c = dict(DEFAULTS)
                                c.update(hour=hour, or_bars=ob, hold_bars=96,
                                         entry_mode=em, stop_mode=2,
                                         stop_atr_mult=dm, use_datr=1,
                                         rr=rr, min_rvol=rv, trend_mode=tm)
                                cfgs.append(c)
    return cfgs


def main():
    df = data.load("BTC/USDT", "15m")
    cfgs = build_grid()
    print(f"configs {len(cfgs)}", flush=True)

    frames = []
    for name, lo, hi in (("IS", IS_START, IS_END), ("OOS", OOS_START, OOS_END)):
        w = df[(df.index >= lo) & (df.index < hi)]
        feats = features(w)
        for mult in (0.0, 1.0, 2.0):
            t = time.time()
            r = sweep(w, cfgs, fee_bps=FEE_BPS * mult, slip_bps=SLIP_BPS * mult,
                      label=f"{name}_cost{mult:g}x", feats=feats)
            r["window"], r["cost_mult"] = name, mult
            frames.append(r)
            print(f"  {name} cost {mult:g}x  {time.time()-t:.0f}s", flush=True)

    out = pd.concat(frames, ignore_index=True)
    out.to_csv(OUT / "stage3_filters.csv", index=False)
    print("saved", len(out), "rows")


if __name__ == "__main__":
    main()
