"""V4: the ORB rules Kris actually trades, mechanised.

Taken from a 9-trade replay log (2026-08-13..08-20) where hand-trading made
+1,693 against the mechanical version's -1,210 on the same window and size.
Four differences showed up in the diff, three of them rules:

  1. A STOP. Four of nine exits were stop losses; v3 has no stop at all.
  2. FAST EXITS. Average hold 2.6h against v3 holding to the session close.
  3. A FIRST-CANDLE FILTER. "If the candle when the session opens is big
     compared to others, it can move; if it is small, there is not much
     chance" - so a small opening candle skips the session entirely.

The fourth difference was three trades taken outside both session windows,
including a Sunday. That is not encoded here: it was described as a mistake
rather than a rule, and two of those three lost.

Sizing is risk-based rather than notional, which the stop now makes possible -
so risk per trade is defined and R multiples exist, unlike v2 and v3.
"""
from __future__ import annotations

from statistics import mean

from proplab.core.context import Context
from proplab.strategy.base import Strategy


class KrisOrbRules(Strategy):
    name = "orb_v4_kris_rules"
    hypothesis = (
        "BTC opening-range breakout: the London and New York opens define a "
        "reference range, and a break of that range can start a short "
        "intraday move."
    )
    mechanism = (
        "Same session-flow mechanism as v2 and v3, plus a conviction filter. A "
        "large opening candle means the auction at the open was active - real "
        "disagreement and real volume - which is what makes a subsequent break "
        "likely to continue. A small opening candle means nobody is committed, "
        "so a break of that narrow range is noise. The stop and the short hold "
        "exist because the flow that drives these moves fades within hours; "
        "holding to the session close gives back what it made."
    )
    variation = (
        "V4 - v3's London and NY ranges, but only when the first candle of the "
        "range is at least `min_candle_ratio` times the recent average candle, "
        "with a stop on the far side of the range, an R-multiple target, a "
        "hold capped near 3h, and weekends skipped."
    )
    references = [
        "crosscheck/manual_kris_20260820.csv - the replay log this came from",
    ]

    higher_timeframes = ()

    params = {
        "london_tz": "Europe/London",
        "london_open": ("08:00", "08:30"),
        "london_trade": ("08:30", "10:30"),
        "ny_tz": "America/New_York",
        "ny_open": ("09:30", "10:00"),
        "ny_trade": ("10:00", "12:00"),
        # --- Kris's rules ---
        "min_candle_ratio": 1.3,   # first range candle vs recent average size
        "candle_lookback": 20,     # what "recent average" means
        "max_hold_bars": 12,       # 3h on 15m; his average was 2.6h
        "target_r": 2.0,
        "stop_buffer_bps": 2.0,
        "risk_pct": 0.005,
        "skip_weekends": True,
        "allow_shorts": True,
        "trade_london": True,
        "trade_ny": True,
    }

    def on_start(self, ctx: Context) -> None:
        ctx.state["sessions"] = {
            "london": {"tz": ctx.params["london_tz"], "open": ctx.params["london_open"],
                       "trade": ctx.params["london_trade"]},
            "ny": {"tz": ctx.params["ny_tz"], "open": ctx.params["ny_open"],
                   "trade": ctx.params["ny_trade"]},
        }
        for s in ctx.state["sessions"].values():
            s.update(hi=None, lo=None, side=None, date=None, ratio=None, seen=False)

    def on_bar(self, ctx: Context) -> None:
        p = ctx.params
        for s in ctx.state["sessions"].values():
            self._roll_day(ctx, s)
            self._record_range(ctx, s)

        if ctx.position is not None:
            return
        if p["skip_weekends"] and ctx.now.weekday() >= 5:
            return

        order = []
        if p["trade_london"]:
            order.append(("london", ctx.state["sessions"]["london"]))
        if p["trade_ny"]:
            order.append(("ny", ctx.state["sessions"]["ny"]))

        for name, s in order:
            if s["hi"] is None or s["lo"] is None or s["side"] is not None:
                continue
            if not self._in_window(ctx, s["tz"], *s["trade"]):
                continue
            # the conviction filter: a quiet open means no trade at all
            if s["ratio"] is None or s["ratio"] < p["min_candle_ratio"]:
                continue

            buf = p["stop_buffer_bps"] / 1e4
            close = ctx.close
            if close > s["hi"]:
                stop = s["lo"] * (1 - buf)
                risk = close - stop
                if risk <= 0:
                    continue
                s["side"] = "long"
                ctx.buy(stop=stop, target=close + p["target_r"] * risk,
                        risk_pct=p["risk_pct"], max_bars=p["max_hold_bars"],
                        tag=f"orb4_{name}_long",
                        reason=f"{name} break up, open candle {s['ratio']:.2f}x avg")
                return
            if p["allow_shorts"] and close < s["lo"]:
                stop = s["hi"] * (1 + buf)
                risk = stop - close
                if risk <= 0:
                    continue
                s["side"] = "short"
                ctx.sell(stop=stop, target=close - p["target_r"] * risk,
                         risk_pct=p["risk_pct"], max_bars=p["max_hold_bars"],
                         tag=f"orb4_{name}_short",
                         reason=f"{name} break down, open candle {s['ratio']:.2f}x avg")
                return

    def _roll_day(self, ctx: Context, s: dict) -> None:
        d = ctx.time.tz_convert(s["tz"]).date()
        if s["date"] != d:
            s.update(date=d, hi=None, lo=None, side=None, ratio=None, seen=False)

    def _record_range(self, ctx: Context, s: dict) -> None:
        if not self._in_window(ctx, s["tz"], *s["open"]):
            return
        bar = ctx.bar
        if not s["seen"]:
            # first candle of the session: how big is it against recent bars?
            s["seen"] = True
            n = ctx.params["candle_lookback"]
            if ctx.bars_seen > n + 1:
                highs = ctx.series("high", n + 1)[:-1]
                lows = ctx.series("low", n + 1)[:-1]
                avg = mean(highs - lows)
                s["ratio"] = (bar.high - bar.low) / avg if avg > 0 else None
        s["hi"] = bar.high if s["hi"] is None else max(s["hi"], bar.high)
        s["lo"] = bar.low if s["lo"] is None else min(s["lo"], bar.low)

    def _in_window(self, ctx: Context, tz: str, start: str, end: str) -> bool:
        o = ctx.time.tz_convert(tz)
        c = ctx.now.tz_convert(tz)
        sm = int(start[:2]) * 60 + int(start[3:])
        em = int(end[:2]) * 60 + int(end[3:])
        return (o.hour * 60 + o.minute) < em and (c.hour * 60 + c.minute) > sm
