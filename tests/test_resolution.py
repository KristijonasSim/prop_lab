"""The days-to-resolution estimate: how long until target or breach.

Total return says nothing about how long an evaluation takes. These tests pin
the estimator against cases whose answer is known by construction.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from proplab.config import PropFirmRules
from proplab.core.metrics import resolution_estimate

RULES = PropFirmRules(starting_balance=100_000.0, profit_target_pct=8.0,
                      max_drawdown_pct=8.0)


def curve(daily_pnl):
    idx = pd.date_range("2024-01-01", periods=len(daily_pnl) + 1, freq="D", tz="UTC")
    return pd.Series(np.concatenate([[100_000.0], 100_000 + np.cumsum(daily_pnl)]),
                     index=idx)


def test_steady_gain_hits_target_in_the_obvious_number_of_days():
    """+$800/day against an $8,000 target must be ~10 days."""
    est = resolution_estimate(curve([800.0] * 40), RULES, "1d")
    assert est["days_to_target_at_current_rate"] == pytest.approx(10.0, abs=0.5)
    assert est["p_target_before_breach"] > 0.99
    assert "fits a 1-2 week phase" in est["verdict"]


def test_steady_loss_reports_days_to_breach_not_target():
    est = resolution_estimate(curve([-400.0] * 40), RULES, "1d")
    assert est["days_to_target_at_current_rate"] is None
    assert est["days_to_breach_at_current_rate"] == pytest.approx(20.0, abs=1.0)
    assert est["p_target_before_breach"] < 0.01


def _driftless(rng, sigma, n):
    """Exactly zero sample drift. Drawing from N(0, sigma) is not enough: 4000
    draws at sigma=500 land ~7.5/day off zero, which against +/-8000 barriers
    genuinely shifts the odds to ~0.38. The estimator is right to say so, so
    the test has to remove the drift rather than assume it away."""
    x = rng.normal(0, sigma, n)
    return x - x.mean()


def test_symmetric_barriers_with_no_drift_are_a_coin_flip():
    rng = np.random.default_rng(0)
    est = resolution_estimate(curve(_driftless(rng, 500, 4000)), RULES, "1d")
    assert est["p_target_before_breach"] == pytest.approx(0.5, abs=0.02)


def test_asymmetric_barriers_favour_the_nearer_one():
    """Driftless, target 4% but drawdown 8%: the target is half as far, so it
    should be hit first about two thirds of the time."""
    rules = PropFirmRules(starting_balance=100_000.0, profit_target_pct=4.0,
                          max_drawdown_pct=8.0)
    rng = np.random.default_rng(1)
    est = resolution_estimate(curve(_driftless(rng, 500, 4000)), rules, "1d")
    assert est["p_target_before_breach"] == pytest.approx(2 / 3, abs=0.02)


def test_small_drift_against_symmetric_barriers_shifts_the_odds():
    """Sanity check on the above: a real -7.5/day drift is NOT a coin flip."""
    rng = np.random.default_rng(0)
    drifted = _driftless(rng, 500, 4000) - 7.55
    est = resolution_estimate(curve(drifted), RULES, "1d")
    assert est["p_target_before_breach"] == pytest.approx(0.38, abs=0.03)


def test_a_slow_grinder_is_called_too_slow():
    est = resolution_estimate(curve([20.0] * 500), RULES, "1d")
    assert est["expected_days_to_resolution"] > 100
    assert "too slow" in est["verdict"]


def test_too_few_days_says_so_rather_than_guessing():
    est = resolution_estimate(curve([100.0] * 3), RULES, "1d")
    assert "not enough daily observations" in est["verdict"]


def test_flat_equity_never_resolves_rather_than_dividing_by_zero():
    est = resolution_estimate(curve([0.0] * 50), RULES, "1d")
    assert est["expected_days_to_resolution"] is None
    assert "never resolves" in est["verdict"]


def test_monte_carlo_agreement():
    """The analytic estimate must match a brute-force simulation of the same
    random walk - otherwise the formula is wrong, not just approximate."""
    mu, sigma = 120.0, 900.0
    rng = np.random.default_rng(7)
    est = resolution_estimate(curve(rng.normal(mu, sigma, 6000)), RULES, "1d")

    hits, times = 0, []
    for _ in range(4000):
        eq, t = 0.0, 0
        while -8000 < eq < 8000 and t < 5000:
            eq += rng.normal(mu, sigma)
            t += 1
        hits += eq >= 8000
        times.append(t)
    assert est["p_target_before_breach"] == pytest.approx(hits / 4000, abs=0.06)
    assert est["expected_days_to_resolution"] == pytest.approx(np.mean(times), rel=0.30)
