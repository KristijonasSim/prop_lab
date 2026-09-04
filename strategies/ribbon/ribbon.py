"""H-016 - LonesomeTheBlue's "Trend Following Moving Averages" ribbon, in Python.

A faithful port of the Pine v4 `study`, plus the aggregates the Pine version
only ever expressed as colour. Nothing here trades; this file is the indicator.

MECHANISM, stated before any result.

The tool draws twenty moving averages, lengths 5..100, and colours each one by
a *trend score* of its own. The score is not the slope. It is where the MA sits
inside its own recent range, measured in units of a channel that is 1% of the
last 280 bars' high-low range:

    hh, ll = highest/lowest of this MA over the last `prd` bars
    diff   = hh - ll                      how far this MA has travelled
    trend  = +1 if the MA is more than one channel ABOVE its own low
             -1 if it is more than one channel BELOW its own high
              0 if it has not travelled a full channel at all
    score  = trend * diff / chan          signed, magnitude >= 1 when non-zero

So a length is "up" when its MA has climbed a meaningful distance and is
sitting near the top of that climb, and the magnitude says how far it climbed
relative to how volatile the market has been. The `chan` denominator is what
makes the score comparable across regimes: in a quiet market a small climb
scores the same as a large climb in a violent one.

The claim the ribbon makes, which is what H-016 has to test, is about
AGREEMENT ACROSS TIMESCALES. One MA turning up is noise. The 5-bar and the
100-bar agreeing means the same direction is being paid for by both the people
who came in this hour and the people who came in last week - which is what
persistent one-way order flow looks like. Whoever is on the other side is
either being stopped out or is adding to a loser.

WHAT WOULD KILL IT, and this is the cheap test to run first: a flat
agreement-response. Bucket forward return by ribbon agreement at ZERO cost. If
20-of-20 agreeing does not beat 12-of-20 agreeing, the ribbon is measuring
nothing that "how many MAs point up" does not already say, and there is no
mechanism to build on. This is the same z-response test that would have killed
H-008 in ten minutes.

STANDING EVIDENCE AGAINST IT, unprompted:
  - Price-derived hypotheses in this project are 0 for 6. Every leg that ever
    worked came from a data feed.
  - `CLAUDE.md` logs trend following as a LONGER-HOLD family, explicitly a
    future candidate rather than something to build in the current phase. A
    100-bar MA on 15m is a ~1-day timescale; on 4h it is over two weeks.
  - The ribbon has 20 lines and 5 free parameters. That is a search space, and
    the null benchmark matters more here than usual.

PORT FIDELITY. Pine differences that were preserved deliberately:
  - `highest(280)` / `lowest(280)` with one argument read `high` / `low`, not
    `close`. The channel is a true-range-style measure, not a close range.
  - `ta.ema` and `ta.rma` seed from an SMA of the first `length` bars, unlike
    pandas' `ewm(adjust=False)`, which seeds from the first value. Seeded the
    Pine way here so a chart and this file agree bar for bar.
  - `linreg(src, len, 0)` is the endpoint of the least-squares line fitted to
    the last `len` values, i.e. `intercept + slope * (len - 1)`.
  - `chan` is global, shared by all twenty lengths. It is not per-length.

NO LOOK-AHEAD. Every column is aligned to the bar that closed it: the value at
bar t uses bars <= t. A consumer that trades on it must shift by one bar and
fill at the next open, the same rule as everywhere else in this repo.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from numba import njit

MA_TYPES = ("EMA", "SMA", "RMA", "WMA", "VWMA")

#: The twenty lengths the Pine tool plots, 5 to 100 step 5.
RIBBON_LENGTHS: tuple[int, ...] = tuple(range(5, 101, 5))


@dataclass(frozen=True)
class RibbonParams:
    """The five inputs of the Pine study, same names, same defaults."""

    matype: str = "EMA"          # MA Type
    prd: int = 20                # Period to Check Trend      (Pine minval 5)
    rateinp: float = 1.0         # Trend Channel Rate %       (Pine minval 0.1)
    ulinreg: bool = True         # Use Linear Regression
    linprd: int = 10             # Linear Regression Period   (Pine minval 2)
    chanlen: int = 280           # the hard-coded 280 in `highest(280)`
    lengths: tuple[int, ...] = field(default=RIBBON_LENGTHS)

    def __post_init__(self) -> None:
        if self.matype not in MA_TYPES:
            raise ValueError(f"matype must be one of {MA_TYPES}, got {self.matype!r}")
        if self.prd < 5:
            raise ValueError("prd has minval 5 in the Pine source")
        if self.rateinp < 0.1:
            raise ValueError("rateinp has minval 0.1 in the Pine source")
        if self.linprd < 2:
            raise ValueError("linprd has minval 2 in the Pine source")

    @property
    def rate(self) -> float:
        return self.rateinp / 100.0


# --------------------------------------------------------------------------
# Pine primitives. Each one matches TradingView bar for bar, not approximately.
# --------------------------------------------------------------------------

@njit(cache=True)
def _wilder_like(x: np.ndarray, length: int, alpha: float) -> np.ndarray:
    """Recursive smoother seeded from an SMA, which is what Pine does.

    Pine's `ta.ema` and `ta.rma` both hold `na` until `length` bars exist, emit
    the SMA of those bars, and recurse from there. pandas' `ewm(adjust=False)`
    seeds from the single first value instead, which leaves a visible offset
    for hundreds of bars at length 100 - enough to move a threshold crossing.
    """
    n = x.size
    out = np.full(n, np.nan)
    if n < length:
        return out
    seed_end = length - 1
    prev = np.mean(x[:length])
    out[seed_end] = prev
    for i in range(length, n):
        prev = alpha * x[i] + (1.0 - alpha) * prev
        out[i] = prev
    return out


def _sma(x: np.ndarray, length: int) -> np.ndarray:
    return pd.Series(x).rolling(length).mean().to_numpy()


def _wma(x: np.ndarray, length: int) -> np.ndarray:
    """Pine `ta.wma`: weights 1..length, the newest bar carrying `length`."""
    w = np.arange(1.0, length + 1.0)
    w /= w.sum()
    out = np.full(x.size, np.nan)
    if x.size >= length:
        # `np.convolve` with the reversed kernel is a trailing weighted sum.
        out[length - 1:] = np.convolve(x, w[::-1], mode="valid")
    return out


def moving_average(close: np.ndarray, volume: np.ndarray, length: int,
                   matype: str) -> np.ndarray:
    """The `getma` / `masrc` branch of the Pine source, all five types."""
    if matype == "EMA":
        return _wilder_like(close, length, 2.0 / (length + 1.0))
    if matype == "RMA":
        return _wilder_like(close, length, 1.0 / length)
    if matype == "SMA":
        return _sma(close, length)
    if matype == "WMA":
        return _wma(close, length)
    if matype == "VWMA":
        # Pine: sma(close * volume, len) / sma(volume, len)
        num = _sma(close * volume, length)
        den = _sma(volume, length)
        with np.errstate(divide="ignore", invalid="ignore"):
            return np.where(den > 0, num / den, np.nan)
    raise ValueError(f"unknown matype {matype!r}")


def linreg(x: np.ndarray, length: int, offset: int = 0) -> np.ndarray:
    """Pine `ta.linreg(src, length, offset)`.

    Least squares over the window with positions 0..length-1, evaluated at
    position `length - 1 - offset`. Written as convolutions so it stays O(n)
    over twenty lengths and 200k bars.
    """
    n = x.size
    out = np.full(n, np.nan)
    if n < length:
        return out
    L = float(length)
    pos = np.arange(length, dtype=float)          # 0 = oldest bar in window
    sum_x = pos.sum()
    sum_xx = (pos * pos).sum()
    denom = L * sum_xx - sum_x * sum_x
    if denom == 0.0:                              # length == 1
        return _sma(x, length)

    ones = np.ones(length)
    sum_y = np.convolve(x, ones, mode="valid")
    # Reversed kernel so the newest bar in each window gets weight length-1.
    sum_xy = np.convolve(x, pos[::-1], mode="valid")

    slope = (L * sum_xy - sum_x * sum_y) / denom
    intercept = (sum_y - slope * sum_x) / L
    out[length - 1:] = intercept + slope * (L - 1.0 - offset)
    return out


def _rolling_max(x: np.ndarray, length: int) -> np.ndarray:
    return pd.Series(x).rolling(length).max().to_numpy()


def _rolling_min(x: np.ndarray, length: int) -> np.ndarray:
    return pd.Series(x).rolling(length).min().to_numpy()


# --------------------------------------------------------------------------
# The study itself
# --------------------------------------------------------------------------

def channel(df: pd.DataFrame, p: RibbonParams) -> pd.Series:
    """`chan` - one channel width shared by every length in the ribbon.

    `pricerange = highest(280) - lowest(280)` reads the HIGH and LOW series,
    which is what a bare `highest(len)` means in Pine v4.
    """
    hi = _rolling_max(df["high"].to_numpy(float), p.chanlen)
    lo = _rolling_min(df["low"].to_numpy(float), p.chanlen)
    return pd.Series((hi - lo) * p.rate, index=df.index, name="chan")


def gettrend(ma: np.ndarray, chan: np.ndarray, prd: int) -> np.ndarray:
    """The `gettrend` function: signed distance travelled, in channel units.

    Returns `trend * diff / chan`, so 0 means "has not travelled a full
    channel", and a non-zero value always has magnitude >= 1.
    """
    hh = _rolling_max(ma, prd)
    ll = _rolling_min(ma, prd)
    diff = np.abs(hh - ll)

    # A flat 280-bar range makes `chan` zero, which is a real state on quiet FX
    # and means "undefined", not "infinitely trending". Divided under errstate
    # and masked out below rather than left to warn on every panel.
    with np.errstate(invalid="ignore", divide="ignore"):
        up = ma > ll + chan
        dn = ma < hh - chan
        trend = np.where(diff > chan, np.where(up, 1.0, np.where(dn, -1.0, 0.0)), 0.0)
        score = trend * diff / chan

    # Any bar where an input is unavailable stays unavailable. Pine propagates
    # `na` here; np.where would have quietly written a 0.0, which reads as
    # "flat" rather than "unknown" and would bias every aggregate below.
    bad = ~np.isfinite(ma) | ~np.isfinite(chan) | (chan <= 0) | ~np.isfinite(diff)
    score[bad] = np.nan
    return score


def ribbon(df: pd.DataFrame, p: RibbonParams | None = None
           ) -> tuple[pd.DataFrame, pd.DataFrame]:
    """The whole study: twenty MA lines and their twenty trend scores.

    Returns `(mas, scores)`, both indexed like `df`, columns named `ma_5`.. and
    `t_5`.. . `mas` are the plotted lines (raw MAs, as `getma` plots them);
    `scores` are what the colour encodes (`gettrend`, which is computed on the
    linreg-smoothed MA when `ulinreg` is on).
    """
    p = p or RibbonParams()
    close = df["close"].to_numpy(float)
    volume = df["volume"].to_numpy(float) if "volume" in df else np.ones(close.size)
    chan = channel(df, p).to_numpy(float)

    mas, scores = {}, {}
    for n in p.lengths:
        raw = moving_average(close, volume, n, p.matype)
        # NOTE the asymmetry, and it is in the original: the PLOTTED line is
        # the raw MA, while the COLOUR is computed on the linreg-smoothed one.
        smoothed = linreg(raw, p.linprd, 0) if p.ulinreg else raw
        mas[f"ma_{n}"] = raw
        scores[f"t_{n}"] = gettrend(smoothed, chan, p.prd)

    return (pd.DataFrame(mas, index=df.index),
            pd.DataFrame(scores, index=df.index))


# --------------------------------------------------------------------------
# What the Pine version only ever said in colour
# --------------------------------------------------------------------------

def features(df: pd.DataFrame, p: RibbonParams | None = None) -> pd.DataFrame:
    """Ribbon aggregates - the candidate signals, one column each.

    The study renders twenty scores as twenty colours and leaves the reading to
    the eye. These are the readings, made explicit so they can be scored:

      agree      mean sign over the twenty lengths, in [-1, +1]. +1 is every
                 length up. This is the ribbon's actual claim.
      n_up/n_dn  counts behind `agree`, for bucketing.
      n_flat     lengths that have not travelled a full channel - the ribbon
                 being compressed, which is the setup a breakout trader waits
                 for and the state a trend follower loses money in.
      strength   mean signed score. Unlike `agree` it is sensitive to HOW far
                 the MAs travelled, not just which way.
      fast/slow  agreement restricted to lengths <= 30 and >= 70. The gap
                 between them is where a turn shows up first.
      stack      fraction of adjacent MA pairs in strict order (fast above
                 slow, or fast below slow). This is the ribbon "fanned out"
                 that the picture actually shows, and it is NOT the same
                 object as `agree` - a ribbon can be perfectly stacked while
                 every line is flat.
      width      spread of the ribbon (fastest minus slowest MA) in channel
                 units, so it is comparable across regimes.

    All aligned to the closing bar. Shift before trading on any of them.
    """
    p = p or RibbonParams()
    mas, scores = ribbon(df, p)
    s = scores.to_numpy(float)

    with np.errstate(invalid="ignore"):
        sign = np.sign(s)
    valid = np.isfinite(s)
    n_valid = valid.sum(axis=1)
    # Aggregates are undefined until every length has a value; a partial
    # ribbon would make early bars look like disagreement that is really just
    # missing data.
    full = n_valid == s.shape[1]

    def _mean(a, cols=None):
        """Mean over the ribbon, evaluated only on rows where it is defined.

        Restricted to `full` rows before averaging: an all-NaN row would make
        `np.nanmean` warn, and the answer is discarded anyway.
        """
        sub = a if cols is None else a[:, cols]
        msk = valid if cols is None else valid[:, cols]
        out = np.full(a.shape[0], np.nan)
        if full.any():
            out[full] = np.nanmean(np.where(msk[full], sub[full], np.nan), axis=1)
        return out

    fast_cols = [i for i, n in enumerate(p.lengths) if n <= 30]
    slow_cols = [i for i, n in enumerate(p.lengths) if n >= 70]

    m = mas.to_numpy(float)
    step = np.sign(np.diff(m, axis=1))            # fast-to-slow ordering
    stack = np.full(len(df), np.nan)
    if full.any():
        stack[full] = np.abs(np.nanmean(step[full], axis=1))
    chan = channel(df, p).to_numpy(float)
    with np.errstate(invalid="ignore", divide="ignore"):
        width = np.where(chan > 0, (m[:, 0] - m[:, -1]) / chan, np.nan)

    out = pd.DataFrame({
        "agree": _mean(sign),
        "n_up": np.where(full, (sign > 0).sum(axis=1), np.nan),
        "n_dn": np.where(full, (sign < 0).sum(axis=1), np.nan),
        "n_flat": np.where(full, ((sign == 0) & valid).sum(axis=1), np.nan),
        "strength": _mean(s),
        "fast_agree": _mean(sign, fast_cols) if fast_cols else np.nan,
        "slow_agree": _mean(sign, slow_cols) if slow_cols else np.nan,
        "stack": stack,
        "width": width,
    }, index=df.index)
    out["fast_minus_slow"] = out["fast_agree"] - out["slow_agree"]
    return out
