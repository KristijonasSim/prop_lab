"""THE MARKETS EVERY STUDY MUST TOUCH. Standing rule, Kris 2026-09-15.

His words: *"i want always to test it on BTC gold / silver and main FX pairs
ALWAYS! no matter what strategy and blah blah blah we need to test on all of
them"*.

WHY IT IS A RULE AND NOT A HABIT. Two of this project's worst hours went into
results that were one market wide. The Asian range break beat its own null by
3.5x on gold and by nothing anywhere else - that only became visible when it was
run on every market. Silver has already fooled this repo once, at 59.9% pass
while losing to its own null. A number from a single market is a hypothesis, not
a result.

USE `STANDARD` UNLESS THERE IS A REASON NOT TO, AND WRITE THE REASON DOWN.
A cross-sectional study needs a group to rank inside and cannot run on one
instrument; that is a real exemption. "It is slow" is not.
"""
from __future__ import annotations

#: Crypto. Binance perp/spot caches in `data/feeds/` and `data/`.
CRYPTO = ["BTCUSDT"]

#: Metals. Dukascopy caches in `data/`. Gold is the project's live market;
#: silver is its nearest relative and its most reliable false positive.
METALS = ["XAUUSD", "XAGUSD"]

#: The main FX pairs. Majors only - these are what every prop firm quotes
#: tightest and what the Dukascopy cache covers back furthest.
FX = ["EURUSD", "GBPUSD", "USDJPY"]

#: THE DEFAULT UNIVERSE. Every study reports every one of these.
STANDARD = CRYPTO + METALS + FX

#: Available if a study wants more breadth. Not required.
EXTRA_FX = ["AUDUSD", "USDCAD", "USDCHF", "NZDUSD"]
EXTRA_CRYPTO = ["ETHUSDT", "SOLUSDT", "XRPUSDT", "BNBUSDT"]
INDICES = ["NAS100", "SPX500", "US30"]
ENERGY = ["WTI", "BRENT"]

#: Where each family's bars live, for the loaders.
SOURCE = {**{s: "binance" for s in CRYPTO + EXTRA_CRYPTO},
          **{s: "dukascopy" for s in METALS + FX + EXTRA_FX + INDICES + ENERGY}}


def check(tested) -> list[str]:
    """Which STANDARD markets a study skipped. Empty list means it complied."""
    t = {str(x).upper() for x in tested}
    return [m for m in STANDARD if m.upper() not in t]
