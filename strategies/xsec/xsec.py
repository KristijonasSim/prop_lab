"""H-007 cross-sectional crypto ranking — the kernel.

MECHANISM (stated before any result, per CLAUDE.md).

The claim is that at any moment some coins are the ones flows are actually going
into and others are being left behind, and that the *relative* ordering carries
information the individual price series does not. Trading top-minus-bottom is
supposed to strip out the market factor: if the whole complex rips, both sides
move together and the spread keeps only the dispersion.

Who is on the other side: index-style buyers and retail who buy whatever is on
the front page, against liquidity providers who have to hold the laggard.

Why it is likely to fail here, recorded up front so the result is not a surprise:

  * The published edge (Kaminski/AQR-style cross-sectional momentum, and the
    equity ORB paper in RESEARCH_LOG) ranks 500-7,000 names. We hold five, and
    all five are high-beta majors with pairwise correlation well above 0.7.
    With five names, "top 1 vs bottom 1" is a coin-flip on dispersion, not a
    cross-section.
  * Published crypto work finds time-series momentum beats cross-sectional, and
    that cross-sectional books carry ~55% drawdowns.
  * A five-name spread is close to a leveraged bet on whichever alt is hottest.

Two ranking signals are tested, because they are different hypotheses:

  `mom`   L-bar log return. The literal "rank coins, trade top vs bottom" ask.
  `rvol`  volume over its own rolling median. This is the signal the equity ORB
          paper actually used (top 20 of 7,000 by opening relative volume), and
          RESEARCH_LOG lists the crypto analogue as next-candidate #2. It is the
          one with a mechanism rather than a pattern.

NO LOOKAHEAD. The signal and the volatility estimate at bar t use bars up to and
including t. Entry is the OPEN of t+1. Exit is the OPEN of t+1+H. Rebalances are
non-overlapping (every H bars), so trades never share a window.

Returns are expressed in R multiples the same way the rest of the repo does it:
each leg is sized to a fixed risk by dividing its return by a trailing
volatility estimate, so R = +1 means the leg made what it risked. Costs are
subtracted in the same units.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

# 15m bars resampled; (pandas rule, bars per day)
TFS = {"1h": ("1h", 24), "4h": ("4h", 6), "1d": ("1d", 1)}

SIGNALS = ("mom", "rvol")
MODES = ("spread", "longonly")

VOL_WIN = 100          # bars of history for the per-coin volatility estimate
MIN_VOL_BPS = 10.0     # floor, so a dead-quiet coin cannot fake a huge R


def resample(df: pd.DataFrame, rule: str) -> pd.DataFrame:
    out = df.resample(rule, label="left", closed="left").agg(
        {"open": "first", "high": "max", "low": "min",
         "close": "last", "volume": "sum"}).dropna(subset=["open"])
    return out


def panel(bars: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    """Align every coin on the timestamps all of them share."""
    idx = None
    for d in bars.values():
        idx = d.index if idx is None else idx.intersection(d.index)
    return {f: pd.DataFrame({s: bars[s][f].reindex(idx) for s in bars}, index=idx)
            for f in ("open", "close", "volume")}


def _signal(kind: str, close: pd.DataFrame, volume: pd.DataFrame, L: int) -> pd.DataFrame:
    if kind == "mom":
        return np.log(close / close.shift(L))
    if kind == "rvol":
        med = volume.rolling(L, min_periods=L).median()
        return volume / med.replace(0.0, np.nan)
    raise ValueError(kind)


def run(pan: dict[str, pd.DataFrame], *, signal: str, L: int, H: int, k: int,
        mode: str, cost_bps: float) -> pd.DataFrame:
    """One configuration. Returns one row per rebalance that traded.

    Vectorised: the cross-sectional rank is an argsort over the coin axis of the
    whole panel at once, then the selected legs are gathered with
    `take_along_axis`. A per-bar Python loop over five coins was the bottleneck.
    """
    close, opn, vol = pan["close"], pan["open"], pan["volume"]
    coins = list(close.columns)
    n_coins = len(coins)
    if mode == "spread" and 2 * k > n_coins:
        return pd.DataFrame()

    sig = _signal(signal, close, vol, L)

    # per-coin volatility of an H-bar move, using history up to and including t
    bar_ret = np.log(close / close.shift(1))
    sigma = (bar_ret.rolling(VOL_WIN, min_periods=VOL_WIN).std()
             * np.sqrt(H)).clip(lower=MIN_VOL_BPS / 1e4)

    # entry at open of t+1, exit at open of t+1+H
    fwd = np.log(opn.shift(-(1 + H)) / opn.shift(-1))

    S, F, G = sig.values, fwd.values, sigma.values
    idx = close.index
    first = max(L, VOL_WIN)
    last = len(idx) - (1 + H)
    if last <= first:
        return pd.DataFrame()

    t = np.arange(first, last, H)
    ok = ~(np.isnan(S[t]).any(1) | np.isnan(F[t]).any(1) | np.isnan(G[t]).any(1))
    t = t[ok]
    if t.size == 0:
        return pd.DataFrame()

    # descending rank across coins
    order = np.argsort(-S[t], axis=1, kind="stable")
    if mode == "spread":
        sel = np.concatenate([order[:, :k], order[:, -k:]], axis=1)
        dirs = np.concatenate([np.ones((t.size, k)), -np.ones((t.size, k))], axis=1)
    else:
        sel = order[:, :k]
        dirs = np.ones((t.size, k))

    g = dirs * np.take_along_axis(F[t], sel, axis=1)
    v = np.take_along_axis(G[t], sel, axis=1)
    cost_r = 2.0 * (cost_bps / 1e4)              # entry + exit, in return units

    def rmult(mult):
        return ((g - mult * cost_r) / v).mean(axis=1)

    exit_i = np.minimum(t + 1 + H, len(idx) - 1)
    return pd.DataFrame({
        "entry_ts": idx[t + 1],
        "exit_ts": idx[exit_i],
        "r_0x": rmult(0.0),
        "r": rmult(1.0),
        "r_2x": rmult(2.0),
        "r_3x": rmult(3.0),
        "long": [coins[i] for i in order[:, 0]],
        "short": [coins[i] for i in order[:, -1]],
    })


def pf_of(r: np.ndarray) -> float:
    g = float(r[r > 0].sum())
    l = float(-r[r < 0].sum())
    return float("inf") if l == 0 else (0.0 if g == 0 else g / l)


def summarise(tr: pd.DataFrame, hold_hours: float) -> dict:
    if tr.empty or len(tr) < 30:
        return {}
    r = tr.r.values
    span = max((tr.exit_ts.iloc[-1] - tr.exit_ts.iloc[0]).days, 1)
    eq = np.concatenate(([0.0], np.cumsum(r)))
    dd = abs(float((eq - np.maximum.accumulate(eq)).min()))
    rpd = float(r.sum()) / span
    sd = float(r.std(ddof=1))
    return {
        "trades": int(len(r)),
        "span_days": span,
        "tpd": len(r) / span,
        "pf": pf_of(r),
        "pf_0x": pf_of(tr.r_0x.values),
        "pf_2x": pf_of(tr.r_2x.values),
        "pf_3x": pf_of(tr.r_3x.values),
        "win": float((r > 0).mean()),
        "avg_r": float(r.mean()),
        "total_r": float(r.sum()),
        "max_dd_r": dd,
        "hold_h": hold_hours,
        "sharpe": 0.0 if sd == 0 else float(r.mean() / sd * np.sqrt(365 * len(r) / span)),
        "r_per_day": rpd,
        # the phase gate: days = maxDD_in_R / R_per_day  (see core/verify_board.py)
        "est_days": float("inf") if rpd <= 0 else dd / rpd,
    }
