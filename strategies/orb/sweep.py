"""ORB parameter sweep + metrics. Stage 1 of the pipeline (fast screen)."""

from __future__ import annotations

import itertools
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from core.metrics import resolution_estimate            # noqa: E402
from strategies.orb.engine import simulate, T_R, T_DIR, T_ENTRY_I, T_EXIT_I, T_REASON  # noqa: E402

BARS_PER_HOUR = 4          # 15m bars
RISK_FRAC = 0.01           # fixed 1% of STARTING equity per trade


# ------------------------------------------------------------------ features
def features(df: pd.DataFrame, atr_len: int = 14, ema_len: int = 200,
             rvol_len: int = 20 * 96, datr_len: int = 14):
    """atr: 14-bar ATR. ema: 200-bar EMA. rvol: bar volume / its trailing mean.
    datr: 14-DAY ATR, broadcast back onto 15m bars — the papers size their stop
    off daily range, not off an intraday one.

    Every series is shifted so a bar only ever sees information that was already
    complete when it opened. No look-ahead.
    """
    h, l, c, v = df.high.values, df.low.values, df.close.values, df.volume.values
    pc = np.roll(c, 1)
    pc[0] = c[0]
    tr = np.maximum(h - l, np.maximum(np.abs(h - pc), np.abs(l - pc)))
    atr = pd.Series(tr).ewm(alpha=1 / atr_len, adjust=False).mean().values
    ema = pd.Series(c).ewm(span=ema_len, adjust=False).mean().values

    vs = pd.Series(v, index=df.index)
    base = vs.rolling(rvol_len, min_periods=rvol_len // 4).mean().shift(1)
    rvol = (vs / base).fillna(0.0).values

    d = df[["high", "low", "close"]].resample("1D").agg(
        {"high": "max", "low": "min", "close": "last"}).dropna()
    dpc = d.close.shift(1).fillna(d.close)
    dtr = np.maximum(d.high - d.low,
                     np.maximum((d.high - dpc).abs(), (d.low - dpc).abs()))
    datr_d = dtr.ewm(alpha=1 / datr_len, adjust=False).mean().shift(1)
    datr = datr_d.reindex(df.index, method="ffill").bfill().values

    return atr, ema, rvol, datr


def session_starts(index: pd.DatetimeIndex, hour: int) -> np.ndarray:
    """Bar indices where a session begins (first bar at `hour`:00 UTC each day)."""
    is_start = (index.hour == hour) & (index.minute == 0)
    return np.flatnonzero(is_start).astype(np.int64)


# ------------------------------------------------------------------ metrics
def trade_metrics(
    trades: np.ndarray,
    index: pd.DatetimeIndex,
    span_days: float,
    cost_mult: float = 1.0,
) -> dict:
    n = len(trades)
    if n == 0:
        return {"trades": 0, "pf": np.nan, "win_rate": np.nan, "avg_r": np.nan,
                "trades_per_day": 0.0, "trades_per_week": 0.0, "avg_hold_h": np.nan,
                "max_dd": np.nan, "max_dd_r": np.nan, "sharpe": np.nan, "total_r": 0.0,
                "days_to_target": math.inf, "days_to_breach": math.inf,
                "p_target_first": np.nan, "expectancy_r": np.nan, "long_share": np.nan}

    r = trades[:, T_R]
    wins, losses = r[r > 0].sum(), -r[r < 0].sum()
    pf = wins / losses if losses > 0 else math.inf

    # Fixed risk per trade, no compounding, so drawdown is linear in R and a
    # losing config cannot drive "equity" negative and produce a nonsense ratio.
    eq_r = np.concatenate(([0.0], np.cumsum(r)))
    dd_r = float((eq_r - np.maximum.accumulate(eq_r)).min())
    max_dd = round(dd_r * RISK_FRAC, 4)          # fraction of starting equity

    exit_ts = index[trades[:, T_EXIT_I].astype(int)]
    entry_ts = index[trades[:, T_ENTRY_I].astype(int)]
    hold_h = float(np.mean((exit_ts - entry_ts).total_seconds()) / 3600.0)

    # daily P&L as a fraction of starting equity -> phase gate
    daily = pd.Series(r * RISK_FRAC, index=exit_ts).resample("1D").sum()
    dtt, dtb, p_up = resolution_estimate(daily)

    sd = daily.std(ddof=1)
    sharpe = float(daily.mean() / sd * math.sqrt(365)) if sd and sd > 0 else 0.0

    return {
        "trades": int(n),
        "pf": round(float(pf), 3),
        "win_rate": round(float((r > 0).mean()), 4),
        "avg_r": round(float(r.mean()), 4),
        "expectancy_r": round(float(r.mean()), 4),
        "trades_per_day": round(n / span_days, 3),
        "trades_per_week": round(n / span_days * 7, 2),
        "avg_hold_h": round(hold_h, 2),
        "max_dd": max_dd,
        "max_dd_r": round(dd_r, 2),
        "sharpe": round(sharpe, 3),
        "total_r": round(float(r.sum()), 2),
        "days_to_target": round(dtt, 1) if np.isfinite(dtt) else math.inf,
        "days_to_breach": round(dtb, 1) if np.isfinite(dtb) else math.inf,
        "p_target_first": round(float(p_up), 4) if p_up == p_up else np.nan,
        "long_share": round(float((trades[:, T_DIR] > 0).mean()), 3),
        "pct_stop": round(float((trades[:, T_REASON] == 0).mean()), 3),
        "pct_target": round(float((trades[:, T_REASON] == 1).mean()), 3),
        "pct_time": round(float((trades[:, T_REASON] == 2).mean()), 3),
    }


# ------------------------------------------------------------------ runner
def run_one(df, feats, cfg, fee_bps, slip_bps) -> np.ndarray:
    atr, ema, rvol, datr = feats
    ss = session_starts(df.index, cfg["hour"])
    return simulate(
        df.open.values, df.high.values, df.low.values, df.close.values,
        atr, ema, rvol, datr,
        ss,
        int(cfg["or_bars"]),
        int(cfg["hold_bars"]),
        int(cfg["dir_mode"]),
        int(cfg["entry_mode"]),
        int(cfg["stop_mode"]),
        float(cfg["stop_atr_mult"]),
        float(cfg["rr"]),
        float(cfg["buffer_bps"]),
        float(fee_bps),
        float(slip_bps),
        int(cfg["one_trade"]),
        float(cfg["min_or_atr"]),
        float(cfg["max_or_atr"]),
        int(cfg["trend_mode"]),
        int(cfg["fade"]),
        float(cfg["min_risk_bps"]),
        float(cfg["min_rvol"]),
        int(cfg["use_datr"]),
    )


DEFAULTS = dict(dir_mode=0, entry_mode=0, stop_mode=0, stop_atr_mult=1.0, rr=0.0,
                buffer_bps=0.0, one_trade=1, min_or_atr=0.0, max_or_atr=0.0,
                trend_mode=0, fade=0, min_rvol=0.0, use_datr=0,
                min_risk_bps=10.0)


def grid(**axes) -> list[dict]:
    keys = list(axes)
    out = []
    for combo in itertools.product(*(axes[k] for k in keys)):
        cfg = dict(DEFAULTS)
        cfg.update(dict(zip(keys, combo)))
        out.append(cfg)
    return out


def sweep(df, configs, fee_bps=5.0, slip_bps=2.0, label="", feats=None) -> pd.DataFrame:
    feats = feats if feats is not None else features(df)
    span_days = (df.index[-1] - df.index[0]).total_seconds() / 86400.0
    rows = []
    for cfg in configs:
        tr = run_one(df, feats, cfg, fee_bps, slip_bps)
        row = dict(cfg)
        row.update(trade_metrics(tr, df.index, span_days))
        row["label"] = label
        rows.append(row)
    return pd.DataFrame(rows)
