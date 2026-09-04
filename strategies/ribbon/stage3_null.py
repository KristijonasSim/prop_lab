"""H-016 stage 3 - the paired null, and the direction control.

The rule this repo learned from H-005 and H-010: re-run the IDENTICAL grid on
phase-randomised copies of the same markets. Real returns, shuffled sequence,
each bar keeping its own volume (`shuffle_market_paired`). Any edge is
destroyed by construction, so whatever the search still finds there is the
score the real data has to beat.

Stage 2 found 1,300+ configurations clearing PF 1.20 at double cost. That
number is meaningless on its own - H-005 found 1,702 and its null found 19,062.

Five seeds, because one shuffle is a sample of size one.

Output: backtests/ribbon/stage3_null.csv
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from strategies.ribbon.sweep import (OUT, TFS, build_grid,        # noqa: E402
                                     load_tf, shuffled, sweep)
from strategies.ribbon.stage2_grid import MARKETS, MIN_BARS       # noqa: E402

NSEEDS = 5


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    frames, t0 = [], time.time()
    for seed in range(NSEEDS):
        for sym in MARKETS:
            for tf in TFS:
                df = load_tf(sym, tf)
                if len(df) < MIN_BARS:
                    continue
                sh = shuffled(df, sym, tf, "s3", seed)
                r = sweep(sh, build_grid(TFS[tf][1]), sym, tf)
                r["seed"] = seed
                frames.append(r)
        done = pd.concat(frames, ignore_index=True)
        print(f"  seed {seed}: best PF@2x {done[done.seed == seed].pf_2x.max():.3f}"
              f"  ({time.time() - t0:.0f}s)", flush=True)
    out = pd.concat(frames, ignore_index=True)
    out.to_csv(OUT / "stage3_null.csv", index=False)
    print(f"\nwrote {OUT / 'stage3_null.csv'}  {len(out):,} rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
