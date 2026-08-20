"""The acceptance bar, in three tiers.

The point of a bar is to stop "is this good?" being decided while looking at
an encouraging number. The point of NOT making it a wall of independent
thresholds is that strategies legitimately come in different shapes: a slow
strategy with a fat edge per trade and a fast one with a thin edge can be
equally good, and separate floors on profit factor, trades/day and average R
would reject one of them for no real reason.

The resolution is that those metrics are not independent. They are all inputs
to the same two questions - will this pass an evaluation, and how quickly -
which the two-barrier model in metrics.resolution already answers jointly:

    daily P&L = trades/day x avg R x risk/trade x equity

Low frequency with a big edge and high frequency with a small edge produce the
same daily drift, and the model treats them as what they are: equivalent. So
they are gated on the OUTCOME they jointly produce, and reported individually
as diagnostics with no thresholds at all.

    Tier 1 VALIDITY     - is the result real? Binary, non-negotiable. No
                          amount of profit compensates for lookahead, a broken
                          prop rule, or a t-stat that the best of N coin flips
                          would beat.
    Tier 2 VIABILITY    - can it clear an evaluation, and fast enough? Gated on
                          the joint outcome, so the trade-offs happen here.
    Tier 3 ROBUSTNESS   - advisory flags. These do not auto-reject; they are
                          what to argue about, with the numbers in front of us.

Tier 3 deliberately does not block acceptance, because judgement belongs
somewhere. Tier 1 deliberately cannot be argued with, because that is where
self-deception happens.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict

from scipy import stats

from .multiple_testing import deflated_sharpe


@dataclass(frozen=True)
class AcceptanceCriteria:
    # --- Tier 1: validity. Change these only with a very good reason. ---
    require_checks_pass: bool = True
    require_prop_pass: bool = True
    min_oos_trades: int = 100
    bonferroni_alpha: float = 0.05
    min_deflated_sharpe: float = 0.95

    # --- Tier 2: viability. The joint outcome, not per-metric floors. ---
    max_days_to_resolve: float = 15.0
    min_p_target_first: float = 0.80
    min_expected_trades_to_resolution: float = 10.0

    # --- Tier 3: robustness. Advisory only. ---
    warn_oos_drawdown_pct: float = 5.0
    warn_worst_day_pct: float = 2.5
    warn_sharpe_decay: float = 0.50
    warn_profit_factor: float = 1.20
    warn_best_trade_share_pct: float = 40.0
    warn_profit_factor_at_2x_costs: float = 1.0

    def to_dict(self) -> dict:
        return asdict(self)


def required_t_stat(n_trials: int, alpha: float = 0.05) -> float:
    """Bonferroni-adjusted t threshold for the number of things tried."""
    return float(stats.norm.ppf(1 - (alpha / max(n_trials, 1)) / 2))


def _row(tier, name, value, threshold, passed, why, higher_is_better=True):
    return {"tier": tier, "gate": name, "value": value, "threshold": threshold,
            "passed": bool(passed), "why": why,
            "direction": "min" if higher_is_better else "max"}


def profile(metrics: dict) -> str:
    """Describe the strategy's shape, so the trade-off being made is visible."""
    tpd = metrics.get("trades_per_day")
    r = metrics.get("avg_r")
    hold = metrics.get("avg_hold_hours")
    if tpd is None or r is None:
        return "unknown shape"
    freq = ("high-frequency" if tpd >= 5 else
            "moderate-frequency" if tpd >= 1 else "low-frequency")
    edge = ("fat edge" if r >= 0.5 else
            "moderate edge" if r >= 0.15 else "thin edge")
    hold_s = (f", holds ~{hold:.0f}h" if hold else "")
    return (f"{freq} ({tpd:.2f}/day), {edge} ({r:.2f}R per trade){hold_s} — "
            f"both shapes are legitimate; what matters is the outcome they "
            f"produce together")


