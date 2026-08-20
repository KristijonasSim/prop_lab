"""Indicator arithmetic, checked against values computed by hand."""
from __future__ import annotations

import numpy as np
import pytest

from proplab.strategy import indicators as ind


def test_sma_matches_mean():
    v = np.arange(1.0, 11.0)
    assert ind.sma(v, 5) == pytest.approx(np.mean([6, 7, 8, 9, 10]))
    assert np.isnan(ind.sma(v, 50))


def test_true_range_uses_previous_close():
    high = np.array([10.0, 12.0])
    low = np.array([9.0, 11.5])
    close = np.array([9.5, 12.0])
    tr = ind.true_range(high, low, close)
    assert tr[0] == pytest.approx(1.0)            # first bar: high - low
    # second bar: max(12-11.5, |12-9.5|, |11.5-9.5|) = 2.5
    assert tr[1] == pytest.approx(2.5)


def test_atr_of_constant_range_is_that_range():
    n = 20
    high = np.full(n + 1, 101.0)
    low = np.full(n + 1, 99.0)
    close = np.full(n + 1, 100.0)
    assert ind.atr(high, low, close, n) == pytest.approx(2.0)


def test_atr_needs_history():
    assert np.isnan(ind.atr(np.ones(3), np.ones(3), np.ones(3), 20))


def test_donchian_excludes_the_current_bar():
    """The whole point: including the current bar makes a close-above-highest
    breakout impossible, since that bar's own high is >= its close."""
    high = np.array([10.0, 11.0, 12.0, 20.0])
    assert ind.donchian_high(high, 3, exclude_current=True) == pytest.approx(12.0)
    assert ind.donchian_high(high, 3, exclude_current=False) == pytest.approx(20.0)


def test_donchian_low_excludes_current():
    low = np.array([10.0, 9.0, 8.0, 1.0])
    assert ind.donchian_low(low, 3, exclude_current=True) == pytest.approx(8.0)


def test_donchian_needs_enough_history():
    assert np.isnan(ind.donchian_high(np.array([1.0, 2.0]), 10))


def test_realised_vol_scales_with_sqrt_time():
    rng = np.random.default_rng(0)
    daily = 0.02
    closes = 100 * np.exp(np.cumsum(rng.normal(0, daily, 5000)))
    v = ind.realised_vol(closes, 4000, periods_per_year=365)
    assert v == pytest.approx(daily * np.sqrt(365), rel=0.1)
