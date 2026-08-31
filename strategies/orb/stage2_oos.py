"""ORB stage 2 — replay the identical grid on unseen data (2024-01 -> now).

The point is the IS->OOS decay, not the OOS number on its own. A config picked
because it topped an 8,000-config IS ranking is the single most overfit thing in
the file; what it does next is the only interesting question.
"""
from __future__ import annotations

import sys, time
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from core import data                                        # noqa: E402
from strategies.orb.sweep import sweep                        # noqa: E402
from strategies.orb.deep_test import (build_grid, FEE_BPS, SLIP_BPS,  # noqa: E402
                                      OOS_START, OOS_END, OUT)


def main():
    df = data.load("BTC/USDT", "15m")
    oos = df[(df.index >= OOS_START) & (df.index < OOS_END)]
    cfgs = build_grid()
    print(f"configs {len(cfgs)} | OOS bars {len(oos)} "
          f"{oos.index[0].date()} -> {oos.index[-1].date()}", flush=True)

    frames = []
    for mult in (0.0, 1.0, 2.0, 3.0):
        t = time.time()
        r = sweep(oos, cfgs, fee_bps=FEE_BPS * mult, slip_bps=SLIP_BPS * mult,
                  label=f"OOS_cost{mult:g}x")
        r["cost_mult"] = mult
        frames.append(r)
        print(f"  cost {mult:g}x done in {time.time()-t:.0f}s", flush=True)

    out = pd.concat(frames, ignore_index=True)
    out.to_csv(OUT / "stage2_oos_grid.csv", index=False)
    print("saved", len(out), "rows")


if __name__ == "__main__":
    main()
