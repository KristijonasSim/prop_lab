"""N5's legs, ported one at a time onto proplab's engine.

Source: /home/kris/trading-bots, `bybit_bot/bot_n5.py`. N5 is a book of NINE
legs, each lifted unchanged from `bot_n2.LEGS`. EIGHT are ported here:

    leg               tf    feeds needed                     live basket has BTC?
    asia_monday       1h    klines                           yes
    nayrafa           30m   klines                           yes
    liquidity_sweep   4h    klines                           yes
    volmom            1h    klines                           yes
    delta_absorption  1h    + taker delta, funding           yes
    ff                1h    + funding                        NO (ATOM/DOGE)
    lsr               1h    + Bybit account ratio            NO (ADA/LINK/SOL/XRP)
    oi                1h    + account ratio, open interest   NO (SOL/XRP/ADA/BCH)
    pc                1h    premium/basis poll               not ported - see below

The extra feeds come from `proplab/data/external_feeds.py`, which builds a
BTCUSDT 1h dataset with `delta`, `funding`, `buy_ratio` and `oi` attached.

`pc` is the one leg with no port. It has `signal=None` and `is_premium=True`:
the live bot drives it from a premium poll rather than a bar-close rule, so
there is no signal function to port. Reconstructing one would be writing a new
strategy and calling it Kris's, which is the opposite of the point.

WHAT A SOLO RUN HERE DOES AND DOES NOT MEASURE
----------------------------------------------
In the real book these legs run together, across many symbols, with several
positions open at once, sized against a shared account. proplab runs ONE
symbol and ONE position. So this measures each leg's standalone edge on BTC -
which is what was asked - and it deliberately does NOT measure the leg's
contribution to N5. A leg can be weak alone and still earn its place in a book
by firing when the others are quiet. The trading-bots repo's own ANSWERS.md
makes exactly that point ("a leg is only worth adding if it raises the BOOK at
matched drawdown"), so read these numbers as "how does this leg do on BTC by
itself", nothing wider.

Ported faithfully: entry rules, stop distances, rr, max_hold, cooldown and
trail are the locked live values, read out of the running registry rather than
retyped. Both engines fill a bar-close intent at the NEXT bar's open, so the
execution convention already matches.

One deliberate difference: the reference `atr()` is Wilder's EWM, while
proplab's `indicators.atr` is a simple mean. The Wilder version is carried in
ctx.state here so the stop distances match the live bot rather than being
approximately right.
"""
from __future__ import annotations

import numpy as np

from proplab.core.context import Context
from proplab.strategy.base import Strategy


