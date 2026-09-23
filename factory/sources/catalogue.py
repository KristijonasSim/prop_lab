"""WHERE IDEAS COME FROM — the list, and what state each source is in.

Kris, 2026-09-23: *"i said we will start from tradingview... then i would want
to choose other source for example quantpedia and see what we found and did
there."*

THE SOURCE IS THE UNIT OF WORK. Before this file the pipeline had a `source`
string on each idea and nothing that said what the sources ARE, so the page
could show "invent 48 waiting" but could not answer "how many did TradingView
give us, how many passed, how many died and where". One row per source here,
and everything on the dashboard hangs off it.

STATUS MEANS WHAT IS TRUE TODAY, not what is planned. A source is `ready` only
when running it needs nothing from Kris. Anything else says exactly what it is
waiting for, because a dashboard that shows a source with 0 ideas and no reason
looks like a source that found nothing.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Source:
    key: str            # what `Strategy.source` carries
    label: str          # what the page shows
    how: str            # one line: how ideas arrive
    status: str         # ready | needs-input | blocked
    note: str           # what it is waiting for, when it is not ready
    order: int          # the order Kris set them in


#: The order is Kris's, set 2026-09-21 and reaffirmed 2026-09-23:
#: TradingView first, then the bot's own ideas, then anything he injects.
CATALOGUE: tuple[Source, ...] = (
    Source("tradingview", "TradingView", "Pine scripts read from data/pine/",
           "needs-input",
           "Drop .pine files in data/pine/ and they are read on the next pass. "
           "Bulk downloading is a terms-of-service question and is not built.",
           0),
    Source("quantpedia", "Quantpedia", "published strategy write-ups",
           "blocked",
           "No reader built yet. Their library is paid and the terms have not "
           "been checked.",
           1),
    Source("agent", "AI agent", "a model proposes rules with a mechanism",
           "ready",
           "python -m factory.sources.agent -n 20", 2),
    Source("invent", "Enumerator", "walks the grammar, 308 combinations",
           "ready",
           "The floor under the queue. It exists so the line never stops, not "
           "because its ideas are good.", 3),
    Source("kris", "Kris", "injected by hand, any time", "ready",
           "Nothing to set up - add a Strategy and queue it.", 4),
)

BY_KEY = {s.key: s for s in CATALOGUE}
#: The drain order `queue.take` uses. Derived, so the two cannot disagree.
ORDER = tuple(s.key for s in sorted(CATALOGUE, key=lambda s: s.order))


def get(key: str) -> Source:
    """A source row, inventing a placeholder for anything unlisted.

    An unknown source must still appear on the page. A silently dropped one is
    how the agent's first batch went untested for a day - see
    `queue.SOURCE_ORDER`.
    """
    return BY_KEY.get(key) or Source(key, key, "unregistered", "ready",
                                     "Not in the catalogue.", 99)
