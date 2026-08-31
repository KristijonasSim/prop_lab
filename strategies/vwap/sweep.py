"""VWAP feature construction and sweep driver."""

from __future__ import annotations

import itertools
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from core.metrics import resolution_estimate                    # noqa: E402
from strategies.vwap.engine import simulate, T_R, T_DIR, T_ENTRY_I, T_EXIT_I, T_REASON  # noqa: E402

RISK_FRAC = 0.01


def vwap_series(df: pd.DataFrame, anchor_hour: int, anchor_minute: int = 0):
    """Session-anchored VWAP and the volume-weighted standard deviation of price
    about it, both reset at the anchor.

    Note on FX: Dukascopy 'volume' is a tick count, not traded size. That is the
    same series an MT5 chart shows, so the VWAP here is the one a retail platform
    would draw — but it is not a true volume-weighted price, and that limits how
    literally the institutional-benchmark mechanism should be read on FX.
    """
    tp = (df.high + df.low + df.close) / 3.0
    vol = df.volume.replace(0, np.nan).ffill().fillna(1.0)

    at_anchor = (df.index.hour == anchor_hour) & (df.index.minute == anchor_minute)
    sess = at_anchor.cumsum()

    pv = (tp * vol).groupby(sess).cumsum()
    v = vol.groupby(sess).cumsum()
    vwap = pv / v

    # volume-weighted variance of price about the running VWAP
    p2v = (tp * tp * vol).groupby(sess).cumsum()
    var = (p2v / v) - vwap * vwap
    vwstd = np.sqrt(var.clip(lower=0.0))

    return vwap.values, vwstd.values, np.flatnonzero(at_anchor).astype(np.int64)


