"""H-015 — is the crowd crowded across the whole complex, or just in this coin?

MECHANISM, stated before any result.

H-009 is the top of this board because it keeps only the trades the crowd is
positioned against, read from Binance's long/short ACCOUNT ratio. But it reads
that ratio one coin at a time: BTC's gate sees BTC's crowd, ETH's sees ETH's.

A single coin's account ratio is one noisy measurement of a quantity that is not
really per-coin. Retail risk appetite is systemic - the same people are long
everything, and they are margined against the same collateral. So:

    if the thing that pays is "the crowd is offside", then the crowd's position
    across ELEVEN coins is a better estimate of it than the position in one.

That is an estimator claim, not a new mechanism, and it is falsifiable: the
systemic reading must rank forward returns BETTER than the coin's own reading,
measured on the same coins over the same horizons. If it does not, the crowding
is genuinely idiosyncratic and H-009 is already using the right feed.

The second object here is the residual. `idio` is a coin's own crowding minus
the complex's, which separates "everyone is long everything" from "everyone is
long THIS". Those are different trades and no signal in this repo distinguishes
them.

WHY IT IS NOT H-006 AGAIN. H-006 tested `crowd_z`, `dcrowd` and `disagree`, all
single-coin, on three coins. Every feature here is CROSS-SECTIONAL and uses
eleven. The data has been on disk since the archive pull; nothing had aggregated
it.

WHAT WOULD KILL IT. The same thing that killed H-008 and, at stage 2, H-013: if
the systemic reading does not rank forward returns better than the coin's own,
there is nothing here worth building.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

# The whole USDT-M complex this repo has metrics for. Deliberately not a chosen
# subset: picking which coins define "the complex" after seeing results would be
# the search, not the signal.
COMPLEX = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT", "DOGEUSDT",
           "ADAUSDT", "AVAXUSDT", "LINKUSDT", "DOTUSDT", "LTCUSDT")

CROWD = "count_long_short_ratio"          # long ACCOUNTS / short accounts
TOPSZ = "sum_toptrader_long_short_ratio"  # top traders, weighted by POSITION size
ROUND_TRIP_BPS = 14.0


def _z(s: pd.Series, win: int) -> pd.Series:
    """Rolling z-score, shifted so a bar is never part of its own baseline."""
    m = s.rolling(win, min_periods=win // 2).mean().shift(1)
    v = s.rolling(win, min_periods=win // 2).std(ddof=0).shift(1)
    return (s - m) / v.replace(0.0, np.nan)


def panel(feeds_dir, win: int = 288, cols=(CROWD, TOPSZ)) -> dict:
    """One z-scored frame per column, coins across the columns, 5m index.

    Each coin is z-scored against ITS OWN history before being averaged. The raw
    ratio has a different resting point on every coin - DOGE sits near 2.5 where
    BTC sits near 1.3 - so averaging the levels would just weight the complex by
    which coins happen to run hot, not by who is crowded today.
    """
    out = {c: {} for c in cols}
    for sym in COMPLEX:
        f = feeds_dir / f"{sym}_metrics_5m.parquet"
        if not f.exists():
            continue
        d = pd.read_parquet(f, columns=list(cols))
        for c in cols:
            s = np.log(d[c].replace(0.0, np.nan))
            out[c][sym] = _z(s, win)
    return {c: pd.DataFrame(v).sort_index() for c, v in out.items()}


def systemic(pan: dict, min_coins: int = 6) -> pd.DataFrame:
    """The complex-wide readings, all point in time.

    `min_coins` guards the early history: in 2020 only a handful of these
    contracts existed, and a "complex" of two coins is not a complex. Bars with
    fewer are dropped rather than averaged over whatever happens to be listed,
    because a signal whose meaning changes as the universe grows is not one
    signal.
    """
    z = pan[CROWD]
    n = z.notna().sum(axis=1)
    out = pd.DataFrame(index=z.index)
    # THE SYSTEMIC READING: how crowded is the whole complex, on average.
    out["sys"] = z.mean(axis=1).where(n >= min_coins)
    # BREADTH: what SHARE of coins is crowded long. Insensitive to one coin
    # blowing out, which the mean is not - if they disagree, the mean is being
    # driven by an outlier rather than by agreement.
    out["breadth"] = (z > 0).sum(axis=1).div(n).where(n >= min_coins) * 2.0 - 1.0
    # DISPERSION: are they moving together or apart? A high mean with high
    # dispersion is not the same trade as a high mean with low dispersion.
    out["disp"] = z.std(axis=1).where(n >= min_coins)
    # SIZE vs CROWD, complex-wide: the retail-against-whales gap H-006 measured
    # per coin, aggregated. Positive = size is longer than the headcount.
    zs = pan[TOPSZ]
    ns = zs.notna().sum(axis=1)
    out["sys_size"] = zs.mean(axis=1).where(ns >= min_coins)
    out["sys_gap"] = out["sys_size"] - out["sys"]
    for k in (12, 48, 144):
        out[f"dsys_{k}"] = out["sys"] - out["sys"].shift(k)
    return out


def features(sym: str, feeds_dir, pan: dict, sysdf: pd.DataFrame,
             win: int = 288) -> pd.DataFrame:
    """Signals for one coin: its own crowding, the complex's, and the residual.

    `own` is deliberately identical in construction to H-006's `crowd_z`, so the
    head-to-head is like for like and any difference is the aggregation rather
    than the definition.
    """
    own = pan[CROWD][sym]
    f = pd.DataFrame(index=own.index)
    f["own"] = own
    f["sys"] = sysdf["sys"].reindex(own.index)
    f["breadth"] = sysdf["breadth"].reindex(own.index)
    f["disp"] = sysdf["disp"].reindex(own.index)
    f["sys_gap"] = sysdf["sys_gap"].reindex(own.index)
    # THE RESIDUAL: crowded in THIS coin beyond how crowded everything is.
    f["idio"] = f["own"] - f["sys"]
    for k in (12, 48, 144):
        f[f"dsys_{k}"] = sysdf[f"dsys_{k}"].reindex(own.index)
        f[f"down_{k}"] = own - own.shift(k)
    return f


def bars(sym: str, feeds_dir) -> pd.DataFrame:
    return pd.read_parquet(feeds_dir / f"{sym}_perp_5m.parquet")


def forward_returns(df: pd.DataFrame, horizons=(12, 48, 96, 144, 288)) -> pd.DataFrame:
    """Next bar's open to the open h bars later - identical to H-006's, so the
    response tables can be compared directly."""
    o = df.open
    entry = o.shift(-1)
    out = pd.DataFrame(index=df.index)
    for h in horizons:
        out[f"fwd_{h}"] = np.log(o.shift(-1 - h) / entry)
    return out
