"""H-042's cost accounting, on hand-worked numbers (`strategies/xsec/book.py`).

The pre-registration (`strategies/xsec/XSEC.md`) names turnover as the most
likely way this hypothesis dies and requires the cost code to be written and
tested BEFORE the signal code. These are the hand-worked examples.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from strategies.xsec.book import (SIDE_BPS, cost_of, period_return,   # noqa: E402
                                  turnover, weights_from_ranks)

COINS = ["A", "B", "C", "D", "E", "F"]


def _z(vals):
    return pd.Series(vals, index=COINS, dtype=float)


def test_the_book_is_dollar_neutral_and_gross_two():
    w = weights_from_ranks(_z([1, 2, 3, 4, 5, 6]), k=2)
    assert w.sum() == pytest.approx(0.0), "the book must net to zero"
    assert w.abs().sum() == pytest.approx(2.0), "gross must be 2.0"


def test_the_most_crowded_are_shorted():
    """H-006's direction, fixed in the pre-registration and not swept: the
    highest crowd ratio is the most crowded long, which is the bearish side."""
    w = weights_from_ranks(_z([1, 2, 3, 4, 5, 6]), k=2)
    assert w["A"] == pytest.approx(0.5) and w["B"] == pytest.approx(0.5)
    assert w["E"] == pytest.approx(-0.5) and w["F"] == pytest.approx(-0.5)
    assert (w[["C", "D"]] == 0).all(), "the middle is not held"


def test_a_missing_reading_is_absent_not_neutral():
    """A coin with no signal must not be rankable. Filling it with zero would
    put an unmeasured coin in the middle of the book and silently trade it."""
    w = weights_from_ranks(_z([1, 2, float("nan"), 4, 5, 6]), k=2)
    assert w["C"] == 0.0
    assert w.abs().sum() == pytest.approx(2.0)
    assert w["A"] == pytest.approx(0.5) and w["F"] == pytest.approx(-0.5)


def test_too_few_names_means_no_book():
    assert (weights_from_ranks(_z([1, 2, None, None, None, None]), k=2) == 0).all()


def test_a_full_flip_is_two_units_of_turnover():
    """THE FACTOR OF TWO. Flipping a +1.0 leg to -1.0 is a sale AND a purchase."""
    prev = pd.Series({"A": 1.0})
    new = pd.Series({"A": -1.0})
    assert turnover(prev, new) == pytest.approx(2.0)


def test_opening_a_book_from_flat_is_gross_turnover():
    w = weights_from_ranks(_z([1, 2, 3, 4, 5, 6]), k=2)
    assert turnover(pd.Series(dtype=float), w) == pytest.approx(2.0)


def test_an_unchanged_book_costs_nothing():
    w = weights_from_ranks(_z([1, 2, 3, 4, 5, 6]), k=2)
    assert turnover(w, w) == pytest.approx(0.0)
    assert cost_of(turnover(w, w)) == pytest.approx(0.0)


def test_cost_is_charged_per_side_not_per_round_trip():
    """Turnover already counts both legs of a switch, so one unit of it pays ONE
    side. Charging a round trip per unit would double the bill."""
    assert cost_of(1.0) == pytest.approx(SIDE_BPS / 1e4)
    assert cost_of(2.0, 1.0) == pytest.approx(2 * SIDE_BPS / 1e4)
    assert cost_of(2.0, 3.0) == pytest.approx(6 * SIDE_BPS / 1e4)


def test_opening_a_fresh_book_costs_one_round_trip_of_gross():
    """Sanity in the units Kris reads: a 2.0-gross book opened from flat pays
    2 x 7bps = 14bps, which is exactly one round trip on the gross."""
    w = weights_from_ranks(_z([1, 2, 3, 4, 5, 6]), k=2)
    assert cost_of(turnover(pd.Series(dtype=float), w)) == pytest.approx(14.0 / 1e4)


def test_period_return_is_the_weighted_sum():
    w = weights_from_ranks(_z([1, 2, 3, 4, 5, 6]), k=2)
    rets = _z([0.01, 0.01, 0.99, 0.99, -0.02, -0.02])   # C,D unheld and huge
    # +0.5*0.01 +0.5*0.01 -0.5*-0.02 -0.5*-0.02 = 0.01 + 0.02 = 0.03
    assert period_return(w, rets) == pytest.approx(0.03)


def test_a_coin_with_no_return_contributes_nothing():
    w = weights_from_ranks(_z([1, 2, 3, 4, 5, 6]), k=2)
    rets = pd.Series({"A": 0.10})           # every other coin missing
    assert period_return(w, rets) == pytest.approx(0.05)
