"""THE 24 CELLS every idea is checked on — six markets x four timeframes.

    BTCUSDT  XAUUSD  XAGUSD  EURUSD  GBPUSD  USDJPY   x   15m  1h  4h  1d

WHY ALL 24 AND NOT JUST GOLD (decided 2026-09-22, `docs/STEP3.md` §B).

* **One cell is the wrong cell.** Gold's round trip is 1.83 bps and EURUSD's is
  0.27. An idea killed on gold alone is killed at six times the cost bar it
  would face on EURUSD.
* **It is affordable.** ~0.35s per idea on gold 1h; a whole market across four
  timeframes is ~120,000 bars, so the full 24 is roughly 11 seconds an idea.
* **The 24-chances-at-luck objection is already answered by step 6.** The
  2026-09-21 simulation: junk reaching the desk is 31 per 1,000 on three years
  alone and 0.5 per 1,000 once the five-year re-check runs. Step 6 pays for the
  width, here as in step 4.
* **The bar does not move because 24 cells were tried** - settled with Kris on
  2026-09-21 and not reopened. The ledger records the 24 so the same idea is not
  tried twice; that is all it is for.

WHY THE COST IS THE **TAKER** ROUND TRIP AND NOT `core.markets.EXEC_MODE`.
`markets.EXEC_MODE` is `mixed`, which assumes the ENTRY is a resting limit
order. The factory's grammar generates breakout-shaped rules whose entry is,
by construction, on the far side of the market - you cannot rest a buy limit
above the price. H-023 measured what a limit entry is worth and the better
entry PRICE was +0.011 profit factor; the whole benefit was the fee, and it is
a fee a breakout cannot collect. So step 3 charges the crossing cost.
"""
from __future__ import annotations

import sys
from functools import lru_cache
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core import markets, universe                                   # noqa: E402
from core.run_hypothesis import YEARS, window                        # noqa: E402

#: Kris's standing rule, `core.universe.STANDARD`.
MARKETS = list(universe.STANDARD)
#: The diagram's four. 1d is included and is expected to fail the 0.4 trades/day
#: floor on most ideas - that is the gate doing its job, not a reason to omit it.
TIMEFRAMES = ("15m", "1h", "4h", "1d")

_DAILY_RULE = "1D"
#: THE FX DAY STARTS AT 22:00 UTC, NOT AT MIDNIGHT, and the daily bar has to
#: know it. The trading week opens Sunday 22:00; resampling on midnight leaves
#: those two hours as a separate one-bar "day", which on gold added 155 phantom
#: trading days across three years - a 21% inflation of the denominator in
#: `check.trading_days` and therefore a 21% understatement of trades/day.
#: Crypto runs 24/7 and is unaffected either way.
_DAILY_OFFSET = "22h"


@lru_cache(maxsize=1)
def common_window(years: int = YEARS) -> tuple[pd.Timestamp, pd.Timestamp]:
    """The [start, end] every one of the 24 cells is trimmed to.

    Kris's standing rule: three years of data, aligned to a COMMON END across
    the whole universe, where the end is the EARLIEST last bar and not the
    latest. Without it BTC brings 9.1 years to a comparison in which gold has 3,
    and "crypto passed more often" partly means "crypto was measured longer".
    `core.run_hypothesis.window` already implements it, including the snap to a
    month boundary that stops adding a market from moving another market's
    numbers.
    """
    return window(MARKETS, ("1h",), years=years)


#: Where the five-year caches live. Built by `scripts/build_5y.py` from the
#: Dukascopy raw .bi5 already on disk, under their OWN name rather than by
#: extending `{sym}_dukascopy_{tf}.parquet`. Overwriting the three-year file
#: would silently change the input of every board number in the repo for a
#: gain step 6 can get without it.
DEEP_SUFFIX = "dukascopy5y"


def _deep(sym: str, tf: str) -> pd.DataFrame:
    """The five-year cache if it exists, otherwise whatever `markets` has."""
    p = markets.DATA / f"{sym}_{DEEP_SUFFIX}_{tf}.parquet"
    if p.exists():
        return pd.read_parquet(p).sort_index()
    return markets.load(sym, tf)


