"""COPY THIS FILE into proplab/strategy/library/<slug>.py for each variation.

Not auto-discovered (it lives outside library/), so it can sit here as a
reference without polluting the registry.
"""
from __future__ import annotations

import numpy as np

from proplab.core.context import Context
from proplab.strategy.base import Strategy


class TemplateStrategy(Strategy):
    # ---- identity: all of this is written into the tracking database -------
    name = "hypothesis_slug_v1"
    hypothesis = "The one-line idea exactly as it was handed to me."
    mechanism = (
        "WHY this should produce an edge: who is on the other side, what "
        "constraint or behaviour creates the mispricing, and why it is not "
        "already arbitraged away. If this paragraph is weak, the backtest "
        "does not matter."
    )
    variation = "What makes this version different from the sibling variations."
    references = []

    higher_timeframes = ()          # e.g. ("4h",) if the logic reads a 4h trend

    # ---- every tunable number gets a name, so it can be logged and swept ---
    params = {
        "lookback": 20,
        "risk_pct": 0.005,          # 0.5% of equity risked per trade
        "stop_atr_mult": 1.5,
        "target_r": 2.0,
        "max_bars": 96,
    }

    # ---- optional one-time setup -------------------------------------------
    def on_start(self, ctx: Context) -> None:
        ctx.state["trades_today"] = 0

    # ---- the only method that matters --------------------------------------
    def on_bar(self, ctx: Context) -> None:
        p = ctx.params
        n = p["lookback"]

        # Not enough history yet -> do nothing. (ctx.series is always sliced at
        # the current bar, so this can never peek forward.)
        if ctx.bars_seen < n + 2:
            return

        highs = ctx.series("high", n)
        lows = ctx.series("low", n)
        closes = ctx.series("close", n + 1)
        atr = float(np.mean(highs - lows))     # crude ATR stand-in
        if atr <= 0:
            return

        # ---- management of an OPEN position --------------------------------
        if ctx.position is not None:
            # e.g. trail the stop, or exit on a condition:
            # ctx.move_stop(ctx.close - 1.0 * atr)
            # ctx.close_position("signal_gone")
            return

        # ---- ENTRY rules ----------------------------------------------------
        prior_high = float(np.max(highs[:-1]))
        breakout = ctx.close > prior_high

        if breakout:
            stop = ctx.close - p["stop_atr_mult"] * atr
            risk = ctx.close - stop
            ctx.buy(
                stop=stop,
                target=ctx.close + p["target_r"] * risk,
                risk_pct=p["risk_pct"],          # fixed fractional: never martingale
                max_bars=p["max_bars"],
                tag="breakout_long",
                reason=f"close {ctx.close:.2f} > {n}-bar high {prior_high:.2f}",
            )
