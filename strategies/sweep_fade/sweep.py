"""H-005 features, grid and sweep driver."""
from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from core.metrics import resolution_estimate                          # noqa: E402
from strategies.sweep_fade.engine import (simulate, T_R, T_DIR,       # noqa: E402
                                          T_ENTRY_I, T_EXIT_I, T_REASON)

RISK_FRAC = 0.01
TFS = {"5m": ("5min", 12), "15m": ("15min", 4), "30m": ("30min", 2),
       "1h": ("1h", 1), "4h": ("4h", 0.25)}


def features(df: pd.DataFrame, atr_len: int = 14, rvol_len: int = 20 * 96):
    h, l, c, v = df.high.values, df.low.values, df.close.values, df.volume.values
    pc = np.roll(c, 1); pc[0] = c[0]
    tr = np.maximum(h - l, np.maximum(np.abs(h - pc), np.abs(l - pc)))
    atr = pd.Series(tr).ewm(alpha=1 / atr_len, adjust=False).mean().values
    vs = pd.Series(v, index=df.index)
    base = vs.rolling(rvol_len, min_periods=rvol_len // 4).mean().shift(1)
    rvol = (vs / base).fillna(0.0).values
    return atr, rvol


DEFAULTS = dict(lookback=20, pierce_atr=0.1, require_wick=1, min_range_atr=1.0,
                stop_mode=0, stop_k=0.5, target_mode=1, rr=0.0, max_hold_bars=0,
                min_rvol=0.0, hour_lo=0, hour_hi=0, dir_mode=0, min_risk_bps=3.0)


def build_grid(bph: float) -> list[dict]:
    hold = [0] + [max(1, int(round(hh * bph))) for hh in (4, 12, 24)]
    cfgs = []
    for lookback in (10, 20, 50, 100):
        for pierce in (0.0, 0.1, 0.25, 0.5):
            for wick in (0, 1):
                for stop_mode, stop_k in ((0, 0.25), (0, 0.5), (0, 1.0), (1, 1.0), (1, 2.0)):
                    for tmode, rr in ((0, 1.0), (0, 2.0), (0, 3.0), (1, 0.0), (2, 0.0)):
                        for hb in hold:
                            # participation is the only filter family that has
                            # lifted a median anywhere in this project
                            for mrv in (0.0, 1.5, 2.5):
                                c = dict(DEFAULTS)
                                c.update(lookback=lookback, pierce_atr=pierce,
                                         require_wick=wick, stop_mode=stop_mode,
                                         stop_k=stop_k, target_mode=tmode, rr=rr,
                                         max_hold_bars=hb, min_rvol=mrv)
                                cfgs.append(c)
    return cfgs


def run_one(df, feats, cfg, fee, slip):
    atr, rvol = feats
    return simulate(
        df.open.values, df.high.values, df.low.values, df.close.values,
        atr, rvol, df.index.hour.values.astype(np.int64),
        int(cfg["lookback"]), float(cfg["pierce_atr"]), int(cfg["require_wick"]),
        float(cfg["min_range_atr"]), int(cfg["stop_mode"]), float(cfg["stop_k"]),
        int(cfg["target_mode"]), float(cfg["rr"]), int(cfg["max_hold_bars"]),
        float(cfg["min_rvol"]), int(cfg["hour_lo"]), int(cfg["hour_hi"]),
        int(cfg["dir_mode"]), float(fee), float(slip), float(cfg["min_risk_bps"]))


def trade_metrics(tr, index, span_days):
    n = len(tr)
    if n == 0:
        return {"trades": 0, "pf": np.nan, "win_rate": np.nan, "avg_r": np.nan,
                "trades_per_day": 0.0, "avg_hold_h": np.nan, "max_dd_r": np.nan,
                "sharpe": np.nan, "total_r": 0.0}
    r = tr[:, T_R]
    w, l = r[r > 0].sum(), -r[r < 0].sum()
    eq = np.concatenate(([0.0], np.cumsum(r)))
    ex = index[tr[:, T_EXIT_I].astype(int)]; en = index[tr[:, T_ENTRY_I].astype(int)]
    daily = pd.Series(r * RISK_FRAC, index=ex).resample("1D").sum()
    sd = daily.std(ddof=1)
    return {"trades": int(n), "pf": round(float(w / l), 3) if l > 0 else np.nan,
            "win_rate": round(float((r > 0).mean()), 4),
            "avg_r": round(float(r.mean()), 4),
            "trades_per_day": round(n / max(span_days, 1e-9), 3),
            "avg_hold_h": round(float(np.mean((ex - en).total_seconds()) / 3600.0), 2),
            "max_dd_r": round(float((eq - np.maximum.accumulate(eq)).min()), 2),
            "sharpe": round(float(daily.mean() / sd * math.sqrt(365)), 3) if sd else 0.0,
            "total_r": round(float(r.sum()), 2),
            "long_share": round(float((tr[:, T_DIR] > 0).mean()), 3)}


def sweep(df, cfgs, fee, slip, feats=None):
    feats = feats if feats is not None else features(df)
    span = (df.index[-1] - df.index[0]).total_seconds() / 86400.0
    rows = []
    for cfg in cfgs:
        tr = run_one(df, feats, cfg, fee, slip)
        row = dict(cfg); row.update(trade_metrics(tr, df.index, span))
        rows.append(row)
    return pd.DataFrame(rows)