class _N5Leg(Strategy):
    """Shared plumbing: Wilder ATR, the R-trail, and the cooldown."""

    higher_timeframes = ()

    # per-leg trade plan, overridden below with the live locked values
    rr = 1.0
    max_hold = 24
    cooldown = 1
    trail_r = 0.0

    params = {"risk_pct": 0.005, "atr_len": 14}

    def on_start(self, ctx: Context) -> None:
        ctx.state.update(atr=None, adx_state=None, last_exit=-10 ** 6,
                         had_position=False, peak=None, trough=None)

    # ---- Wilder's ATR, advanced every bar ---------------------------------
    def _atr(self, ctx: Context) -> float:
        s = ctx.state
        prev_close = ctx.value("close", 1)
        bar = ctx.bar
        if prev_close != prev_close:
            tr = bar.high - bar.low
        else:
            tr = max(bar.high - bar.low,
                     abs(bar.high - prev_close), abs(bar.low - prev_close))
        alpha = 1.0 / ctx.params["atr_len"]
        s["atr"] = tr if s["atr"] is None else s["atr"] + alpha * (tr - s["atr"])
        return s["atr"]

    # ---- cooldown ----------------------------------------------------------
    def _track_exit(self, ctx: Context) -> None:
        s = ctx.state
        if s["had_position"] and ctx.position is None:
            s["last_exit"] = ctx.i
            s["peak"] = s["trough"] = None
        s["had_position"] = ctx.position is not None

    def _cool(self, ctx: Context) -> bool:
        return ctx.i - ctx.state["last_exit"] > self.cooldown

    # ---- trailing stop, in R, ratcheting only ------------------------------
    def _apply_trail(self, ctx: Context) -> None:
        if self.trail_r <= 0 or ctx.position is None:
            return
        pos = ctx.position
        if pos.qty <= 0 or pos.initial_risk <= 0:
            return
        risk = pos.initial_risk / pos.qty        # per-unit risk, in price
        s = ctx.state
        bar = ctx.bar
        if pos.is_long:
            s["peak"] = bar.high if s["peak"] is None else max(s["peak"], bar.high)
            if s["peak"] > pos.entry_price:
                want = s["peak"] - self.trail_r * risk
                if want > pos.stop:
                    ctx.move_stop(want)
        else:
            s["trough"] = bar.low if s["trough"] is None else min(s["trough"], bar.low)
            if s["trough"] < pos.entry_price:
                want = s["trough"] + self.trail_r * risk
                if want < pos.stop:
                    ctx.move_stop(want)

    # ---- entry helper ------------------------------------------------------
    def _take(self, ctx: Context, side: int, stop: float, target=None) -> None:
        close = ctx.close
        risk = abs(close - stop)
        if risk <= 0:
            return
        tgt = target if target is not None else (
            close + side * self.rr * risk)
        ctx.state["peak"] = ctx.state["trough"] = None
        kw = dict(stop=stop, target=tgt, risk_pct=ctx.params["risk_pct"],
                  max_bars=self.max_hold, tag=f"{self.name}_{'long' if side > 0 else 'short'}",
                  reason=self.name)
        (ctx.buy if side > 0 else ctx.sell)(**kw)


# ═══════════════════════════════════════════════════════════════════════════
# asia_monday - 1h, long only, Friday and Sunday 23:00 UTC
# ═══════════════════════════════════════════════════════════════════════════
class N5AsiaMonday(_N5Leg):
    name = "n5_asia_monday"
    hypothesis = (
        "Buying BTC at 23:00 UTC on Friday and Sunday, into the Asian session "
        "open, catches a repeatable weekly flow."
    )
    mechanism = (
        "A calendar leg: the claim is that the Asia handover at the weekend "
        "edges is a moment when a different set of participants sets the "
        "price, with Western desks flat or thin. Who is on the other side is "
        "whoever is closing weekend risk. The weakness is that a calendar rule "
        "with two firing times per week has very few independent observations "
        "however many years you run it, and nothing about the mechanism says "
        "the effect must persist once it is known."
    )
    variation = (
        "Locked live values: entry 23:00 UTC on dayofweek 4 and 6, an 80-bar "
        "SMA trend filter, stop 3 Wilder ATR, target 100 ATR (i.e. unreachable "
        "by design, so the real exit is the 24-bar hold), cooldown 1."
    )
    references = ["trading-bots: scalping/strategy_asia_monday.py, bot_n5.LEGS"]

    rr, max_hold, cooldown, trail_r = 1.5, 24, 1, 0.0
    params = {"risk_pct": 0.005, "atr_len": 14,
              "entry_hour": 23, "entry_days": (4, 6),
              "trend_len": 80, "stop_atr": 3.0, "far_atr": 100.0}

    def on_bar(self, ctx: Context) -> None:
        p = ctx.params
        a = self._atr(ctx)
        self._track_exit(ctx)
        if ctx.position is not None or not self._cool(ctx):
            return
        if ctx.bars_seen < p["trend_len"] + 2 or not a > 0:
            return
        # `start` in the reference is the bar OPEN time, which is ctx.time here
        t = ctx.time
        if t.dayofweek not in p["entry_days"] or t.hour != p["entry_hour"]:
            return
        sma = float(np.mean(ctx.series("close", p["trend_len"])))
        c = ctx.close
        if not c > sma:
            return
        self._take(ctx, +1, c - p["stop_atr"] * a, target=c + p["far_atr"] * a)


