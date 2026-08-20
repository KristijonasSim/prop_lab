"""V1 of the trend-following swing hypothesis: Donchian channel breakout.

The canonical published version of the idea (Turtle system, 1983), kept
deliberately plain so it can serve as the baseline every other variation is
measured against.
"""
from __future__ import annotations

from proplab.core.context import Context
from proplab.strategy.base import Strategy
from proplab.strategy.indicators import atr, donchian_high, donchian_low


class DonchianBreakout(Strategy):
    name = "ts_v1_donchian"
    hypothesis = (
        "Trend following swing trading: ride established multi-day directional "
        "moves in BTC rather than fading them."
    )
    mechanism = (
        "Trends persist because information diffuses slowly and large flows are "
        "worked over days or weeks, so the buying pressure that moved price "
        "yesterday is often still present today. In crypto, perp liquidations "
        "add a mechanical push in the direction of the move. A new N-day high is "
        "the simplest evidence that such a flow is underway. The edge survives "
        "publication because capturing it requires accepting a low win rate and "
        "long flat periods."
    )
    variation = (
        "V1 - plain Donchian breakout on daily bars. Entry on an N-day high, "
        "exit on an M-day low, with an ATR disaster stop. The honest baseline: "
        "if this has no edge in-sample, the fancier variants are fitting noise."
    )
    references = [
        "Turtle Trading system (Dennis & Eckhardt, 1983)",
        "Moskowitz, Ooi & Pedersen, Time Series Momentum (2012)",
    ]

    higher_timeframes = ()

    params = {
        "n_entry": 20,        # breakout lookback (prior N bars)
        "n_exit": 10,         # opposite-channel exit lookback
        "atr_window": 20,
        "atr_mult": 2.0,      # disaster stop distance
        "risk_pct": 0.005,    # 0.5% of equity risked to the stop
        "allow_shorts": True,
    }

    def on_bar(self, ctx: Context) -> None:
        p = ctx.params
        need = max(p["n_entry"], p["n_exit"], p["atr_window"]) + 2
        if ctx.bars_seen < need:
            return

        highs = ctx.series("high")
        lows = ctx.series("low")
        closes = ctx.series("close")
        close = ctx.close

        a = atr(highs, lows, closes, p["atr_window"])
        if not a > 0:
            return

        # ---- manage an open position: channel exit ------------------------
        if ctx.position is not None:
            if ctx.position.is_long:
                if close < donchian_low(lows, p["n_exit"]):
                    ctx.close_position("channel_exit")
            else:
                if close > donchian_high(highs, p["n_exit"]):
                    ctx.close_position("channel_exit")
            return

        # ---- entry: a new N-bar extreme ------------------------------------
        hi = donchian_high(highs, p["n_entry"])
        lo = donchian_low(lows, p["n_entry"])
        if hi != hi or lo != lo:          # nan guard
            return

        if close > hi:
            ctx.buy(
                stop=close - p["atr_mult"] * a,
                risk_pct=p["risk_pct"],
                tag="donchian_long",
                reason=f"close {close:.0f} > {p['n_entry']}-bar high {hi:.0f}",
            )
        elif p["allow_shorts"] and close < lo:
            ctx.sell(
                stop=close + p["atr_mult"] * a,
                risk_pct=p["risk_pct"],
                tag="donchian_short",
                reason=f"close {close:.0f} < {p['n_entry']}-bar low {lo:.0f}",
            )
