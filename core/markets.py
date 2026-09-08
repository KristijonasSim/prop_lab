"""One loader for every market this project trades. Part of Engine 2.

Before this, `strategies/vwap/stage3_timeframes.py` knew how to load BTC and FX,
`strategies/ribbon/sweep.py` knew how to load three coins and FX, and each had
its own timeframe spelling. A new hypothesis had to import across from one of
them or write a third copy.

TWO CACHE NAMING CONVENTIONS EXIST and both are real:
  * FX and metals: `data/<SYM>_dukascopy_<rule>.parquet`, already resampled,
    where `rule` is pandas spelling — `5min`, `15min`, `30min`, `1h`, `4h`.
  * Crypto: `data/<SYM>_spot_15m.parquet` only, resampled here on demand. There
    is no crypto cache finer than 15m, so 5m is not available on a coin.

COSTS ARE PER MARKET AND MOSTLY MEASURED. Gold and EURUSD come from Dukascopy
tick data; the rest are assumptions and are labelled as such, because this repo
has been wrong about an assumed spread by 5.5x in one direction and 7.6x in the
other on the same instrument.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

DATA = ROOT / "data"

#: label -> pandas resample rule / dukascopy filename suffix
TF_RULE = {"5m": "5min", "15m": "15min", "30m": "30min", "1h": "1h", "4h": "4h"}
#: bars per hour, for sizing hold horizons so they mean the same thing everywhere
TF_BPH = {"5m": 12.0, "15m": 4.0, "30m": 2.0, "1h": 1.0, "4h": 0.25}

CRYPTO = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT")

AGG = {"open": "first", "high": "max", "low": "min", "close": "last",
       "volume": "sum"}


@dataclass(frozen=True)
class Cost:
    """What a round trip costs, split the way the kernels charge it.

    The kernels charge `(fee_bps + slip_bps)` against BOTH fills, so a cost has
    to be expressed per side. `slip_bps` is the half-spread a taker crosses; a
    maker does not cross it at all.
    """
    maker_fee: float          # bps per side, resting order
    taker_fee: float          # bps per side, crossing order
    half_spread: float        # bps per side paid only when crossing
    min_risk_bps: float
    measured: bool
    note: str = ""

    def per_side(self, mode: str = "mixed") -> tuple[float, float]:
        """(fee_bps, slip_bps) averaged per side for the execution mode.

        `mixed` is the default and the honest one: **the ENTRY is a resting
        limit order and the EXIT is a market order**, because a stop-loss cannot
        be a limit — it is a market order by definition. So one side is maker and
        one is taker, and the kernel gets the average of the two.
        """
        if mode == "taker":
            return self.taker_fee, self.half_spread
        if mode == "maker":
            return self.maker_fee, 0.0
        if mode == "mixed":
            entry = self.maker_fee
            exit_ = self.taker_fee + self.half_spread
            return (entry + exit_) / 2.0, 0.0
        raise KeyError(mode)

    def round_trip(self, mode: str = "mixed") -> float:
        f, s = self.per_side(mode)
        return 2 * (f + s)


# MAKER ENTRIES ARE THE DEFAULT, AND THEY ARE MEASURED SAFE - on BTC.
#
# H-023 stage 12 measured the fill assumption on TICKS rather than bars:
# through-given-touch is 99.8-100% at every distance from 5 to 80bps, 96-98%
# even assuming 10 BTC already resting ahead in the queue, and adverse selection
# is ~0 - the forward return 1h after a through-fill is within 0.08bps of after
# a mere touch. A 15m BTC perp bar carries ~1,600 trades; price does not kiss a
# level and leave.
#
# SCOPE, AND IT MATTERS: one market, one bar size, one regime. ETH, SOL and
# XAUUSD are UNMEASURED and their maker numbers are an extrapolation.
#
# And do not expect this to fix pace: H-023 stage 14 priced a whole book from
# 14bps down to ZERO and it moved 57 days to 32. Free execution buys 33-44% of
# the days; the target needs about 85%. Take the fee saving because it is real
# and free - not because it solves the problem.
COSTS: dict[str, Cost] = {
    # MEASURED from Dukascopy ticks (core/fx_spread.py). On a retail FX/CFD
    # venue the quoted spread is the broker's, so a limit order does not earn
    # it the way it does on an exchange order book - maker and taker fees are
    # the same and only the commission differs. Modelled as such.
    "XAUUSD": Cost(0.15, 0.15, 0.765, 3.0, True,
                   "MEASURED 0.915bps/side: 1.671 mean spread + 0.15 commission"),
    "EURUSD": Cost(0.05, 0.05, 0.087, 1.0, True,
                   "MEASURED 0.137bps/side; mid-week median spread 0.190bps"),
    "GBPUSD": Cost(0.05, 0.05, 0.310, 1.5, True,
                   "MEASURED; median mid-week spread 0.515bps"),
    "USDJPY": Cost(0.05, 0.05, 0.45, 1.5, False, "ASSUMED - spread never measured"),
    "AUDUSD": Cost(0.05, 0.05, 0.55, 1.5, False, "ASSUMED - spread never measured"),
    "USDCAD": Cost(0.05, 0.05, 0.60, 1.5, False, "ASSUMED - spread never measured"),
    # Energy. Dukascopy CFDs, spread never measured here and wider than FX.
    "WTI": Cost(0.15, 0.15, 2.50, 5.0, False, "ASSUMED - CFD, spread never measured"),
    "BRENT": Cost(0.15, 0.15, 2.50, 5.0, False, "ASSUMED - CFD, spread never measured"),
    "XAGUSD": Cost(0.15, 0.15, 4.40, 6.0, True, "MEASURED 9.108bps spread"),
    # Binance USD-M futures: maker 0.02%/side, taker 0.05%/side. The SPREAD is
    # unmeasured - bookTicker stopped in 2024-03 - so half_spread is an
    # assumption and is the weakest number in this table.
    "BTCUSDT": Cost(2.0, 5.0, 2.0, 8.0, False,
                    "futures maker 0.02% / taker 0.05%; spread ASSUMED"),
    "ETHUSDT": Cost(2.0, 5.0, 2.0, 10.0, False,
                    "futures maker/taker; spread ASSUMED; fills UNMEASURED"),
    "SOLUSDT": Cost(2.0, 5.0, 3.0, 12.0, False,
                    "futures maker/taker; spread ASSUMED; fills UNMEASURED"),
    "BNBUSDT": Cost(2.0, 5.0, 3.0, 12.0, False, "spread ASSUMED"),
    "XRPUSDT": Cost(2.0, 5.0, 3.0, 12.0, False, "spread ASSUMED"),
}

#: How trades are assumed to execute. `mixed` = limit entry, market exit.
EXEC_MODE = "mixed"

#: how the board groups markets. Kris's layout, 2026-09-08.
ASSET_CLASS = {
    # "Gold" widened to metals and energy on Kris's instruction 2026-09-08 - the
    # class is the thing a basket is built from, so it has to hold more than one
    # tradeable market or there is no basket to build.
    "XAUUSD": "Metals/Energy", "XAGUSD": "Metals/Energy",
    "WTI": "Metals/Energy", "BRENT": "Metals/Energy",
    "EURUSD": "FX", "GBPUSD": "FX", "USDJPY": "FX",
    "AUDUSD": "FX", "USDCAD": "FX",
    **{c: "Crypto" for c in CRYPTO},
}


def path_for(sym: str, tf: str) -> Path:
    if sym in CRYPTO:
        return DATA / f"{sym}_spot_15m.parquet"
    return DATA / f"{sym}_dukascopy_{TF_RULE[tf]}.parquet"


def load(sym: str, tf: str) -> pd.DataFrame:
    """Bars for one market and timeframe, from the caches already in the repo."""
    if tf not in TF_RULE:
        raise KeyError(f"unknown timeframe {tf!r}")
    p = path_for(sym, tf)
    if not p.exists():
        raise FileNotFoundError(p)
    df = pd.read_parquet(p).sort_index()
    if sym in CRYPTO:
        if tf == "5m":
            # the crypto cache is 15m-based and cannot go finer. Returning an
            # empty frame rather than raising, because a sweep over every
            # (market, tf) pair should skip this cell, not die on it.
            return pd.DataFrame()
        if tf != "15m":
            df = (df.resample(TF_RULE[tf], label="left", closed="left")
                    .agg(AGG).dropna(subset=["open"]))
    return df


def markets_for(syms, tfs) -> list[tuple[str, str]]:
    """Every (sym, tf) pair that actually has data."""
    out = []
    for s in syms:
        for t in tfs:
            try:
                if len(load(s, t)):
                    out.append((s, t))
            except (FileNotFoundError, KeyError):
                continue
    return out
