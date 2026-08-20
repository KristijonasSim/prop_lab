"""V3 of the ORB hypothesis: London AND New York, mirroring the Pine indicator.

Matches crosscheck/orb_v2_ny_rvol_indicator.pine rule for rule, so results from
this engine and from trading the indicator by hand are comparable:

  London   range 08:00-08:30 London, trade 08:30-10:30 London
  New York range 09:30-10:00 NY,     trade 10:00-12:00 NY
  filter   weekly relative volume > 1
  entry    first close outside the range, one signal per session per day
  exit     flatten at 15:50-15:55 New York - there is no stop and no target

The missing stop is inherited from the supplied Pine reference and is a real
weakness, not an oversight: with no stop the risk per trade is undefined, so
avg R cannot be computed and nothing caps a bad session.
"""
from __future__ import annotations

from collections import defaultdict, deque
from statistics import mean

from proplab.core.context import Context
from proplab.strategy.base import Strategy


class LondonAndNyOrb(Strategy):
    name = "orb_v3_london_ny"
    hypothesis = (
        "BTC opening-range breakout on both liquidity sessions: the London and "
        "New York opens each define a reference range, and a break of either "
        "can start a short intraday move."
    )
    mechanism = (
        "Both opens concentrate flow - London brings European desks and the "
        "start of the overlap, New York brings US macro, ETF and risk-asset "
        "flow. BTC trades as a high-beta liquidity asset into both. A break of "
        "the range that formed during the open, confirmed by above-normal "
        "relative volume, may capture continuation while that flow persists."
    )
    variation = (
        "V3 - London 08:00-08:30 range trading to 10:30 London, plus NY "
        "09:30-10:00 range trading to 12:00 NY, RVOL > 1, flat by 15:55 NY. "
        "No stop and no target, matching the Pine reference."
    )
    references = ["crosscheck/orb_v2_ny_rvol_indicator.pine"]

    higher_timeframes = ()

    params = {
        "london_tz": "Europe/London",
        "london_open": ("08:00", "08:30"),
        "london_trade": ("08:30", "10:30"),
        "ny_tz": "America/New_York",
        "ny_open": ("09:30", "10:00"),
        "ny_trade": ("10:00", "12:00"),
        "flat_tz": "America/New_York",
        "flat_window": ("15:50", "15:55"),
        "rvol_length": 3,
        "rvol_threshold": 1.0,
        "notional_pct": 0.1,
        "allow_shorts": True,
        "trade_london": True,
        "trade_ny": True,
    }

    def on_start(self, ctx: Context) -> None:
        ctx.state["sessions"] = {
            "london": {"tz": ctx.params["london_tz"], "open": ctx.params["london_open"],
                       "trade": ctx.params["london_trade"], "hi": None, "lo": None,
                       "side": None, "date": None},
            "ny": {"tz": ctx.params["ny_tz"], "open": ctx.params["ny_open"],
                   "trade": ctx.params["ny_trade"], "hi": None, "lo": None,
                   "side": None, "date": None},
        }
        ctx.state["rvol_week"] = None
        ctx.state["rvol_offset"] = -1
        ctx.state["rvol_cum"] = 0.0
        ctx.state["rvol_week_cums"] = {}
        ctx.state["rvol_history"] = defaultdict(
            lambda: deque(maxlen=ctx.params["rvol_length"]))

    def on_bar(self, ctx: Context) -> None:
        rvol = self._update_rvol(ctx)
        for s in ctx.state["sessions"].values():
            self._roll_day(ctx, s)
            self._record_range(ctx, s)

        if self._in_window(ctx, ctx.params["flat_tz"], *ctx.params["flat_window"]):
            for s in ctx.state["sessions"].values():
                s["side"] = None
            if ctx.position is not None:
                ctx.close_position("end_session")
            return

        if ctx.position is not None:
            return
        if rvol != rvol or rvol <= ctx.params["rvol_threshold"]:
            return

        enabled = []
        if ctx.params["trade_london"]:
            enabled.append(("london", ctx.state["sessions"]["london"]))
        if ctx.params["trade_ny"]:
            enabled.append(("ny", ctx.state["sessions"]["ny"]))

        for name, s in enabled:
            if s["hi"] is None or s["lo"] is None or s["side"] is not None:
                continue
            if not self._in_window(ctx, s["tz"], *s["trade"]):
                continue
            if ctx.close > s["hi"]:
                s["side"] = "long"
                ctx.buy(notional_pct=ctx.params["notional_pct"],
                        tag=f"orb_{name}_long",
                        reason=f"{name} range break up, RVOL {rvol:.2f}")
                return
            if ctx.params["allow_shorts"] and ctx.close < s["lo"]:
                s["side"] = "short"
                ctx.sell(notional_pct=ctx.params["notional_pct"],
                         tag=f"orb_{name}_short",
                         reason=f"{name} range break down, RVOL {rvol:.2f}")
                return

    def _roll_day(self, ctx: Context, s: dict) -> None:
        d = ctx.time.tz_convert(s["tz"]).date()
        if s["date"] != d:
            s.update(date=d, hi=None, lo=None, side=None)

    def _record_range(self, ctx: Context, s: dict) -> None:
        if not self._in_window(ctx, s["tz"], *s["open"]):
            return
        bar = ctx.bar
        s["hi"] = bar.high if s["hi"] is None else max(s["hi"], bar.high)
        s["lo"] = bar.low if s["lo"] is None else min(s["lo"], bar.low)

    def _update_rvol(self, ctx: Context) -> float:
        week = ctx.time.isocalendar()[:2]
        if ctx.state["rvol_week"] != week:
            for off, cum in (ctx.state.get("rvol_week_cums") or {}).items():
                ctx.state["rvol_history"][off].append(cum)
            ctx.state["rvol_week"] = week
            ctx.state["rvol_offset"] = 0
            ctx.state["rvol_cum"] = 0.0
            ctx.state["rvol_week_cums"] = {}
        else:
            ctx.state["rvol_offset"] += 1
        off = ctx.state["rvol_offset"]
        ctx.state["rvol_cum"] += ctx.bar.volume
        ctx.state["rvol_week_cums"][off] = ctx.state["rvol_cum"]
        past = list(ctx.state["rvol_history"][off])
        if not past:
            return float("nan")
        avg = mean(past)
        return ctx.state["rvol_cum"] / avg if avg > 0 else float("nan")

    def _in_window(self, ctx: Context, tz: str, start: str, end: str) -> bool:
        o = ctx.time.tz_convert(tz)
        c = ctx.now.tz_convert(tz)
        s = int(start[:2]) * 60 + int(start[3:])
        e = int(end[:2]) * 60 + int(end[3:])
        return (o.hour * 60 + o.minute) < e and (c.hour * 60 + c.minute) > s
