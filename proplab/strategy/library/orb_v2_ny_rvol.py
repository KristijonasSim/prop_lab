"""V2 of the ORB hypothesis: closer to the supplied TradingView script.

The Pine reference:
  - opening range: 09:30-10:00 New York time
  - trading window: 10:00-12:00 New York time
  - end-session flatten: 15:50-15:55 New York time
  - relative volume filter: current weekly-relative volume > 1
  - no explicit stop or target; entries are held until the end-session flatten

This implementation uses BTC's own OHLCV for the opening range. The Pine script
can reference SPY for the range (`asset_correlation = SPY`), but this project
currently only has the BTCUSDT Binance data feed, so a true SPY-correlated
version needs an equity data loader before it can be tested honestly.
"""
from __future__ import annotations

from collections import defaultdict, deque
from statistics import mean

from proplab.core.context import Context
from proplab.data.timeframes import parse_timeframe
from proplab.strategy.base import Strategy


class NyOpenRangeRvol(Strategy):
    name = "orb_v2_ny_rvol"
    hypothesis = (
        "BTC NY opening-range breakout: use the 09:30-10:00 New York range as "
        "the reference auction, then trade breakouts during 10:00-12:00 only "
        "when relative volume is above normal."
    )
    mechanism = (
        "The US equity open concentrates macro, ETF and risk-asset flow. BTC "
        "often trades as a high-beta liquidity asset during that window. A "
        "break above or below the opening range, confirmed by above-normal "
        "relative volume, may capture short intraday continuation. The supplied "
        "Pine script does not use stops or profit targets; it exits at the "
        "end-of-day window, so this version tests that behavior directly."
    )
    variation = (
        "V2 - NY 09:30-10:00 range, trade 10:00-12:00, weekly RVOL > 1, "
        "notional-sized entry, flatten near 15:50 NY. BTC self-reference "
        "instead of SPY until an equity data feed exists."
    )
    references = [
        "User-supplied Pine Script: Opening Range Breakout (ORB) Heikin Ashi "
        "SPY 5min Correlation Strategy",
    ]

    higher_timeframes = ()

    params = {
        "session_tz": "America/New_York",
        "open_start": "09:30",
        "open_end": "10:00",
        "trade_start": "10:00",
        "trade_end": "12:00",
        "flat_start": "15:50",
        "flat_end": "15:55",
        "rvol_length": 3,
        "rvol_threshold": 1.0,
        "notional_pct": 1.0,
        "allow_shorts": True,
    }

    def on_start(self, ctx: Context) -> None:
        ctx.state["orb_open_high"] = None
        ctx.state["orb_open_low"] = None
        ctx.state["orb_date"] = None
        ctx.state["orb_trade_side"] = None
        ctx.state["orb_flattened"] = False

        ctx.state["rvol_week"] = None
        ctx.state["rvol_offset"] = -1
        ctx.state["rvol_cum"] = 0.0
        ctx.state["rvol_week_cums"] = {}
        ctx.state["rvol_history"] = defaultdict(lambda: deque(maxlen=ctx.params["rvol_length"]))

        minutes = parse_timeframe(ctx.timeframe).total_seconds() / 60
        if 30 % minutes != 0:
            ctx.log(
                f"NY 09:30-10:00 ORB is not aligned on {ctx.timeframe}; "
                "prefer 5m or 15m."
            )

    def on_bar(self, ctx: Context) -> None:
        rvol = self._update_rvol(ctx)
        self._reset_daily_state_if_needed(ctx)
        self._record_opening_range(ctx)

        if self._in_window(ctx, "flat_start", "flat_end"):
            ctx.state["orb_trade_side"] = None
            ctx.state["orb_flattened"] = True
            if ctx.position is not None:
                ctx.close_position("end_session")
            return

        if ctx.position is not None:
            return

        if not self._in_window(ctx, "trade_start", "trade_end"):
            return
        if rvol != rvol or rvol <= ctx.params["rvol_threshold"]:
            return

        hi = ctx.state.get("orb_open_high")
        lo = ctx.state.get("orb_open_low")
        if hi is None or lo is None:
            return

        # Mirrors the Pine flags: once a long or short has triggered, do not
        # allow the opposite direction until the end-session reset.
        trade_side = ctx.state.get("orb_trade_side")
        if ctx.close > hi and trade_side != "short":
            ctx.state["orb_trade_side"] = "long"
            ctx.buy(
                notional_pct=ctx.params["notional_pct"],
                tag="orb_ny_rvol_long",
                reason=f"BTC close > NY ORB high and RVOL {rvol:.2f}",
            )
        elif ctx.params["allow_shorts"] and ctx.close < lo and trade_side != "long":
            ctx.state["orb_trade_side"] = "short"
            ctx.sell(
                notional_pct=ctx.params["notional_pct"],
                tag="orb_ny_rvol_short",
                reason=f"BTC close < NY ORB low and RVOL {rvol:.2f}",
            )

    def _reset_daily_state_if_needed(self, ctx: Context) -> None:
        local_date = ctx.time.tz_convert(ctx.params["session_tz"]).date()
        if ctx.state["orb_date"] == local_date:
            return
        ctx.state["orb_date"] = local_date
        ctx.state["orb_open_high"] = None
        ctx.state["orb_open_low"] = None
        ctx.state["orb_trade_side"] = None
        ctx.state["orb_flattened"] = False

    def _record_opening_range(self, ctx: Context) -> None:
        if not self._in_window(ctx, "open_start", "open_end"):
            return
        bar = ctx.bar
        hi = ctx.state.get("orb_open_high")
        lo = ctx.state.get("orb_open_low")
        ctx.state["orb_open_high"] = bar.high if hi is None else max(hi, bar.high)
        ctx.state["orb_open_low"] = bar.low if lo is None else min(lo, bar.low)

    def _update_rvol(self, ctx: Context) -> float:
        """Approximate TradingView ta.relativeVolume(length, "W", true).

        Uses cumulative volume since the start of the UTC week and compares the
        current bar offset's cumulative volume with the same offset in the last
        `rvol_length` completed weeks. This is deterministic and lookahead-safe.
        """
        ts = ctx.time
        week = ts.isocalendar()[:2]
        if ctx.state["rvol_week"] != week:
            prior = ctx.state.get("rvol_week_cums") or {}
            hist = ctx.state["rvol_history"]
            for offset, cum in prior.items():
                hist[offset].append(cum)
            ctx.state["rvol_week"] = week
            ctx.state["rvol_offset"] = 0
            ctx.state["rvol_cum"] = 0.0
            ctx.state["rvol_week_cums"] = {}
        else:
            ctx.state["rvol_offset"] += 1

        offset = ctx.state["rvol_offset"]
        ctx.state["rvol_cum"] += ctx.bar.volume
        ctx.state["rvol_week_cums"][offset] = ctx.state["rvol_cum"]

        past = list(ctx.state["rvol_history"][offset])
        if not past:
            return float("nan")
        avg = mean(past)
        return ctx.state["rvol_cum"] / avg if avg > 0 else float("nan")

    def _in_window(self, ctx: Context, start_key: str, end_key: str) -> bool:
        local_open = ctx.time.tz_convert(ctx.params["session_tz"])
        local_close = ctx.now.tz_convert(ctx.params["session_tz"])
        start = self._minute_of_day(ctx.params[start_key])
        end = self._minute_of_day(ctx.params[end_key])
        open_min = local_open.hour * 60 + local_open.minute
        close_min = local_close.hour * 60 + local_close.minute
        return open_min < end and close_min > start

    @staticmethod
    def _minute_of_day(hhmm: str) -> int:
        hour, minute = hhmm.split(":")
        return int(hour) * 60 + int(minute)