# ═══════════════════════════════════════════════════════════════════════════
# nayrafa - 30m, Bollinger-driven trendline flip
# ═══════════════════════════════════════════════════════════════════════════
class N5Nayrafa(_N5Leg):
    name = "n5_nayrafa"
    hypothesis = (
        "A ratcheting trendline that only moves when price closes outside a "
        "wide Bollinger band flips direction at the start of real moves."
    )
    mechanism = (
        "The trendline tracks lows while price is above the upper band and "
        "highs while it is below the lower one, and never moves against "
        "itself. So it only turns when price has travelled far enough to "
        "close outside a 2.5-sigma band over 180 bars, which is meant to be a "
        "regime change rather than noise. The ADX gate is there to refuse the "
        "signal in chop. The weakness: rr is 0.625, so this is a low-payoff "
        "high-hit-rate shape, and those die quietly to costs rather than "
        "loudly to drawdowns."
    )
    variation = (
        "Locked live values: BB(180, 2.5) on population sigma, ADX(14) >= 15, "
        "minimum 3 bars between flips, stop 5 Wilder ATR, rr 0.625, 80-bar "
        "hold, cooldown 1, shorts allowed."
    )
    references = ["trading-bots: scalping/strategy_nayrafa.py, bot_n5.LEGS"]

    rr, max_hold, cooldown, trail_r = 0.625, 80, 1, 0.0
    params = {"risk_pct": 0.005, "atr_len": 14,
              "bb_period": 180, "bb_dev": 2.5, "sl_mult": 5.0,
              "adx_min": 15.0, "min_flip_gap": 3, "allow_short": True}

    def on_start(self, ctx: Context) -> None:
        super().on_start(ctx)
        ctx.state.update(tl=float("nan"), itrend=0, last_flip=-10 ** 6,
                         plus_dm=None, minus_dm=None, adx=None, dx_seed=False)

    def on_bar(self, ctx: Context) -> None:
        p = ctx.params
        a = self._atr(ctx)
        adx = self._adx(ctx)
        flipped_long, flipped_short = self._trendline(ctx)
        self._track_exit(ctx)

        if ctx.position is not None or not self._cool(ctx):
            return
        if not (flipped_long or flipped_short) or not a > 0:
            return
        if p["min_flip_gap"] > 0 and (ctx.i - ctx.state["last_flip"]) <= p["min_flip_gap"]:
            return
        if p["adx_min"] > 0 and not (adx == adx and adx >= p["adx_min"]):
            return

        ctx.state["last_flip"] = ctx.i
        stop_dist = a * p["sl_mult"]
        if flipped_long:
            self._take(ctx, +1, ctx.close - stop_dist)
        elif p["allow_short"]:
            self._take(ctx, -1, ctx.close + stop_dist)

    def _trendline(self, ctx: Context):
        """The ratcheting TrendLine and its direction. Stateful by nature: the
        line holds its value on every bar that closes inside the band."""
        p = ctx.params
        s = ctx.state
        n = p["bb_period"]
        if ctx.bars_seen < n:
            return False, False
        closes = ctx.series("close", n)
        ma = float(np.mean(closes))
        sd = float(np.std(closes))          # population sigma, as Pine's ta.stdev
        upper, lower = ma + p["bb_dev"] * sd, ma - p["bb_dev"] * sd
        bar = ctx.bar

        bb = 1 if bar.close > upper else (-1 if bar.close < lower else 0)
        prev_tl, prev_it = s["tl"], s["itrend"]

        if prev_tl != prev_tl:
            tl = bar.low if bb >= 0 else bar.high
        elif bb == 1:
            tl = max(bar.low, prev_tl)       # tracks lows, never falls
        elif bb == -1:
            tl = min(bar.high, prev_tl)      # tracks highs, never rises
        else:
            tl = prev_tl

        it = prev_it
        if prev_tl == prev_tl:
            if tl > prev_tl:
                it = 1
            elif tl < prev_tl:
                it = -1

        flipped_long = prev_it == -1 and it == 1
        flipped_short = prev_it == 1 and it == -1
        s["tl"], s["itrend"] = tl, it
        return flipped_long, flipped_short

    def _adx(self, ctx: Context) -> float:
        """Wilder's ADX(14), smoothed incrementally to match the reference."""
        s = ctx.state
        if ctx.i < 1:
            return float("nan")
        bar = ctx.bar
        up = bar.high - ctx.value("high", 1)
        dn = ctx.value("low", 1) - bar.low
        plus = up if (up > dn and up > 0) else 0.0
        minus = dn if (dn > up and dn > 0) else 0.0
        alpha = 1.0 / ctx.params["atr_len"]
        s["plus_dm"] = plus if s["plus_dm"] is None else s["plus_dm"] + alpha * (plus - s["plus_dm"])
        s["minus_dm"] = minus if s["minus_dm"] is None else s["minus_dm"] + alpha * (minus - s["minus_dm"])
        a = s["atr"]
        if not a or a <= 0:
            return float("nan")
        pdi, mdi = 100 * s["plus_dm"] / a, 100 * s["minus_dm"] / a
        denom = pdi + mdi
        if denom == 0:
            return s["adx"] if s["adx"] is not None else float("nan")
        dx = 100 * abs(pdi - mdi) / denom
        s["adx"] = dx if s["adx"] is None else s["adx"] + alpha * (dx - s["adx"])
        return s["adx"]