def score(oos_result, *, n_trials: int, is_result=None,
          pf_at_2x_costs: float | None = None,
          criteria: AcceptanceCriteria | None = None) -> dict:
    """Grade one out-of-sample run. Returns tiered gates plus diagnostics."""
    c = criteria or AcceptanceCriteria()
    m, prop = oos_result.metrics, oos_result.prop
    res = m.get("resolution") or {}
    checks = oos_result.meta.get("checks", [])
    rows = []

    # ---------------- Tier 1: is the result real? ----------------
    rows.append(_row(1, "automated checks",
                     "pass" if all(x["passed"] for x in checks) else "FAIL", "pass",
                     not checks or all(x["passed"] for x in checks),
                     "Lookahead or a template violation invalidates everything."))
    rows.append(_row(1, "prop rules (OOS)", "PASS" if prop.get("passed") else "FAIL",
                     "PASS", prop.get("passed") or not c.require_prop_pass,
                     "Profitable but rule-breaking is not tradeable."))
    n = m.get("n_trades") or 0
    rows.append(_row(1, "OOS trades", n, c.min_oos_trades, n >= c.min_oos_trades,
                     "Too few trades and the result is mostly luck."))
    t = m.get("t_stat")
    t_need = round(required_t_stat(n_trials, c.bonferroni_alpha), 2)
    rows.append(_row(1, "t-stat", t, t_need, t is not None and t >= t_need,
                     f"Adjusted for {n_trials} logged trials - the best of "
                     f"{n_trials} worthless strategies clears 1.96 routinely."))
    years = max((m.get("days_tested") or 0) / 365, 1e-6)
    dsr = deflated_sharpe(m.get("sharpe") or 0.0, n_trials, years,
                          oos_result.meta.get("bars", 0))
    d = dsr.get("deflated_sharpe")
    rows.append(_row(1, "deflated Sharpe", d, c.min_deflated_sharpe,
                     d is not None and d == d and d >= c.min_deflated_sharpe,
                     f"Beats the best-of-{n_trials} noise benchmark "
                     f"(Sharpe ~{dsr.get('benchmark_sharpe')})."))

    # ------------- Tier 2: can it clear an evaluation? -------------
    days = res.get("expected_days_to_resolution")
    rows.append(_row(2, "days to resolve", days, c.max_days_to_resolve,
                     days is not None and days <= c.max_days_to_resolve,
                     "Joint effect of frequency, edge and sizing. However it "
                     "gets there, the evaluation has to finish.",
                     higher_is_better=False))
    p = res.get("p_target_before_breach")
    rows.append(_row(2, "P(target first)", p, c.min_p_target_first,
                     p is not None and p >= c.min_p_target_first,
                     "Chance of reaching the target before the drawdown limit."))
    n_win = res.get("expected_trades_to_resolution")
    rows.append(_row(2, "trades per evaluation", n_win,
                     c.min_expected_trades_to_resolution,
                     n_win is not None and n_win >= c.min_expected_trades_to_resolution,
                     "Low frequency is fine if the edge per trade is large "
                     "enough; an evaluation decided by five trades is not."))

    # ---------------- Tier 3: advisory flags ----------------
    flags = []

    def flag(name, value, threshold, ok, why, higher_is_better=True):
        r_ = _row(3, name, value, threshold, ok, why, higher_is_better)
        rows.append(r_)
        if not ok:
            flags.append(name)

    dd = m.get("max_drawdown_pct")
    flag("drawdown margin", dd, c.warn_oos_drawdown_pct,
         dd is None or dd <= c.warn_oos_drawdown_pct,
         "Comfort against the hard limit, not just survival.", False)
    worst = prop.get("checks", {}).get("daily_loss_limit", {}).get("worst_day_loss")
    start = m.get("starting_balance") or 1
    worst_pct = round(100 * worst / start, 2) if worst is not None else None
    flag("worst-day margin", worst_pct, c.warn_worst_day_pct,
         worst_pct is None or worst_pct <= c.warn_worst_day_pct,
         "Comfort against the daily loss limit.", False)
    pf = m.get("profit_factor")
    flag("profit factor", pf, c.warn_profit_factor,
         pf is None or pf >= c.warn_profit_factor,
         "Diagnostic, not a floor: a low PF is fine if frequency carries it.")
    conc = m.get("best_trade_pct_of_profit")
    flag("profit concentration", conc, c.warn_best_trade_share_pct,
         conc is None or conc <= c.warn_best_trade_share_pct,
         "One trade carrying the result means an effective sample of ~1.", False)
    if is_result is not None and (is_result.metrics.get("sharpe") or 0) > 0:
        decay = round(1 - (m.get("sharpe") or 0) / is_result.metrics["sharpe"], 3)
        flag("Sharpe decay IS->OOS", decay, c.warn_sharpe_decay,
             decay <= c.warn_sharpe_decay,
             "Large decay suggests the in-sample result was tuning.", False)
    if pf_at_2x_costs is not None:
        flag("profit factor @2x costs", pf_at_2x_costs,
             c.warn_profit_factor_at_2x_costs,
             pf_at_2x_costs >= c.warn_profit_factor_at_2x_costs,
             "The venue is still an assumption.")

    t1 = [r_ for r_ in rows if r_["tier"] == 1]
    t2 = [r_ for r_ in rows if r_["tier"] == 2]
    failed1 = [r_["gate"] for r_ in t1 if not r_["passed"]]
    failed2 = [r_["gate"] for r_ in t2 if not r_["passed"]]
    accepted = not failed1 and not failed2

    if failed1:
        verdict = ("NOT ACCEPTED - the result is not established: "
                   + ", ".join(failed1))
    elif failed2:
        verdict = ("NOT ACCEPTED - real but cannot clear an evaluation: "
                   + ", ".join(failed2))
    elif flags:
        verdict = ("ACCEPTED with " + str(len(flags)) + " robustness flag(s) to "
                   "discuss: " + ", ".join(flags))
    else:
        verdict = "ACCEPTED - clears every gate with no flags"

    return {
        "accepted": accepted,
        "verdict": verdict,
        "profile": profile(m),
        "failed_validity": failed1,
        "failed_viability": failed2,
        "robustness_flags": flags,
        "gates": rows,
        "diagnostics": {
            "profit_factor": pf,
            "avg_r": m.get("avg_r"),
            "win_rate_pct": m.get("win_rate_pct"),
            "trades_per_day": m.get("trades_per_day"),
            "avg_hold_hours": m.get("avg_hold_hours"),
            "cagr_pct": m.get("cagr_pct"),
            "total_return_pct": m.get("total_return_pct"),
            "sharpe": m.get("sharpe"),
            "max_drawdown_pct": dd,
        },
        "n_trials_at_scoring": n_trials,
        "criteria": c.to_dict(),
    }
