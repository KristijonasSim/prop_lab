"""Plain English for every candidate. `VIX_TERM.change5.XAUUSD.h3` is not a name.

Kris, 2026-09-18: *"add always good namings what kind of strategy it is, not
some random namings"*. He is right and it is not cosmetic. A board he cannot
read is a board he stops opening, and the formula names were only ever an
internal key - they were never meant to be the label on a page.

THE RULE. A name says **what it watches, which way it bets, and for how long**,
in the words a trader uses. `VIX_TERM.change5.XAUUSD.h3` becomes

    "Calm building → sell Gold (3-day hold)"

The formula stays available underneath as the identity; this is the caption.
"""
from __future__ import annotations

MARKETS = {
    "XAUUSD": "Gold", "XAGUSD": "Silver", "EURUSD": "Euro",
    "GBPUSD": "Pound", "USDJPY": "Yen", "BTCUSDT": "Bitcoin",
}

#: feed -> (what it measures, what a HIGH reading means in plain words)
FEEDS = {
    "DFII10": ("real yields", "yields rising"),
    "DTWEXBGS": ("the dollar", "dollar strengthening"),
    "T10YIE": ("inflation expectations", "inflation expectations rising"),
    "REAL_MINUS_BE": ("real yields vs inflation", "real yields outpacing inflation"),
    "GVZ": ("gold volatility", "gold fear rising"),
    "VIX": ("stock-market fear", "fear rising"),
    "VIX3M": ("3-month fear", "longer-term fear rising"),
    "VIX_TERM": ("the fear curve", "calm building"),
    "GOLD_IMB": ("gold order book", "more size offered than bid"),
    "GOLD_SPREAD": ("gold trading costs", "spreads widening"),
    "GOLD_TICKS": ("gold activity", "trading activity spiking"),
}

#: transform -> how it qualifies the trigger. `{w}` is the window, `{u}` the
#: feed's own unit, so an hourly feed never says "days".
TRANSFORMS = {
    "level": "",
    "change": "over {w} {u}s",
    "zscore": "unusually fast for {w} {u}s",
    "pctile": "to a {w}-{u} high",
}


def market(sym: str) -> str:
    return MARKETS.get(sym, sym)


def feed_phrase(feed: str) -> tuple[str, str]:
    return FEEDS.get(feed, (feed.replace("_", " ").lower(), f"{feed} rising"))


def describe(feed: str, transform: str, window: int, market_sym: str,
             hold: int, direction: int, cadence: str = "1d") -> str:
    """One readable line for a candidate."""
    _what, high = feed_phrase(feed)
    unit = "hour" if cadence in ("1h", "1H") else "day"
    qualifier = TRANSFORMS.get(transform, "").format(w=window, u=unit)
    trigger = f"{high} {qualifier}".strip()
    side = "buy" if direction > 0 else "sell"
    plural = "" if hold == 1 else "s"
    return (f"{trigger[0].upper()}{trigger[1:]} → {side} {market(market_sym)} "
            f"({hold} {unit}{plural})")


def short(feed: str, market_sym: str) -> str:
    """A two-part label for a cramped column."""
    what, _ = feed_phrase(feed)
    return f"{what.title()} · {market(market_sym)}"


def from_key(key: str, cadence: str = "1d") -> str:
    """Describe a candidate from its ledger `candidate_key`."""
    try:
        feed, transform, window, _lag, mkt, hold, direction = key.split("|")
        return describe(feed, transform, int(window), mkt, int(hold),
                        int(direction), cadence)
    except (ValueError, AttributeError):
        return key
