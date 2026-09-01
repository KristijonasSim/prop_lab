"""H-003 improvement study — participation and time of day, paired.

Same method as H-002's stage 8 so the two are directly comparable. H-003 was
rejected because it lost to its own null benchmark; the question here is whether
either established lever changes that, or whether it just moves a dead family
around.
"""
from __future__ import annotations

import sys, time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from core.lift_study import LEVERS, subsample, summarise             # noqa: E402
from strategies.vwap.stage1_grid import ASSETS                       # noqa: E402
from strategies.ema_vwap.sweep import build_grid, sweep, TFS         # noqa: E402
from strategies.ema_vwap.stage1_grid import load_tf, OUT, EMAS, ANCHORS  # noqa: E402


def _job(args):
    sym, tf = args
    try:
        df = load_tf(sym, tf)
    except Exception:
        return None
    if len(df) < 3000:
        return None
    fee, slip, minrisk = ASSETS[sym]
    bph = TFS[tf][1]
    roll = max(20, int(round(24 * 4 * bph)))
    base = build_grid(bph)
    for c in base:
        c["min_risk_bps"] = minrisk
    # the EMA length and anchor are part of the config space here
    cfgs = []
    for ema_len in EMAS:
        for anchor in ANCHORS:
            for c in base:
                cfgs.append({**c, "_ema": ema_len, "_anchor": anchor})
    cfgs = subsample(cfgs)
    for i, c in enumerate(cfgs):
        c["cfg_id"] = i

    frames = []
    t0 = time.time()
    for lever, over in LEVERS.items():
        rows = []
        for ema_len in EMAS:
            for anchor in ANCHORS:
                grp = [{**c, **over} for c in cfgs
                       if c["_ema"] == ema_len and c["_anchor"] == anchor]
                if not grp:
                    continue
                r = sweep(df, grp, ema_len, anchor, roll, fee, slip)
                r["cfg_id"] = [c["cfg_id"] for c in grp]
                rows.append(r)
        if not rows:
            continue
        r = pd.concat(rows, ignore_index=True)
        r["lever"] = lever
        r["combo"] = f"{sym} {tf}"
        frames.append(r[["combo", "cfg_id", "lever", "pf", "trades", "trades_per_day"]])
    print(f"  {sym:8s} {tf:4s} [{time.time()-t0:.0f}s]", flush=True)
    return pd.concat(frames, ignore_index=True)


def main():
    combos = [(s, tf) for s in ASSETS for tf in TFS
              if not (s == "BTCUSDT" and tf in ("3m", "5m")) and tf != "1d"]
    frames = []
    with ProcessPoolExecutor(max_workers=12) as ex:
        futs = [ex.submit(_job, c) for c in combos]
        for fu in as_completed(futs):
            r = fu.result()
            if r is not None:
                frames.append(r)
    d = pd.concat(frames, ignore_index=True)
    d.to_parquet(OUT / "stage4_lift_raw.parquet", index=False)
    s = summarise(frames)
    s.to_csv(OUT / "stage4_lift.csv", index=False)
    print("\n=== H-003 EMA x VWAP: paired lift on the median ===")
    print(s.to_string(index=False))


if __name__ == "__main__":
    main()
