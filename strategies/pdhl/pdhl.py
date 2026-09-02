"""H-011 previous-day high/low reversal — levels, feeds and glue.

HOW THIS DIFFERS FROM H-005, which is already rejected.

H-005 faded the extreme of the last 10 to 100 BARS. That is a rolling level: it
moves every bar, it depends on a lookback nobody agreed on, and no other trader
is watching it. Its null cleared the gate 19,062 times against the real market's
1,702, which is what a fade rule does on shuffled data.

The previous day's high and low are a different kind of object. They are a
SCHELLING POINT - printed on every platform, identical for everyone, and fixed
for the whole session. If resting stops cluster anywhere, they cluster there.
The mechanism is not "price reverts from extremes", which is the claim that
died; it is "a known pool of stops is taken, and once it is taken the forced
buying or selling is finished".

That difference is testable rather than rhetorical, and this adds the two things
H-005 had no way to check:

  * **open interest across the sweep.** Positions CLOSING while price takes out
    the level is the fingerprint of stops being run. Positions OPENING is a real
    breakout wearing the same clothes. H-006 showed open interest carries no
    directional information on its own - but conditioned on a level being taken
    out, it separates the two events, which is a different question.
  * **the crowd gate** from H-009.

If the schelling-point version does no better than H-005's rolling version, that
is a clean result about the whole family rather than about one lookback.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

TFS = {"15m": "15min", "30m": "30min", "1h": "1h", "4h": "4h"}
AGG = {"open": "first", "high": "max", "low": "min", "close": "last",
       "volume": "sum", "taker_buy_base": "sum"}

FEE_BPS, SLIP_BPS = 5.0, 2.0


def load(sym: str, tf: str, feeds) -> pd.DataFrame:
    px = pd.read_parquet(feeds / f"{sym}_perp_5m.parquet")
    df = px.resample(TFS[tf], label="left", closed="left").agg(AGG).dropna(subset=["open"])

    mx = pd.read_parquet(feeds / f"{sym}_metrics_5m.parquet")
    oi = mx["sum_open_interest"].replace(0.0, np.nan)
    crowd = np.log(mx["count_long_short_ratio"].replace(0.0, np.nan))
    cz = ((crowd - crowd.rolling(288, min_periods=144).mean().shift(1))
          / crowd.rolling(288, min_periods=144).std(ddof=0).shift(1))
    # both are read at the bar's CLOSE, one bar before the fill
    df["oi"] = oi.reindex(df.index.union(oi.index)).ffill().reindex(df.index)
    df["crowd"] = cz.reindex(df.index.union(cz.index)).ffill().reindex(df.index)
    return df


def levels(df: pd.DataFrame) -> pd.DataFrame:
    """Previous day's and previous week's extremes, and the day's midpoint.

    Shifted by one period, so the level a bar is measured against was fully
    formed before that bar existed. A level built from the day the bar is in
    would be the answer written on the question."""
    d = df.index.floor("D")
    day = df.groupby(d).agg(h=("high", "max"), l=("low", "min"), c=("close", "last"))
    pd_h = day.h.shift(1)
    pd_l = day.l.shift(1)
    pd_c = day.c.shift(1)
    wk = df.index.to_period("W").start_time
    week = df.groupby(wk).agg(h=("high", "max"), l=("low", "min"))
    pw_h, pw_l = week.h.shift(1), week.l.shift(1)

    out = pd.DataFrame(index=df.index)
    out["pdh"] = pd.Series(d, index=df.index).map(pd_h)
    out["pdl"] = pd.Series(d, index=df.index).map(pd_l)
    out["pdc"] = pd.Series(d, index=df.index).map(pd_c)
    out["pwh"] = pd.Series(wk, index=df.index).map(pw_h)
    out["pwl"] = pd.Series(wk, index=df.index).map(pw_l)
    out["mid"] = (out.pdh + out.pdl) / 2.0
    out["day_i"] = pd.factorize(d)[0]
    return out


def atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    tr = pd.concat([df.high - df.low,
                    (df.high - df.close.shift(1)).abs(),
                    (df.low - df.close.shift(1)).abs()], axis=1).max(axis=1)
    return tr.rolling(n, min_periods=n // 2).mean()


def d_oi(df: pd.DataFrame, k: int) -> pd.Series:
    """Log change in open interest over k bars, ending at this bar's close.

    Negative means contracts were closed while the level was being taken - the
    fingerprint of stops running rather than of new positions being opened."""
    oi = df.oi.replace(0.0, np.nan)
    return np.log(oi / oi.shift(k))


def cvd_share(df: pd.DataFrame) -> pd.Series:
    v = df.volume.replace(0.0, np.nan)
    return (2.0 * df.taker_buy_base - df.volume) / v


def pf_of(r: np.ndarray) -> float:
    w, l = r[r > 0].sum(), -r[r < 0].sum()
    return float(w / l) if l > 0 else (float("inf") if w > 0 else float("nan"))


def max_dd(r: np.ndarray) -> float:
    eq = np.concatenate(([0.0], np.cumsum(r)))
    return float((eq - np.maximum.accumulate(eq)).min())
