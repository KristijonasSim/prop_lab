"""The four Renko variations.

All four read bricks through ctx.tf("renko"), which only exposes bricks whose
source bar has closed - so a brick is actionable strictly after the bar that
completed it, never at the moment price crossed the level.

Renko hides time. Every one of these reports days-to-resolve, because a
strategy can look excellent and still take three weeks per trade.
"""
from __future__ import annotations

from proplab.core.context import Context
from proplab.strategy.base import Strategy

_HYPOTHESIS = (
    "Renko: stripping time out of the chart and printing a brick only when "
    "price moves a fixed distance filters noise, so what remains is directional "
    "movement worth trading."
)
_MECHANISM = (
    "A time bar prints whether or not anything happened, so most bars are "
    "noise. A brick prints only on real displacement, which removes the "
    "chop that whipsaws time-based trend rules. What survives should be "
    "genuine momentum - the same continuation effect the trend hypothesis "
    "relies on, but with the quiet periods deleted rather than traded through. "
    "The counter-argument, which the test has to settle, is that deleting time "
    "also deletes the information that a move was FAST, and speed is most of "
    "what distinguishes a real move from drift."
)


def _brick_size(view) -> float:
    b = view.bar(0)
    return abs(b.close - b.open) if b else float("nan")


def _flipped(ctx, view, key: str = "last_dir") -> int:
    """Direction of a fresh flip, or 0.

    Compares against the direction remembered from the previous bar rather than
    against the previous brick. A Traditional Renko reversal prints TWO bricks
    at once - both completed by the same source bar - so "the last two bricks
    differ" is never true on a reversal, and a naive check finds no flips at
    all, which is exactly what happened here.
    """
    if not view.ready:
        return 0
    now = int(view.last("direction"))
    prev = ctx.state.get(key)
    ctx.state[key] = now
    if prev is None or now == prev:
        return 0
    return now


class RenkoFlip(Strategy):
    name = "renko_v1_flip"
    hypothesis = _HYPOTHESIS
    mechanism = _MECHANISM
    variation = ("V1 - trade every brick colour flip. The plain baseline: if "
                 "this has no edge, the filtered versions are fitting noise.")
    higher_timeframes = ("renko",)
    params = {"stop_bricks": 2.0, "target_bricks": 3.0, "risk_pct": 0.005,
              "max_bars": 96, "allow_shorts": True}

    def on_bar(self, ctx: Context) -> None:
        v = ctx.tf("renko")
        flip = _flipped(ctx, v)
        if v.n_closed < 3 or ctx.position is not None or flip == 0:
            return
        size = _brick_size(v)
        if not size > 0:
            return
        p, close = ctx.params, ctx.close
        if flip > 0:
            stop = close - p["stop_bricks"] * size
            ctx.buy(stop=stop, target=close + p["target_bricks"] * size,
                    risk_pct=p["risk_pct"], max_bars=p["max_bars"],
                    tag="renko_flip_long", reason="brick flipped up")
        elif p["allow_shorts"]:
            stop = close + p["stop_bricks"] * size
            ctx.sell(stop=stop, target=close - p["target_bricks"] * size,
                     risk_pct=p["risk_pct"], max_bars=p["max_bars"],
                     tag="renko_flip_short", reason="brick flipped down")


