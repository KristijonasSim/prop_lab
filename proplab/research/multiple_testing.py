"""Multiple-testing correction.

Testing many strategies guarantees some will look good by luck. These helpers
convert "how good does this look" into "how good does this look GIVEN that it
is the Nth thing we tried".

Rule of thumb baked in here: with N independent trials, the expected maximum
Sharpe from pure noise grows roughly like sqrt(2*ln(N)) / sqrt(T) in annual
terms. A result must clear that bar before it is interesting at all.
"""
from __future__ import annotations

import math

import numpy as np
from scipy import stats


def expected_max_sharpe(n_trials: int, n_years: float) -> float:
    """Expected best annualised Sharpe from `n_trials` worthless strategies."""
    if n_trials < 2 or n_years <= 0:
        return 0.0
    e = 0.5772156649
    z = ((1 - e) * stats.norm.ppf(1 - 1 / n_trials)
         + e * stats.norm.ppf(1 - 1 / (n_trials * math.e)))
    return float(z / math.sqrt(n_years))


def deflated_sharpe(observed_sharpe: float, n_trials: int, n_years: float,
                    n_obs: int, skew: float = 0.0, kurt: float = 3.0) -> dict:
    """Probability the observed Sharpe beats what noise would have produced.

    Bailey & Lopez de Prado's deflated Sharpe ratio, in annualised terms.
    Returns the benchmark it had to beat and the resulting probability.
    """
    sr0 = expected_max_sharpe(n_trials, n_years)
    if n_obs < 10:
        return {"deflated_sharpe": float("nan"), "benchmark_sharpe": round(sr0, 3),
                "verdict": "too few observations"}
    sr_per_obs = observed_sharpe / math.sqrt(n_obs / n_years)
    sr0_per_obs = sr0 / math.sqrt(n_obs / n_years)
    denom = math.sqrt(max(1e-12, 1 - skew * sr_per_obs + (kurt - 1) / 4 * sr_per_obs ** 2))
    z = (sr_per_obs - sr0_per_obs) * math.sqrt(n_obs - 1) / denom
    psr = float(stats.norm.cdf(z))
    return {
        "deflated_sharpe": round(psr, 4),
        "benchmark_sharpe": round(sr0, 3),
        "observed_sharpe": round(observed_sharpe, 3),
        "n_trials": n_trials,
        "verdict": ("survives multiple-testing adjustment" if psr > 0.95 else
                    "does NOT survive multiple-testing adjustment" if psr < 0.90 else
                    "borderline"),
    }


def bonferroni_alpha(alpha: float, n_trials: int) -> float:
    return alpha / max(n_trials, 1)


def trade_level_significance(r_multiples, n_trials: int = 1) -> dict:
    """t-test on per-trade R multiples, with a Bonferroni-adjusted threshold."""
    r = np.asarray([x for x in r_multiples if x == x], dtype=float)
    if len(r) < 5:
        return {"n": len(r), "verdict": "sample too small to say anything"}
    t, p = stats.ttest_1samp(r, 0.0)
    adj = bonferroni_alpha(0.05, n_trials)
    return {
        "n": int(len(r)),
        "mean_r": round(float(r.mean()), 4),
        "t_stat": round(float(t), 3),
        "p_value": round(float(p), 5),
        "bonferroni_alpha": round(adj, 5),
        "significant_after_correction": bool(p < adj and r.mean() > 0),
        "note": "trades are not fully independent; treat p as optimistic",
    }