def rolling_vwap(df: pd.DataFrame, window: int):
    """VWAP over a trailing window with no session reset — the other way the
    indicator is used, and the only anchor that makes sense on a market with no
    real session at all."""
    tp = (df.high + df.low + df.close) / 3.0
    vol = df.volume.replace(0, np.nan).ffill().fillna(1.0)
    pv = (tp * vol).rolling(window, min_periods=window // 4).sum()
    v = vol.rolling(window, min_periods=window // 4).sum()
    vwap = (pv / v)
    p2v = (tp * tp * vol).rolling(window, min_periods=window // 4).sum()
    var = (p2v / v) - vwap * vwap
    vwstd = np.sqrt(var.clip(lower=0.0))
    # "sessions" become a rolling restart every `window` bars so the horizon
    # logic still has something to hang on
    ss = np.arange(window, len(df), window, dtype=np.int64)
    return vwap.values, vwstd.values, ss


def features(df: pd.DataFrame, atr_len: int = 14, rvol_len: int = 20 * 96):
    h, l, c, v = df.high.values, df.low.values, df.close.values, df.volume.values
    pc = np.roll(c, 1); pc[0] = c[0]
    tr = np.maximum(h - l, np.maximum(np.abs(h - pc), np.abs(l - pc)))
    atr = pd.Series(tr).ewm(alpha=1 / atr_len, adjust=False).mean().values

    vs = pd.Series(v, index=df.index)
    base = vs.rolling(rvol_len, min_periods=rvol_len // 4).mean().shift(1)
    rvol = (vs / base).fillna(0.0).values

    atr_rank = (pd.Series(atr, index=df.index)
                .rolling(96 * 60, min_periods=96 * 5)
                .rank(pct=True).shift(1).fillna(0.5).values)
    return atr, rvol, atr_rank


DEFAULTS = dict(mode=0, fill_mode=1, band_k=2.0, stop_mode=0, stop_k=1.0,
                target_mode=0, rr=0.0, max_hold_bars=0, warmup_bars=8,
                one_trade=0, min_rvol=0.0, min_atr_rank=0.0, max_atr_rank=0.0,
                dir_mode=0, min_risk_bps=2.0, anchor_hour=0, anchor_minute=0)


def run_one(df, feats, vw_cache, cfg, fee_bps, slip_bps) -> np.ndarray:
    atr, rvol, atr_rank = feats
    key = (int(cfg["anchor_hour"]), int(cfg["anchor_minute"]))
    if key not in vw_cache:
        # anchor_hour == -1 selects the rolling window, sized by anchor_minute
        vw_cache[key] = (rolling_vwap(df, int(cfg["anchor_minute"]))
                         if key[0] == -1 else vwap_series(df, *key))
    vwap, vwstd, ss = vw_cache[key]
    return simulate(
        df.open.values, df.high.values, df.low.values, df.close.values,
        atr, vwap, vwstd, rvol, atr_rank, ss,
        int(cfg["mode"]), int(cfg["fill_mode"]), float(cfg["band_k"]),
        int(cfg["stop_mode"]), float(cfg["stop_k"]), int(cfg["target_mode"]),
        float(cfg["rr"]), int(cfg["max_hold_bars"]), int(cfg["warmup_bars"]),
        int(cfg["one_trade"]), float(cfg["min_rvol"]), float(cfg["min_atr_rank"]),
        float(cfg["max_atr_rank"]), int(cfg["dir_mode"]),
        float(fee_bps), float(slip_bps), float(cfg["min_risk_bps"]),
    )


def trade_metrics(trades: np.ndarray, index: pd.DatetimeIndex, span_days: float) -> dict:
    n = len(trades)
    if n == 0:
        return {"trades": 0, "pf": np.nan, "win_rate": np.nan, "avg_r": np.nan,
                "trades_per_day": 0.0, "avg_hold_h": np.nan, "max_dd": np.nan,
                "max_dd_r": np.nan, "sharpe": np.nan, "total_r": 0.0,
                "days_to_target": math.inf, "long_share": np.nan}
    r = trades[:, T_R]
    wins, losses = r[r > 0].sum(), -r[r < 0].sum()
    pf = wins / losses if losses > 0 else math.inf
    eq = np.concatenate(([0.0], np.cumsum(r)))
    dd_r = float((eq - np.maximum.accumulate(eq)).min())
    exit_ts = index[trades[:, T_EXIT_I].astype(int)]
    entry_ts = index[trades[:, T_ENTRY_I].astype(int)]
    hold_h = float(np.mean((exit_ts - entry_ts).total_seconds()) / 3600.0)
    daily = pd.Series(r * RISK_FRAC, index=exit_ts).resample("1D").sum()
    dtt, _dtb, _p = resolution_estimate(daily)
    sd = daily.std(ddof=1)
    sharpe = float(daily.mean() / sd * math.sqrt(365)) if sd and sd > 0 else 0.0
    return {
        "trades": int(n), "pf": round(float(pf), 3),
        "win_rate": round(float((r > 0).mean()), 4),
        "avg_r": round(float(r.mean()), 4),
        "trades_per_day": round(n / span_days, 3),
        "avg_hold_h": round(hold_h, 2),
        "max_dd": round(dd_r * RISK_FRAC, 4), "max_dd_r": round(dd_r, 2),
        "sharpe": round(sharpe, 3), "total_r": round(float(r.sum()), 2),
        "days_to_target": round(dtt, 1) if np.isfinite(dtt) else math.inf,
        "long_share": round(float((trades[:, T_DIR] > 0).mean()), 3),
        "pct_stop": round(float((trades[:, T_REASON] == 0).mean()), 3),
        "pct_target": round(float((trades[:, T_REASON] == 1).mean()), 3),
        "pct_vwap": round(float((trades[:, T_REASON] == 4).mean()), 3),
        "pct_flip": round(float((trades[:, T_REASON] == 3).mean()), 3),
    }


def sweep(df, configs, fee_bps, slip_bps, feats=None, label="") -> pd.DataFrame:
    feats = feats if feats is not None else features(df)
    vw_cache: dict = {}
    span = (df.index[-1] - df.index[0]).total_seconds() / 86400.0
    rows = []
    for cfg in configs:
        tr = run_one(df, feats, vw_cache, cfg, fee_bps, slip_bps)
        row = dict(cfg)
        row.update(trade_metrics(tr, df.index, span))
        row["label"] = label
        rows.append(row)
    return pd.DataFrame(rows)
