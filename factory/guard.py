"""STEP 2's ONE GUARANTEE — a strategy cannot read a bar it has not reached.

WHY THIS FILE IS THE MOST IMPORTANT ONE IN `factory/`.

Every other check in the workflow is a statistic, and **no statistic catches a
leak.** arXiv 2608.27734 planted an oracle with Sharpe 34.7 and the deflation
machinery scored it a perfect 1.00. A leaking strategy is not overfit - it is
genuinely predictive, of data it should not have had. The paired null, the luck
check and the 5-year re-check all pass it happily, because it really does
predict.

This repo has found three look-ahead bugs by hand already (`CLAUDE.md`). The
plan is now to translate thousands of outside strategies automatically. One
translator bug would silently poison every number downstream and nothing in
steps 3 to 7 would notice.

So the guarantee has to be STRUCTURAL. `Window` is a read-only view of history
that ends at the current bar. Reading further does not return a wrong answer or
a NaN - it raises `LookAheadError` and the run dies loudly.

    w = Window(frame, t=100)
    w.close[-1]        # this bar's close            OK
    w.close[-20:]      # the last twenty closes      OK
    w.close[101]       # tomorrow                    LookAheadError
    w.full             # the whole frame             AttributeError

**The negative index is the only way in.** `w.close[-1]` is the newest bar the
strategy is allowed to see, and there is no positive indexing and no attribute
that reaches the underlying frame, so "read one bar ahead" is not a mistake
that can be made - it is a sentence that cannot be written.

WHAT IT DOES NOT COVER. It guards the DECISION. Filling, stops and targets are
the engine's job and have their own rules in `CLAUDE.md` - a stop that gaps
fills at the open, a padded weekend bar is never traded. Those bugs live
downstream of here and this file does not pretend to catch them.
"""
from __future__ import annotations

import numpy as np


class LookAheadError(Exception):
    """A strategy tried to read a bar that had not happened yet."""


class Series:
    """One column of history, ending at the current bar. Past-only by shape."""

    __slots__ = ("_a", "_name")

    def __init__(self, a: np.ndarray, name: str):
        self._a, self._name = a, name

    def __getitem__(self, k):
        if isinstance(k, slice):
            if (k.start is not None and k.start >= 0) or \
               (k.stop is not None and k.stop > 0):
                raise LookAheadError(
                    f"{self._name}[{k.start}:{k.stop}] - slices must be negative, "
                    "e.g. [-20:]. Positive indices could reach the future.")
            return self._a[k]
        if k >= 0:
            raise LookAheadError(
                f"{self._name}[{k}] - only negative indices are allowed. "
                "[-1] is the current bar, [-2] the one before it.")
        if -k > len(self._a):
            raise LookAheadError(
                f"{self._name}[{k}] - only {len(self._a)} bars have happened.")
        return self._a[k]

    def __len__(self) -> int:
        return len(self._a)

    def __array__(self, dtype=None):          # np.mean(w.close[-20:]) etc.
        return self._a if dtype is None else self._a.astype(dtype)

    def __repr__(self) -> str:
        return f"<Series {self._name} {len(self._a)} bars, ends at the current one>"


class Window:
    """Everything a strategy is allowed to know at bar `t`.

    Built once per bar. Holds a VIEW, not a copy, so the cost is a pointer -
    which matters when a 22,000-bar backtest builds 22,000 of them.
    """

    #: `hour` is UTC hour of day, added 2026-09-22 for step 4's session
    #: repairs. It is a property OF BAR t and of no other bar, so it cannot
    #: leak: knowing that the current bar is 14:00 says nothing about the next
    #: one's price. It is carried as a column by `factory/cells.py` because
    #: `build.run` drops the DatetimeIndex before the strategy ever runs.
    COLUMNS = ("open", "high", "low", "close", "volume", "hour")

    __slots__ = COLUMNS + ("t", "_n")

    def __init__(self, frame, t: int):
        if t < 0:
            raise ValueError("t must be >= 0")
        n = t + 1
        self.t, self._n = t, n
        for col in self.COLUMNS:
            arr = frame[col].values[:n] if col in frame else np.zeros(n)
            object.__setattr__(self, col, Series(arr, col))

    def __len__(self) -> int:
        return self._n

    def __repr__(self) -> str:
        return f"<Window at bar {self.t}, {self._n} bars visible>"
