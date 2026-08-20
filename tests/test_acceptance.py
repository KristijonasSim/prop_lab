"""The acceptance bar, in tiers.

Tier 1 (validity) and Tier 2 (viability) decide acceptance. Tier 3 raises
flags to argue about but never auto-rejects - judgement has to live somewhere,
and it should not live in whether the result is real.
"""
from __future__ import annotations

import pytest

from proplab.core.types import BacktestResult
from proplab.research.acceptance import (AcceptanceCriteria, profile,
                                         required_t_stat, score)


class Fake(BacktestResult):
    """A result that clears everything, so tests can break one thing at a time."""

    def __init__(self, **over):
        super().__init__()
        self.metrics = {
            "n_trades": 400, "profit_factor": 1.6, "avg_r": 0.25, "t_stat": 5.0,
            "sharpe": 3.2, "days_tested": 700, "trades_per_day": 4.0,
            "avg_hold_hours": 6.0, "win_rate_pct": 48.0, "cagr_pct": 22.0,
            "max_drawdown_pct": 3.0, "starting_balance": 100_000.0,
            "best_trade_pct_of_profit": 12.0,
            "resolution": {"expected_days_to_resolution": 9.0,
                           "p_target_before_breach": 0.9,
                           "expected_trades_to_resolution": 36.0},
        }
        self.metrics.update(over.pop("metrics", {}))
        self.prop = {"passed": True,
                     "checks": {"daily_loss_limit": {"worst_day_loss": 1500.0}}}
        self.prop.update(over.pop("prop", {}))
        self.meta = {"bars": 5000, "checks": [{"name": "x", "passed": True}]}
        self.meta.update(over.pop("meta", {}))


def gate(card, name):
    return next(g for g in card["gates"] if g["gate"] == name)


# ----------------------------------------------------- tier 1: validity
def test_a_strong_result_is_accepted():
    card = score(Fake(), n_trials=10)
    assert card["accepted"], card["verdict"]
    assert "ACCEPTED" in card["verdict"]


def test_lookahead_blocks_acceptance_whatever_the_profit():
    card = score(Fake(meta={"checks": [{"name": "scramble", "passed": False}]}),
                 n_trials=10)
    assert not card["accepted"]
    assert "automated checks" in card["failed_validity"]
    assert "not established" in card["verdict"]


def test_missing_automated_checks_block_acceptance():
    card = score(Fake(meta={"checks": []}), n_trials=10)
    assert not card["accepted"]
    assert gate(card, "automated checks")["value"] == "not run"
    assert "automated checks" in card["failed_validity"]


def test_breaking_prop_rules_blocks_acceptance():
    assert "prop rules (OOS)" in score(Fake(prop={"passed": False}),
                                       n_trials=10)["failed_validity"]


def test_too_few_trades_blocks_acceptance():
    assert "OOS trades" in score(Fake(metrics={"n_trades": 20}),
                                 n_trials=10)["failed_validity"]


def test_the_t_stat_bar_rises_with_the_number_of_trials():
    """The main defence against testing many things: 1.96 stops meaning
    anything once forty things have been tried."""
    assert required_t_stat(1) == pytest.approx(1.96, abs=0.01)
    assert required_t_stat(40) == pytest.approx(3.23, abs=0.02)
    marginal = Fake(metrics={"t_stat": 2.5, "sharpe": 0.9})
    assert gate(score(marginal, n_trials=2), "t-stat")["passed"]
    assert not gate(score(marginal, n_trials=200), "t-stat")["passed"]


# ---------------------------------------------------- tier 2: viability
def test_slow_strategies_cannot_be_accepted_however_profitable():
    card = score(Fake(metrics={"resolution": {"expected_days_to_resolution": 400.0,
                                              "p_target_before_breach": 0.99,
                                              "expected_trades_to_resolution": 1600.0}}),
                 n_trials=10)
    assert "days to resolve" in card["failed_viability"]
    assert "cannot clear an evaluation" in card["verdict"]


def test_an_evaluation_decided_by_a_handful_of_trades_is_rejected():
    card = score(Fake(metrics={
        "trades_per_day": 0.5, "avg_r": 3.0,
        "resolution": {"expected_days_to_resolution": 8.0,
                       "p_target_before_breach": 0.9,
                       "expected_trades_to_resolution": 4.0}}), n_trials=10)
    assert "trades per evaluation" in card["failed_viability"]


