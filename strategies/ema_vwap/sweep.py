"""H-003 feature construction, grid and sweep driver."""
from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from core.metrics import resolution_estimate                       # noqa: E402
from strategies.vwap.sweep import vwap_series, rolling_vwap        # noqa: E402
from strategies.ema_vwap.engine import (simulate, T_R, T_DIR, T_ENTRY_I,  # noqa: E402
                                        T_EXIT_I, T_REASON)

RISK_FRAC = 0.01

# timeframe -> (pandas rule, bars per hour). 3m and 5m come off the cached
# 1-minute Dukascopy files; BTC has a 15m base and cannot go finer.
TFS = {"3m": ("3min", 20), "5m": ("5min", 12), "15m": ("15min", 4),
       "30m": ("30min", 2), "1h": ("1h", 1), "4h": ("4h", 0.25),
       "1d": ("1D", 1 / 24)}

EXITS = {0: "A cross back", 1: "B price/EMA", 2: "C fixed R", 3: "D session close"}


def features(df: pd.DataFrame, ema_len: int, atr_len: int = 14,
             rvol_len: int = 20 * 96):
    h, l, c, v = df.high.values, df.low.values, df.close.values, df.volume.values
    pc = np.roll(c, 1); pc[0] = c[0]
    tr = np.maximum(h - l, np.maximum(np.abs(h - pc), np.abs(l - pc)))
    atr = pd.Series(tr).ewm(alpha=1 / atr_len, adjust=False).mean().values
    ema = pd.Series(c).ewm(span=ema_len, adjust=False).mean().values
    vs = pd.Series(v, index=df.index)
    base = vs.rolling(rvol_len, min_periods=rvol_len // 4).mean().shift(1)
    rvol = (vs / base).fillna(0.0).values
    return atr, ema, rvol


def vwap_for(df: pd.DataFrame, anchor: str, roll_bars: int):
    """`anchor` is 'session' (resets at 00:00 UTC) or 'rolling'.

    This is the fork that changes the strategy most: a session VWAP resets every
    day, so the EMA crosses it often and near session boundaries; a rolling VWAP
    never resets and crosses far less."""
    if anchor == "rolling":
        v, _sd, _ss = rolling_vwap(df, roll_bars)
    else:
        v, _sd, _ss = vwap_series(df, 0, 0)
    sess = df.index.normalize().view("int64") // 10**9
    return v, sess.astype(np.int64)


def run_one(df, feats, vw, sess, cfg, fee_bps, slip_bps) -> np.ndarray:
    atr, ema, rvol = feats
    return simulate(
        df.open.values, df.high.values, df.low.values, df.close.values,
        atr, ema, vw, sess, rvol, df.index.hour.values.astype(np.int64),
        int(cfg["exit_mode"]), float(cfg["stop_atr"]), float(cfg["rr"]),
        int(cfg["max_hold_bars"]), int(cfg["warmup_bars"]),
        int(cfg["slope_len"]), float(cfg.get("min_rvol", 0.0)),
        int(cfg.get("hour_lo", 0)), int(cfg.get("hour_hi", 0)),
        int(cfg["dir_mode"]), int(cfg["reverse"]),
        float(fee_bps), float(slip_bps), float(cfg["min_risk_bps"]),
    )


def trade_metrics(trades: np.ndarray, index: pd.DatetimeIndex, span_days: float) -> dict:
    n = len(trades)
    if n == 0:
        return {"trades": 0, "pf": np.nan, "win_rate": np.nan, "avg_r": np.nan,
                "trades_per_day": 0.0, "avg_hold_h": np.nan, "max_dd_r": np.nan,
                "sharpe": np.nan, "total_r": 0.0, "days_to_target": math.inf}
    r = trades[:, T_R]
    wins, losses = r[r > 0].sum(), -r[r < 0].sum()
    pf = wins / losses if losses > 0 else math.inf
    eq = np.concatenate(([0.0], np.cumsum(r)))
    dd_r = float((eq - np.maximum.accumulate(eq)).min())
    exit_ts = index[trades[:, T_EXIT_I].astype(int)]
    entry_ts = index[trades[:, T_ENTRY_I].astype(int)]
    hold_h = float(np.mean((exit_ts - entry_ts).total_seconds()) / 3600.0)
    daily = pd.Series(r * RISK_FRAC, index=exit_ts).resample("1D").sum()
    dtt, _b, _p = resolution_estimate(daily)
    sd = daily.std(ddof=1)
    return {
        "trades": int(n), "pf": round(float(pf), 3),
        "win_rate": round(float((r > 0).mean()), 4),
        "avg_r": round(float(r.mean()), 4),
        "trades_per_day": round(n / max(span_days, 1e-9), 3),
        "avg_hold_h": round(hold_h, 2),
        "max_dd_r": round(dd_r, 2),
        "sharpe": round(float(daily.mean() / sd * math.sqrt(365)), 3) if sd else 0.0,
        "total_r": round(float(r.sum()), 2),
        "days_to_target": round(dtt, 1) if np.isfinite(dtt) else math.inf,
        "long_share": round(float((trades[:, T_DIR] > 0).mean()), 3),
        "pct_stop": round(float((trades[:, T_REASON] == 0).mean()), 3),
    }


DEFAULTS = dict(exit_mode=0, stop_atr=3.0, rr=0.0, max_hold_bars=0,
                warmup_bars=5, slope_len=0, dir_mode=0, reverse=0,
                min_risk_bps=3.0, min_rvol=0.0, hour_lo=0, hour_hi=0)


def build_grid(bars_per_hour: float) -> list[dict]:
    """All four exits, with a participation threshold as the filter axis.

    The slope filter (variant E) has been REMOVED. The paired-lift study scored
    it at -0.024 on the median with only 49.2% of configurations improving, so
    keeping it in the grid would only give the fold selection a proven-negative
    lever to pick and would double the search for nothing.

    In its place, `min_rvol`. The same study scored participation at +0.071 to
    +0.078 on the median here, with 67-75% of configurations improving - the
    fourth independent time in this project that a participation measure is the
    only filter family that carries anything."""
    hold = [0] + [max(1, int(round(hh * bars_per_hour))) for hh in (8, 24)]
    cfgs = []
    for exit_mode in (0, 1, 2, 3):
        rrs = [1.0, 2.0, 3.0] if exit_mode == 2 else [0.0]
        # a 6x ATR stop is the honest way to say "no stop" - R stays defined
        for stop_atr in (1.0, 2.0, 3.0, 6.0):
            for rr in rrs:
                for hb in ([0] if exit_mode == 3 else hold):
                    for reverse in ((0, 1) if exit_mode == 0 else (0,)):
                        for min_rvol in (0.0, 1.0, 1.5, 2.0, 2.5):
                            # Session windows. Unlike H-002 - where hour filters
                            # were flat - the paired study lifted H-003 by +0.046
                            # on London (65.9% improved) and +0.061 on the NY
                            # open (66.5%), so both go in the grid here.
                            for hl, hh in ((0, 0), (7, 16), (13, 17)):
                                c = dict(DEFAULTS)
                                c.update(exit_mode=exit_mode, stop_atr=stop_atr,
                                         rr=rr, max_hold_bars=hb, reverse=reverse,
                                         slope_len=0, min_rvol=min_rvol,
                                         hour_lo=hl, hour_hi=hh,
                                         warmup_bars=max(3, int(round(bars_per_hour))))
                                cfgs.append(c)
    return cfgs


def sweep(df, cfgs, ema_len, anchor, roll_bars, fee_bps, slip_bps) -> pd.DataFrame:
    feats = features(df, ema_len)
    vw, sess = vwap_for(df, anchor, roll_bars)
    span = (df.index[-1] - df.index[0]).total_seconds() / 86400.0
    rows = []
    for cfg in cfgs:
        tr = run_one(df, feats, vw, sess, cfg, fee_bps, slip_bps)
        row = dict(cfg)
        row.update(trade_metrics(tr, df.index, span))
        row.update(ema_len=ema_len, anchor=anchor, exit_name=EXITS[cfg["exit_mode"]])
        rows.append(row)
    return pd.DataFrame(rows)
