"""H-003 stage 1 — the full screen, with a null benchmark.

All four exits, the slope filter on and off, seven timeframes, both VWAP
anchors, three EMA lengths, nine markets, at 1x / 2x / 3x cost.

The identical grid also runs on a phase-randomised copy of every market. This
search is large enough that its maximum is interesting on its own, and on this
dataset shuffled markets have already produced profit factors above 2.4. Any
edge is destroyed by construction there, so whatever the search still finds is
the score to beat.
"""
from __future__ import annotations

import sys, time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from core import data as crypto_data                            # noqa: E402
from core import fx_data                                        # noqa: E402
from strategies.vwap.stage1_grid import ASSETS                  # noqa: E402
from strategies.vwap.stage3_timeframes import shuffle_market, null_seed  # noqa: E402
from strategies.ema_vwap.sweep import build_grid, sweep, TFS    # noqa: E402

OUT = ROOT / "backtests" / "ema_vwap"
OUT.mkdir(parents=True, exist_ok=True)
START, END = "2023-09-01", "2026-09-01"

EMAS = (50, 100, 200)          # 200 is the hypothesis; the others test sensitivity
ANCHORS = ("session", "rolling")
COSTS = (1, 2, 3)


def load_tf(sym: str, tf: str) -> pd.DataFrame:
    rule = TFS[tf][0]
    if sym == "BTCUSDT":
        if tf in ("3m", "5m"):
            return pd.DataFrame()            # 15m base cannot go finer
        base = crypto_data.load("BTC/USDT", "15m")
        if tf != "15m":
            base = base.resample(rule, label="left", closed="left").agg(
                {"open": "first", "high": "max", "low": "min",
                 "close": "last", "volume": "sum"}).dropna(subset=["open"])
        df = base
    else:
        df = fx_data.load(sym, rule)
    return df[(df.index >= START) & (df.index < END)]


def _job(args):
    sym, tf = args
    try:
        df = load_tf(sym, tf)
    except Exception as e:
        print(f"  !! {sym} {tf}: {type(e).__name__}: {e}", flush=True)
        return None
    if len(df) < 2000:
        return None
    fee, slip, minrisk = ASSETS[sym]
    bph = TFS[tf][1]
    cfgs = build_grid(bph)
    for c in cfgs:
        c["min_risk_bps"] = minrisk
    roll = max(20, int(round(24 * 4 * bph)))          # 4 days of bars

    sh = shuffle_market(df, seed=null_seed(sym, tf, "h003"))
    frames = []
    t0 = time.time()
    for kind, d in (("real", df), ("shuffled", sh)):
        for ema_len in EMAS:
            for anchor in ANCHORS:
                for mult in COSTS:
                    r = sweep(d, cfgs, ema_len, anchor, roll,
                              fee * mult, slip * mult)
                    r["symbol"], r["tf"], r["kind"], r["cost_mult"] = sym, tf, kind, mult
                    frames.append(r)
    out = pd.concat(frames, ignore_index=True)
    a = out[(out.kind == "real") & (out.cost_mult == 1) & (out.trades >= 50)]
    b = out[(out.kind == "shuffled") & (out.cost_mult == 1) & (out.trades >= 50)]
    nan = float("nan")
    print(f"{sym:8s} {tf:4s} n={len(out):6d}  "
          f"REAL best {(a.pf.max() if len(a) else nan):.3f} "
          f"med {(a.pf.median() if len(a) else nan):.3f} "
          f"clear1.2 {int((a.pf >= 1.2).sum()):4d} | "
          f"NULL best {(b.pf.max() if len(b) else nan):.3f} "
          f"clear1.2 {int((b.pf >= 1.2).sum()):4d}  "
          f"tpd {(a.trades_per_day.median() if len(a) else nan):.2f}  "
          f"[{time.time()-t0:.0f}s]", flush=True)
    return out


def main():
    combos = [(s, tf) for s in ASSETS for tf in TFS]
    print(f"{len(combos)} market x timeframe combinations", flush=True)
    frames = []
    t0 = time.time()
    with ProcessPoolExecutor(max_workers=12) as ex:
        futs = {ex.submit(_job, c): c for c in combos}
        for fu in as_completed(futs):
            r = fu.result()
            if r is not None and len(r):
                frames.append(r)
    out = pd.concat(frames, ignore_index=True)
    out.to_parquet(OUT / "stage1_grid.parquet", index=False)
    print(f"\nsaved {len(out)} rows in {time.time()-t0:.0f}s", flush=True)


if __name__ == "__main__":
    main()
