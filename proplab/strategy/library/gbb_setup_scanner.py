"""Kris's "Setup Scanner [GBB]" v1.0, ported for backtesting.

Six independent setups sharing one trade engine. Ported faithfully rather than
improved, so the test says something about the idea and not about my edits.

The one thing worth reading before the numbers, because it changes what they
mean: **the Pine never exits at TP1 or TP2.** Tracing `closeTrade` in the
original, the only exits are the stop, TP3, and the `maxBars` timeout - TP1 and
TP2 only set `stage` and promote a line to solid. So the panel's "-> TP1"
column is not a win rate and not an exit; it is "this trade at some point
traded through 1R on its way to 3R or the stop". A trade can touch TP1 and
still be a full stop-out, and in the port it usually is.

That single fact reconciles the two numbers on the chart: a ~53% "-> TP1" row
and a much lower real win rate are the same strategy.

Notes on the port:

  - `ta.vwap(hlc3)` anchors to the exchange session; BTC has none, so it
    anchors to the UTC day here, as in scalper_neural_edge.
  - EMA, RSI and VWAP are stateful and carried in ctx.state one bar at a time,
    which is what Pine does internally.
  - `maxOpen = 1` and `oneWay` are free: the engine holds one position.
  - Setup priority is the Pine's loop order (VWAP, EMA, B&R, sweep,
    divergence, ORB) - the first to fire on a bar takes the trade and the rest
    are dropped. That ordering is arbitrary in the original and it biases the
    per-setup counts, which is why every setup also gets a solo variation here.
  - `volOk` gates VWAP, EMA and sweep only, exactly as the original comment
    describes. B&R, divergence and ORB run unfiltered.
  - `reentry = 0`, so nothing blocks a new trade the bar after one resolves.
"""
from __future__ import annotations

import numpy as np

from proplab.core.context import Context
from proplab.strategy.base import Strategy
from proplab.strategy.indicators import atr, pivot_high, pivot_low, sma

S_VWAP, S_EMA, S_BRT, S_SWEEP, S_DIV, S_ORB = range(6)

SETUP_NAMES = {
    S_VWAP: "vwap_reclaim",
    S_EMA: "ema_pullback",
    S_BRT: "break_retest",
    S_SWEEP: "liquidity_sweep",
    S_DIV: "rsi_divergence",
    S_ORB: "opening_range",
}


