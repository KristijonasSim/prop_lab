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
    left: Term
    op: str
    right: Term

    def label(self) -> str:
        return f"{self.left.label()} {self.op} {self.right.label()}"


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
        terms = "&".join(sorted(c.label() for c in self.entry))
        return (f"{self.side}|{terms}|stop{self.stop_atr:g}"
                f"|tgt{self.target_atr:g}|hold{self.max_hold}")

    def to_dict(self) -> dict:
        return asdict(self)