# ═══════════════════════════════════════════════════════════════════════════
# liquidity_sweep - 4h, pierce a confirmed pivot and close back
# ═══════════════════════════════════════════════════════════════════════════
class N5LiquiditySweep(_N5Leg):
    name = "n5_liquidity_sweep"
    hypothesis = (
        "Price pierces a confirmed swing level, closes back through it, and "
        "reverses - the stops resting beyond the level were the fuel."
    )
    mechanism = (
        "Obvious swing highs and lows collect resting stop orders. Running "
        "them fills large orders against forced liquidity, and once that fuel "
        "is spent the move has nothing behind it. The close-location filter "
        "(0.7) is what separates a sweep from a genuine break: the bar must "
        "reject, not just poke. Each level is armed once and consumed, which "
        "stops the same level being traded repeatedly."
    )
    variation = (
        "Locked live values from u44's widened variant: pivot 3, close "
        "location 0.7, stop buffer 0.35 of the signal bar's range, rr 3.0, "
        "10-bar hold, cooldown 1, shorts allowed."
    )
    references = ["trading-bots: scalping/strategy_liquidity_sweep.py, "
                  "bot_upcomers44._sig_liquidity_sweep_wide (LIQ_BUF=0.35)"]

    rr, max_hold, cooldown, trail_r = 3.0, 10, 1, 0.0
    params = {"risk_pct": 0.005, "atr_len": 14,
              "pivot": 3, "cloc": 0.7, "buf": 0.35, "allow_short": True}

    def on_start(self, ctx: Context) -> None:
        super().on_start(ctx)
        ctx.state.update(res=None, sup=None, res_used=True, sup_used=True)

    def on_bar(self, ctx: Context) -> None:
        p = ctx.params
        self._atr(ctx)
        self._arm_levels(ctx)
        self._track_exit(ctx)
        if ctx.position is not None or not self._cool(ctx):
            return

        s = ctx.state
        bar = ctx.bar
        rng = bar.high - bar.low
        if rng <= 0:
            return
        cloc = (bar.close - bar.low) / rng

        if (s["sup"] is not None and not s["sup_used"]
                and bar.low < s["sup"] < bar.close and cloc >= p["cloc"]):
            s["sup_used"] = True
            self._take(ctx, +1, bar.low - p["buf"] * rng)
        elif (p["allow_short"] and s["res"] is not None and not s["res_used"]
                and bar.high > s["res"] > bar.close and cloc <= (1 - p["cloc"])):
            s["res_used"] = True
            self._take(ctx, -1, bar.high + p["buf"] * rng)

    def _arm_levels(self, ctx: Context) -> None:
        """A pivot at bar i is only confirmed `pivot` bars later, which is why
        the reference reads index i-pivot. Slicing here gives the same delay."""
        p, s = ctx.params, ctx.state
        k = p["pivot"]
        need = 2 * k + 1
        if ctx.bars_seen < need:
            return
        highs, lows = ctx.series("high", need), ctx.series("low", need)
        ch, cl = highs[k], lows[k]
        if ch == highs.max() and int((highs == ch).sum()) == 1:
            s["res"], s["res_used"] = float(ch), False
        if cl == lows.min() and int((lows == cl).sum()) == 1:
            s["sup"], s["sup_used"] = float(cl), False


