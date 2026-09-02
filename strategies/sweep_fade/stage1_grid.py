"""H-005 stage 1 — full grid with a phase-randomised null, all markets."""
from __future__ import annotations

import sys, time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from core import data as crypto_data                                # noqa: E402
from core import fx_data                                            # noqa: E402
from strategies.vwap.stage1_grid import ASSETS                      # noqa: E402
from strategies.vwap.stage3_timeframes import (shuffle_market_paired,  # noqa: E402
                                               null_seed)
from strategies.sweep_fade.sweep import build_grid, sweep, TFS, features  # noqa: E402

OUT = ROOT / "backtests" / "sweep_fade"
OUT.mkdir(parents=True, exist_ok=True)
START, END = "2023-09-01", "2026-09-01"
CRYPTO = {"BTCUSDT": "BTC/USDT", "ETHUSDT": "ETH/USDT", "SOLUSDT": "SOL/USDT"}
COSTS = dict(ASSETS)
COSTS.update({"ETHUSDT": (5.0, 2.0, 10.0), "SOLUSDT": (5.0, 3.0, 12.0),
              "XAGUSD": (1.5, 0.8, 4.0)})


def load_tf(sym, tf):
    rule = TFS[tf][0]
    if sym in CRYPTO:
        if tf == "5m":
            return pd.DataFrame()
        base = crypto_data.load(CRYPTO[sym], "15m")
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
    except Exception:
        return None
    if len(df) < 3000:
        return None
    fee, slip, minrisk = COSTS[sym]
    cfgs = build_grid(TFS[tf][1])
    for c in cfgs:
        c["min_risk_bps"] = minrisk
    # paired shuffle: each bar keeps its own volume, so the rvol filter cannot
    # win against the null just by having a volume/return link the null lacks
    sh = shuffle_market_paired(df, seed=null_seed(sym, tf, "h005"))
    frames = []
    t0 = time.time()
    for kind, d in (("real", df), ("shuffled", sh)):
        f = features(d)
        for m in (1, 2, 3):
            r = sweep(d, cfgs, fee * m, slip * m, feats=f)
            r["symbol"], r["tf"], r["kind"], r["cost_mult"] = sym, tf, kind, m
            frames.append(r)
    out = pd.concat(frames, ignore_index=True)
    a = out[(out.kind == "real") & (out.cost_mult == 1) & (out.trades >= 100)]
    b = out[(out.kind == "shuffled") & (out.cost_mult == 1) & (out.trades >= 100)]
    nan = float("nan")
    print(f"{sym:8s} {tf:4s} REAL med {(a.pf.median() if len(a) else nan):.3f} "
          f"best {(a.pf.max() if len(a) else nan):.3f} clear {int((a.pf>=1.2).sum()):4d} | "
          f"NULL med {(b.pf.median() if len(b) else nan):.3f} "
          f"clear {int((b.pf>=1.2).sum()):4d}  tpd {(a.trades_per_day.median() if len(a) else nan):.2f} "
          f"[{time.time()-t0:.0f}s]", flush=True)
    return out


def main():
    syms = list(ASSETS) + ["ETHUSDT", "SOLUSDT", "XAGUSD"]
    combos = [(s, tf) for s in syms for tf in TFS]
    print(f"{len(combos)} combinations", flush=True)
    frames = []
    with ProcessPoolExecutor(max_workers=12) as ex:
        futs = [ex.submit(_job, c) for c in combos]
        for fu in as_completed(futs):
            r = fu.result()
            if r is not None:
                frames.append(r)
    d = pd.concat(frames, ignore_index=True)
    d.to_parquet(OUT / "stage1_grid.parquet", index=False)
    print(f"\nsaved {len(d)} rows", flush=True)


if __name__ == "__main__":
    main()