class GbbScanner(Strategy):
    """All six setups, in the Pine's own priority order."""

    name = "gbb_scanner_all"
    hypothesis = (
        "Six classic intraday setups - VWAP reclaim, EMA pullback, break and "
        "retest, liquidity sweep, RSI divergence and opening-range break - "
        "each mark a point where price is likely to continue, and a scanner "
        "that trades whichever fires first captures more of them than any one "
        "setup alone."
    )
    mechanism = (
        "Each setup names a different group getting trapped. A VWAP reclaim "
        "traps sellers who sold below the day's average price. An EMA pullback "
        "buys the profit-taking inside an intact trend. A break and retest "
        "sells the breakout buyers who bought the first push and are now "
        "defending it. A liquidity sweep runs the stops sitting under an "
        "obvious low and reverses on the traders who placed them. Divergence "
        "says the second push had less force behind it. The opening range is "
        "the day's first agreed boundary, so leaving it is information.\n\n"
        "The risk is that these are six names for one thing - short-term "
        "momentum - and that bundling them raises the trade count without "
        "raising the edge. If that is what is happening, the combined scanner "
        "will not beat its own best single setup, and the per-setup runs will "
        "show it."
    )
    variation = (
        "Faithful port of the full scanner: all six setups enabled, first to "
        "fire on a bar wins, stop at 1.2 ATR, exit at 3R or after 60 bars. "
        "TP1/TP2 are markers only, as in the Pine."
    )
    references = ["User-supplied Pine: Setup Scanner [GBB] v1.0"]

    higher_timeframes = ()

    # Enabled setups. Subclasses narrow this to isolate one at a time.
    setups = (S_VWAP, S_EMA, S_BRT, S_SWEEP, S_DIV, S_ORB)

    params = {
        # trade plan (Pine group "Trade plan")
        "stop_atr": 1.2,
        "r3": 3.0,                 # the only profit exit the Pine actually takes
        "max_bars": 60,
        # filters
        "atr_len": 14,
        "vol_mult": 1.0,
        "pivot_len": 5,
        # setup tuning
        "vwap_away": 6,
        "ema_window": 3,
        "brt_tol": 0.3,
        "brt_window": 20,
        "sweep_len": 20,
        "div_gap": 60,
        # opening range
        "or_session": ("09:30", "16:00"),
        "or_tz": "America/New_York",
        "or_minutes": 15,
        # sizing
        "risk_pct": 0.005,
        "allow_shorts": True,
    }

    # ---- lifecycle ---------------------------------------------------------
    def on_start(self, ctx: Context) -> None:
        ctx.state.update(
            ema9=None, ema21=None, ema50=None, ema50_hist=[],
            rsi=None, rsi_gain=None, rsi_loss=None, rsi_hist=[],
            vwap_day=None, vwap_pv=0.0, vwap_v=0.0,
            below_run=0, above_run=0,
            since_touch_up=10 ** 6, since_touch_dn=10 ** 6,
            brt_hi_lvl=None, brt_hi_brk=False, brt_hi_bar=None, brt_hi_pend=None,
            brt_lo_lvl=None, brt_lo_brk=False, brt_lo_bar=None, brt_lo_pend=None,
            last_pl_p=None, last_pl_r=None, last_pl_b=None,
            last_ph_p=None, last_ph_r=None, last_ph_b=None,
            or_h=None, or_l=None, or_done=False, or_fired=False,
            or_start=None, or_date=None,
        )

    def on_bar(self, ctx: Context) -> None:
        p = ctx.params

        # Stateful indicators must advance on EVERY bar, before any early
        # return - the same reason Pine hoists ta.* out of conditionals. Miss a
        # bar and the EMA is quietly wrong from then on.
        ema9, ema21, ema50, ema50_3 = self._emas(ctx)
        rsi_now = self._rsi(ctx)
        vwap = self._vwap(ctx)
        self._track_vwap_runs(ctx, vwap)
        self._track_ema_touch(ctx, ema21)
        ph, pl = self._pivots(ctx)
        self._track_break_retest(ctx, ph, pl)
        div_l, div_s = self._track_divergence(ctx, ph, pl, rsi_now)
        self._track_opening_range(ctx)

        if ctx.position is not None:
            return

        need = max(50, p["sweep_len"], p["brt_window"], p["atr_len"]) + p["pivot_len"] + 2
        if ctx.bars_seen < need:
            return

        a = atr(ctx.series("high"), ctx.series("low"), ctx.series("close"), p["atr_len"])
        if not a > 0:
            return

        vol_ok = self._vol_ok(ctx)

        # First setup to fire wins, in the Pine's loop order.
        for sid in self.setups:
            long_sig, short_sig = self._signal(
                sid, ctx, ema9, ema21, ema50, ema50_3, vwap, vol_ok, div_l, div_s, a)
            if long_sig:
                self._enter(ctx, sid, +1, a)
                return
            if short_sig and p["allow_shorts"]:
                self._enter(ctx, sid, -1, a)
                return

    # ---- entry -------------------------------------------------------------
    def _enter(self, ctx: Context, sid: int, direction: int, a: float) -> None:
        p = ctx.params
        risk = a * p["stop_atr"]
        close = ctx.close
        tag = SETUP_NAMES[sid]
        if direction > 0:
            ctx.buy(stop=close - risk, target=close + risk * p["r3"],
                    risk_pct=p["risk_pct"], max_bars=p["max_bars"],
                    tag=f"{tag}_long", reason=f"{tag} long")
        else:
            ctx.sell(stop=close + risk, target=close - risk * p["r3"],
                     risk_pct=p["risk_pct"], max_bars=p["max_bars"],
                     tag=f"{tag}_short", reason=f"{tag} short")

    # ---- the six setups ----------------------------------------------------
    def _signal(self, sid, ctx, ema9, ema21, ema50, ema50_3, vwap, vol_ok,
                div_l, div_s, a):
        p = ctx.params
        s = ctx.state
        bar = ctx.bar
        prev_close = ctx.value("close", 1)
        bull = bar.close > bar.open
        bear = bar.close < bar.open

        if sid == S_VWAP:
            if vwap != vwap:
                return False, False
            crossed_up = prev_close <= s["vwap_prev"] and bar.close > vwap
            crossed_dn = prev_close >= s["vwap_prev"] and bar.close < vwap
            long_ok = crossed_up and s["below_run_prev"] >= p["vwap_away"] and vol_ok
            short_ok = crossed_dn and s["above_run_prev"] >= p["vwap_away"] and vol_ok
            return long_ok, short_ok

        if sid == S_EMA:
            if ema50_3 != ema50_3:
                return False, False
            trend_up = ema21 > ema50 and ema50 > ema50_3
            trend_dn = ema21 < ema50 and ema50 < ema50_3
            long_ok = (trend_up and s["since_touch_up"] <= p["ema_window"]
                       and bar.close > ema9 and bull
                       and bar.close > ctx.value("high", 1) and vol_ok)
            short_ok = (trend_dn and s["since_touch_dn"] <= p["ema_window"]
                        and bar.close < ema9 and bear
                        and bar.close < ctx.value("low", 1) and vol_ok)
            return long_ok, short_ok

        if sid == S_BRT:
            long_ok = short_ok = False
            if self._brt_busy(ctx, s["brt_hi_brk"], s["brt_hi_bar"]) and s["brt_hi_lvl"] is not None:
                long_ok = (bar.low <= s["brt_hi_lvl"] + a * p["brt_tol"]
                           and bar.close > s["brt_hi_lvl"] and bull)
            if self._brt_busy(ctx, s["brt_lo_brk"], s["brt_lo_bar"]) and s["brt_lo_lvl"] is not None:
                short_ok = (bar.high >= s["brt_lo_lvl"] - a * p["brt_tol"]
                            and bar.close < s["brt_lo_lvl"] and bear)
            # the Pine arms the level again once its retest has been taken
            if long_ok:
                s["brt_hi_brk"] = False
            if short_ok:
                s["brt_lo_brk"] = False
            return long_ok, short_ok

        if sid == S_SWEEP:
            n = p["sweep_len"]
            lows, highs = ctx.series("low", n + 1), ctx.series("high", n + 1)
            if len(lows) < n + 1:
                return False, False
            sw_lo, sw_hi = float(np.min(lows[:-1])), float(np.max(highs[:-1]))
            long_ok = (bar.low < sw_lo and bar.close > sw_lo and bull
                       and (bar.close - bar.low) > (bar.high - bar.close) and vol_ok)
            short_ok = (bar.high > sw_hi and bar.close < sw_hi and bear
                        and (bar.high - bar.close) > (bar.close - bar.low) and vol_ok)
            return long_ok, short_ok

        if sid == S_DIV:
            return div_l, div_s

        if sid == S_ORB:
            if not (s["or_done"] and not s["or_fired"] and self._in_or_session(ctx)):
                return False, False
            long_ok = s["or_h"] is not None and bar.close > s["or_h"]
            short_ok = s["or_l"] is not None and bar.close < s["or_l"]
            if long_ok or short_ok:
                s["or_fired"] = True     # one break per session, either direction
            return long_ok, short_ok

        return False, False

    # ---- stateful indicators, one bar at a time ----------------------------
    def _emas(self, ctx: Context):
        s = ctx.state
        c = ctx.close
        for key, n in (("ema9", 9), ("ema21", 21), ("ema50", 50)):
            prev = s[key]
            k = 2.0 / (n + 1)
            s[key] = c if prev is None else prev + k * (c - prev)
        hist = s["ema50_hist"]
        ema50_3 = hist[-3] if len(hist) >= 3 else float("nan")
        hist.append(s["ema50"])
        if len(hist) > 4:
            hist.pop(0)
        return s["ema9"], s["ema21"], s["ema50"], ema50_3

    def _rsi(self, ctx: Context) -> float:
        """Wilder's RSI(14), smoothed incrementally as Pine does."""
        s = ctx.state
        prev = ctx.value("close", 1)
        if prev != prev:
            return float("nan")
        change = ctx.close - prev
        gain, loss = max(change, 0.0), max(-change, 0.0)
        if s["rsi_gain"] is None:
            s["rsi_gain"], s["rsi_loss"] = gain, loss
        else:
            s["rsi_gain"] = (s["rsi_gain"] * 13 + gain) / 14
            s["rsi_loss"] = (s["rsi_loss"] * 13 + loss) / 14
        rs_loss = s["rsi_loss"]
        value = 100.0 if rs_loss == 0 else 100 - 100 / (1 + s["rsi_gain"] / rs_loss)
        s["rsi"] = value
        # the divergence setup reads RSI as it was AT the pivot, pivot_len back
        hist = s["rsi_hist"]
        hist.append(value)
        if len(hist) > ctx.params["pivot_len"] + 2:
            hist.pop(0)
        return value

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

    def _track_vwap_runs(self, ctx: Context, vwap: float) -> None:
        """Bars spent on one side of VWAP. The signal reads the PREVIOUS bar's
        run, so both the run and the VWAP level are snapshotted before update -
        `nz(belowRun[1])` and `close[1] vs vwap[1]` in the original."""
        s = ctx.state
        s["below_run_prev"] = s["below_run"]
        s["above_run_prev"] = s["above_run"]
        s["vwap_prev"] = s.get("vwap_cur", float("nan"))
        s["vwap_cur"] = vwap
        if vwap == vwap:
            s["below_run"] = s["below_run"] + 1 if ctx.close < vwap else 0
            s["above_run"] = s["above_run"] + 1 if ctx.close > vwap else 0

    def _track_ema_touch(self, ctx: Context, ema21: float) -> None:
        """ta.barssince(low <= ema21) and its mirror, as counters."""
        s = ctx.state
        bar = ctx.bar
        s["since_touch_up"] = 0 if bar.low <= ema21 else s["since_touch_up"] + 1
        s["since_touch_dn"] = 0 if bar.high >= ema21 else s["since_touch_dn"] + 1

    def _pivots(self, ctx: Context):
        n = ctx.params["pivot_len"]
        return (pivot_high(ctx.series("high"), n, n),
                pivot_low(ctx.series("low"), n, n))

    def _brt_busy(self, ctx: Context, broken: bool, break_bar) -> bool:
        return (broken and break_bar is not None
                and ctx.i - break_bar <= ctx.params["brt_window"])

    def _track_break_retest(self, ctx: Context, ph: float, pl: float) -> None:
        s = ctx.state
        # a new pivot replaces the level, unless a break of the old one is
        # still inside its retest window - then it waits as `pend`
        if ph == ph:
            if self._brt_busy(ctx, s["brt_hi_brk"], s["brt_hi_bar"]):
                s["brt_hi_pend"] = ph
            else:
                s.update(brt_hi_lvl=ph, brt_hi_brk=False, brt_hi_pend=None)
        if pl == pl:
            if self._brt_busy(ctx, s["brt_lo_brk"], s["brt_lo_bar"]):
                s["brt_lo_pend"] = pl
            else:
                s.update(brt_lo_lvl=pl, brt_lo_brk=False, brt_lo_pend=None)

        if s["brt_hi_lvl"] is not None and not s["brt_hi_brk"] and ctx.close > s["brt_hi_lvl"]:
            s.update(brt_hi_brk=True, brt_hi_bar=ctx.i)
        if s["brt_lo_lvl"] is not None and not s["brt_lo_brk"] and ctx.close < s["brt_lo_lvl"]:
            s.update(brt_lo_brk=True, brt_lo_bar=ctx.i)

        if not self._brt_busy(ctx, s["brt_hi_brk"], s["brt_hi_bar"]) and s["brt_hi_pend"] is not None:
            s.update(brt_hi_lvl=s["brt_hi_pend"], brt_hi_brk=False, brt_hi_pend=None)
        if not self._brt_busy(ctx, s["brt_lo_brk"], s["brt_lo_bar"]) and s["brt_lo_pend"] is not None:
            s.update(brt_lo_lvl=s["brt_lo_pend"], brt_lo_brk=False, brt_lo_pend=None)

    def _track_divergence(self, ctx: Context, ph: float, pl: float, rsi_now: float):
        """Confirms pivot_len bars after the pivot. Late by construction."""
        s = ctx.state
        n = ctx.params["pivot_len"]
        hist = s["rsi_hist"]
        rsi_at_pivot = hist[-(n + 1)] if len(hist) >= n + 1 else float("nan")
        div_l = div_s = False

        if pl == pl and rsi_at_pivot == rsi_at_pivot:
            if (s["last_pl_p"] is not None
                    and ctx.i - s["last_pl_b"] <= ctx.params["div_gap"]):
                div_l = pl < s["last_pl_p"] and rsi_at_pivot > s["last_pl_r"]
            s.update(last_pl_p=pl, last_pl_r=rsi_at_pivot, last_pl_b=ctx.i)

        if ph == ph and rsi_at_pivot == rsi_at_pivot:
            if (s["last_ph_p"] is not None
                    and ctx.i - s["last_ph_b"] <= ctx.params["div_gap"]):
                div_s = ph > s["last_ph_p"] and rsi_at_pivot < s["last_ph_r"]
            s.update(last_ph_p=ph, last_ph_r=rsi_at_pivot, last_ph_b=ctx.i)

        return div_l, div_s

    def _in_or_session(self, ctx: Context) -> bool:
        p = ctx.params
        local = ctx.now.tz_convert(p["or_tz"])
        hhmm = local.strftime("%H:%M")
        start, end = p["or_session"]
        return start <= hhmm < end

    def _track_opening_range(self, ctx: Context) -> None:
        s = ctx.state
        p = ctx.params
        in_sess = self._in_or_session(ctx)
        local = ctx.now.tz_convert(p["or_tz"])
        day = local.date()

        if in_sess and (not s.get("or_in_sess") or s["or_date"] != day):
            bar = ctx.bar
            s.update(or_h=bar.high, or_l=bar.low, or_done=False, or_fired=False,
                     or_start=ctx.now, or_date=day)
        elif in_sess and not s["or_done"]:
            bar = ctx.bar
            elapsed = (ctx.now - s["or_start"]).total_seconds() / 60
            if elapsed >= p["or_minutes"]:
                s["or_done"] = True
            else:
                s["or_h"] = max(s["or_h"], bar.high)
                s["or_l"] = min(s["or_l"], bar.low)
        s["or_in_sess"] = in_sess

    def _vol_ok(self, ctx: Context) -> bool:
        p = ctx.params
        if p["vol_mult"] <= 0:
            return True
        vols = ctx.series("volume")
        avg = sma(vols, 20)
        if avg != avg:
            return True
        return ctx.bar.volume >= avg * p["vol_mult"]