# ═══════════════════════════════════════════════════════════════════════════
# volmom - 1h, volatility-managed momentum
# ═══════════════════════════════════════════════════════════════════════════
class N5VolMomentum(_N5Leg):
    name = "n5_volmom"
    hypothesis = (
        "A 12-bar return that is extreme against its own 240-bar history "
        "continues, but only while short-term realised volatility is not "
        "elevated against its baseline."
    )
    mechanism = (
        "Plain momentum with a volatility brake. The momentum claim is the "
        "usual one: a large move against a long trend filter is information "
        "rather than noise. The brake is the part that is meant to add value - "
        "momentum crashes happen in high-volatility regimes, so the leg "
        "refuses to fire when 24-bar realised vol is more than 1.2x its "
        "240-bar baseline. That gate is also the risk: it is a single "
        "threshold fitted on history, and a filter that removes the worst "
        "regime in-sample is exactly the kind that fails to know the next one."
    )
    variation = (
        "Locked live values: 12-bar return, z-scored on a 240-bar window, "
        "threshold 2.5, 400-bar SMA trend filter, vol gate 1.2, stop 3 Wilder "
        "ATR, rr 3.0, 72-bar hold, 1.5R trailing stop, cooldown 1."
    )
    references = ["trading-bots: scalping/strategy_vol_managed_momentum.py "
                  "(LOCKED), bot_n2._sig_volmom"]

    rr, max_hold, cooldown, trail_r = 3.0, 72, 1, 1.5
    params = {"risk_pct": 0.005, "atr_len": 14,
              "lookback": 12, "zthr": 2.5, "rv_mult": 1.2,
              "stop_atr": 3.0, "z_win": 240, "trend_win": 400}

    def on_bar(self, ctx: Context) -> None:
        p = ctx.params
        a = self._atr(ctx)
        self._track_exit(ctx)

        if ctx.position is not None:
            self._apply_trail(ctx)
            return
        if not self._cool(ctx):
            return

        need = max(p["z_win"] + p["lookback"], p["trend_win"]) + 2
        if ctx.bars_seen < need or not a > 0:
            return

        closes = ctx.series("close", need)
        # ret over `lookback` bars, then z-scored on the last z_win of those
        ret = closes[p["lookback"]:] / closes[:-p["lookback"]] - 1.0
        window = ret[-p["z_win"]:]
        sd = float(np.std(window, ddof=1))
        if not sd > 0:
            return
        rz = (float(ret[-1]) - float(np.mean(window))) / sd

        ret1 = closes[1:] / closes[:-1] - 1.0
        rv24 = float(np.std(ret1[-24:], ddof=1))
        rv_base = float(np.std(ret1[-p["z_win"]:], ddof=1))
        if not (rv24 == rv24 and rv_base == rv_base):
            return
        if rv24 >= p["rv_mult"] * rv_base:      # the volatility brake
            return

        sma = float(np.mean(closes[-p["trend_win"]:]))
        c = ctx.close
        if rz >= p["zthr"] and c > sma:
            self._take(ctx, +1, c - p["stop_atr"] * a)
        elif rz <= -p["zthr"] and c < sma:
            self._take(ctx, -1, c + p["stop_atr"] * a)