@lru_cache(maxsize=64)
def untrimmed(sym: str, tf: str) -> pd.DataFrame:
    """Every bar on disk for one cell, with the clock column attached.

    SEPARATE FROM `load` BECAUSE STEP 6 NEEDS THE YEARS `load` THROWS AWAY.
    `load` trims to the common three-year window, which is the whole point of
    steps 3 and 4; the five-year re-check has to reach behind that start date,
    and re-reading and re-resampling the parquet for every cell made it the
    slowest thing in the pipeline. Cached here once, sliced by both.

    `core.markets.TF_RULE` has no `1d` entry and adding one there would change a
    mapping the board reads, so the daily resample is done here instead.
    """
    if tf == "1d":
        base = untrimmed(sym, "1h")
        df = ((base.resample(_DAILY_RULE, label="left", closed="left",
                             offset=_DAILY_OFFSET)
                   .agg(markets.AGG).dropna(subset=["open"]))
              if len(base) else base)
    else:
        df = _deep(sym, tf)
    if not len(df):
        return df
    df = df.copy()
    # THE CLOCK, carried as a column because `build.run` resets the index
    # before a strategy ever sees the frame. It is a property of bar t alone,
    # so it cannot leak - see `guard.Window.COLUMNS`. Step 4's session repairs
    # are the only thing that reads it.
    df["hour"] = df.index.hour.astype(float)
    return df


@lru_cache(maxsize=64)
def load(sym: str, tf: str) -> pd.DataFrame:
    """Bars for one cell, trimmed to the common three-year window."""
    df = untrimmed(sym, tf)
    if not len(df):
        return df
    lo, hi = common_window()
    return df.loc[(df.index >= lo) & (df.index <= hi)]


@lru_cache(maxsize=64)
def trading_days(sym: str) -> float:
    """Full sessions this MARKET was open in the window - one number per market.

    Measured once on the 1h series and reused for all four timeframes, because
    the number of days a market traded is a property of the market and not of
    the bar size it is looked at through. Deriving it per timeframe instead let
    the 1d cell disagree with the 1h cell by 13-21% on FX, purely because the
    Sunday session-open stub becomes its own daily bar.
    """
    from factory.check import trading_days as _days           # local: cycle
    return _days(load(sym, "1h"))


#: Step 6's ceiling. Kris, 2026-09-15: "maximum we need is 5 always not more
#: then 5 ideal 3 years". Steps 3 and 4 use YEARS (3); the re-check is allowed
#: the other two and nothing beyond them.
RECHECK_YEARS = 5


@lru_cache(maxsize=64)
def holdout(sym: str, tf: str, years: int = RECHECK_YEARS) -> pd.DataFrame:
    """The years BEFORE the step-3 window - bars the idea has never been on.

    NOT "the same test on five years", which is what step 6 was drawn as and
    what the first version of this function did. The five-year window CONTAINS
    the three the idea already passed, so a rule that did well there is carried
    by its own training data and the re-check is not an independent draw. The
    two years in front of it are, so that is what is returned.

    The full five years is still worth reporting and `recheck` reports it, as
    context rather than as the gate.

    The span is per MARKET and not common across the universe, deliberately.
    `common_window` exists so that markets can be RANKED against each other;
    step 6 asks one question about one idea on one cell, so trimming gold back
    to silver's history would throw away evidence and buy nothing.
    """
    df = untrimmed(sym, tf)
    if not len(df):
        return df
    lo, _ = common_window()
    start = lo - pd.DateOffset(years=years - YEARS)
    return df.loc[(df.index >= start) & (df.index < lo)]


def cost_bps(sym: str) -> float:
    """The round trip an idea must clear on this market, in bps. Crossing cost."""
    return markets.COSTS[sym].round_trip("taker")


def all_cells(markets_: list[str] | None = None,
              timeframes: tuple[str, ...] | None = None) -> list[tuple[str, str]]:
    """Every (market, timeframe) pair that has data. 24 by default."""
    out = []
    for s in (markets_ or MARKETS):
        for t in (timeframes or TIMEFRAMES):
            try:
                if len(load(s, t)):
                    out.append((s, t))
            except (FileNotFoundError, KeyError):
                continue
    return out