# ------------------------------- the point: shapes trade off against each other
def test_slow_fat_edge_and_fast_thin_edge_are_both_acceptable():
    """The whole reason per-metric floors were removed. These two strategies
    look nothing alike and are equally acceptable, because the outcome they
    produce is what is gated."""
    slow_fat = Fake(metrics={
        "trades_per_day": 0.8, "avg_r": 1.10, "profit_factor": 2.3,
        "win_rate_pct": 38.0, "avg_hold_hours": 30.0,
        "resolution": {"expected_days_to_resolution": 14.0,
                       "p_target_before_breach": 0.85,
                       "expected_trades_to_resolution": 11.2}})
    fast_thin = Fake(metrics={
        "trades_per_day": 12.0, "avg_r": 0.06, "profit_factor": 1.14,
        "win_rate_pct": 61.0, "avg_hold_hours": 0.8,
        "resolution": {"expected_days_to_resolution": 12.0,
                       "p_target_before_breach": 0.83,
                       "expected_trades_to_resolution": 144.0}})
    for r in (slow_fat, fast_thin):
        assert score(r, n_trials=10)["accepted"], score(r, n_trials=10)["verdict"]


def test_a_thin_profit_factor_only_raises_a_flag_not_a_rejection():
    """PF 1.14 would have failed the old PF >= 1.25 floor outright."""
    card = score(Fake(metrics={"profit_factor": 1.14, "avg_r": 0.06,
                               "trades_per_day": 12.0}), n_trials=10)
    assert card["accepted"]
    assert "profit factor" in card["robustness_flags"]
    assert "flag" in card["verdict"]


# --------------------------------------------------- tier 3: advisory only
def test_robustness_flags_do_not_block_acceptance():
    card = score(Fake(metrics={"max_drawdown_pct": 7.0,
                               "best_trade_pct_of_profit": 80.0}), n_trials=10)
    assert card["accepted"]
    assert {"drawdown margin", "profit concentration"} <= set(card["robustness_flags"])


def test_flags_are_still_reported_so_they_can_be_argued_about():
    card = score(Fake(), n_trials=10, pf_at_2x_costs=0.8)
    assert card["accepted"]
    assert "profit factor @2x costs" in card["robustness_flags"]


def test_sharpe_decay_flag_only_applies_when_in_sample_is_given():
    assert not any(g["gate"].startswith("Sharpe decay")
                   for g in score(Fake(), n_trials=10)["gates"])
    card = score(Fake(), n_trials=10, is_result=Fake(metrics={"sharpe": 12.0}))
    assert "Sharpe decay IS->OOS" in card["robustness_flags"]
    assert card["accepted"]          # advisory, not fatal


# -------------------------------------------------------------- reporting
def test_profile_describes_the_shape_being_traded():
    assert "low-frequency" in profile({"trades_per_day": 0.4, "avg_r": 1.2})
    assert "fat edge" in profile({"trades_per_day": 0.4, "avg_r": 1.2})
    assert "high-frequency" in profile({"trades_per_day": 9.0, "avg_r": 0.05})
    assert "thin edge" in profile({"trades_per_day": 9.0, "avg_r": 0.05})


def test_diagnostics_carry_the_numbers_worth_arguing_over():
    d = score(Fake(), n_trials=10)["diagnostics"]
    for k in ("profit_factor", "avg_r", "win_rate_pct", "trades_per_day",
              "avg_hold_hours", "cagr_pct", "sharpe", "max_drawdown_pct"):
        assert k in d


def test_criteria_are_adjustable_in_one_place():
    loose = AcceptanceCriteria(min_oos_trades=10, max_days_to_resolve=1000.0,
                               min_expected_trades_to_resolution=0.0)
    slow = Fake(metrics={"n_trades": 20, "trades_per_day": 0.1,
                         "resolution": {"expected_days_to_resolution": 400.0,
                                        "p_target_before_breach": 0.9,
                                        "expected_trades_to_resolution": 40.0}})
    assert not score(slow, n_trials=10)["accepted"]
    assert score(slow, n_trials=10, criteria=loose)["accepted"]