# ═══════════════════════════════════════════════════════════════════════════
# The feed-dependent legs.
#
# These four are the ones that could not run on OHLCV alone. They now can,
# because `proplab/data/external_feeds.py` builds a BTCUSDT 1h dataset with
# `delta`, `funding`, `buy_ratio` and `oi` attached. Run them with
# `--timeframe 1h --base-timeframe 1h` so the extra columns survive the load.
#
# ff, lsr and oi were fitted on baskets that DO NOT CONTAIN BTC - ATOM/DOGE,
# ADA/LINK/SOL/XRP and SOL/XRP/ADA/BCH respectively. So BTC is genuinely
# out-of-sample for them in the symbol dimension, which is the most useful
# property of this whole exercise: it is the one test here that the original
# research could not have fitted to. delta_absorption does trade BTC live, so
# it gets no such credit.
# ═══════════════════════════════════════════════════════════════════════════

def _feed(ctx: Context, col: str, n: int) -> np.ndarray:
    """Last n values of an auxiliary column.

    Context exposes OHLCV directly but not extra columns, so these come
    through `ctx.frame()`, which is sliced at the current bar exactly like
    `ctx.series()` - the lookahead wall is the same one.
    """
    return ctx.frame(n)[col].to_numpy(float)


def _zscore_pair(values: np.ndarray, win: int):
    """(z at this bar, z at the previous bar) for a rolling window.

    The fade legs trigger on a CROSS of the threshold, so both are needed;
    computing only the current z would fire on every bar that stays above it.
    """
    if len(values) < win + 1:
        return float("nan"), float("nan")
    cur, prev = values[-win:], values[-win - 1:-1]
    out = []
    for w, x in ((cur, values[-1]), (prev, values[-2])):
        sd = float(np.std(w, ddof=1))
        out.append((x - float(np.mean(w))) / sd if sd > 0 else float("nan"))
    return out[0], out[1]


class _FadeLeg(_N5Leg):
    """Shared shape of ff / lsr / oi: a crowding gauge z-crosses a threshold
    while price is chasing and taker flow is going the other way -> fade it.

    The mechanism is the same in all three; only the gauge changes. That is
    also the honest weakness - three legs that fire on the same setup measured
    three ways are not three independent bets, and in a book they will lose
    together.
    """

    gauge = "funding"      # which column is z-scored
    stop_atr = 1.5

    def _fade_signal(self, ctx: Context):
        p = ctx.params
        need = max(p["z_win"] + 2, p["ret_win"] + 2)
        if ctx.bars_seen < need:
            return 0, float("nan")
        a = ctx.state["atr"]
        if not a or not a > 0:
            return 0, float("nan")

        g = _feed(ctx, self.gauge, p["z_win"] + 2)
        z, z_prev = _zscore_pair(g, p["z_win"])
        if z != z or z_prev != z_prev:
            return 0, float("nan")

        closes = ctx.series("close", p["ret_win"] + 1)
        if len(closes) < p["ret_win"] + 1 or closes[0] <= 0:
            return 0, float("nan")
        ret = closes[-1] / closes[0] - 1.0
        d = float(np.sum(_feed(ctx, "delta", p["ret_win"])))

        thr = p["z_thr"]
        # crowd piles long, price chases up, but flow is selling into it
        if z_prev < thr <= z and ret > 0 and d < 0:
            return -1, a
        # mirror
        if z_prev > -thr >= z and ret < 0 and d > 0:
            return +1, a
        return 0, a

    def on_bar(self, ctx: Context) -> None:
        a = self._atr(ctx)
        self._track_exit(ctx)
        if ctx.position is not None:
            self._apply_trail(ctx)
            return
        if not self._cool(ctx):
            return
        side, a = self._fade_signal(ctx)
        if side == 0 or not a > 0:
            return
        c = ctx.close
        self._take(ctx, side, c - side * self.stop_atr * a)


