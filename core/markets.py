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
TF_RULE = {"5m": "5min", "15m": "15min", "30m": "30min", "1h": "1h", "4h": "4h",
           #: VOLUME-CLOCK BARS, built by `core/volbars.py`, not a resample rule.
           #: Safe here only because TF_RULE is used as a pandas rule for CRYPTO
           #: alone; for everything else it is just the filename suffix. Never
           #: request one of these for a crypto symbol.
           "vol1h": "vol1h", "dol1h": "dol1h"}
#: bars per hour, for sizing hold horizons so they mean the same thing everywhere
#:
#: THE VOLUME-CLOCK ENTRIES ARE AN AVERAGE, NOT A CONSTANT. A volume bar can span
#: minutes at the NY open and hours in a dead Asian session, so `max_hold` on one
#: of these is a horizon in VOLUME, not in time. 1.0 makes it average out to the
#: 1h control and is exactly right on average and wrong on any single trade. No
#: result on these bars may be reported without saying so —
#: `strategies/vwapbreak/research/VOLBARS.md`.
TF_BPH = {"5m": 12.0, "15m": 4.0, "30m": 2.0, "1h": 1.0, "4h": 0.25,
          "vol1h": 1.0, "dol1h": 1.0}

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
    # Binance USD-M futures: maker 0.02%/side, taker 0.05%/side.
    #
    # THE HALF-SPREAD IS NOW MEASURED (H-049 stage 1, 2026-09-16,
    # `strategies/costmap/stage1_table.py`). It used to be an assumption of
    # 2.0-3.0 bps/side, flagged here as "the weakest number in this table"
    # because `bookTicker` stopped in 2024-03. The archive really does end
    # 2024-03-30 and it was never needed: a spread is visible in the trades.
    #
    # half_spread(S) = quoted_half_spread + impact(S), and the two scale
    # differently, so they are measured separately:
    #
    #   QUOTED  - the bid-ask bounce on adjacent aggTrades, 14 stratified days
    #             2024-06 -> 2026-08. Independent of order size.
    #             DO NOT measure it as vwap(buys) - vwap(sells) over a bar; that
    #             is separated by the bar's own trend as much as by the spread
    #             and reads NEGATIVE on falling bars. Stage 0 did, dropped the
    #             negatives, deleted 39% of its sample and had to be retracted.
    #   IMPACT  - from `data/feeds/*_depth_5m.parquet`, the resting notional
    #             within 0.2% of mid, at its 10th percentile (a thin book):
    #             impact_bps = 20 * (S/depth) / 2.  LINEAR in size.
    #
    # Measured at S = $100,000 of notional per leg. The live book runs five legs
    # at ~$877 each on $10,000 of equity, so $100k a leg is about a $1.1M
    # account - an order of magnitude past anything in scope.
    #
    #   sym       quoted   impact    measured    was     over by
    #   BTCUSDT   0.0062    0.021       0.027    2.00      74.7x
    #   ETHUSDT   0.0183    0.052       0.070    2.00      28.6x
    #   SOLUSDT   0.2876    0.178       0.465    3.00       6.4x
    #   XRPUSDT   0.3002    0.362       0.662    3.00       4.5x
    #   BNBUSDT   0.0795    0.436       0.516    3.00       5.8x
    #
    # THE NUMBERS BELOW ARE 2x THE MEASURED ONES, and that multiplier is a
    # deliberate, disclosed safety factor - for the sampled days, for the
    # uniform-book approximation behind the impact term, and for regime change.
    # It is NOT hidden inside the measurement.
    #
    # AND IT EXPIRES WITH ACCOUNT SIZE. The old assumption was not nonsense, it
    # was sized for an order this project does not place. Break-even leg size,
    # i.e. where the OLD number becomes correct: BTC $9.7M, ETH $3.8M,
    # SOL $1.5M, XRP $0.7M, BNB $0.7M. Re-run stage 1 before trading legs that
    # approach those.
    "BTCUSDT": Cost(2.0, 5.0, 0.05, 8.0, True,
                    "MEASURED 0.027bps/side at $100k/leg (quoted 0.0062 + "
                    "impact 0.021); carried at 2x. Was 2.00 ASSUMED"),
    "ETHUSDT": Cost(2.0, 5.0, 0.14, 10.0, True,
                    "MEASURED 0.070bps/side at $100k/leg (quoted 0.0183 + "
                    "impact 0.052); carried at 2x. Was 2.00 ASSUMED"),
    "SOLUSDT": Cost(2.0, 5.0, 0.93, 12.0, True,
                    "MEASURED 0.465bps/side at $100k/leg (quoted 0.2876 + "
                    "impact 0.178); carried at 2x. Was 3.00 ASSUMED"),
    "BNBUSDT": Cost(2.0, 5.0, 1.03, 12.0, True,
                    "MEASURED 0.516bps/side at $100k/leg (quoted 0.0795 + "
                    "impact 0.436); carried at 2x. Was 3.00 ASSUMED"),
    "XRPUSDT": Cost(2.0, 5.0, 1.32, 12.0, True,
                    "MEASURED 0.662bps/side at $100k/leg (quoted 0.3002 + "
                    "impact 0.362); carried at 2x. Was 3.00 ASSUMED"),
    # THE OTHER SIX H-024 PANEL COINS. They had no entry here at all; any study
    # touching them charged the small-coin assumption of 3.0bps/side by hand.
    # Measured the same way, and the result is the opposite of the majors:
    #
    #   sym        quoted   impact   measured    the 3.00 assumption was
    #   ADAUSDT    1.2155    1.747      2.962    about right
    #   LINKUSDT   0.4014    1.908      2.309    about right
    #   LTCUSDT    0.6587    1.912      2.570    about right
    #   DOGEUSDT   0.3532    0.589      0.942    3.2x too expensive
    #   AVAXUSDT   0.2351    3.393      3.628    TOO CHEAP
    #   DOTUSDT    1.2347    3.224      4.458    TOO CHEAP
    #
    # **THE OVERCHARGE IS A MAJORS-ONLY STORY.** BTC and ETH were charged 75x
    # and 29x too much; the small caps were charged about right and two of them
    # too little. Carried at the same disclosed 2x as everything above, which
    # makes five of these six MORE expensive than the assumption they replace.
    # That is the honest direction: impact dominates on a thin book and it is
    # measured here at the 10th percentile of depth.
    #
    # This also answers the "move down the cap curve" argument in
    # `strategies/depth/stage2_cost.py` with a number: the small-cap edge the
    # literature reports is real, and so is the cost of reaching it.
    "ADAUSDT":  Cost(2.0, 5.0, 5.92, 12.0, True,
                     "MEASURED 2.962bps/side at $100k/leg; carried at 2x"),
    "AVAXUSDT": Cost(2.0, 5.0, 7.26, 14.0, True,
                     "MEASURED 3.628bps/side at $100k/leg; carried at 2x"),
    "DOGEUSDT": Cost(2.0, 5.0, 1.88, 12.0, True,
                     "MEASURED 0.942bps/side at $100k/leg; carried at 2x"),
    "DOTUSDT":  Cost(2.0, 5.0, 8.92, 14.0, True,
                     "MEASURED 4.458bps/side at $100k/leg; carried at 2x"),
    "LINKUSDT": Cost(2.0, 5.0, 4.62, 12.0, True,
                     "MEASURED 2.309bps/side at $100k/leg; carried at 2x"),
    "LTCUSDT":  Cost(2.0, 5.0, 5.14, 12.0, True,
                     "MEASURED 2.570bps/side at $100k/leg; carried at 2x"),
    # ADDED 2026-09-10 for the H-027 cross-market diagnosis. Kris asked for a
    # 6-7 market basket and these six were already cached and never tested; the
    # index CFDs matter most, because a follow-the-break rule wants a market
    # that trends and this repo has never run one on an index.
    #
    # EVERY NUMBER HERE IS ASSUMED and deliberately PESSIMISTIC: 1.5bps of
    # half-spread on an index whose real Dukascopy spread is nearer 0.5-1.0, and
    # FX half-spreads set at the top of the range measured on EUR/GBP. A cell
    # that clears at these costs would clear at real ones; a cell that fails at
    # these might not. Measure before trading any of them.
    "NAS100": Cost(0.15, 0.15, 1.50, 3.0, False, "ASSUMED - index CFD, pessimistic"),
    "SPX500": Cost(0.15, 0.15, 1.50, 3.0, False, "ASSUMED - index CFD, pessimistic"),
    "US30":   Cost(0.15, 0.15, 1.50, 3.0, False, "ASSUMED - index CFD, pessimistic"),
    "USDCHF": Cost(0.05, 0.05, 0.60, 1.5, False, "ASSUMED - spread never measured"),
    "NZDUSD": Cost(0.05, 0.05, 0.70, 1.5, False, "ASSUMED - spread never measured"),
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
    "AUDUSD": "FX", "USDCAD": "FX", "USDCHF": "FX", "NZDUSD": "FX",
    "NAS100": "Indices", "SPX500": "Indices", "US30": "Indices",
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
