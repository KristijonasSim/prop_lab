"""THE ACTION SURFACE. What a candidate is allowed to see, and nothing else.

WHY THIS FILE IS THE WHOLE SAFETY STORY. Kris picked an LLM-driven generator
(2026-09-18). The published failure mode of that design is not bad ideas — it is
**look-ahead written by a confident model**, and arXiv 2608.27734's planted-oracle
test showed that statistics do not catch it: an oracle with Sharpe 34.7 sailed
through deflation with a perfect score. Their answer, and this file's:

    Look-ahead must be STRUCTURALLY INEXPRESSIBLE, not discouraged.

So a candidate here **never writes code**. It picks a `FeedSpec` from a registry,
a transform from a fixed enum, a lag at or above the feed's own floor, a market
and a hold. `research/run.py` builds the signal from those choices. There is no
path by which a proposal can read a future bar, because nothing it can say maps
onto one.

THE THREE RULES THE REGISTRY ENFORCES

1. **Every transform is backward-looking and then shifted again.** A rolling
   window ending at t, shifted by `lag` periods. The shift is applied by the
   runner, not by the candidate, and the floor is per feed.
2. **Every feed declares its knowable lag.** FRED publishes with a delay and
   revises; CFTC's COT lands Friday for Tuesday. A feed whose value at date d was
   not READABLE on date d is worth nothing, and H-035 died on exactly this — its
   signal alternated sign when the knowable lag was pushed out one day.
3. **A feed declares its cadence.** Daily feeds give ~750 events in three years,
   which `core/screen.independent_events` will mostly reject. That is the
   registry telling the truth early rather than the study finding out late.

WHAT GOES IN HERE. Feeds, not rules. This is the C-target the evidence supports:
every leg that has ever worked in two repos came from a new data feed, never a
new arrangement of price. A new entry here resets a search space that was never
tested; a new parameter on an old feed does not.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

DATA = ROOT / "data"


# ---------------------------------------------------------------------------
# Transforms — the complete list. A candidate may name one of these and nothing
# else. Each takes a raw series and returns a signal aligned to the same index.
# ---------------------------------------------------------------------------
def _level(s: pd.Series, n: int) -> pd.Series:
    return s


def _change(s: pd.Series, n: int) -> pd.Series:
    return s.diff(n)


def _zscore(s: pd.Series, n: int) -> pd.Series:
    m = s.rolling(n, min_periods=max(5, n // 2)).mean()
    v = s.rolling(n, min_periods=max(5, n // 2)).std(ddof=0)
    return (s - m) / v.replace(0.0, np.nan)


def _pctile(s: pd.Series, n: int) -> pd.Series:
    return s.rolling(n, min_periods=max(5, n // 2)).rank(pct=True)


#: name -> (function, needs a window?). THE COMPLETE SET.
TRANSFORMS: dict[str, tuple[Callable[[pd.Series, int], pd.Series], bool]] = {
    "level": (_level, False),
    "change": (_change, True),
    "zscore": (_zscore, True),
    "pctile": (_pctile, True),
}

#: Windows a candidate may choose, in the feed's own periods.
WINDOWS = (5, 20, 60, 250)

#: Holds a candidate may choose, in the feed's own periods.
HOLDS = (1, 3, 5, 10, 20)


@dataclass(frozen=True)
class FeedSpec:
    """One data source, and the honest facts about it.

    `lag_floor` is the minimum shift the runner will apply, in the feed's own
    periods. It is the single most important field here and the one most likely
    to be wrong in a way that flatters a result - so it is stated per feed, with
    the reason, rather than defaulted globally.
    """
    name: str
    desc: str = ""
    kind: str = "macro"                 # macro | vol | flow | positioning | price
    cadence: str = "1d"
    lag_floor: int = 1
    lag_reason: str = ""
    #: +1 if HIGH values should predict the market UP, -1 for down, 0 if the
    #: mechanism does not say. **A feed with no declared sign is a feed whose
    #: mechanism has not been written**, and the library proposer will not emit
    #: it — because enumerating both directions is a free second attempt at the
    #: same test and one of the two always matches the data. That is search
    #: inflation with no name on it, and it was in this file's first draft.
    prior_sign: int = 0
    sign_reason: str = ""
    loader: Callable[[], pd.Series] | None = None
    markets: tuple[str, ...] = ()       # empty = applies to all
    source: str = ""
    cached: str = ""                    # path under data/, for the UI
    revised: bool = False               # is the published value restated later?
    notes: tuple[str, ...] = field(default_factory=tuple)

    def load(self) -> pd.Series:
        if self.loader is None:
            raise RuntimeError(f"feed {self.name} has no loader")
        return self.loader().sort_index()

    def available(self) -> bool:
        p = DATA / self.cached if self.cached else None
        return bool(p and p.exists())


# ---------------------------------------------------------------------------
# Loaders. Each returns a plain dated series. Cached files only - the harvester
# is what touches the network, never this.
# ---------------------------------------------------------------------------
def _fred(sid: str) -> Callable[[], pd.Series]:
    def go() -> pd.Series:
        d = pd.read_csv(DATA / "macro" / f"{sid}.csv")
        d.columns = ["date", "val"]
        d["date"] = pd.to_datetime(d.date, utc=True)
        d["val"] = pd.to_numeric(d.val, errors="coerce")
        return d.dropna().set_index("date").val.rename(sid)
    return go


def _cboe(name: str) -> Callable[[], pd.Series]:
    def go() -> pd.Series:
        d = pd.read_csv(DATA / "vix" / f"{name}.csv")
        d["DATE"] = pd.to_datetime(d["DATE"], format="%m/%d/%Y", utc=True)
        col = "CLOSE" if "CLOSE" in d.columns else name
        return d.set_index("DATE")[col].rename(name).sort_index()
    return go


# ---------------------------------------------------------------------------
# THE REGISTRY
# ---------------------------------------------------------------------------
FEEDS: dict[str, FeedSpec] = {}


def register(f: FeedSpec) -> FeedSpec:
    if f.name in FEEDS:
        raise ValueError(f"feed {f.name} already registered")
    FEEDS[f.name] = f
    return f


register(FeedSpec(
    name="DFII10", desc="US 10-year real yield (TIPS)", kind="macro",
    lag_floor=1, prior_sign=-1,
    sign_reason="Gold pays no coupon, so a higher real yield raises the cost "
                "of holding it. High DFII10 should predict gold DOWN.",
    lag_reason="FRED publishes the previous business day; one day is the "
               "earliest it is readable.",
    loader=_fred("DFII10"), source="FRED", cached="macro/DFII10.csv",
    notes=("The single most-cited driver of gold in the literature - gold pays "
           "no coupon, so the real yield is its carrying cost.",)))

register(FeedSpec(
    name="DTWEXBGS", desc="Broad trade-weighted dollar index", kind="macro",
    lag_floor=1, prior_sign=-1,
    sign_reason="Gold is quoted in dollars; a stronger dollar makes the same "
                "ounce cost fewer of them. High DTWEXBGS predicts gold DOWN.",
    lag_reason="FRED daily, published next business day.",
    loader=_fred("DTWEXBGS"), source="FRED", cached="macro/DTWEXBGS.csv",
    notes=("Preferred over building DXY from the FX cache: this is the series "
           "the literature uses.",)))

register(FeedSpec(
    name="T10YIE", desc="10-year inflation breakeven", kind="macro",
    lag_floor=1, prior_sign=1,
    sign_reason="Gold is held as an inflation hedge, so rising expected "
                "inflation should predict gold UP.", lag_reason="FRED daily, published next business day.",
    loader=_fred("T10YIE"), source="FRED", cached="macro/T10YIE.csv",
    notes=("Gold's other standard driver in the literature.",)))

register(FeedSpec(
    name="GVZ", desc="CBOE gold volatility index", kind="vol",
    lag_floor=1, prior_sign=1,
    sign_reason="Elevated gold vol is priced fear, and the marginal buyer in "
                "a fear episode is a hedger. High GVZ predicts gold UP. "
                "Weakest prior in the registry - vol also mean-reverts.",
    lag_reason="Settlement value, readable the following session.",
    loader=_cboe("GVZ"), source="CBOE", cached="vix/GVZ.csv",
    markets=("XAUUSD",),
    notes=("H-045: the best filter result this project has produced - the only "
           "one that raised profit factor AND R per day together, against 24 "
           "of 25 entry filters that raised PF while lowering R/day.",)))

register(FeedSpec(
    name="VIX", desc="CBOE equity volatility index", kind="vol",
    lag_floor=1, prior_sign=1,
    sign_reason="Equity stress sends allocators to the safe haven; the seller "
                "is a risk-parity book cutting equity. High VIX predicts "
                "gold UP, and by the same mechanism crypto DOWN - which is "
                "what the cross-market re-run is for.", lag_reason="Settlement value, readable the following session.",
    loader=_cboe("VIX"), source="CBOE", cached="vix/VIX.csv"))

register(FeedSpec(
    name="VIX3M", desc="CBOE 3-month volatility index", kind="vol",
    lag_floor=1, prior_sign=1,
    sign_reason="Same mechanism as VIX, at a longer tenor.", lag_reason="Settlement value, readable the following session.",
    loader=_cboe("VIX3M"), source="CBOE", cached="vix/VIX3M.csv",
    notes=("With VIX, gives the term-structure slope H-043 used.",)))


# ---------------------------------------------------------------------------
# Derived feeds — combinations that are themselves a feed, declared not coded
# ---------------------------------------------------------------------------
def _vix_term() -> pd.Series:
    a, b = FEEDS["VIX"].load(), FEEDS["VIX3M"].load()
    j = pd.concat([a, b], axis=1).dropna()
    return (j.VIX3M - j.VIX).rename("VIX_TERM")


def _real_yield_minus_be() -> pd.Series:
    a, b = FEEDS["DFII10"].load(), FEEDS["T10YIE"].load()
    j = pd.concat([a, b], axis=1).dropna()
    return (j.DFII10 - j.T10YIE).rename("REAL_MINUS_BE")


register(FeedSpec(
    name="VIX_TERM", desc="VIX3M minus VIX (term structure slope)", kind="vol",
    lag_floor=1, prior_sign=-1,
    sign_reason="The curve is normally upward-sloping; it INVERTS under "
                "stress. So a high slope means calm, and calm predicts the "
                "safe haven DOWN.", lag_reason="Both legs are settlement values.",
    loader=_vix_term, source="CBOE (derived)", cached="vix/VIX.csv",
    notes=("Inversion is the stress signal H-043 measured on gold.",)))

# ---------------------------------------------------------------------------
# Intraday — the gold tick archive. THE REASON THE REGISTRY STOPPED BEING THIN.
#
# Every feed above is DAILY, which is ~750 rows in three years, and event count
# was the single biggest killer in the loop's first 187 tests. These are HOURLY
# on the market whose round trip is 1.06 bps, from tick files already on disk.
#
# WHAT THEY ARE, STATED ONCE AND CARRIED EVERYWHERE. Spot gold has no central
# exchange, so `askvol`/`bidvol` are Dukascopy's own liquidity-provider volume,
# not a consolidated tape. Measured 2026-09-18: the contemporaneous correlation
# between imbalance and the same-bar return is +0.025 hourly and -0.062 daily,
# which is flat - real aggressor flow would move price in its own bar almost
# mechanically. **So this is quoted size, not traded size**, which puts it in
# the H-024 family (book depth: real, monotone, beat its null, cleared its cost
# in 0 of 935 cells) and not the H-006 family. H-024 died on crypto's 14 bps;
# gold's bar is 2.13, so the family is not automatically dead here - but the
# prior is poor and the registry should say so rather than the write-up.
#
# COVERAGE IS PARTIAL: 245 of 689 business days, and 2024 is entirely missing.
# The screen reports the honest event count, so this understates rather than
# flatters.
# ---------------------------------------------------------------------------
def _flow(col: str) -> Callable[[], pd.Series]:
    def go() -> pd.Series:
        from core.gold_flow import load_flow
        d = load_flow("XAUUSD", "1h")
        if d.empty or col not in d:
            raise RuntimeError(f"no gold flow column {col!r} cached")
        return d[col].dropna().rename(f"GOLD_{col.upper()}")
    return go


register(FeedSpec(
    name="GOLD_IMB", desc="Gold ask/bid volume imbalance", kind="flow",
    cadence="1h", lag_floor=1, prior_sign=1,
    sign_reason="More size resting on the ask than the bid means dealers are "
                "leaning to sell; the marginal taker who lifts it pays up. "
                "High imbalance predicts gold UP. Weak prior - the same "
                "reading is equally consistent with supply that caps the move, "
                "which is exactly why H-024's version cleared no costs.",
    lag_reason="One completed hour. The bar must close before it is readable.",
    loader=_flow("imb"), source="Dukascopy ticks", cached="flow/XAUUSD",
    markets=("XAUUSD",),
    notes=("Quoted size, not traded size - measured, not assumed. Partial "
           "coverage: 245 of 689 business days, 2024 absent.",)))

register(FeedSpec(
    name="GOLD_SPREAD", desc="Gold quoted spread", kind="flow",
    cadence="1h", lag_floor=1, prior_sign=-1,
    sign_reason="A wide spread is dealers charging for risk they do not want. "
                "The forced seller into a wide market is the one who pays, so "
                "a wide spread should precede weakness. Never tested here in "
                "any form - core/fx_spread.py measured it to PRICE trades, "
                "never to predict them.",
    lag_reason="One completed hour.",
    loader=_flow("spread_bps"), source="Dukascopy ticks", cached="flow/XAUUSD",
    markets=("XAUUSD",),
    notes=("The one genuinely untouched idea in this registry: the cost series "
           "this project prices everything with, used as a signal.",)))

register(FeedSpec(
    name="GOLD_TICKS", desc="Gold tick count (activity)", kind="flow",
    cadence="1h", lag_floor=1, prior_sign=1,
    sign_reason="Tick count is participation. The 'stocks in play' literature "
                "(Zarattini et al.) finds the edge lives in the instruments "
                "being repriced, not the quiet ones, so high activity should "
                "precede continuation rather than fade.",
    lag_reason="One completed hour.",
    loader=_flow("ticks"), source="Dukascopy ticks", cached="flow/XAUUSD",
    markets=("XAUUSD",),
    notes=("H-020 tested relative volume on crypto perps; this is the same "
           "mechanism on the market that can pay for it.",)))


register(FeedSpec(
    name="REAL_MINUS_BE", desc="Real yield minus breakeven", kind="macro",
    lag_floor=1, prior_sign=-1,
    sign_reason="Both legs point the same way for gold: higher real yield "
                "and lower expected inflation are each bearish.", lag_reason="Both legs are FRED daily.",
    loader=_real_yield_minus_be, source="FRED (derived)",
    cached="macro/DFII10.csv"))


# ---------------------------------------------------------------------------
# What the search space actually is
# ---------------------------------------------------------------------------
def space(markets: tuple[str, ...]) -> int:
    """Raw candidate count over the registry. Quoted so nobody guesses it.

    This is the number `core/ledger.py` will charge against, one per candidate
    actually run - so it is also the honest statement of how expensive turning
    the loop on will be.
    """
    total = 0
    for f in FEEDS.values():
        mk = f.markets or markets
        for tname, needs_window in TRANSFORMS.items():
            wins = WINDOWS if needs_window[1] else (0,)
            total += len(mk) * len(wins) * len(HOLDS)
    return total


def summary() -> str:
    lines = [f"{len(FEEDS)} feeds, {len(TRANSFORMS)} transforms, "
             f"{len(WINDOWS)} windows, {len(HOLDS)} holds"]
    for f in sorted(FEEDS.values(), key=lambda x: (x.kind, x.name)):
        ok = "cached" if f.available() else "MISSING"
        lines.append(f"  {f.name:16}{f.kind:12}{f.cadence:5}lag>={f.lag_floor} "
                     f"{ok:8}{f.desc}")
    return "\n".join(lines)


if __name__ == "__main__":
    from core.universe import STANDARD
    print(summary())
    print()
    print(f"raw candidate space over the standard universe: "
          f"{space(tuple(STANDARD)):,}")