class N5FundingFade(_FadeLeg):
    name = "n5_ff"
    hypothesis = (
        "When the funding rate spikes against its own recent history while "
        "price chases in the same direction and taker flow contradicts it, "
        "the crowd is offside and the move reverses."
    )
    mechanism = (
        "Funding is the price longs pay shorts to hold a perp. A funding "
        "z-spike means positioning has become one-sided, and someone is "
        "paying to stay there. If price is chasing up while the taker delta "
        "is negative, the buying is leveraged perp demand rather than real "
        "purchase, and the people on the other side are the market makers who "
        "will be squeezing those positions out. The fade is a bet on who can "
        "hold the position longer. It fails when the crowd is right and the "
        "trend simply continues, which is why it needs a stop rather than "
        "conviction."
    )
    variation = (
        "Locked live values with u37's widened stop: funding z over 75 bars, "
        "threshold 1.25 on the cross, 12-bar return and 12-bar delta sum as "
        "confirmation, stop 2.5 Wilder ATR, rr 2.0, 24-bar hold, no cooldown."
    )
    references = ["trading-bots: scalping/strategy_funding_fade.py (LOCKED), "
                  "bot_upcomers37.FF_STOP=2.5"]

    gauge, stop_atr = "funding", 2.5
    rr, max_hold, cooldown, trail_r = 2.0, 24, 0, 0.0
    params = {"risk_pct": 0.005, "atr_len": 14,
              "z_win": 75, "z_thr": 1.25, "ret_win": 12}


class N5LsrFade(_FadeLeg):
    name = "n5_lsr"
    hypothesis = (
        "When the share of accounts positioned long spikes against its own "
        "history while price chases and flow contradicts, the retail crowd is "
        "offside and the move reverses."
    )
    mechanism = (
        "Same trade as funding fade, but the crowding gauge is Bybit's "
        "account long/short ratio - a direct count of how many ACCOUNTS are "
        "on each side, which weights small traders heavily. The claim is that "
        "the account count is a cleaner read on retail than funding, because "
        "funding also moves for basis and hedging reasons that have nothing "
        "to do with crowding. The counterparty is whoever is filling those "
        "accounts. Note this leg has never traded BTC live: it was fitted on "
        "ADA, LINK, SOL and XRP, where retail concentration is higher."
    )
    variation = (
        "Locked live values with u44's widened stop: buy_ratio z over 100 "
        "bars, threshold 1.25 on the cross, 8-bar return and delta sum, stop "
        "3.5 Wilder ATR, rr 4.0, 48-bar hold, no cooldown."
    )
    references = ["trading-bots: scalping/strategy_lsr_fade.py (LOCKED), "
                  "bot_upcomers44.LSR_STOP_ATR=3.5"]

    gauge, stop_atr = "buy_ratio", 3.5
    rr, max_hold, cooldown, trail_r = 4.0, 48, 0, 0.0
    params = {"risk_pct": 0.005, "atr_len": 14,
              "z_win": 100, "z_thr": 1.25, "ret_win": 8}


class N5OiFade(_FadeLeg):
    name = "n5_oi"
    hypothesis = (
        "The LSR fade, but only when open interest is also rising - so the "
        "crowd is not just leaning one way, it is adding leverage to do it."
    )
    mechanism = (
        "Open interest rising while the account ratio spikes means new "
        "positions are being opened rather than existing ones rotating. New "
        "leveraged positions are the fuel for a squeeze: they have margin "
        "that can be called. That extra condition is meant to separate real "
        "crowding from a shift in who holds the same risk. The cost is "
        "sample - requiring a third condition cuts the trade count, and this "
        "leg also never traded BTC live (basket SOL/XRP/ADA/BCH)."
    )
    variation = (
        "Locked live values with u37's widened stop: buy_ratio z over 100 "
        "bars, threshold 1.25, 8-bar return and delta sum, 8-bar open "
        "interest change must be positive, stop 5.0 Wilder ATR, rr 4.0, "
        "48-bar hold, no cooldown."
    )
    references = ["trading-bots: scalping/strategy_oi_fade.py (LOCKED), "
                  "bot_upcomers37.OI_STOP=5.0"]

    gauge, stop_atr = "buy_ratio", 5.0
    rr, max_hold, cooldown, trail_r = 4.0, 48, 0, 0.0
    params = {"risk_pct": 0.005, "atr_len": 14,
              "z_win": 100, "z_thr": 1.25, "ret_win": 8}

    def _fade_signal(self, ctx: Context):
        side, a = super()._fade_signal(ctx)
        if side == 0:
            return side, a
        n = ctx.params["ret_win"]
        oi = _feed(ctx, "oi", n + 1)
        if len(oi) < n + 1 or not oi[0] > 0:
            return 0, a
        if not (oi[-1] / oi[0] - 1.0) > 0:      # leverage must be BUILDING
            return 0, a
        return side, a


