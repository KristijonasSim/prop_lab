"""INFRASTRUCTURE TEST ONLY - not a trading hypothesis, not to be evaluated.

Deterministic, mechanical rules whose fills can be verified by hand. Exists
so the engine, metrics, prop-rule checker, DB and dashboard can be tested
end-to-end without pretending anything about markets.
"""
from __future__ import annotations

from proplab.core.context import Context
from proplab.strategy.base import Strategy


class InfraSmoke(Strategy):
    name = "_infra_smoke"
    hypothesis = "NONE - infrastructure smoke test."
    mechanism = "NONE. Enters on a fixed bar cadence to exercise the engine."
    variation = "every_n_bars"
    params = {"every_n": 50, "risk_pct": 0.004, "stop_pct": 0.01,
              "target_pct": 0.02, "max_bars": 20}

    def on_bar(self, ctx: Context) -> None:
        p = ctx.params
        if ctx.position is not None:
            return
        if ctx.i % p["every_n"] != 0:
            return
        px = ctx.close
        ctx.buy(
            stop=px * (1 - p["stop_pct"]),
            target=px * (1 + p["target_pct"]),
            risk_pct=p["risk_pct"],
            max_bars=p["max_bars"],
            tag="smoke",
            reason="cadence",
        )
