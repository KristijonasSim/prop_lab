"""V1 of the opening-range breakout hypothesis.

Range = the first candle of the London or New York session. After that candle
closes, mark its high/low and trade the first close outside the range. The
management is intentionally plain: fixed fractional risk, stop on the far side
of the opening range, move the stop to breakeven after +1R, target +2R, and a
same-session time stop.
"""
from __future__ import annotations

import math

from proplab.core.context import Context
from proplab.data.timeframes import parse_timeframe
from proplab.strategy.base import Strategy


class SessionOpenRangeBreakout(Strategy):
    name = "orb_v1_session_open"
    hypothesis = (
        "BTC opening-range breakout: the first candle after the London or New "
        "York session open defines an early liquidity range; a later break of "
        "that range can start a directional intraday move."
    )
    mechanism = (
        "London and New York opens concentrate discretionary flow, systematic "
        "rebalancing, stop orders and liquidity-seeking execution. The first "
        "session candle often maps the initial auction between buyers and "
        "sellers. A clean break after that range forms can trigger stops and "
        "momentum participation, creating short-horizon continuation. The edge "
        "is not assumed to be large, so the strategy uses fixed risk, quick "
        "breakeven protection and a same-session time stop."
    )
    variation = (
        "V1 - London/New York 08:00 local opening candle, first close outside "
        "the range, stop on the opposite side, +1R breakeven, +2R target, "
        "maximum 8h hold."
    )
    references = [
        "Common discretionary ORB practice: mark first session candle high/low",
        "Crypto trades 24/7, so session opens are treated as liquidity events "
        "rather than exchange opens",
    ]

    higher_timeframes = ()

    params = {
        "sessions": [
            {"name": "london", "tz": "Europe/London", "hour": 8, "minute": 0},
            {"name": "new_york", "tz": "America/New_York", "hour": 8, "minute": 0},
        ],
        "entry_window_hours": 3.0,
        "max_hold_hours": 8.0,
        "risk_pct": 0.005,
        "target_r": 2.0,
        "breakeven_trigger_r": 1.0,
        "stop_buffer_bps": 2.0,
        "min_range_pct": 0.0005,
        "max_range_pct": 0.015,
        "allow_shorts": True,
    }

    def on_start(self, ctx: Context) -> None:
        bar_hours = parse_timeframe(ctx.timeframe).total_seconds() / 3600
        ctx.state["orb_bar_hours"] = bar_hours
        ctx.state["orb_entry_window_bars"] = max(
            1, int(math.ceil(ctx.params["entry_window_hours"] / bar_hours))
        )
        ctx.state["orb_max_hold_bars"] = max(
            1, int(math.ceil(ctx.params["max_hold_hours"] / bar_hours))
        )
        ctx.state["orb_ranges"] = {}

    def on_bar(self, ctx: Context) -> None:
        self._record_opening_range(ctx)
        self._manage_open_position(ctx)
        if ctx.position is not None:
            return
        self._enter_breakout(ctx)

    def _record_opening_range(self, ctx: Context) -> None:
        p = ctx.params
        bar = ctx.bar
        ranges = ctx.state["orb_ranges"]

        for session in p["sessions"]:
            local_open = ctx.time.tz_convert(session["tz"])
            if local_open.hour != session["hour"] or local_open.minute != session["minute"]:
                continue

            range_pct = (bar.high - bar.low) / bar.close if bar.close > 0 else 0.0
            key = f"{session['name']}:{local_open.date()}"
            ranges[key] = {
                "name": session["name"],
                "date": str(local_open.date()),
                "bar_i": ctx.i,
                "high": bar.high,
                "low": bar.low,
                "range_pct": range_pct,
                "traded": False,
                "valid": p["min_range_pct"] <= range_pct <= p["max_range_pct"],
            }

    def _manage_open_position(self, ctx: Context) -> None:
        pos = ctx.position
        if pos is None or pos.initial_risk <= 0 or pos.qty <= 0:
            return

        risk_per_unit = pos.initial_risk / pos.qty
        if risk_per_unit <= 0:
            return

        if pos.is_long:
            open_r = (ctx.close - pos.entry_price) / risk_per_unit
            if open_r >= ctx.params["breakeven_trigger_r"] and (pos.stop is None or pos.stop < pos.entry_price):
                ctx.move_stop(pos.entry_price)
        else:
            open_r = (pos.entry_price - ctx.close) / risk_per_unit
            if open_r >= ctx.params["breakeven_trigger_r"] and (pos.stop is None or pos.stop > pos.entry_price):
                ctx.move_stop(pos.entry_price)

    def _enter_breakout(self, ctx: Context) -> None:
        p = ctx.params
        buffer = p["stop_buffer_bps"] / 1e4
        entry_window = ctx.state["orb_entry_window_bars"]
        max_bars = ctx.state["orb_max_hold_bars"]

        candidates = sorted(
            ctx.state["orb_ranges"].items(),
            key=lambda item: item[1]["bar_i"],
            reverse=True,
        )
        for key, r in candidates:
            if r["traded"]:
                continue
            bars_after_range = ctx.i - r["bar_i"]
            if bars_after_range <= 0:
                continue
            if bars_after_range > entry_window:
                r["traded"] = True
                continue
            if not r["valid"]:
                continue

            if ctx.close > r["high"]:
                stop = r["low"] * (1 - buffer)
                risk = ctx.close - stop
                if risk <= 0:
                    return
                r["traded"] = True
                ctx.buy(
                    stop=stop,
                    target=ctx.close + p["target_r"] * risk,
                    risk_pct=p["risk_pct"],
                    max_bars=max_bars,
                    tag=f"orb_{r['name']}_long",
                    reason=f"{r['name']} opening range break up",
                )
                return

            if p["allow_shorts"] and ctx.close < r["low"]:
                stop = r["high"] * (1 + buffer)
                risk = stop - ctx.close
                if risk <= 0:
                    return
                r["traded"] = True
                ctx.sell(
                    stop=stop,
                    target=ctx.close - p["target_r"] * risk,
                    risk_pct=p["risk_pct"],
                    max_bars=max_bars,
                    tag=f"orb_{r['name']}_short",
                    reason=f"{r['name']} opening range break down",
                )
                return