# ---------------------------------------------------------------------------
# One variation per setup. Same code path, same trade plan - the only
# difference is which setup is allowed to fire, so the per-setup numbers are
# not contaminated by whichever setup happened to grab the slot first.
# ---------------------------------------------------------------------------

def _solo(sid: int, slug: str, variation: str):
    class Solo(GbbScanner):
        name = slug
        setups = (sid,)
    Solo.variation = variation
    Solo.__name__ = "".join(w.title() for w in slug.split("_"))
    return Solo


GbbVwapReclaim = _solo(
    S_VWAP, "gbb_vwap_reclaim",
    "VWAP reclaim only: price spends >= 6 bars one side of the session VWAP, "
    "then closes back across it on above-average volume.")

GbbEmaPullback = _solo(
    S_EMA, "gbb_ema_pullback",
    "EMA pullback only: 21/50 trend, price touches the 21 within 3 bars, then "
    "closes back past the 9 and beyond the prior bar's extreme.")

GbbBreakRetest = _solo(
    S_BRT, "gbb_break_retest",
    "Break and retest only: a confirmed swing is broken, price returns within "
    "0.3 ATR of it inside 20 bars, and closes back in the break direction.")

GbbLiquiditySweep = _solo(
    S_SWEEP, "gbb_liquidity_sweep",
    "Liquidity sweep only: the wick takes out a 20-bar extreme, the body "
    "closes back inside, and the rejection wick is the larger half.")

GbbRsiDivergence = _solo(
    S_DIV, "gbb_rsi_divergence",
    "RSI divergence only: consecutive price pivots make a new extreme while "
    "RSI does not, confirmed 5 bars late.")

GbbOpeningRange = _solo(
    S_ORB, "gbb_opening_range",
    "Opening range only: the first 15 minutes of the NY session define a "
    "range, and the first close outside it takes the trade. One per session.")
