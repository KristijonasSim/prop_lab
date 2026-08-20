"""The acceptance bar. "Is this good?" must be a computation, not a judgement
made while looking at an encouraging number."""
from __future__ import annotations

import pytest

from proplab.core.types import BacktestResult
from proplab.research.acceptance import AcceptanceCriteria, required_t_stat, score


class Fake(BacktestResult):
    """A result good enough to clear every gate, so tests can break one at a time."""

    def __init__(self, **over):
        super().__init__()
        self.metrics = {
            "n_trades": 400, "profit_factor": 1.6, "avg_r": 0.25, "t_stat": 5.0,
            "sharpe": 3.2, "days_tested": 700, "trades_per_day": 4.0,
            "max_drawdown_pct": 3.0, "starting_balance": 100_000.0,
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


def test_a_strong_result_is_accepted():
    card = score(Fake(), n_trials=10)
    assert card["accepted"], card["failed_gates"]
    assert "ACCEPTED" in card["verdict"]


def test_lookahead_failure_blocks_acceptance():
    card = score(Fake(meta={"checks": [{"name": "scramble", "passed": False}]}),
                 n_trials=10)
    assert not card["accepted"]
    assert "automated checks" in card["failed_gates"]


def test_breaking_prop_rules_blocks_acceptance():
    card = score(Fake(prop={"passed": False}), n_trials=10)
    assert "prop rules (OOS)" in card["failed_gates"]


def test_slow_strategies_are_rejected_however_profitable():
    """The current phase needs an evaluation resolved in ~1-2 weeks."""
    card = score(Fake(metrics={"resolution": {"expected_days_to_resolution": 400.0,
                                              "p_target_before_breach": 0.99,
                                              "expected_trades_to_resolution": 1600.0}}),
                 n_trials=10)
    assert "days to resolve" in card["failed_gates"]
    assert not card["accepted"]


def test_too_few_trades_is_rejected():
    card = score(Fake(metrics={"n_trades": 20}), n_trials=10)
    assert "OOS trades" in card["failed_gates"]


def test_thin_edge_per_trade_is_rejected():
    card = score(Fake(metrics={"avg_r": 0.02, "profit_factor": 1.05}), n_trials=10)
    assert "avg R" in card["failed_gates"]
    assert "profit factor" in card["failed_gates"]


def test_a_near_miss_on_the_daily_limit_is_rejected():
    """Surviving by 0.04% in-sample is not margin, it is a coin landing right."""
    card = score(Fake(prop={"passed": True,
                            "checks": {"daily_loss_limit": {"worst_day_loss": 3960.0}}}),
                 n_trials=10)
    assert "worst day %" in card["failed_gates"]


def test_the_t_stat_bar_rises_with_the_number_of_trials():
    """The core defence against testing many strategies: 1.96 means nothing
    once you have tried forty things."""
    assert required_t_stat(1) == pytest.approx(1.96, abs=0.01)
    assert required_t_stat(40) == pytest.approx(3.23, abs=0.02)
    assert required_t_stat(400) > required_t_stat(40) > required_t_stat(1)

    marginal = Fake(metrics={"t_stat": 2.5, "sharpe": 0.9})
    assert score(marginal, n_trials=2)["gates"][5]["passed"]
    assert not score(marginal, n_trials=200)["gates"][5]["passed"]


def test_sharpe_decay_gate_only_applies_when_in_sample_is_given():
    assert not any(g["gate"].startswith("Sharpe decay")
                   for g in score(Fake(), n_trials=10)["gates"])
    is_res = Fake(metrics={"sharpe": 12.0})         # OOS 3.2 vs IS 12.0 = 73% decay
    card = score(Fake(), n_trials=10, is_result=is_res)
    assert "Sharpe decay IS->OOS" in card["failed_gates"]


def test_cost_gate_applies_only_when_supplied():
    assert score(Fake(), n_trials=10, pf_at_2x_costs=0.8)["failed_gates"] == \
        ["profit factor @2x costs"]
    assert score(Fake(), n_trials=10, pf_at_2x_costs=1.4)["accepted"]


def test_criteria_are_adjustable_in_one_place():
    loose = AcceptanceCriteria(min_oos_trades=10, max_days_to_resolve=1000.0,
                               min_trades_per_day=0.0,
                               min_expected_trades_to_resolution=0.0)
    slow = Fake(metrics={"n_trades": 20,
                         "resolution": {"expected_days_to_resolution": 400.0,
                                        "p_target_before_breach": 0.9,
                                        "expected_trades_to_resolution": 40.0},
                         "trades_per_day": 0.1})
    assert not score(slow, n_trials=10)["accepted"]
    assert score(slow, n_trials=10, criteria=loose)["accepted"]


def test_low_frequency_is_allowed_if_the_edge_per_trade_is_big_enough():
    """0.5 trades/day is fine - what matters is trades per EVALUATION. A slow
    strategy with a large edge still fills the window."""
    slow_but_strong = Fake(metrics={
        "trades_per_day": 0.6, "avg_r": 1.2, "profit_factor": 2.4,
        "resolution": {"expected_days_to_resolution": 14.0,
                       "p_target_before_breach": 0.85,
                       "expected_trades_to_resolution": 8.4}})
    card = score(slow_but_strong, n_trials=10)
    assert "trades/day" not in card["failed_gates"]          # 0.6 >= 0.5
    assert "trades per evaluation" in card["failed_gates"]   # 8.4 < 10


def test_an_evaluation_decided_by_a_handful_of_trades_is_rejected():
    coin_flip = Fake(metrics={
        "trades_per_day": 0.5, "avg_r": 3.0,
        "resolution": {"expected_days_to_resolution": 8.0,
                       "p_target_before_breach": 0.9,
                       "expected_trades_to_resolution": 4.0}})
    assert "trades per evaluation" in score(coin_flip, n_trials=10)["failed_gates"]


def test_low_frequency_with_enough_trades_in_the_window_is_accepted():
    ok = Fake(metrics={
        "trades_per_day": 0.9, "avg_r": 0.9, "profit_factor": 2.1,
        "resolution": {"expected_days_to_resolution": 14.0,
                       "p_target_before_breach": 0.86,
                       "expected_trades_to_resolution": 12.6}})
    card = score(ok, n_trials=10)
    assert card["accepted"], card["failed_gates"]
