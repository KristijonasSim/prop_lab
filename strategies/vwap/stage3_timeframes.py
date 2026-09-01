"""H-002 VWAP stage 3 — the timeframe axis, plus a null benchmark.

Two jobs.

**Timeframes.** Everything so far ran on 15m. FX and metals are rebuilt from the
cached 1-minute files at 5m / 15m / 30m / 1h / 4h; BTC is resampled from its 15m
base. Bar-count parameters are scaled so "4 hours of holding" means four hours on
every timeframe rather than four hours on one and sixteen on another.

**The null benchmark.** This search is now large enough that its maximum is
interesting on its own. So the identical grid is also run on a phase-randomised
version of each market: the real bar-to-bar returns, shuffled, so all the
distributional properties survive and every trace of sequence is destroyed. Any
edge is gone by construction, and whatever maximum profit factor the search still
produces is the score to beat. A live result only counts if it clears the null.
"""
from __future__ import annotations

import sys, time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from core import data as crypto_data                       # noqa: E402
from core import fx_data                                   # noqa: E402
from strategies.vwap.sweep import sweep, features, DEFAULTS  # noqa: E402
from strategies.vwap.stage1_grid import ASSETS, OUT, START, END  # noqa: E402

# timeframe -> (pandas rule, bars per hour)
TFS = {"5m": ("5min", 12), "15m": ("15min", 4), "30m": ("30min", 2),
       "1h": ("1h", 1), "4h": ("4h", 0.25)}

ANCHORS = [(0, 0), (8, 0), (13, 30), (-1, 0)]   # rolling window sized per timeframe
# The paired-lift study (stage 8) scored every one of these on the median across
# all 44 market x timeframe combinations. Participation is the only family that
# lifts it, and the lift grows with the threshold: rvol>2.5 gave +0.063 with 65%
# of configurations improving, against +0.038 and a coin-flip 50% for rvol>1.5.
# The higher thresholds are added here so the walk-forward can choose them.
# Time-of-day windows were tested and did NOT transfer from H-001 (+0.010 at
# best, ~50% improved), so no hour filter is in the grid.
FILTERS = {"none": {}, "rvol>1.5": {"min_rvol": 1.5},
           "rvol>2.0": {"min_rvol": 2.0}, "rvol>2.5": {"min_rvol": 2.5},
           "ATRrank>0.5": {"min_atr_rank": 0.5}, "ATRrank>0.7": {"min_atr_rank": 0.7},
           "ATRrank<0.5": {"max_atr_rank": 0.5}}


def load_tf(sym: str, tf: str, full_history: bool = False) -> pd.DataFrame:
    """`full_history` keeps everything the cache holds instead of clamping to the
    common START/END window. Only BTC has anything outside it; the FX cache
    begins at START anyway."""
    if sym == "BTCUSDT":
        base = crypto_data.load("BTC/USDT", "15m")
        rule = TFS[tf][0]
        if tf == "5m":
            return pd.DataFrame()               # cannot go finer than the 15m base
        if tf != "15m":
            base = base.resample(rule, label="left", closed="left").agg(
                {"open": "first", "high": "max", "low": "min",
                 "close": "last", "volume": "sum"}).dropna(subset=["open"])
        df = base
    else:
        df = fx_data.load(sym, TFS[tf][0])
    if full_history:
        return df
    return df[(df.index >= START) & (df.index < END)]


def shuffle_market(df: pd.DataFrame, seed: int) -> pd.DataFrame:
    """Phase-randomise: keep every return, destroy their order. Bars are rebuilt
    around the new path so highs and lows stay consistent with it."""
    rng = np.random.default_rng(seed)
    c = df.close.values
    ret = np.diff(np.log(c))
    rng.shuffle(ret)
    new_c = c[0] * np.exp(np.concatenate(([0.0], np.cumsum(ret))))
    scale = new_c / c
    out = pd.DataFrame({
        "open": df.open.values * scale, "high": df.high.values * scale,
        "low": df.low.values * scale, "close": new_c,
        "volume": rng.permutation(df.volume.values)}, index=df.index)
    out["high"] = out[["open", "high", "close"]].max(axis=1)
    out["low"] = out[["open", "low", "close"]].min(axis=1)
    return out


