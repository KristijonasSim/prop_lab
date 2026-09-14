"""One interface over every kernel. Item 4 of `STEPS_1_2_4.md`.

`core/KERNEL_CONTRACT.md` section 1 is the valuable part and it is already true
of both kernels; this file only gives it a name in code. The class shape is
negotiable, the contract is not.

WHY THIS IS SAFE, AND ALSO WHY IT IS NOT URGENT. Everything downstream - `sweep`,
the walk-forward, the paired null, `core/board.py`, `core/riskladder`,
`core/scorecard` - already works off the `(n, 8)` trade array and does not care
which kernel produced it. The integration point exists. This adds a declaration
and a conformance check, and moves no arithmetic.

WHAT IT BUYS. Three things a bare convention did not:

  1. An invariant written once runs against every kernel. `tests/kernels.py`
     already proved that: 64 tests, both kernels, one adapter - and writing it
     turned up an empty-series crash in both.
  2. A new hypothesis inherits the whole suite instead of reimplementing an
     engine. Twelve hypotheses have died here and most of them rebuilt a
     simulator first.
  3. `conforms()` states the contract as executable checks, so "we follow the
     kernel contract" stops being a claim in a markdown file.

WHAT IT DOES NOT BUY. Not one board number moves. This is a refactor. The pace
problem - 143.6 and 175.9 expected days against a 5-14 day target - is untouched
by everything in items 1 through 4.
"""
from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

import numpy as np
import pandas as pd

# Columns 0-6 are fixed for every kernel. Column 7 is deliberately per-kernel:
# vwap stores the session index, ribbon the maximum favourable excursion.
T_ENTRY_I, T_EXIT_I, T_DIR, T_ENTRY_PX, T_EXIT_PX, T_R, T_REASON = range(7)
T_EXTRA = 7
N_COLS = 8

COLUMNS = ("entry_i", "exit_i", "dir", "entry_px", "exit_px", "r", "reason",
           "extra")


@runtime_checkable
class Strategy(Protocol):
    """What a hypothesis must provide. See KERNEL_CONTRACT.md section 1."""

    name: str

    def features(self, df: pd.DataFrame) -> Any:
        """Everything the kernel needs that does not depend on the config.

        MUST NOT look forward. Enforced by `tests/test_no_lookahead.py`, which
        truncates the series and requires every already-closed trade to come back
        byte-identical.
        """

    def grid(self) -> list[dict]:
        """Every configuration this hypothesis wants tested."""

    def run(self, df: pd.DataFrame, cfg: dict,
            fee_bps: float, slip_bps: float) -> np.ndarray:
        """One configuration, one market. Returns the (n, 8) trade array.

        Signals on closed bars, fills at the next bar's open, stop wins every
        tie, costs charged both sides, risk fixed-fractional against the initial
        stop, and no decision, fill or EXIT on a bar where nothing traded.
        """


def conforms(trades: np.ndarray, n_bars: int) -> list[str]:
    """Check a trade array against the contract. Returns the violations.

    Deliberately a function over the OUTPUT rather than a check on the class:
    a kernel is what it produces, and a Protocol can only assert that methods
    exist.
    """
    bad: list[str] = []
    if trades.ndim != 2 or trades.shape[1] != N_COLS:
        return [f"shape {trades.shape}, expected (n, {N_COLS})"]
    if len(trades) == 0:
        return bad

    ei, xi = trades[:, T_ENTRY_I], trades[:, T_EXIT_I]
    if not np.isfinite(trades[:, :7]).all():
        bad.append("a non-finite value in columns 0-6")
    if (ei < 0).any() or (ei >= n_bars).any():
        bad.append("an entry bar outside the series")
    if (xi < 0).any() or (xi >= n_bars).any():
        bad.append("an exit bar outside the series")
    if (xi < ei).any():
        bad.append("a trade exits before it enters")
    if not np.isin(trades[:, T_DIR], (-1.0, 1.0)).all():
        bad.append("a direction that is neither +1 nor -1")
    if (trades[:, T_ENTRY_PX] <= 0).any() or (trades[:, T_EXIT_PX] <= 0).any():
        bad.append("a non-positive fill price")
    # No overlapping positions: the next entry must not precede the previous
    # exit. Both kernels resume scanning at the exit bar for this reason - a
    # ribbon stays green for long stretches and without it the book is a
    # leveraged hold, not a strategy.
    if len(trades) > 1 and (ei[1:] < xi[:-1]).any():
        bad.append("overlapping positions")
    if (np.diff(ei) < 0).any():
        bad.append("trades not in entry order")
    return bad


def as_frame(trades: np.ndarray, index: pd.DatetimeIndex,
             extra: str = "extra") -> pd.DataFrame:
    """The trade array with timestamps attached, in one place rather than
    re-derived per stage. `extra` names column 7 for the kernel at hand."""
    cols = list(COLUMNS[:-1]) + [extra]
    df = pd.DataFrame(trades, columns=cols)
    if len(df):
        df["entry_ts"] = index[df.entry_i.astype(int)]
        df["exit_ts"] = index[df.exit_i.astype(int)]
    else:
        df["entry_ts"] = pd.Series(dtype="datetime64[ns, UTC]")
        df["exit_ts"] = pd.Series(dtype="datetime64[ns, UTC]")
    return df
