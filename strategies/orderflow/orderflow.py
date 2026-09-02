"""H-006 order flow — the feed kernel: features, forward returns, alignment.

The standing pattern in this project and in the repo before it is that every leg
that ever worked came from a DATA FEED, not a price pattern. Six price-pattern
hypotheses have now been rejected here. This is the first one built on feeds the
exchange publishes about positioning and aggression, which is the thing the
pattern says should work.

WHAT THE FEEDS ARE, and what each one can and cannot say:

  open interest        contracts outstanding. It says whether a move is new risk
                       being taken or old risk being closed - the same price move
                       means opposite things depending on which.
  taker buy/sell       who crossed the spread. Aggression, not positioning.
  count long/short     long accounts over short accounts, every account equal.
                       A headcount, so it is a crowd gauge, not a money gauge.
  top-trader sum       the same ratio for the largest accounts, weighted by
                       POSITION SIZE. Money, not headcount.

The count/sum split is the whole reason this feed is interesting: it publishes
where the crowd is standing and where size is standing, separately, and lets the
two disagree.

NO LOOKAHEAD. Every feature at bar t uses metric rows with `create_time <= t`
and bars that have closed at t. Forward returns are measured from the NEXT bar's
open, which is the first price this could be filled at.

Costs: a Binance USDT-M perp round trip is taken as 5bps taker + 2bps slippage
per side, so 14bps round trip - the same assumption the rest of the repo uses.
Every response table below is printed in basis points so it can be read straight
against that number.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

ROUND_TRIP_BPS = 14.0          # 1x cost: (5bps taker + 2bps slip) x 2 sides

METRICS = {
    "oi": "sum_open_interest",
    "oi_usd": "sum_open_interest_value",
    "crowd": "count_long_short_ratio",
    "top_count": "count_toptrader_long_short_ratio",
    "top_size": "sum_toptrader_long_short_ratio",
    "taker": "sum_taker_long_short_vol_ratio",
}


def load(sym: str, feeds_dir) -> pd.DataFrame:
    """Perp bars and the metrics feed on one 5-minute index.

    Both come from the same venue and the same archive, so no resampling is
    needed - they are joined, not interpolated. Rows where either side is
    missing are dropped rather than filled: a forward-filled order-flow reading
    is a number nobody could have seen."""
    px = pd.read_parquet(feeds_dir / f"{sym}_perp_5m.parquet")
    mx = pd.read_parquet(feeds_dir / f"{sym}_metrics_5m.parquet")
    df = px.join(mx, how="inner").sort_index()
    return df[~df.index.duplicated(keep="last")]


def _z(s: pd.Series, win: int) -> pd.Series:
    """Rolling z-score, shifted so the current bar is never in its own baseline."""
    m = s.rolling(win, min_periods=win // 2).mean().shift(1)
    v = s.rolling(win, min_periods=win // 2).std(ddof=0).shift(1)
    return (s - m) / v.replace(0.0, np.nan)


def features(df: pd.DataFrame, win: int = 288) -> pd.DataFrame:
    """Point-in-time feed features. `win` is the z-score baseline in 5m bars
    (288 = one day), and it is shifted, so a bar is never scored against itself.

    Everything here is a CHANGE or a DEVIATION, never a level. Open interest in
    contracts is not comparable across 2020 and 2026, and the raw long/short
    ratio has a different resting point on every coin."""
    f = pd.DataFrame(index=df.index)
    px = df.close

    # price moves, for the quadrant reads
    for k, name in ((3, "15m"), (12, "1h"), (48, "4h")):
        f[f"ret_{name}"] = np.log(px / px.shift(k))

    oi = df[METRICS["oi"]].replace(0.0, np.nan)
    for k, name in ((3, "15m"), (12, "1h"), (48, "4h")):
        f[f"doi_{name}"] = np.log(oi / oi.shift(k))

    # THE QUADRANT. Positive when the move and open interest agree - new risk
    # going on - and negative when they disagree, which is unwinding: short
    # covering into a rally, longs being closed into a fall. Forced closes are
    # price-insensitive and have to end; new positioning does not.
    for name in ("15m", "1h", "4h"):
        f[f"quad_{name}"] = np.sign(f[f"ret_{name}"]) * f[f"doi_{name}"]

    # aggression: who crossed the spread. Two readings of the same thing - the
    # exchange's own ratio, and the one rebuilt from the bars themselves.
    tk = df[METRICS["taker"]].replace(0.0, np.nan)
    f["taker"] = np.log(tk)
    f["taker_z"] = _z(f["taker"], win)
    buy = df.taker_buy_base
    sell = (df.volume - buy).clip(lower=0.0)
    f["cvd"] = (buy - sell) / df.volume.replace(0.0, np.nan)
    f["cvd_z"] = _z(f["cvd"], win)
    for k, name in ((12, "1h"), (48, "4h")):
        f[f"cvd_{name}"] = ((buy - sell).rolling(k).sum()
                            / df.volume.rolling(k).sum().replace(0.0, np.nan))

    # positioning: the crowd, size, and the gap between them
    crowd = np.log(df[METRICS["crowd"]].replace(0.0, np.nan))
    size = np.log(df[METRICS["top_size"]].replace(0.0, np.nan))
    f["crowd_z"] = _z(crowd, win)
    f["size_z"] = _z(size, win)
    # positive = size is longer than the crowd; negative = the crowd is longer
    # than size, which is the configuration people mean by "overcrowded"
    f["disagree"] = f["size_z"] - f["crowd_z"]
    for k, name in ((12, "1h"), (48, "4h")):
        f[f"dcrowd_{name}"] = crowd - crowd.shift(k)

    return f


def forward_returns(df: pd.DataFrame, horizons=(12, 48, 96, 144, 288)) -> pd.DataFrame:
    """Log returns from the NEXT bar's open to the open h bars later.

    Next-bar open, not this bar's close: a signal read off a closed bar cannot
    be filled at that bar's close. Horizons are in 5-minute bars, so the
    defaults are 1h, 4h, 8h, 12h and 24h."""
    o = df.open
    out = pd.DataFrame(index=df.index)
    entry = o.shift(-1)
    for h in horizons:
        out[f"fwd_{h}"] = np.log(o.shift(-1 - h) / entry)
    return out


def block_shuffle(f: pd.Series, seed: int, block: int = 288) -> pd.Series:
    """The null: cut the FEATURE into day-long blocks and reorder them, leaving
    returns untouched.

    Shuffling bar by bar would destroy the feature's own autocorrelation and
    make it trivially easy to beat - the null has to keep the signal looking
    like itself and only break its alignment with the future. Same reasoning as
    `shuffle_market_paired` elsewhere in this repo."""
    rng = np.random.default_rng(seed)
    v = f.values
    n = len(v)
    nb = int(np.ceil(n / block))
    pad = np.full(nb * block, np.nan)
    pad[:n] = v
    blocks = pad.reshape(nb, block)
    rng.shuffle(blocks)
    return pd.Series(blocks.reshape(-1)[:n], index=f.index, name=f.name)


# ---------------------------------------------------------------------------
# The trading kernel.
#
# Every rule here is read straight off the stage-1 diagnostic and nothing else:
# the crowd-positioning features rank forward returns monotonically over 8-24
# hours, negatively, so the rule is to fade the crowd on a fixed hold. There is
# no stop and no target.
#
# FIXED-HOLD EXITS ONLY, deliberately. A stop or a target needs an assumption
# about the order in which the high and the low were touched inside a bar, and
# this repo has already been burned once by a fill assumption - the VWAP
# std-band fade backtested at PF 3.0 and traded at 0.7 because resting limits
# were filled on any wick touch. H-008 was built the same way for the same
# reason. If this survives on fixed holds, stops can be added and argued about
# afterwards; if it only works with a stop, the stop is the strategy.
# ---------------------------------------------------------------------------

SIGNALS = ("dcrowd", "crowd_z", "disagree")


def signal_series(df: pd.DataFrame, kind: str, look: int, win: int) -> pd.Series:
    """One signal, point in time.

    `look` is the change window in 5m bars, `win` the z-score baseline. Both are
    shifted where they need to be so no bar is scored against itself."""
    crowd = np.log(df[METRICS["crowd"]].replace(0.0, np.nan))
    if kind == "dcrowd":
        return crowd - crowd.shift(look)
    if kind == "crowd_z":
        return _z(crowd, win)
    if kind == "disagree":
        size = np.log(df[METRICS["top_size"]].replace(0.0, np.nan))
        return _z(size, win) - _z(crowd, win)
    raise ValueError(kind)


def thresholds(sig: pd.Series, q: float, band: int) -> tuple:
    """Trailing quantiles of the signal, shifted one bar.

    Split out of `run_one` because this is where the time goes: a rolling
    quantile over a 30-day window of 5-minute bars is expensive, and it does not
    depend on the hold or the direction. Computing it once and reusing it across
    those turned a grid that exhausted this box into one that finishes."""
    lo = sig.rolling(band, min_periods=band // 2).quantile(q).shift(1).values
    hi = sig.rolling(band, min_periods=band // 2).quantile(1 - q).shift(1).values
    return lo, hi


def run_one(df: pd.DataFrame, sig: pd.Series, *, hold: int, q: float,
            band: int, fee_bps: float, cost_mult: float = 1.0,
            contrarian: bool = True, thr: tuple | None = None,
            stop_k: float = 0.0, vol: np.ndarray | None = None) -> np.ndarray:
    """One configuration, one market. Returns an array of trade records.

    Entry: the signal is compared with its own TRAILING quantiles over `band`
    bars, so the thresholds use only what had already happened. Stage 1 cut its
    buckets on the whole sample, which is fine for asking whether a signal ranks
    returns at all and not fine for a backtest.

    A bar in the top `q` tail means the crowd has been getting longer, and the
    diagnostic says that is followed by weakness, so the trade is SHORT. The
    bottom tail is the reverse. `contrarian=False` flips it, which is the honest
    control: if going WITH the crowd made money too, the signal is not what is
    paying.

    One position at a time. Entry and exit are both at a bar OPEN - the next
    open after the signal bar closes, and the open `hold` bars later.

    Columns: entry_i, exit_i, direction, entry_px, exit_px, r, ret_bps
    """
    o = df.open.values
    hi_px, lo_px = df.high.values, df.low.values
    n = len(o)
    s = sig.values
    lo, hi = thr if thr is not None else thresholds(sig, q, band)
    cost = fee_bps * cost_mult / 1e4          # round trip, as a fraction

    out = []
    i = band
    while i < n - hold - 2:
        sv, l, h = s[i], lo[i], hi[i]
        if sv != sv or l != l or h != h:
            i += 1
            continue
        d = 0
        if sv <= l:
            d = 1 if contrarian else -1       # crowd shrinking -> long
        elif sv >= h:
            d = -1 if contrarian else 1       # crowd crowding -> short
        if d == 0:
            i += 1
            continue
        e, x = i + 1, i + 1 + hold
        if x >= n:
            break
        pe = o[e]
        if not pe > 0:
            i += 1
            continue

        # THE STOP, and the assumption it rests on. Without one, R is a return
        # over trailing volatility and a single loser runs the whole hold, which
        # is what made the no-stop version undrawable inside an 8% cap. With one,
        # an intrabar assumption is unavoidable: this takes the FIRST bar whose
        # low (long) or high (short) breaches the level and fills AT the level.
        # That is optimistic - a gap through fills worse - so the cost multiple
        # is where the pessimism has to live, and any result here is provisional
        # until it is checked against a matching engine.
        xi, stopped = x, False
        if stop_k > 0.0 and vol is not None:
            v = vol[e - 1] if e >= 1 else np.nan
            if not (v == v and v > 0):
                i += 1
                continue
            level = pe * (1.0 - d * stop_k * v)
            for k in range(e, min(x, n - 1) + 1):
                if (d > 0 and lo_px[k] <= level) or (d < 0 and hi_px[k] >= level):
                    xi, stopped = k, True
                    break
        px = level if stopped else o[min(xi, n - 1)]
        if not px > 0:
            i += 1
            continue
        gross = d * (px - pe) / pe
        net = gross - cost
        out.append((e, xi, d, pe, px, net, net * 1e4))
        i = max(xi, e)                         # flat before the next entry
    return np.asarray(out, dtype="float64") if out else np.empty((0, 7))


def pf_of(r: np.ndarray) -> float:
    w, l = r[r > 0].sum(), -r[r < 0].sum()
    return float(w / l) if l > 0 else (float("inf") if w > 0 else float("nan"))
