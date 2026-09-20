"""Pin the search-cost arithmetic to the published worked examples.

These are not smoke tests. `core/searchcost.py` decides what bar a result has to
clear, so a silent change to it silently re-scores every hypothesis in the
project. The paper's own worked example is the only external anchor available,
and it is checked here.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core import searchcost as S  # noqa: E402


def test_min_backtest_length_matches_the_paper():
    """Bailey, Borwein, Lopez de Prado & Zhu (2014) worked example: 45 trials
    need 5 years of history before an in-sample Sharpe of 1 means anything."""
    assert S.min_backtest_years(45) == pytest.approx(5.0, abs=0.01)


def test_one_trial_is_free_and_more_trials_cost_more():
    """The arithmetic reward for pre-registering: at N=1 the luck threshold is
    zero, so the deflated Sharpe collapses to the plain probabilistic one."""
    assert S.expected_max_z(1) == 0.0
    assert S.sr_threshold(0.04, 1) == 0.0
    zs = [S.expected_max_z(n) for n in (1, 10, 48, 228, 8160)]
    assert zs == sorted(zs)
    assert zs[-1] > 3.0


def test_deflated_sharpe_falls_as_the_search_widens():
    """One arm passes, the same arm found by a wide sweep does not."""
    sr, n_obs, var = 0.12, 750, 0.0036   # per-observation Sharpe, 3y of days
    alone = S.deflated_sharpe(sr, n_obs, var, n_trials=1)
    searched = S.deflated_sharpe(sr, n_obs, var, n_trials=228)
    assert alone > searched
    assert alone > 0.95


def test_negative_skew_costs_you():
    """H-027's profit is one big winner in five and `docs/FIRMS.md` measures a
    single day at 76-95% of all profit. The probabilistic Sharpe must price that
    shape below an even series with the same Sharpe."""
    even = S.probabilistic_sharpe(0.1, 500, skew=0.0, kurtosis=3.0)
    lumpy = S.probabilistic_sharpe(0.1, 500, skew=-1.5, kurtosis=9.0)
    assert lumpy < even


def test_effective_trials_needs_returns_not_sharpes():
    rng = np.random.default_rng(0)
    indep = rng.normal(size=(2000, 20))
    assert S.effective_trials(indep) == pytest.approx(20, rel=0.15)

    base = rng.normal(size=(2000, 1))
    clones = base + 0.01 * rng.normal(size=(2000, 20))
    assert S.effective_trials(clones) < 2.0


def test_pbo_flags_a_selector_that_picks_noise():
    """Twenty pure-noise columns: the in-sample winner should land below the
    out-of-sample median about half the time, so PBO sits near 0.5."""
    rng = np.random.default_rng(7)
    noise = rng.normal(size=(1600, 20))
    r = S.pbo_cscv(noise, n_subsets=8)
    assert r.n_splits == S.n_cscv_splits(8) == 70
    assert 0.3 < r.pbo < 0.7

    signal = noise.copy()
    signal[:, 0] += 0.25          # one column with a genuine, stable edge
    good = S.pbo_cscv(signal, n_subsets=8)
    assert good.pbo < r.pbo


def test_accounts_consumed_is_what_the_board_omits():
    """39.3% pass is 2.5 evaluations per funded seat, not a free 15.3 days."""
    assert S.accounts_consumed(0.393) == pytest.approx(2.544, abs=0.01)
    assert S.cost_per_funded(61, 0.637) == pytest.approx(95.8, abs=0.5)
    assert S.accounts_consumed(0.0) == float("inf")


def test_ev_per_evaluation_signs():
    """FundingPips 1-Step Flex on the shipped rule: EUR 61, 63.7% pass, 10%
    target on a 5k account. Positive at face value, negative once the published
    share of funded accounts that ever withdraw is applied."""
    optimistic = S.ev_per_evaluation(61, 0.637, 5000, 0.10, split=0.9)
    realistic = S.ev_per_evaluation(61, 0.637, 5000, 0.10, split=0.9,
                                    payout_rate=0.45)
    assert optimistic > 0
    assert realistic < optimistic
