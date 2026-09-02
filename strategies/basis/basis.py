"""H-013 — the derivative against the cash market it is supposed to track.

MECHANISM, stated before any result.

A perpetual has no expiry, so nothing forces it back to spot except the funding
transfer and the people who arbitrage the gap. When leveraged takers push the
perp away from its index, two named counterparties are on the other side: basis
traders who short the perp against cash and collect the premium, and the funding
payment itself, which bills the crowded side every eight hours. Neither of them
cares which way price goes. They care only that the gap closes.

So the claim is NOT "price reverts". It is narrower and it names its victim:

    a move paid for with leverage rather than with cash has to be unwound,
    because the people holding it are being charged to hold it.

TWO INDEPENDENT MEASUREMENTS OF THAT, both new to this repo:

  premium   (mark - index) / index, per 5m bar, from premiumIndexKlines.
            H-004 tested the 8-hourly funding SETTLEMENT, which is a clamped
            TWAP of this series; it found the widest stage-1 null margin in the
            project (828 gate-clearing configs against 2) and died in
            walk-forward at 0.20 trades/day. The settlement is the summary. This
            is the thing itself, at ~100x the resolution, which is the one
            reason to reopen the family.

  flow gap  perp taker imbalance minus SPOT taker imbalance on the same clock.
            Every flow feature this project has ever used is perp-only, so it
            cannot tell a move the cash market is paying for from one it is not.
            This can.

WHAT WOULD MAKE IT DIFFERENT FROM H-006/H-009. Those measure POSITIONING - a
headcount of who is standing where. This measures PRICE and PAYMENT - what the
crowded side is being charged. They can disagree, and the whole point of adding
it is that it is a different quantity, not a better estimate of the same one.

WHAT WOULD KILL IT. The same thing that killed H-008: a flat response. If the
size of the dislocation does not rank what follows, there is no mechanism and
nothing here is worth building.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

# A Binance USDT-M perp round trip, same figure H-006 uses, so the numbers here
# are directly comparable with `backtests/orderflow/stage1_ic.csv`.
ROUND_TRIP_BPS = 14.0


def load(sym: str, feeds_dir) -> pd.DataFrame:
    """Perp bars, the perp premium and the spot bars on one 5-minute index.

    Joined, never interpolated, and rows missing on any side are dropped: a
    forward-filled basis is a dislocation nobody could have observed. The spot
    frame is suffixed rather than merged so the two books stay distinguishable -
    conflating them is the exact error this hypothesis exists to avoid.
    """
    px = pd.read_parquet(feeds_dir / f"{sym}_perp_5m.parquet")
    pm = pd.read_parquet(feeds_dir / f"{sym}_premium_5m.parquet")[["close"]]
    pm.columns = ["premium"]
    sp = pd.read_parquet(feeds_dir / f"{sym}_spot_5m.parquet")[
        ["close", "volume", "taker_buy_base"]]
    sp.columns = ["spot_close", "spot_volume", "spot_taker_buy"]
    df = px.join(pm, how="inner").join(sp, how="inner").sort_index()
    return df[~df.index.duplicated(keep="last")]


def _z(s: pd.Series, win: int) -> pd.Series:
    """Rolling z-score, shifted so a bar is never part of its own baseline."""
    m = s.rolling(win, min_periods=win // 2).mean().shift(1)
    v = s.rolling(win, min_periods=win // 2).std(ddof=0).shift(1)
    return (s - m) / v.replace(0.0, np.nan)


def _imb(buy: pd.Series, vol: pd.Series) -> pd.Series:
    """Signed taker imbalance in [-1, 1]: (buy - sell) / total."""
    sell = (vol - buy).clip(lower=0.0)
    return (buy - sell) / vol.replace(0.0, np.nan)


def features(df: pd.DataFrame, win: int = 288) -> pd.DataFrame:
    """Point-in-time features. `win` is the z baseline in 5m bars (288 = 1 day).

    Levels are avoided except for the premium itself, which is already a ratio
    and comparable across coins and years - unlike open interest in contracts.
    """
    f = pd.DataFrame(index=df.index)
    px, spx = df.close, df.spot_close

    for k, name in ((12, "1h"), (48, "4h")):
        f[f"ret_{name}"] = np.log(px / px.shift(k))

    # ---- the premium ------------------------------------------------------
    prem = df.premium
    f["prem"] = prem
    f["prem_z"] = _z(prem, win)
    for k, name in ((12, "1h"), (48, "4h")):
        f[f"dprem_{name}"] = prem - prem.shift(k)

    # THE LEVERAGE READ. Price and premium moving together means the move is
    # being made in the derivative and not in cash: longs paying up for the
    # perp, funding about to bill them. Price up with the premium falling is
    # the opposite - cash leading, the perp lagging, nobody being charged.
    for name in ("1h", "4h"):
        f[f"lev_{name}"] = np.sign(f[f"ret_{name}"]) * f[f"dprem_{name}"]

    # ---- perp flow against cash flow --------------------------------------
    perp_i = _imb(df.taker_buy_base, df.volume)
    spot_i = _imb(df.spot_taker_buy, df.spot_volume)
    f["gap"] = perp_i - spot_i
    f["gap_z"] = _z(f["gap"], win)
    for k, name in ((12, "1h"), (48, "4h")):
        pb = df.taker_buy_base.rolling(k).sum()
        pv = df.volume.rolling(k).sum()
        sb = df.spot_taker_buy.rolling(k).sum()
        sv = df.spot_volume.rolling(k).sum()
        f[f"gap_{name}"] = _imb(pb, pv) - _imb(sb, sv)
        # CASH CONFIRMATION: is the cash market aggressing the same way price
        # moved? Negative means the move happened without cash behind it.
        f[f"cash_{name}"] = np.sign(f[f"ret_{name}"]) * _imb(sb, sv)

    # ---- perp price leading spot price ------------------------------------
    # The index is a multi-exchange basket, so it is not the same object as
    # Binance spot; measuring the lead on the venue's own two books is the
    # cleaner read of "the derivative moved and the cash did not".
    for k, name in ((12, "1h"), (48, "4h")):
        f[f"lead_{name}"] = np.log(px / px.shift(k)) - np.log(spx / spx.shift(k))

    return f


def forward_returns(df: pd.DataFrame, horizons=(12, 48, 96, 144, 288)) -> pd.DataFrame:
    """Log returns from the NEXT bar's open to the open h bars later.

    Next-bar open, not this bar's close: a signal read off a closed bar cannot
    be filled at that bar's close. Identical construction to H-006's, so the
    response tables are directly comparable."""
    o = df.open
    entry = o.shift(-1)
    out = pd.DataFrame(index=df.index)
    for h in horizons:
        out[f"fwd_{h}"] = np.log(o.shift(-1 - h) / entry)
    return out


# ---------------------------------------------------------------------------
# Signals for the grid. Kept separate from `features` on purpose: `features` is
# the diagnostic's wide net, this is the narrow set stage 1 said was worth
# trading, parameterised so the grid can vary the lookback rather than being
# stuck with the two the diagnostic happened to print.
# ---------------------------------------------------------------------------

SIGNALS = ("prem_z", "dprem", "lead", "gap")


def signal_series(df: pd.DataFrame, kind: str, look: int, win: int) -> pd.Series:
    """One signal, point in time. `look` and `win` are in 5-minute bars.

    Sign convention is the same for all four: HIGH means the derivative is
    running ahead of the cash market, which stage 1 says is followed by
    weakness, so the contrarian rule shorts the top tail.
    """
    prem = df.premium
    if kind == "prem_z":
        return _z(prem, win)
    if kind == "dprem":
        return prem - prem.shift(look)
    if kind == "lead":
        return (np.log(df.close / df.close.shift(look))
                - np.log(df.spot_close / df.spot_close.shift(look)))
    if kind == "gap":
        pb = df.taker_buy_base.rolling(look).sum()
        pv = df.volume.rolling(look).sum()
        sb = df.spot_taker_buy.rolling(look).sum()
        sv = df.spot_volume.rolling(look).sum()
        return _imb(pb, pv) - _imb(sb, sv)
    raise ValueError(kind)
