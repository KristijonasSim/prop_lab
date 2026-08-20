"""V2 of the trend-following swing hypothesis: daily filter, 4h entry.

Same idea as V1, but the trend is defined on the daily chart while the entry is
timed on 4h. The point is stop distance: a daily-only entry needs a wide stop,
so 0.5% risk buys very little position. Timing on 4h allows a much tighter
stop, which should mean a better reward-to-risk ratio and a shallower equity
curve - the thing our trailing-drawdown rule actually punishes.
"""
from __future__ import annotations

from proplab.core.context import Context
from proplab.strategy.base import Strategy
from proplab.strategy.indicators import atr, donchian_high, donchian_low, sma


class DailyTrendFourHourEntry(Strategy):
    name = "ts_v2_mtf_1d_4h"
    hypothesis = (
        "Trend following swing trading: ride established multi-day directional "
        "moves in BTC rather than fading them."
    )
    mechanism = (
        "Same persistence mechanism as V1 - slow information diffusion, flows "
        "worked over days, liquidation cascades extending moves. The refinement "
        "is that direction and timing are different questions: the daily chart "
        "says which way the flow is running, while a 4h breakout says it is "
        "resuming right now. Entering on the smaller timeframe puts the stop "
        "just under recent 4h structure instead of two daily ATRs away, so the "
        "same risk budget buys a larger position on a tighter invalidation."
    )
    variation = (
        "V2 - daily MA200 regime filter, entry on a 4h channel breakout in the "
        "direction of that filter, stop under the recent 4h swing, exit when "
        "the daily filter flips or the 4h channel breaks against us."
    )
    references = [
        "Moskowitz, Ooi & Pedersen, Time Series Momentum (2012)",
        "Managed-futures practice: regime filter on the slow timeframe, "
        "execution on the fast one",
    ]

    higher_timeframes = ("1d",)

    params = {
        "daily_ma": 200,        # daily regime filter length
        "entry_lookback": 10,   # 4h breakout lookback
        "exit_lookback": 6,     # 4h opposite-channel exit
        "atr_window": 14,       # on 4h bars
        "atr_mult": 1.5,        # stop distance floor
        "risk_pct": 0.005,
        "allow_shorts": True,
    }

    def on_bar(self, ctx: Context) -> None:
        p = ctx.params
        daily = ctx.tf("1d")

        # The daily filter must be fully formed. `daily.series` only ever
        # returns bars that have CLOSED as of this 4h bar, so a partially
        # formed day can never leak in.
        if daily.n_closed < p["daily_ma"] + 1:
            return
        need = max(p["entry_lookback"], p["exit_lookback"], p["atr_window"]) + 2
        if ctx.bars_seen < need:
            return

        daily_closes = daily.series("close")
        ma = sma(daily_closes, p["daily_ma"])
        if ma != ma:
            return
        daily_close = daily.last("close")
        uptrend = daily_close > ma
        downtrend = daily_close < ma

        highs = ctx.series("high")
        lows = ctx.series("low")
        closes = ctx.series("close")
        close = ctx.close
        a = atr(highs, lows, closes, p["atr_window"])
        if not a > 0:
            return

        # ---- manage an open position --------------------------------------
        if ctx.position is not None:
            if ctx.position.is_long:
                if downtrend:
                    ctx.close_position("daily_filter_flipped")
                elif close < donchian_low(lows, p["exit_lookback"]):
                    ctx.close_position("4h_channel_exit")
            else:
                if uptrend:
                    ctx.close_position("daily_filter_flipped")
                elif close > donchian_high(highs, p["exit_lookback"]):
                    ctx.close_position("4h_channel_exit")
            return

        # ---- entry: 4h breakout, but only with the daily trend -------------
        hi = donchian_high(highs, p["entry_lookback"])
        lo = donchian_low(lows, p["entry_lookback"])
        if hi != hi or lo != lo:
            return

        if uptrend and close > hi:
            swing_low = donchian_low(lows, p["entry_lookback"])
            stop = min(swing_low, close - p["atr_mult"] * a)
            ctx.buy(
                stop=stop, risk_pct=p["risk_pct"], tag="mtf_long",
                reason=(f"daily {daily_close:.0f} > MA{p['daily_ma']} {ma:.0f}; "
                        f"4h close {close:.0f} > {p['entry_lookback']}-bar high {hi:.0f}"),
            )
        elif p["allow_shorts"] and downtrend and close < lo:
            swing_high = donchian_high(highs, p["entry_lookback"])
            stop = max(swing_high, close + p["atr_mult"] * a)
            ctx.sell(
                stop=stop, risk_pct=p["risk_pct"], tag="mtf_short",
                reason=(f"daily {daily_close:.0f} < MA{p['daily_ma']} {ma:.0f}; "
                        f"4h close {close:.0f} < {p['entry_lookback']}-bar low {lo:.0f}"),
            )
