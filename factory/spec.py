"""The STRATEGY GRAMMAR — what an idea is allowed to say, and nothing more.

WHY A GRAMMAR AND NOT CODE. Step 1 pulls ideas from outside - a TradingView
script, a paper, the bot's own invention. Step 2 has to turn them into
something runnable. If that translation emits arbitrary Python, then one bad
translation is a look-ahead bug, and `factory/guard.py` explains why no
statistic downstream would ever catch it.

So an idea is not code. It is a handful of choices from fixed sets, exactly
like `research/vocab.py` does for feeds. `build.py` is the only thing that
touches a price. A translator's whole job is to fill this struct in, and the
worst it can do is fill it in wrongly - which shows up as a strategy that does
not behave like the original, not as a strategy that cheats.

WHAT THIS FIXES. `research/vocab.py` has four transforms and all four are
CONTINUOUS - level, change, zscore, pctile. Measured 2026-09-21
(`research/poscontrol.py`): that makes the loop unable to express an
intermittent signal at all, including H-027's own shape. **CROSS_ABOVE and
CROSS_BELOW are here for that reason.** They fire on a bar and are silent the
rest of the time, which is what a trading rule actually looks like and what
most of TradingView is made of.

THE SIZE OF THE SPACE IS THE POINT, NOT A BUG. Nine indicators, four
comparisons, and up to two conditions is already large. `queue.py` refuses a
fingerprint it has seen, so the same idea wearing a different name is tested
once.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

import numpy as np

# --------------------------------------------------------------------------
# Indicators. Each takes a guard.Window and returns a float for THIS bar, or
# nan when there is not enough history. None of them can see past the window.
# --------------------------------------------------------------------------
def _need(w, n):
    return len(w) >= n

def _price(w, _n=0):      return float(w.close[-1])
def _sma(w, n):           return float(np.mean(w.close[-n:])) if _need(w,n) else np.nan
def _ema(w, n):
    if not _need(w, n): return np.nan
    a = 2.0/(n+1.0); x = np.asarray(w.close[-(4*n):], dtype=float)
    e = x[0]
    for v in x[1:]: e = a*v + (1-a)*e
    return float(e)
def _highest(w, n):
    """The highest high of the n bars BEFORE this one.

    Excluding the current bar is not a detail, it is the whole indicator. With
    the current bar included, `highest` is always >= this bar's high, which is
    always >= its close - so `close > highest(n)` can never be true and every
    breakout rule in the grammar silently produced zero trades. Found by
    running the queue end to end on gold, 2026-09-21.
    """
    return float(np.max(w.high[-(n+1):-1])) if _need(w, n+1) else np.nan


def _lowest(w, n):
    return float(np.min(w.low[-(n+1):-1])) if _need(w, n+1) else np.nan
def _stdev(w, n):         return float(np.std(np.asarray(w.close[-n:], dtype=float))) if _need(w,n) else np.nan
def _roc(w, n):
    if not _need(w, n+1): return np.nan
    a = np.asarray(w.close[-(n+1):], dtype=float)
    return float((a[-1]-a[0])/a[0]*1e4) if a[0] else np.nan
def _rsi(w, n):
    if not _need(w, n+1): return np.nan
    d = np.diff(np.asarray(w.close[-(n+1):], dtype=float))
    up, dn = d.clip(min=0).mean(), (-d).clip(min=0).mean()
    if dn == 0: return 100.0
    return float(100 - 100/(1 + up/dn))
def _atr(w, n):
    if not _need(w, n+1): return np.nan
    h = np.asarray(w.high[-n:], dtype=float); l = np.asarray(w.low[-n:], dtype=float)
    c = np.asarray(w.close[-(n+1):-1], dtype=float)
    return float(np.mean(np.maximum(h-l, np.maximum(abs(h-c), abs(l-c)))))

def _wpr(w, n):
    """Williams %R over n bars: 0 at the top of the range, -100 at the bottom.

    ADDED 2026-09-23, from Kris's first real TradingView script. "Boxes PRO"
    is built on a fast/slow %R pair and the grammar had no oscillator bounded
    to a price RANGE - `rsi` measures the size of up moves against down moves,
    which is a different quantity and cannot stand in for it.

    THE CURRENT BAR IS INCLUDED HERE, unlike `_highest`. The two exclude or
    include for the same reason: `highest` is a level price must BREAK, so a
    bar cannot break its own high; %R asks where this bar's close sits INSIDE
    the recent range, which is meaningless without the bar in it. Pine's
    ta.wpr does the same.
    """
    if not _need(w, n):
        return np.nan
    hi = float(np.max(w.high[-n:]))
    lo = float(np.min(w.low[-n:]))
    rng = hi - lo
    if rng <= 0:
        return np.nan                 # a flat range has no position in it
    return float(100.0 * (float(w.close[-1]) - hi) / rng)


def _hour(w, _n=0):
    """UTC hour of THIS bar, 0-23. The session filter, expressed in the grammar.

    A window is `hour above 6.5 and hour below 16.5`, which is 07:00-16:00
    inclusive - two ordinary conditions, so no new comparison is needed. The
    half-integers are deliberate: `above`/`below` are strict, and a hour of 7
    must satisfy "after 6.5" rather than sit on a boundary.

    ZERO WHEN THE COLUMN IS ABSENT, which makes every hour condition false on a
    frame that has no clock. That is the safe direction - a session filter that
    silently matched everything would look like a working filter.
    """
    return float(w.hour[-1])


def _vwap(w, n):
    """Volume-weighted average of typical price over the last n bars.

    IT IS A ROLLING VWAP, NOT A SESSION VWAP, and the difference is worth
    stating. H-027 anchors its VWAP to a session and that anchor is the
    strategy; this is a FILTER, and a filter wants a stable reference rather
    than one that resets to the price every morning. A rolling window is also
    bounded, which keeps it inside `guard.Window` where it can be checked,
    instead of needing a precomputed cumulative column the guard cannot see.

    Falls back to the unweighted mean where volume is absent or all zero - a
    padded weekend stretch has no volume and a division by it would be nan.
    """
    if not _need(w, n):
        return np.nan
    tp = (np.asarray(w.high[-n:], dtype=float)
          + np.asarray(w.low[-n:], dtype=float)
          + np.asarray(w.close[-n:], dtype=float)) / 3.0
    v = np.asarray(w.volume[-n:], dtype=float)
    tot = v.sum()
    return float((tp * v).sum() / tot) if tot > 0 else float(tp.mean())


def _ema_arr(x: np.ndarray, n: int) -> np.ndarray:
    """EMA of a whole array in C. Seeded on the first value, like `_ema`."""
    from scipy.signal import lfilter
    a = 2.0 / (n + 1.0)
    y, _ = lfilter([a], [1.0, a - 1.0], x[1:], zi=[(1.0 - a) * x[0]])
    return np.concatenate(([x[0]], y))


def _run_all(ok: np.ndarray, n: int) -> np.ndarray:
    """True at i when ok[i-n+1..i] are all True (integer rolling sum: exact)."""
    k = np.concatenate(([0], np.cumsum(ok.astype(np.int64))))
    out = np.zeros(len(ok), dtype=bool)
    if len(ok) >= n:
        out[n - 1:] = (k[n:] - k[:-n]) == n
    return out


def _squeeze_core(c: np.ndarray, n: int) -> np.ndarray:
    """The squeeze-end event at EVERY bar of `c`, from bar 0's history on.

    Every operation is prefix-stable - a sequential EMA filter, elementwise
    maths, integer rolling sums - so the value at bar t depends on c[:t+1]
    only, and computing it on the whole series or on the prefix gives the
    same float. `tests/test_factory_speed.py` pins that against the
    guard-protected per-bar reader `_squeeze_end`.
    """
    L = 6 * n + 2
    out = np.full(len(c), np.nan)
    if len(c) < 2:
        return out
    ema_c = _ema_arr(c, n)
    safe = np.maximum(np.abs(ema_c), 1e-12)
    nb = np.abs(c - ema_c) / safe
    q = 0.68 * nb * nb + 0.79 * nb + nb
    b = np.abs(np.sin(q) * np.cos(q)) * safe
    d = _ema_arr(b, n)
    hi = _ema_arr(np.maximum(ema_c + d, c), n)
    lo = _ema_arr(np.minimum(c, ema_c - d), n)
    width = hi - lo
    dec = np.concatenate(([False], np.diff(width) < 0))
    falling = _run_all(dec, n)
    ended = np.concatenate(([False], falling[:-1] & ~falling[1:]))
    rp = max(1, n // 5)
    up = np.concatenate(([False], np.diff(lo) > 0))
    dn = np.concatenate(([False], np.diff(hi) < 0))
    wedge = _run_all(up, rp) & _run_all(dn, rp)
    ev = (ended & ~wedge).astype(float)
    out[L - 1:] = ev[L - 1:]
    return out


def _squeeze_end(w, n):
    """1 on the bar a band squeeze ENDS, else 0. The Quadapt ML Trader trigger.

    ADDED 2026-09-24, from Kris's second real TradingView script, which the
    translator refused because the grammar could not say it. The script builds
    an envelope around EMA(n) - a band whose width is an EMA of a sin*cos of
    the normalised distance from it - smooths each edge with a further EMA(n),
    and fires when the edge-to-edge width has been FALLING for n bars on the
    previous bar and is not falling now. A "wedge" (lower edge rising while
    the upper falls, over n/5 bars) vetoes it. Direction is not part of it:
    the script takes the side from its trend filter.

    THIS IS THE REFERENCE READER and it is slow on purpose: it hands the whole
    visible history to `_squeeze_core` through the guard, once per bar. The
    backtest uses `SERIES` instead, computed once; the two are pinned equal.
    EMAs are seeded at the first bar, as Pine seeds them.
    """
    if not _need(w, 6 * n + 2):
        return np.nan
    return float(_squeeze_core(np.asarray(w.close[-len(w):], dtype=float), n)[-1])


#: Indicators that ALSO have a whole-series form, computed once per backtest
#: instead of once per bar. Only for prefix-stable maths, and each one is
#: pinned equal to its per-bar reader in tests/test_factory_speed.py.
SERIES = {
    "squeeze_end": lambda cols, n: _squeeze_core(np.asarray(cols["close"], dtype=float), n),
}

#: name -> (function, does it need a window length?)
INDICATORS = {
    "price":   (_price,   False),
    "sma":     (_sma,     True),
    "ema":     (_ema,     True),
    "rsi":     (_rsi,     True),
    "atr":     (_atr,     True),
    "highest": (_highest, True),
    "lowest":  (_lowest,  True),
    "stdev":   (_stdev,   True),
    "roc":     (_roc,     True),
    # ADDED 2026-09-22 for step 4's repair list. Neither is offered to the
    # idea GENERATOR - `sources/invent.py` does not enumerate them - because
    # they exist to be bolted onto an idea that already nearly works, not to
    # widen the search. See `factory/repair.py`.
    "wpr":     (_wpr,     True),
    "hour":    (_hour,    False),
    "vwap":    (_vwap,    True),
    "squeeze_end": (_squeeze_end, True),
}

#: The comparisons. The two CROSS ones fire on a single bar and are silent
#: otherwise - the shape `research/vocab.py` could not express.
COMPARISONS = ("cross_above", "cross_below", "above", "below")

LENGTHS = (5, 10, 14, 20, 50, 100, 200)
SIDES = ("long", "short")


@dataclass(frozen=True)
class Term:
    """One side of a comparison: an indicator, or a plain number."""
    kind: str                     # an INDICATORS name, or "const"
    length: int = 0
    value: float = 0.0            # only for kind == "const"

    def at(self, w) -> float:
        if self.kind == "const":
            return self.value
        fn, needs_n = INDICATORS[self.kind]
        return fn(w, self.length) if needs_n else fn(w)

    def label(self) -> str:
        if self.kind == "const": return f"{self.value:g}"
        return self.kind if not INDICATORS[self.kind][1] else f"{self.kind}{self.length}"


@dataclass(frozen=True)
class Condition:
    """One comparison, optionally required to have HELD for several bars.

    `hold` ADDED 2026-09-23, and it is the structural gap Kris's first real
    script exposed. Every condition here was a single-bar test, while real
    TradingView scripts are state machines: "Boxes PRO" will not signal until
    momentum has sat in the zone for `i_minBoxBars` bars, which is its entire
    answer to "small boxes / one-bar pokes". With `hold` that is expressible;
    without it the script cannot be translated at all, only refused.

    It reads only bars at or before t, so `guard.Window` still covers it - the
    streak is counted forward as the backtest walks, never looked up.

    `hold` applies to `above` and `below`. A CROSS is a one-bar event by
    definition and "crossed for three bars running" is not a thing, so
    `__post_init__` refuses it rather than quietly ignoring it.
    """
    left: Term
    op: str
    right: Term
    hold: int = 1

    def __post_init__(self):
        if self.hold < 1:
            raise ValueError("hold must be >= 1")
        if self.hold > 1 and self.op.startswith("cross"):
            raise ValueError(f"{self.op} is a one-bar event; hold must be 1")

    def label(self) -> str:
        base = f"{self.left.label()} {self.op} {self.right.label()}"
        return base if self.hold <= 1 else f"{base} for {self.hold} bars"


@dataclass(frozen=True)
class Strategy:
    """A complete, runnable idea. Frozen: step 2 builds it, nothing edits it."""
    name: str
    side: str = "long"                       # which way it trades
    entry: tuple[Condition, ...] = ()        # ALL must hold on the same bar
    stop_atr: float = 2.0                    # stop distance, in ATR(14)
    target_atr: float = 3.0                  # target distance, in ATR(14)
    max_hold: int = 48                       # bars, then close regardless
    source: str = "unknown"                  # where the idea came from
    note: str = ""                           # what it is meant to capture

    def __post_init__(self):
        if self.side not in SIDES:
            raise ValueError(f"side must be one of {SIDES}")
        if not self.entry:
            raise ValueError("a strategy with no entry condition never trades")
        for c in self.entry:
            if c.op not in COMPARISONS:
                raise ValueError(f"unknown comparison {c.op!r}")
            for t in (c.left, c.right):
                if t.kind != "const" and t.kind not in INDICATORS:
                    raise ValueError(f"unknown indicator {t.kind!r}")

    def label(self) -> str:
        return f"{self.side} when " + " and ".join(c.label() for c in self.entry)

    def fingerprint(self) -> str:
        """WHAT IT DOES, not what it is called.

        Two TradingView scripts with different names, authors and colours that
        compute the same thing collapse to the same string here, so `queue.py`
        tests the idea once. The name, the note and the source are deliberately
        NOT part of it.
        """
        # c.label() carries `hold`, so a rule that requires two bars and one
        # that requires one are DIFFERENT ideas to the queue. Without this they
        # collapse to the same fingerprint and the second is dropped as a
        # duplicate of the first.
        terms = "&".join(sorted(c.label() for c in self.entry))
        return (f"{self.side}|{terms}|stop{self.stop_atr:g}"
                f"|tgt{self.target_atr:g}|hold{self.max_hold}")

    def to_dict(self) -> dict:
        return asdict(self)


# --------------------------------------------------------------------------
# SCRIPT PORTS (factory/scripts.py): one TradingView script's own entry signal
# per term. Whole-series form in SERIES; the per-bar reader hands the guarded
# history to the same port, and the two are pinned equal in
# tests/test_factory_scripts.py.
# --------------------------------------------------------------------------
def _register_ports():
    from factory import scripts as _sc

    def _cols(w):
        k = len(w)
        return {c: np.asarray(getattr(w, c)[-k:], dtype=float) for c in
                ("open", "high", "low", "close", "volume", "hour")}

    for kind, (fn, side) in _sc.PORTS.items():
        def series(cols, n, fn=fn, side=side):
            return fn({k: np.asarray(v, dtype=float) for k, v in cols.items()},
                      *( (n,) if n else ()))[side]

        def reader(w, n=0, series=series):
            return float(series(_cols(w), n)[-1])

        SERIES[kind] = series
        INDICATORS[kind] = (reader, False)


_register_ports()
