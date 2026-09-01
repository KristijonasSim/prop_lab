"""H-002 improvement study — participation and time of day, paired."""
from __future__ import annotations

import sys, time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from core.lift_study import LEVERS, subsample, summarise            # noqa: E402
from strategies.vwap.sweep import sweep, features                   # noqa: E402
from strategies.vwap.stage1_grid import ASSETS, OUT                 # noqa: E402
from strategies.vwap.stage3_timeframes import load_tf, TFS, build_grid  # noqa: E402


def _job(args):
    sym, tf = args
    try:
        df = load_tf(sym, tf)
    except Exception:
        return None
    if len(df) < 3000:
        return None
    fee, slip, minrisk = ASSETS[sym]
    cfgs = subsample(build_grid(TFS[tf][1]))
    for i, c in enumerate(cfgs):
        c["min_risk_bps"] = minrisk
        c["cfg_id"] = i
    feats = features(df)
    frames = []
    t0 = time.time()
    for lever, over in LEVERS.items():
        cs = [{**c, **over} for c in cfgs]
        r = sweep(df, cs, fee, slip, feats=feats)
        r["lever"] = lever
        r["combo"] = f"{sym} {tf}"
        frames.append(r[["combo", "cfg_id", "lever", "pf", "trades", "trades_per_day"]])
    print(f"  {sym:8s} {tf:4s} [{time.time()-t0:.0f}s]", flush=True)
    return pd.concat(frames, ignore_index=True)


def main():
    combos = [(s, tf) for s in ASSETS for tf in TFS
              if not (s == "BTCUSDT" and tf == "5m")]
    frames = []
    with ProcessPoolExecutor(max_workers=12) as ex:
        futs = [ex.submit(_job, c) for c in combos]
        for fu in as_completed(futs):
            r = fu.result()
            if r is not None:
                frames.append(r)
    d = pd.concat(frames, ignore_index=True)
    d.to_parquet(OUT / "stage8_lift_raw.parquet", index=False)
    s = summarise(frames)
    s.to_csv(OUT / "stage8_lift.csv", index=False)
    print("\n=== H-002 VWAP: paired lift on the median ===")
    print(s.to_string(index=False))


if __name__ == "__main__":
    main()
