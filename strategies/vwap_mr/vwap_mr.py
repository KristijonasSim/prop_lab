"""H-010 feature glue: anchored VWAP with bands, real taker delta, crowd gate.

Bars are the USDT-M PERPETUAL 5-minute klines resampled up, not the repo's
cached spot bars, for two reasons: the klines carry
`taker_buy_base_asset_volume`, which is the true taker split rather than the
`volume * sign(close - open)` guess the source indicator uses, and the crowd
feed describes the same perpetual book, so signal and price come from one venue.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

TFS = {"15m": ("15min", 3), "30m": ("30min", 6), "1h": ("1h", 12),
       "4h": ("4h", 48)}          # rule, and how many 5m bars make one bar

AGG = {"open": "first", "high": "max", "low": "min", "close": "last",
       "volume": "sum", "quote_volume": "sum", "taker_buy_base": "sum"}

# Binance USDT-M perp taker is 5bps; 2bps of slippage per side is the
# assumption the rest of this repo uses.
FEE_BPS, SLIP_BPS, MIN_RISK_BPS = 5.0, 2.0, 10.0


def load(sym: str, tf: str, feeds) -> pd.DataFrame:
    px = pd.read_parquet(feeds / f"{sym}_perp_5m.parquet")
    rule = TFS[tf][0]
    df = px.resample(rule, label="left", closed="left").agg(AGG).dropna(subset=["open"])
    mx = pd.read_parquet(feeds / f"{sym}_metrics_5m.parquet")
    # last reading at or before each bar's CLOSE, which is when the signal is
    # read and one bar before the fill
    crowd = np.log(mx["count_long_short_ratio"].replace(0.0, np.nan))
    z = ((crowd - crowd.rolling(288, min_periods=144).mean().shift(1))
         / crowd.rolling(288, min_periods=144).std(ddof=0).shift(1))
    df["crowd"] = z.reindex(df.index.union(z.index)).ffill().reindex(df.index)
    return df


def anchored(df: pd.DataFrame, anchor: str) -> tuple:
    """Volume-weighted mean and standard deviation of hlc3 since the anchor.

    Same accumulation the source indicator uses - running sums of price x
    volume and price squared x volume, reset when the anchor changes - so the
    bands are the ones a trader would see on the chart."""
    if anchor.startswith("roll"):
        w = int(anchor[4:])
        p = (df.high + df.low + df.close) / 3.0
        pv = (p * df.volume).rolling(w, min_periods=w // 2).sum()
        v = df.volume.rolling(w, min_periods=w // 2).sum().replace(0.0, np.nan)
        p2v = (p * p * df.volume).rolling(w, min_periods=w // 2).sum()
        vwap = pv / v
        var = (p2v / v) - vwap * vwap
        newa = pd.Series(0, index=df.index)
    else:
        key = {"D": df.index.floor("D"), "W": df.index.to_period("W").start_time,
               "M": df.index.to_period("M").start_time}[anchor]
        newa = pd.Series((pd.Series(key, index=df.index) !=
                          pd.Series(key, index=df.index).shift(1)).astype(int),
                         index=df.index)
        p = (df.high + df.low + df.close) / 3.0
        g = pd.Series(key, index=df.index)
        pv = (p * df.volume).groupby(g).cumsum()
        v = df.volume.groupby(g).cumsum().replace(0.0, np.nan)
        p2v = (p * p * df.volume).groupby(g).cumsum()
        vwap = pv / v
        var = (p2v / v) - vwap * vwap
    sd = np.sqrt(var.clip(lower=0.0))
    return vwap, sd, newa


def atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    tr = pd.concat([df.high - df.low,
                    (df.high - df.close.shift(1)).abs(),
                    (df.low - df.close.shift(1)).abs()], axis=1).max(axis=1)
    return tr.rolling(n, min_periods=n // 2).mean()


def cvd_share(df: pd.DataFrame) -> pd.Series:
    """Taker buy volume minus taker sell volume, over total volume, in -1..1.

    The real split, from the exchange's own field, not inferred from the bar's
    direction - which would be a signal that already knows the answer."""
    v = df.volume.replace(0.0, np.nan)
    return (2.0 * df.taker_buy_base - df.volume) / v


def pf_of(r: np.ndarray) -> float:
    w, l = r[r > 0].sum(), -r[r < 0].sum()
    return float(w / l) if l > 0 else (float("inf") if w > 0 else float("nan"))


def max_dd(r: np.ndarray) -> float:
    eq = np.concatenate(([0.0], np.cumsum(r)))
    return float((eq - np.maximum.accumulate(eq)).min())
