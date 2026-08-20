"""The acceptance bar: what a strategy must clear to be worth paper trading.

Every threshold here is derived from the account rules and from how many
things we have tried - not from taste. The point is that "is this good?"
stops being a judgement call made while looking at an encouraging number.

Where the numbers come from (100k account, 4% daily loss, 8% max loss,
8% target, evaluation to resolve inside ~2 weeks):

  daily P&L = trades_per_day x avg_R x risk_per_trade x equity

  To make 8% in ~10-15 trading days you need roughly 0.5-0.8% per day. That
  is reachable at ~3 trades/day with 0.5R, or ~10 trades/day with 0.2R -
  but NOT at 1 trade/day and 0.2R, which needs 80 days.

  The 4% daily limit has to sit several daily standard deviations away.
  sd ~ sqrt(trades_per_day) x risk_per_trade. Under ~3.5 sd the limit gets
  hit by ordinary bad luck, so sizing must keep it at 4.5 sd or better -
  which caps how hot the strategy can be run, and therefore how fast it can
  reach the target.

  The t-stat bar is Bonferroni-adjusted for the number of trials logged: at
  40 trials a 1.96 t-stat is meaningless, because the best of 40 coin-flip
  strategies clears that routinely. It is computed live, not hardcoded.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict

from scipy import stats

from .multiple_testing import deflated_sharpe


@dataclass(frozen=True)
class AcceptanceCriteria:
    """What "passed" means. Tighten or loosen deliberately, in one place."""

    # --- does it work at all, on data it never saw ---
    require_checks_pass: bool = True        # no lookahead, template-compliant
    require_prop_pass: bool = True          # OOS run breaks no prop-firm rule
    min_profit_factor: float = 1.25
    min_avg_r: float = 0.10

    # --- is the result big enough to be distinguishable from luck ---
    min_oos_trades: int = 100
    bonferroni_alpha: float = 0.05          # adjusted by the trial count
    min_deflated_sharpe: float = 0.95
    max_sharpe_decay: float = 0.50          # IS -> OOS

    # --- can it actually clear an evaluation, and quickly ---
    max_days_to_resolve: float = 15.0
    min_p_target_first: float = 0.80
    min_trades_per_day: float = 0.5
    min_expected_trades_to_resolution: float = 10.0

    # --- margin against the hard limits, not just survival ---
    max_oos_drawdown_pct: float = 5.0       # against an 8% limit
    max_worst_day_pct: float = 2.5          # against a 4% limit

    # --- does it survive the venue being different than assumed ---
    min_profit_factor_at_2x_costs: float = 1.0

    def to_dict(self) -> dict:
        return asdict(self)


def required_t_stat(n_trials: int, alpha: float = 0.05) -> float:
    """Bonferroni-adjusted t threshold for the number of things tried."""
    return float(stats.norm.ppf(1 - (alpha / max(n_trials, 1)) / 2))


def _gate(name, value, threshold, passed, why, higher_is_better=True):
    return {"gate": name, "value": value, "threshold": threshold,
            "passed": bool(passed), "why": why,
            "direction": "min" if higher_is_better else "max"}


def score(oos_result, *, n_trials: int, is_result=None,
          pf_at_2x_costs: float | None = None,
          criteria: AcceptanceCriteria | None = None) -> dict:
    """Grade one out-of-sample run against the bar. Returns every gate."""
    c = criteria or AcceptanceCriteria()
    m, prop = oos_result.metrics, oos_result.prop
    res = m.get("resolution") or {}
    checks = oos_result.meta.get("checks", [])
    gates = []

    gates.append(_gate(
        "automated checks", "pass" if all(x["passed"] for x in checks) else "FAIL",
        "pass", not checks or all(x["passed"] for x in checks),
        "Lookahead or template violations invalidate everything else."))

    gates.append(_gate(
        "prop rules (OOS)", "PASS" if prop.get("passed") else "FAIL", "PASS",
        prop.get("passed") or not c.require_prop_pass,
        "Profitable but rule-breaking is not tradeable on an evaluation."))

    n = m.get("n_trades") or 0
    gates.append(_gate("OOS trades", n, c.min_oos_trades, n >= c.min_oos_trades,
                       "Few trades means the result is mostly luck."))

    pf = m.get("profit_factor")
    gates.append(_gate("profit factor", pf, c.min_profit_factor,
                       pf is not None and pf >= c.min_profit_factor,
                       "Gross win / gross loss after costs."))

    r = m.get("avg_r")
    gates.append(_gate("avg R", r, c.min_avg_r, r is not None and r >= c.min_avg_r,
                       "Edge per trade, as a multiple of what is risked."))

    t = m.get("t_stat")
    t_need = round(required_t_stat(n_trials, c.bonferroni_alpha), 2)
    gates.append(_gate("t-stat", t, t_need, t is not None and t >= t_need,
                       f"Adjusted for {n_trials} logged trials: the best of "
                       f"{n_trials} worthless strategies clears 1.96 routinely."))

    years = max((m.get("days_tested") or 0) / 365, 1e-6)
    dsr = deflated_sharpe(m.get("sharpe") or 0.0, n_trials, years,
                          oos_result.meta.get("bars", 0))
    d = dsr.get("deflated_sharpe")
    gates.append(_gate("deflated Sharpe", d, c.min_deflated_sharpe,
                       d is not None and d == d and d >= c.min_deflated_sharpe,
                       f"Probability of beating the best-of-{n_trials} noise "
                       f"benchmark (Sharpe ~{dsr.get('benchmark_sharpe')})."))

    if is_result is not None and (is_result.metrics.get("sharpe") or 0) > 0:
        decay = 1 - (m.get("sharpe") or 0) / is_result.metrics["sharpe"]
        gates.append(_gate("Sharpe decay IS->OOS", round(decay, 3),
                           c.max_sharpe_decay, decay <= c.max_sharpe_decay,
                           "Large decay means the in-sample result was tuning.",
                           higher_is_better=False))

    days = res.get("expected_days_to_resolution")
    gates.append(_gate("days to resolve", days, c.max_days_to_resolve,
                       days is not None and days <= c.max_days_to_resolve,
                       "An evaluation has to finish in a usable time.",
                       higher_is_better=False))

    p = res.get("p_target_before_breach")
    gates.append(_gate("P(target first)", p, c.min_p_target_first,
                       p is not None and p >= c.min_p_target_first,
                       "Chance of reaching the target before the drawdown limit."))

    tpd = m.get("trades_per_day")
    gates.append(_gate("trades/day", tpd, c.min_trades_per_day,
                       tpd is not None and tpd >= c.min_trades_per_day,
                       "A floor on frequency, kept low deliberately: what "
                       "matters is trades per EVALUATION, not per day."))

    n_win = res.get("expected_trades_to_resolution")
    gates.append(_gate("trades per evaluation", n_win,
                       c.min_expected_trades_to_resolution,
                       n_win is not None and n_win >= c.min_expected_trades_to_resolution,
                       "trades/day x days to resolve. Low frequency is fine if "
                       "the edge per trade is large enough to still fill the "
                       "window; what is not fine is an evaluation decided by a "
                       "handful of trades, where luck outweighs the edge."))

    dd = m.get("max_drawdown_pct")
    gates.append(_gate("max drawdown %", dd, c.max_oos_drawdown_pct,
                       dd is not None and dd <= c.max_oos_drawdown_pct,
                       "Margin against the hard limit, not a near miss.",
                       higher_is_better=False))

    worst = prop.get("checks", {}).get("daily_loss_limit", {}).get("worst_day_loss")
    start = m.get("starting_balance") or 1
    worst_pct = round(100 * worst / start, 2) if worst is not None else None
    gates.append(_gate("worst day %", worst_pct, c.max_worst_day_pct,
                       worst_pct is not None and worst_pct <= c.max_worst_day_pct,
                       "Margin against the daily loss limit.",
                       higher_is_better=False))

    if pf_at_2x_costs is not None:
        gates.append(_gate("profit factor @2x costs", pf_at_2x_costs,
                           c.min_profit_factor_at_2x_costs,
                           pf_at_2x_costs >= c.min_profit_factor_at_2x_costs,
                           "The venue is not chosen yet; costs are an assumption."))

    failed = [g["gate"] for g in gates if not g["passed"]]
    return {
        "accepted": not failed,
        "n_gates": len(gates),
        "n_failed": len(failed),
        "failed_gates": failed,
        "gates": gates,
        "n_trials_at_scoring": n_trials,
        "criteria": c.to_dict(),
        "verdict": ("ACCEPTED - clears every gate; candidate for paper trading"
                    if not failed else
                    f"NOT ACCEPTED - fails {len(failed)} of {len(gates)} gates: "
                    + ", ".join(failed)),
    }
