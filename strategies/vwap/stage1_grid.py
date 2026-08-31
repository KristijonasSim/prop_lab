"""H-002 VWAP — full model-family grid across every instrument we hold.

Five families, three session anchors, both fill assumptions, at 0x / 1x / 2x / 3x
cost. Combinations that are meaningless are skipped rather than run and
explained away later:
  * a VWAP target makes no sense for reclaim or pullback - those enter AT VWAP,
    so the trade would exit on the bar it opened;
  * band width is irrelevant to the trend family, which only cares about the
    VWAP line itself;
  * the limit-fill assumption only differs from close-confirmation for the two
    families that enter at a band.
"""
from __future__ import annotations

import sys, time
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from core import data as crypto_data                       # noqa: E402
from core import fx_data                                   # noqa: E402
from strategies.vwap.sweep import sweep, features, DEFAULTS  # noqa: E402

OUT = ROOT / "backtests" / "vwap"
OUT.mkdir(parents=True, exist_ok=True)

START, END = "2023-09-01", "2026-09-01"

# symbol -> (fee bps/side, slippage bps/side, min_risk_bps)
ASSETS = {
    "BTCUSDT": (5.0, 2.0, 10.0),
    "XAUUSD":  (1.00, 0.50, 3.0),
    "EURUSD":  (0.45, 0.30, 2.0),
    "GBPUSD":  (0.50, 0.30, 2.0),
    "USDJPY":  (0.45, 0.30, 2.0),
    "AUDUSD":  (0.60, 0.35, 2.0),
    "USDCAD":  (0.65, 0.35, 2.0),
    "USDCHF":  (0.70, 0.35, 2.0),
    "NZDUSD":  (0.85, 0.45, 2.5),
}

ANCHORS = [(0, 0), (8, 0), (13, 30)]      # UTC day, London open, NY cash open
MODES = {0: "trend", 1: "fade", 2: "break", 3: "reclaim", 4: "pullback"}
BAND_K = [1.0, 1.5, 2.0, 2.5, 3.0]
STOPS = [(0, 0.5), (0, 1.0), (0, 2.0), (1, 1.0), (1, 2.0), (1, 3.0)]
RR = [1.0, 2.0, 3.0]
HOLD = [0, 16, 32]                        # session horizon, 4h, 8h


def build_grid() -> list[dict]:
    cfgs = []
    for ah, am in ANCHORS:
        for mode in MODES:
            band_ks = [2.0] if mode in (0, 4) else BAND_K
            fills = [0, 1] if mode in (1, 2) else [1]
            # target_mode: 0 session end, 1 VWAP, 2 opposite band, 3 R multiple
            targets = [0, 3] if mode in (0, 3, 4) else [0, 1, 2, 3]
            for bk in band_ks:
                for fm in fills:
                    for sm, sk in STOPS:
                        for tm in targets:
                            rrs = RR if tm == 3 else [0.0]
                            for rr in rrs:
                                for hold in HOLD:
                                    c = dict(DEFAULTS)
                                    c.update(anchor_hour=ah, anchor_minute=am,
                                             mode=mode, fill_mode=fm, band_k=bk,
                                             stop_mode=sm, stop_k=sk,
                                             target_mode=tm, rr=rr,
                                             max_hold_bars=hold)
                                    cfgs.append(c)
    return cfgs


def load(sym: str) -> pd.DataFrame:
    df = crypto_data.load("BTC/USDT", "15m") if sym == "BTCUSDT" else fx_data.load(sym)
    return df[(df.index >= START) & (df.index < END)]


def main():
    cfgs = build_grid()
    print(f"{len(cfgs)} configs per market x {len(ASSETS)} markets", flush=True)
    frames = []
    for sym, (fee, slip, minrisk) in ASSETS.items():
        try:
            df = load(sym)
        except FileNotFoundError:
            print(f"SKIP {sym}", flush=True)
            continue
        for c in cfgs:
            c["min_risk_bps"] = minrisk
        feats = features(df)
        t = time.time()
        for mult in (0.0, 1.0, 2.0, 3.0):
            r = sweep(df, cfgs, fee * mult, slip * mult, feats=feats)
            r["symbol"], r["cost_mult"] = sym, mult
            frames.append(r)
        k = frames[-3]           # the 1x frame
        k = k[k.trades >= 100]
        print(f"{sym}: best {k.pf.max():.3f}  median {k.pf.median():.3f}  "
              f"clear1.2 {int((k.pf>=1.2).sum())}  [{time.time()-t:.0f}s]", flush=True)
        frames = frames  # keep

    out = pd.concat(frames, ignore_index=True)
    out.to_csv(OUT / "stage1_grid.csv", index=False)
    print("saved", len(out), "rows", flush=True)


if __name__ == "__main__":
    main()
