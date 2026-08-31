"""ORB stage 8 — split the 3-year window per asset and see what survives.

Stage 7 showed Gold and GBPUSD producing configurations above the PF 1.20 gate,
which BTC never did. That is a real difference, and it is also exactly the point
where an 8,160-way search is most likely to be fooling itself. So: fit on the
first two years, test on the last one, and check whether the SAME configuration
is still there.
"""
from __future__ import annotations

import sys, time
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from strategies.orb.sweep import sweep, features          # noqa: E402
from strategies.orb.deep_test import build_grid, OUT      # noqa: E402
from strategies.orb.stage7_assets import ASSETS, load     # noqa: E402

SPLIT = "2025-09-01"        # 2 years fit / 1 year test


def main():
    cfgs = build_grid()
    frames = []
    for sym, (fee, slip, minrisk) in ASSETS.items():
        df = load(sym)
        for c in cfgs:
            c["min_risk_bps"] = minrisk
        for name, w in (("IS", df[df.index < SPLIT]), ("OOS", df[df.index >= SPLIT])):
            feats = features(w)
            for mult in (0.0, 1.0, 2.0):
                t = time.time()
                r = sweep(w, cfgs, fee_bps=fee * mult, slip_bps=slip * mult,
                          label=f"{sym}_{name}_{mult:g}x", feats=feats)
                r["symbol"], r["window"], r["cost_mult"] = sym, name, mult
                frames.append(r)
                print(f"  {sym} {name} {mult:g}x  {time.time()-t:.0f}s", flush=True)

    out = pd.concat(frames, ignore_index=True)
    out.to_csv(OUT / "stage8_asset_oos.csv", index=False)
    print("saved stage8_asset_oos.csv", len(out), "rows")


if __name__ == "__main__":
    main()
