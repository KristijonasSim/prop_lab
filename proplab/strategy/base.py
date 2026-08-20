"""The fixed strategy template.

A strategy file may ONLY define entry rules, exit rules and position sizing.
It never touches P&L math, fees, slippage or the prop-rule checker - those
live in proplab/core/ and are owned by the account holder.

Contract
--------
    class MyStrategy(Strategy):
        name        = "orb_v1"           # unique slug, matches the DB row
        hypothesis  = "..."              # the idea this came from
        mechanism   = "..."              # WHY this should work, in one paragraph
        higher_timeframes = ("4h",)      # extra timeframes the logic reads
        params      = {...}              # every tunable number, named

        def on_start(self, ctx): ...     # optional: precompute, init state
        def on_bar(self, ctx): ...       # called after each primary bar closes

Inside `on_bar` you may only:
    read   ctx.bar / ctx.close / ctx.series(...) / ctx.value(...) / ctx.frame(...)
           ctx.tf("4h").last(...) / .series(...) / .bar(...)
           ctx.position, ctx.equity, ctx.now, ctx.state, ctx.params
    act    ctx.buy(...) / ctx.sell(...) / ctx.close_position(...) / ctx.move_stop(...)

Every accessor is sliced at the current bar, so future data is unreachable.
Orders placed on bar i fill at the OPEN of bar i+1.

Sizing must be explicit on every entry - either
    risk_pct=0.005 with a stop   (risk 0.5% of equity to the stop; preferred)
or  notional_pct=0.25           (position notional = 25% of equity)
Sizing must not increase after losses: the prop checker flags martingale.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from ..core.context import Context


class Strategy(ABC):
    # --- identity / documentation (all of this lands in the database) ---
    name: str = "unnamed"
    hypothesis: str = ""          # the idea as given, verbatim-ish
    mechanism: str = ""           # why it should work; not "it backtested well"
    variation: str = ""           # what makes THIS version different
    references: list[str] = []    # where the rules came from

    # --- data requirements ---
    higher_timeframes: tuple[str, ...] = ()

    # --- tunables ---
    params: dict[str, Any] = {}

    def __init__(self, **overrides):
        merged = dict(self.params)
        unknown = set(overrides) - set(merged)
        if unknown:
            raise ValueError(
                f"{self.name}: unknown params {sorted(unknown)}. "
                f"Declare every tunable in `params` so it gets logged."
            )
        merged.update(overrides)
        self.params = merged

    def on_start(self, ctx: Context) -> None:
        """Optional one-time setup. ctx has no bar data yet - init state only."""

    @abstractmethod
    def on_bar(self, ctx: Context) -> None:
        """Called once per closed primary bar. Place at most one intent."""

    # --- metadata for the tracking DB ---
    def describe(self) -> dict:
        return {
            "name": self.name,
            "class": type(self).__name__,
            "module": type(self).__module__,
            "hypothesis": self.hypothesis,
            "mechanism": self.mechanism,
            "variation": self.variation,
            "references": list(self.references),
            "higher_timeframes": list(self.higher_timeframes),
            "params": dict(self.params),
        }
