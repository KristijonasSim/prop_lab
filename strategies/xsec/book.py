"""H-042 cross-sectional book: weights, turnover and cost. Pre-reg: XSEC.md.

THIS FILE IS THE COST ACCOUNTING AND IT IS WRITTEN BEFORE THE SIGNAL CODE,
because the pre-registration names turnover as the most likely way the idea
dies. Eleven coins, four legs, rebalanced every four hours is roughly six round
trips a day at 14 bps; a gross spread of 5 bps against a 20 bps bill is dead
however well the ranking works, and a bug that charged cost once per rebalance
instead of once per unit of weight CHANGED would hide exactly that.

Every function here is covered by `tests/test_xsec.py` on hand-worked numbers.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

#: 1x cost, matching `strategies/orderflow/orderflow.ROUND_TRIP_BPS`:
#: (5bps taker + 2bps slippage) per side, both sides.
ROUND_TRIP_BPS = 14.0
SIDE_BPS = ROUND_TRIP_BPS / 2.0


def weights_from_ranks(z: pd.Series, k: int) -> pd.Series:
    """Dollar-neutral weights from one cross-section of signal values.

    `z` is one row: the signal per coin at one rebalance. SHORT the `k` highest
    (most crowded long, which H-006 says is the bearish side) and LONG the `k`
    lowest, each side carrying total weight 1.0 so gross exposure is 2.0 and net
    is 0.0 by construction.

    Coins with no signal are simply absent from the ranking - never filled with
    a zero, because a missing reading is not a neutral reading.
    """
    s = z.dropna()
    if len(s) < 2 * k:
        return pd.Series(0.0, index=z.index)
    order = s.sort_values()
    w = pd.Series(0.0, index=z.index)
    w[order.index[:k]] = 1.0 / k          # least crowded -> long
    w[order.index[-k:]] = -1.0 / k        # most crowded  -> short
    return w


def turnover(prev: pd.Series, new: pd.Series) -> float:
    """Gross weight changed between two books, in units of notional.

    Sum of |dw| over every name. A full flip of one 1.0-weight leg is 2.0 of
    turnover, not 1.0, because it is a sale and a purchase - that factor of two
    is the bug this function exists to make impossible to write.
    """
    a, b = prev.align(new, fill_value=0.0)
    return float(np.abs(b - a).sum())


def cost_of(turn: float, cost_mult: float = 1.0) -> float:
    """Cost of `turn` units of turnover, as a return on gross book value.

    Charged per SIDE: turnover already counts both the sale and the purchase,
    so each unit of it pays one side's cost, not a round trip.
    """
    return turn * (SIDE_BPS / 1e4) * cost_mult


def period_return(w: pd.Series, rets: pd.Series) -> float:
    """Book return over one holding period, gross of cost.

    Weights are held fixed across the period - this is a rebalanced book, not a
    continuously reweighted one, and the drift inside a period is deliberately
    ignored because rebalancing it would create turnover the cost model does not
    see.
    """
    a, b = w.align(rets, fill_value=0.0)
    return float((a * b).sum())
