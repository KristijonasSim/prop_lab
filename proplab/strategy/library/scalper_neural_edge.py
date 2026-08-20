"""Kris's "Neural Edge - Quantum Momentum Scalper", ported for backtesting.

The original is a TradingView INDICATOR: it marks signals but never manages a
position, so the exits below are the ones its own alerts describe - stop at
1.618 ATR, target at 2.618 ATR, stop to breakeven once 1.618 ATR is reached.

Ported faithfully rather than improved, so the test says something about the
idea rather than about my edits. Two honest notes on the port:

  - `ta.vwap` anchors to the exchange session; BTC has none, so it anchors to
    the UTC day here.
  - Supertrend and VWAP are stateful, carried in ctx.state and updated one bar
    at a time, which is what Pine does internally. Recomputing them from
    scratch each bar would be both slow and subtly different.

The design is for 1m-5m. Running it on 15m tests a different strategy.
"""
from __future__ import annotations

import numpy as np

from proplab.core.context import Context
from proplab.strategy.base import Strategy
from proplab.strategy.indicators import alma, atr, delta_pressure, sma


class NeuralEdgeScalper(Strategy):
    name = "scalper_neural_edge"
    hypothesis = (
        "Momentum-first scalping: when a fast trend, a volume surge, order-flow "
        "pressure and VWAP position all agree, the next few minutes continue in "
        "that direction."
    )
    mechanism = (
        "Each layer is meant to remove a different false positive. ALMA plus "
        "Supertrend says the short-term trend is up. A volume surge says the "
        "move has participation rather than being a drift on thin books. The "
        "delta proxy says the bars are closing near their highs, i.e. buyers "
        "are the ones lifting. VWAP position says the move is on the right side "
        "of the day's average traded price, where trapped sellers sit below. "
        "The claim is that requiring all four at once leaves only real "
        "displacement. The risk is the opposite: four correlated momentum "
        "filters may just be one filter counted four times, and each extra "
        "condition cuts the sample rather than the noise."
    )
    variation = (
        "Faithful port of the supplied Pine indicator: ALMA(9, 0.85, 6) rising, "
        "Supertrend(7, 2.5) bullish, volume >= 1.5x its 20-bar average, "
        "10-bar cumulative delta positive, price the right side of VWAP. Stop "
        "1.618 ATR, target 2.618 ATR, breakeven at 1.618 ATR."
    )
    references = ["User-supplied Pine: Neural Edge - Quantum Momentum Scalper"]

    higher_timeframes = ()

    params = {
        "alma_len": 9, "alma_offset": 0.85, "alma_sigma": 6.0,
        "st_atr_len": 7, "st_factor": 2.5,
        "vol_len": 20, "vol_mult": 1.5,
        "delta_lookback": 10,
        "atr_risk_len": 14,
        "phi_sl": 1.618, "phi_tp": 2.618, "phi_be": 1.618,
        "risk_pct": 0.005,
        "max_bars": 96,
        "allow_shorts": True,
    }

    def on_start(self, ctx: Context) -> None:
        ctx.state.update(st_upper=None, st_lower=None, st_dir=1,
                         vwap_day=None, vwap_pv=0.0, vwap_v=0.0, be_done=False)

    def on_bar(self, ctx: Context) -> None:
        p = ctx.params
        bar = ctx.bar
        need = max(p["alma_len"], p["st_atr_len"], p["vol_len"],
                   p["delta_lookback"], p["atr_risk_len"]) + 2
        st_dir, st_line = self._supertrend(ctx)
        vwap = self._vwap(ctx)
        if ctx.bars_seen < need:
            return

        # ---- manage an open position: breakeven at TP1, as the alerts describe
        if ctx.position is not None:
            pos = ctx.position
            if not ctx.state["be_done"] and pos.initial_risk > 0:
                per_unit = pos.initial_risk / pos.qty
                move = ((ctx.close - pos.entry_price) if pos.is_long
                        else (pos.entry_price - ctx.close))
                if move >= per_unit * (p["phi_be"] / p["phi_sl"]):
                    ctx.move_stop(pos.entry_price)
                    ctx.state["be_done"] = True
            return

        closes = ctx.series("close")
        highs, lows = ctx.series("high"), ctx.series("low")
        vols = ctx.series("volume")

        a = alma(closes, p["alma_len"], p["alma_offset"], p["alma_sigma"])
        a_prev = alma(closes[:-1], p["alma_len"], p["alma_offset"], p["alma_sigma"])
        if a != a or a_prev != a_prev or vwap != vwap:
            return

        vol_avg = sma(vols, p["vol_len"])
        vol_surge = vol_avg == vol_avg and bar.volume >= vol_avg * p["vol_mult"]
        if not vol_surge:
            return

        d = delta_pressure(highs, lows, closes, vols, p["delta_lookback"])
        atr_risk = atr(highs, lows, closes, p["atr_risk_len"])
        if not atr_risk > 0 or d != d:
            return

        long_ok = (a > a_prev) and (st_dir < 0) and (bar.close > a) and \
                  (d > 0) and (bar.close > vwap)
        short_ok = (a < a_prev) and (st_dir > 0) and (bar.close < a) and \
                   (d < 0) and (bar.close < vwap)

        if long_ok:
            ctx.state["be_done"] = False
            ctx.buy(stop=bar.close - atr_risk * p["phi_sl"],
                    target=bar.close + atr_risk * p["phi_tp"],
                    risk_pct=p["risk_pct"], max_bars=p["max_bars"],
                    tag="ne_long", reason="4/4 layers aligned long")
        elif p["allow_shorts"] and short_ok:
            ctx.state["be_done"] = False
            ctx.sell(stop=bar.close + atr_risk * p["phi_sl"],
                     target=bar.close - atr_risk * p["phi_tp"],
                     risk_pct=p["risk_pct"], max_bars=p["max_bars"],
                     tag="ne_short", reason="4/4 layers aligned short")

    # ---- stateful indicators, updated one bar at a time like Pine does ----
    def _supertrend(self, ctx: Context):
        p = ctx.params
        highs, lows, closes = ctx.series("high"), ctx.series("low"), ctx.series("close")
        a = atr(highs, lows, closes, p["st_atr_len"])
        if a != a:
            return 1, float("nan")
        mid = (ctx.bar.high + ctx.bar.low) / 2
        up, dn = mid + p["st_factor"] * a, mid - p["st_factor"] * a
        s = ctx.state
        prev_close = ctx.value("close", 1)

        lower = dn if (s["st_lower"] is None or dn > s["st_lower"]
                       or prev_close < s["st_lower"]) else s["st_lower"]
        upper = up if (s["st_upper"] is None or up < s["st_upper"]
                       or prev_close > s["st_upper"]) else s["st_upper"]

        if s["st_upper"] is None:
            direction = 1
        elif ctx.close > upper:
            direction = -1
        elif ctx.close < lower:
            direction = 1
        else:
            direction = s["st_dir"]

        s["st_lower"], s["st_upper"], s["st_dir"] = lower, upper, direction
        return direction, (lower if direction < 0 else upper)

    def _vwap(self, ctx: Context) -> float:
        s = ctx.state
        day = ctx.time.date()
        if s["vwap_day"] != day:
            s.update(vwap_day=day, vwap_pv=0.0, vwap_v=0.0)
        bar = ctx.bar
        tp = (bar.high + bar.low + bar.close) / 3
        s["vwap_pv"] += tp * bar.volume
        s["vwap_v"] += bar.volume
        return s["vwap_pv"] / s["vwap_v"] if s["vwap_v"] > 0 else float("nan")
