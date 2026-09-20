"""Every hypothesis this project has ever run, sorted into baskets.

WHY. Kris, 2026-09-18: *"what kind of strategies, put them into baskets like
oscillators, bands etc"*. Until now the only grouping was the H-number, which is
chronological and tells you nothing about what was tried. 55 hypotheses in a
column of numbers is not a picture of a search; 13 baskets is.

WHAT IT IS FOR, BEYOND THE PAGE. A basket with fifty trials and no survivor is a
closed direction, and a basket with nothing in it is either an opportunity or a
deliberate refusal. Both are invisible when the only axis is time.

THE MAPPING IS HAND-WRITTEN AND THAT IS DELIBERATE. It is a judgement about what
an idea WAS, and it is recorded here so it can be argued with, rather than
guessed from a name at render time. Anything unmapped falls into `other` and
shows up on the page as unmapped rather than being silently dropped.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Family:
    key: str
    name: str
    blurb: str          # four or five words, shown under the name
    kind: str           # "price" | "data" | "method"


#: Ordered for display: price shapes first, then data feeds, then the
#: method work that is not a strategy at all.
FAMILIES: tuple[Family, ...] = (
    Family("bands", "Bands & envelopes", "VWAP, sigma bands, anchors", "price"),
    Family("breakout", "Breakouts", "opening range, session break", "price"),
    Family("trend", "Trend & moving averages", "EMA, ribbons, crosses", "price"),
    Family("fade", "Fades & mean reversion", "sweeps, prior highs, ratios", "price"),
    Family("structure", "Market structure / SMC", "fair value gaps, AMD", "price"),
    Family("xsec", "Cross-sectional", "rank one market against others", "price"),

    Family("flow", "Order flow", "taker delta, depth, footprint", "data"),
    Family("position", "Positioning & carry", "funding, open interest, COT", "data"),
    Family("ivol", "Implied volatility", "VIX, GVZ, DVOL, term structure", "data"),
    Family("macro", "Macro rates & dollar", "real yields, DXY, breakevens", "data"),

    Family("portfolio", "Portfolio & sizing", "weights, legs, vol targeting", "method"),
    Family("exec", "Execution & risk", "fills, drawdown, guards", "method"),
    Family("event", "Events", "listings, session reopens", "method"),
    Family("other", "Unmapped", "not yet classified", "method"),
)

BY_KEY = {f.key: f for f in FAMILIES}

#: hypothesis id -> (family key, human name). The name is what the strategy
#: actually was, in the words a trader would use - not the internal codename.
HYPOTHESES: dict[str, tuple[str, str]] = {
    "H-001": ("breakout", "Opening range breakout"),
    "H-002": ("bands", "VWAP mean reversion"),
    "H-003": ("trend", "EMA x VWAP cross"),
    "H-004": ("position", "Funding rate level"),
    "H-005": ("fade", "Liquidity sweep / stop-run fade"),
    "H-006": ("flow", "Crowd long/short ratio"),
    "H-007": ("xsec", "Cross-sectional ranking"),
    "H-008": ("fade", "Beta-residual reversion"),
    "H-009": ("bands", "VWAP breakout book"),
    "H-010": ("bands", "VWAP band rejection scalper"),
    "H-011": ("fade", "Prior day/week high-low reversal"),
    "H-012": ("portfolio", "Widening the book with more legs"),
    "H-013": ("position", "Perpetual premium"),
    "H-015": ("xsec", "Systemic crowd positioning"),
    "H-016": ("trend", "Moving-average ribbon"),
    "H-017": ("bands", "VWAP on crypto"),
    "H-018": ("portfolio", "Volatility-managed sizing"),
    "H-019": ("flow", "Common flow factor"),
    "H-020": ("xsec", "Relative volume / stocks in play"),
    "H-021": ("flow", "Quarter-hour clock effect"),
    "H-022": ("flow", "Absorption"),
    "H-023": ("exec", "Maker execution / queue priority"),
    "H-024": ("flow", "Book depth imbalance"),
    "H-025": ("ivol", "DVOL implied volatility"),
    "H-026": ("structure", "Power of Three / AMD"),
    "H-027": ("bands", "VWAP band breakout"),
    "H-028": ("event", "Metals daily-reopen premium"),
    "H-029": ("fade", "Gold/silver relative value"),
    "H-030": ("position", "CFTC COT positioning"),
    "H-031": ("flow", "Liquidation-pressure fade"),
    "H-034": ("position", "Term structure of leverage"),
    "H-035": ("flow", "On-chain exchange netflow"),
    "H-036": ("position", "Funding settlement as an event"),
    "H-037": ("ivol", "Variance risk premium"),
    "H-038": ("structure", "Fair value gaps"),
    "H-039": ("exec", "Equity vs closed-balance drawdown"),
    "H-040": ("bands", "Band shape"),
    "H-041": ("exec", "Daily-loss guard overlay"),
    "H-042": ("flow", "Cross-sectional crowd ratio"),
    "H-043": ("ivol", "VIX term structure"),
    "H-044": ("bands", "Anchor family"),
    "H-045": ("ivol", "GVZ gold volatility"),
    "H-046": ("flow", "Gold footprint"),
    "H-047": ("event", "Buy the Binance listing"),
    "H-049": ("macro", "Three macro feeds"),
    "H-050": ("portfolio", "Shipped rule on five markets"),
    "H-051": ("fade", "Gold/silver ratio convergence"),
    "H-052": ("flow", "Gold net buying pressure"),
}

#: Live loop candidates carry a FEED-<name> id instead of an H-number.
FEED_FAMILY: dict[str, tuple[str, str]] = {
    "DFII10": ("macro", "US 10y real yield"),
    "DTWEXBGS": ("macro", "Broad dollar index"),
    "T10YIE": ("macro", "10y inflation breakeven"),
    "REAL_MINUS_BE": ("macro", "Real yield minus breakeven"),
    "GVZ": ("ivol", "Gold volatility index"),
    "VIX": ("ivol", "Equity volatility index"),
    "VIX3M": ("ivol", "3-month volatility index"),
    "VIX_TERM": ("ivol", "Volatility term structure"),
}


def classify(hypothesis: str) -> tuple[str, str]:
    """(family key, human name) for any ledger row's hypothesis id."""
    h = (hypothesis or "").strip()
    if h.startswith("FEED-"):
        feed = h[5:]
        if feed in FEED_FAMILY:
            return FEED_FAMILY[feed]
        return ("other", feed.replace("_", " ").title())
    if h in HYPOTHESES:
        return HYPOTHESES[h]
    return ("other", h or "unknown")


def coverage() -> dict:
    """How much of the map is filled in. Printed so gaps are visible."""
    used = {k for k, _ in HYPOTHESES.values()} | {k for k, _ in FEED_FAMILY.values()}
    return {"families": len(FAMILIES),
            "mapped_hypotheses": len(HYPOTHESES),
            "mapped_feeds": len(FEED_FAMILY),
            "empty_families": sorted(f.key for f in FAMILIES
                                     if f.key not in used and f.key != "other")}


if __name__ == "__main__":
    c = coverage()
    print(f"{c['families']} families, {c['mapped_hypotheses']} hypotheses, "
          f"{c['mapped_feeds']} feeds mapped")
    if c["empty_families"]:
        print("nothing ever tried in:", ", ".join(c["empty_families"]))
    for f in FAMILIES:
        names = [n for k, n in HYPOTHESES.values() if k == f.key]
        print(f"\n{f.name} ({f.kind}) — {len(names)}")
        for n in names:
            print(f"    {n}")