class N5DeltaAbsorption(_N5Leg):
    name = "n5_delta_absorption"
    hypothesis = (
        "A new extreme in price that is NOT confirmed by a new extreme in "
        "cumulative taker delta means the move is being absorbed, and it "
        "reverses back with the longer trend."
    )
    mechanism = (
        "Price makes a fresh 96-bar low, but the 16-bar delta sum is HIGHER "
        "than it was at the previous such low. Sellers are still hitting the "
        "bid, yet less aggressively than last time price was here - someone "
        "is absorbing that supply without letting price fall further. That "
        "someone is a passive buyer with size, and absorption is the visible "
        "footprint of them filling. The trend filter keeps it from fading a "
        "genuine breakdown, and the funding condition keeps it from buying "
        "when longs are already paying to be there."
    )
    variation = (
        "Locked live values: 96-bar extreme, 16-bar delta sum, minimum 5 bars "
        "between compared extremes, 400-bar SMA trend filter, funding "
        "threshold 0.0, stop 1.5 Wilder ATR beyond the extreme, rr 4.0, "
        "120-bar hold, 1.5R trail, cooldown 1."
    )
    references = ["trading-bots: scalping/strategy_delta_absorption.py "
                  "(LOCKED), bot_upcomers35._sig_da"]

    rr, max_hold, cooldown, trail_r = 4.0, 120, 1, 1.5
    params = {"risk_pct": 0.005, "atr_len": 14,
              "win": 96, "dsum": 16, "atr_mult": 1.5, "fthr": 0.0,
              "trend_win": 400}

    def on_start(self, ctx: Context) -> None:
        super().on_start(ctx)
        ctx.state.update(last_low=None, last_high=None)

    def on_bar(self, ctx: Context) -> None:
        p = ctx.params
        a = self._atr(ctx)
        self._track_exit(ctx)

        need = max(p["win"] + p["dsum"], p["trend_win"]) + 2
        if ctx.bars_seen < need or not a > 0:
            return

        s = ctx.state
        bar = ctx.bar
        dd = float(np.sum(_feed(ctx, "delta", p["dsum"])))
        fr = float(_feed(ctx, "funding", 1)[-1])
        lows, highs = ctx.series("low", p["win"]), ctx.series("high", p["win"])
        sma = float(np.mean(ctx.series("close", p["trend_win"])))
        stop_dist = a * p["atr_mult"]

        at_low = bar.low <= float(np.min(lows))
        at_high = bar.high >= float(np.max(highs))
        # the extremes must be recorded on EVERY bar that makes one, whether or
        # not it trades - the comparison is against the previous extreme, not
        # the previous trade
        prev_low, prev_high = s["last_low"], s["last_high"]
        if at_low:
            s["last_low"] = (ctx.i, dd)
        if at_high:
            s["last_high"] = (ctx.i, dd)

        if ctx.position is not None:
            self._apply_trail(ctx)
            return
        if not self._cool(ctx) or fr != fr:
            return

        if at_low and prev_low is not None:
            if (dd > prev_low[1] and ctx.i - prev_low[0] >= 5
                    and bar.close > sma and fr <= p["fthr"]):
                self._take(ctx, +1, bar.low - stop_dist)
                return
        if at_high and prev_high is not None:
            if (dd < prev_high[1] and ctx.i - prev_high[0] >= 5
                    and bar.close < sma and fr >= -p["fthr"]):
                self._take(ctx, -1, bar.high + stop_dist)
