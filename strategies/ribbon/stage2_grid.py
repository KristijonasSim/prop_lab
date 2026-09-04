"""H-016 stage 2 - the full grid, every market and every timeframe.

Runs the rule Kris reports having traded (`entry_thr=1.0, require_flip=1,
rr=0` - enter the bar the ribbon FIRST goes fully green, exit only on the
trailing stop) alongside 659 neighbours, so the question "is that corner
special or is it one draw from a cloud" can be answered rather than asserted.

Covers variations B (extremes-only long/short, which IS the all-green corner)
and C (the squeeze). A and D are separate stages because they need an external
series - H-009's trades and the crowd feed respectively.

Output: backtests/ribbon/stage2_real.csv
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from strategies.ribbon.sweep import (COSTS, CRYPTO, FX, OUT, TFS,  # noqa: E402
                                     build_grid, load_tf, sweep)

MARKETS = list(FX) + list(CRYPTO)
MIN_BARS = 5000


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    frames, t0 = [], time.time()
    for sym in MARKETS:
        for tf in TFS:
            df = load_tf(sym, tf)
            if len(df) < MIN_BARS:
                print(f"  skip {sym} {tf}: {len(df)} bars")
                continue
            g = build_grid(TFS[tf][1])
            r = sweep(df, g, sym, tf)
            r["bars"] = len(df)
            r["start"] = df.index[0]
            r["end"] = df.index[-1]
            frames.append(r)
            best = r["pf_2x"].max()
            print(f"  {sym:8s} {tf:4s} {len(df):>7,} bars  "
                  f"{len(g)} cfgs  best PF@2x {best:.3f}  "
                  f"clears 1.20: {(r.pf_2x >= 1.2).sum():>3d}", flush=True)
    out = pd.concat(frames, ignore_index=True)
    out.to_csv(OUT / "stage2_real.csv", index=False)
    print(f"\nwrote {OUT / 'stage2_real.csv'}  {len(out):,} rows  "
          f"({time.time() - t0:.0f}s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