class RenkoTrend(Strategy):
    name = "renko_v2_trend"
    hypothesis = _HYPOTHESIS
    mechanism = _MECHANISM + (
        " V2 additionally requires several bricks in a row before committing, "
        "on the argument that one brick is displacement while three is a trend."
    )
    variation = ("V2 - enter after N consecutive same-colour bricks, exit on a "
                 "single opposite brick. Waits for confirmation instead of "
                 "trading the first flip.")
    higher_timeframes = ("renko",)
    params = {"n_bricks": 3, "stop_bricks": 2.0, "risk_pct": 0.005,
              "max_bars": 192, "allow_shorts": True}

    def on_bar(self, ctx: Context) -> None:
        v = ctx.tf("renko")
        p = ctx.params
        if v.n_closed < p["n_bricks"] + 1:
            return
        d = v.series("direction", p["n_bricks"])
        size = _brick_size(v)
        if not size > 0:
            return

        if ctx.position is not None:
            if (ctx.position.is_long and d[-1] < 0) or \
               (not ctx.position.is_long and d[-1] > 0):
                ctx.close_position("opposite_brick")
            return

        if all(x > 0 for x in d):
            ctx.buy(stop=ctx.close - p["stop_bricks"] * size,
                    risk_pct=p["risk_pct"], max_bars=p["max_bars"],
                    tag="renko_trend_long",
                    reason=f"{p['n_bricks']} up bricks in a row")
        elif p["allow_shorts"] and all(x < 0 for x in d):
            ctx.sell(stop=ctx.close + p["stop_bricks"] * size,
                     risk_pct=p["risk_pct"], max_bars=p["max_bars"],
                     tag="renko_trend_short",
                     reason=f"{p['n_bricks']} down bricks in a row")


class RenkoAtrBricks(RenkoTrend):
    name = "renko_v3_atr_bricks"
    variation = ("V3 - identical rules to V2, but the dataset is built with "
                 "ATR-sized bricks instead of a fixed size. A robustness check: "
                 "if V2 works and V3 does not, V2's brick size was fitted to "
                 "one volatility regime rather than chosen for a reason.")
    params = dict(RenkoTrend.params)


class RenkoSession(Strategy):
    name = "renko_v4_session"
    hypothesis = _HYPOTHESIS
    mechanism = _MECHANISM + (
        " V4 adds the one thing already known to matter on this instrument: "
        "the London and New York opens concentrate flow, so a brick flip "
        "during those hours is more likely to be real displacement than one at "
        "04:00 UTC on a Sunday."
    )
    variation = ("V4 - V1's brick flips, but only inside the London or New York "
                 "session windows, and never at weekends.")
    higher_timeframes = ("renko",)
    params = {"stop_bricks": 2.0, "target_bricks": 3.0, "risk_pct": 0.005,
              "max_bars": 96, "allow_shorts": True, "skip_weekends": True,
              "london": ("08:00", "12:00"), "london_tz": "Europe/London",
              "ny": ("09:30", "16:00"), "ny_tz": "America/New_York"}

    def on_bar(self, ctx: Context) -> None:
        p = ctx.params
        v = ctx.tf("renko")
        # Track the flip on EVERY bar, before any filter. If the tracker only
        # ran inside sessions, a flip that happened overnight would surface at
        # the session open and be traded as if it had just occurred.
        flip = _flipped(ctx, v)

        if ctx.position is not None or v.n_closed < 3 or flip == 0:
            return
        if p["skip_weekends"] and ctx.now.weekday() >= 5:
            return
        if not (self._in(ctx, p["london_tz"], *p["london"])
                or self._in(ctx, p["ny_tz"], *p["ny"])):
            return
        size = _brick_size(v)
        if not size > 0:
            return
        close = ctx.close
        if flip > 0:
            ctx.buy(stop=close - p["stop_bricks"] * size,
                    target=close + p["target_bricks"] * size,
                    risk_pct=p["risk_pct"], max_bars=p["max_bars"],
                    tag="renko_session_long", reason="brick flip up in session")
        elif p["allow_shorts"]:
            ctx.sell(stop=close + p["stop_bricks"] * size,
                     target=close - p["target_bricks"] * size,
                     risk_pct=p["risk_pct"], max_bars=p["max_bars"],
                     tag="renko_session_short", reason="brick flip down in session")

    def _in(self, ctx: Context, tz: str, start: str, end: str) -> bool:
        o = ctx.time.tz_convert(tz)
        c = ctx.now.tz_convert(tz)
        sm = int(start[:2]) * 60 + int(start[3:])
        em = int(end[:2]) * 60 + int(end[3:])
        return (o.hour * 60 + o.minute) < em and (c.hour * 60 + c.minute) > sm