def shuffle_market_paired(df: pd.DataFrame, seed: int) -> pd.DataFrame:
    """A STRICTER null for volume-based filters.

    `shuffle_market` permutes volume independently of returns, so on that null a
    bar's volume tells you nothing about its own move. That is the right null for
    a price-pattern strategy, but it quietly hands any participation filter a
    free win: the filter has a real contemporaneous volume/return relationship to
    work with on the live data and none at all on the null, so it looks
    predictive even if all it captures is "high-volume bars are bigger bars".

    This version permutes (return, volume) as PAIRS. Each bar keeps its own
    volume, so the contemporaneous relationship survives and only the sequence is
    destroyed. A participation filter that still beats this null is finding
    something about regime and ordering, not just bar size.
    """
    rng = np.random.default_rng(seed)
    c = df.close.values
    v = df.volume.values
    ret = np.diff(np.log(c))
    perm = rng.permutation(len(ret))
    ret = ret[perm]
    # volume[i+1] is the volume of the bar that produced ret[i]
    vol = np.concatenate(([v[0]], v[1:][perm]))

    new_c = c[0] * np.exp(np.concatenate(([0.0], np.cumsum(ret))))
    scale = new_c / c
    out = pd.DataFrame({
        "open": df.open.values * scale, "high": df.high.values * scale,
        "low": df.low.values * scale, "close": new_c, "volume": vol},
        index=df.index)
    out["high"] = out[["open", "high", "close"]].max(axis=1)
    out["low"] = out[["open", "low", "close"]].min(axis=1)
    return out


def build_grid(bars_per_hour: float) -> list[dict]:
    """Hold horizons in HOURS, converted per timeframe so they mean the same
    thing everywhere."""
    hold_bars = [0] + [max(1, int(round(h * bars_per_hour))) for h in (4, 12)]
    roll = max(20, int(round(24 * 4 * bars_per_hour)))     # 4 days of bars
    cfgs = []
    for ah, am in ANCHORS:
        am2 = roll if ah == -1 else am
        for mode in (0, 1, 2, 3, 4):
            band_ks = [2.0] if mode in (0, 4) else [1.5, 2.0, 2.5]
            targets = [0, 3] if mode in (0, 3, 4) else [0, 1, 2, 3]
            stops = ([(0, 6.0), (1, 6.0)] if mode == 0
                     else [(0, 0.5), (0, 1.0), (1, 1.0), (1, 2.0)])
            for bk in band_ks:
                for sm, sk in stops:
                    for tm in targets:
                        for rr in ([1.0, 2.0, 3.0] if tm == 3 else [0.0]):
                            for hb in hold_bars:
                                for fname, fover in FILTERS.items():
                                    c = dict(DEFAULTS)
                                    c.update(anchor_hour=ah, anchor_minute=am2,
                                             mode=mode, fill_mode=1, band_k=bk,
                                             stop_mode=sm, stop_k=sk,
                                             target_mode=tm, rr=rr,
                                             max_hold_bars=hb,
                                             warmup_bars=max(2, int(bars_per_hour * 2)))
                                    c.update(fover)
                                    c["filter"] = fname
                                    cfgs.append(c)
    return cfgs


def main():
    real, null = [], []
    for sym, (fee, slip, minrisk) in ASSETS.items():
        for tf, (rule, bph) in TFS.items():
            try:
                df = load_tf(sym, tf)
            except Exception:
                continue
            if len(df) < 3000:
                continue
            cfgs = build_grid(bph)
            for c in cfgs:
                c["min_risk_bps"] = minrisk
            t = time.time()

            r = sweep(df, cfgs, fee, slip, feats=features(df))
            r["symbol"], r["tf"], r["kind"] = sym, tf, "real"
            real.append(r)

            sh = shuffle_market(df, seed=abs(hash((sym, tf))) % (2**31))
            rn = sweep(sh, cfgs, fee, slip, feats=features(sh))
            rn["symbol"], rn["tf"], rn["kind"] = sym, tf, "shuffled"   # not "null": pandas reads that back as NaN
            null.append(rn)

            a = r[r.trades >= 100]
            b = rn[rn.trades >= 100]
            print(f"{sym:8s} {tf:4s} n={len(cfgs):5d}  REAL best {a.pf.max():.3f} "
                  f"med {a.pf.median():.3f} clear1.6 {int((a.pf>=1.6).sum()):4d} | "
                  f"NULL best {b.pf.max():.3f} med {b.pf.median():.3f} "
                  f"clear1.6 {int((b.pf>=1.6).sum()):4d}  [{time.time()-t:.0f}s]", flush=True)

    out = pd.concat(real + null, ignore_index=True)
    out.to_csv(OUT / "stage3_timeframes.csv", index=False)
    print("saved", len(out), "rows", flush=True)


if __name__ == "__main__":
    main()
