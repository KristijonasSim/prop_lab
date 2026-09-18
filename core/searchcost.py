"""What the SEARCH cost, not what the winner scored.

WHY THIS EXISTS. This repo has written the same debt down twice and never paid
it. `STRATEGY_LOG.md` carries 48 hypotheses and `backtests/` carries 325 result
files, and **not one number anywhere has been charged for the number of things
tried to find it**. The two entries:

    2026-09-13, H-035  "LESSON 1 - price the SEARCH, not just the test. 96 tests
                        at a 95th percentile expect 4.8 false passes; 7 were
                        observed."
    2026-09-17, NEXT.md "two other method debts are still open ... the search is
                        not priced."

Three days apart, the second one re-derived because the first had no code behind
it. A lesson with no function to call is a lesson that gets re-learned.

WHAT IS AND IS NOT COVERED HERE. Three different questions need three different
tests and using one where another belongs is the single most common way this
project has fooled itself:

    is THIS rule's edge real?          a paired null on its own series.
                                       ALREADY BUILT - `core/nulls.py`, and it
                                       is the gate that killed top-N and H-049.
    is the BEST of N trials real?      multiple testing. Deflated Sharpe, below.
                                       NEVER BUILT HERE UNTIL NOW.
    will the RANKING survive OOS?      combinatorially symmetric cross-validation.
                                       NEVER BUILT HERE UNTIL NOW.

The paired null answers the first and cannot answer the other two, because it is
run per candidate and knows nothing about the candidates it was not run on. That
is precisely how 96 tests produced 7 passes at a 95th percentile and the write-up
called them findings.

THE ONE RESULT THAT SHOULD CHANGE BEHAVIOUR. `sr_threshold` rises with the trial
count, so the bar a result must clear depends on how much was tried to find it.
At N=1 the threshold collapses to the benchmark and the deflated Sharpe becomes
the plain probabilistic Sharpe. **A pre-registered single arm faces a materially
lower bar than the winner of a sweep, as arithmetic rather than as discipline.**
That is the reason to fix the arm list before running, and it is the only reason
that does not rely on anybody being good.

VERIFIED. `min_backtest_years(45)` returns 4.998 against the 5.0 worked example
in Bailey, Borwein, Lopez de Prado & Zhu (2014). `tests/test_searchcost.py`
pins it.

Bailey & Lopez de Prado, "The Deflated Sharpe Ratio" (2014).
Bailey, Borwein, Lopez de Prado & Zhu, "Pseudo-Mathematics and Financial
Charlatanism" (2014) - minimum backtest length.
Bailey, Borwein, Lopez de Prado & Zhu, "The Probability of Backtest
Overfitting" (2015) - CSCV.
"""
from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
from math import comb, e, log, sqrt

import numpy as np
from scipy.stats import norm

#: Euler-Mascheroni. Appears in the expected maximum of N standard normals.
EULER = 0.5772156649015329

#: The annualised Sharpe a zero-skill search is assumed to be able to fake.
#: 1.0 is the paper's convention and the value its worked example uses.
FAKE_SR = 1.0


# ---------------------------------------------------------------------------
# The expected maximum of N draws, which is the whole of multiple testing
# ---------------------------------------------------------------------------
def expected_max_z(n_trials: int) -> float:
    """Expected maximum of `n_trials` independent standard normals.

    This is the quantity every result in this repo has been compared against
    implicitly and never explicitly. It grows without bound in N, slowly - which
    is why "we tried a lot of things and the best one looked good" is not an
    observation about the market.

        N=1   0.00        N=48    2.03        N=325   2.68
        N=10  1.54        N=96    2.24

    48 is this project's hypothesis count and 325 is its backtest-artifact count,
    so the honest bar for "the best thing we have ever seen" sits between two and
    two and a half standard deviations of pure luck.
    """
    n = max(1, int(n_trials))
    if n == 1:
        return 0.0
    return ((1.0 - EULER) * norm.ppf(1.0 - 1.0 / n)
            + EULER * norm.ppf(1.0 - 1.0 / (n * e)))


def min_backtest_years(n_trials: int, fake_sr: float = FAKE_SR) -> float:
    """Years of history needed before an in-sample Sharpe of `fake_sr` means
    anything after `n_trials` searches.

    Inverted, this is a BUDGET: the history on hand buys a fixed number of
    trials and every backtest debits one. The repo's own test-window rule caps
    history at 3 years ideal, 5 maximum (CLAUDE.md, set 2026-09-15), so:

        3 years  buys  ~11 trials
        5 years  buys  ~45 trials

    Against 48 hypotheses and 325 backtest files. **The search has been running
    over budget for most of the project's life**, which is a statement about the
    bar, not about the work - it means a headline needs a paired null and a
    pre-registration to be worth anything, which is exactly what the 2026-09-17
    top-N withdrawal demonstrated the hard way.
    """
    z = expected_max_z(n_trials)
    return (z * z) / (fake_sr * fake_sr) if fake_sr else float("inf")


def trials_affordable(years: float, fake_sr: float = FAKE_SR) -> int:
    """How many trials `years` of history pays for. Inverse of the above."""
    n = 1
    while min_backtest_years(n + 1, fake_sr) <= years and n < 10_000_000:
        n += 1
    return n


# ---------------------------------------------------------------------------
# Probabilistic and deflated Sharpe
# ---------------------------------------------------------------------------
def probabilistic_sharpe(sr: float, n_obs: int, benchmark: float = 0.0,
                         skew: float = 0.0, kurtosis: float = 3.0) -> float:
    """P(true Sharpe > `benchmark`), given a track record of `n_obs` returns.

    `sr` and `benchmark` are PER-OBSERVATION Sharpes, not annualised - divide an
    annual figure by sqrt(periods per year) before passing it in. `kurtosis` is
    the raw fourth moment, so 3.0 is normal.

    Negative skew and fat tails both LOWER this, which matters here more than in
    most places: H-027's profit is one big winner in five and `docs/FIRMS.md`
    measures a single day at 76-95% of all profit. A Sharpe computed on that
    shape is worth less than the same Sharpe on an even series, and this is the
    function that says by how much.
    """
    if n_obs < 2:
        return float("nan")
    denom = 1.0 - skew * sr + 0.25 * (kurtosis - 1.0) * sr * sr
    if denom <= 0:
        return float("nan")
    return float(norm.cdf((sr - benchmark) * sqrt(n_obs - 1.0) / sqrt(denom)))


def sr_threshold(sr_variance: float, n_trials: int) -> float:
    """The Sharpe a zero-skill search of `n_trials` is expected to produce.

    `sr_variance` is the variance of the trial Sharpes ACROSS the search. A wide
    spread of results means the search was exploring genuinely different things
    and luck had more room, so the bar goes up; a tight cluster means the trials
    were near-duplicates and the effective search was smaller than its raw count.

    This is the number to quote beside any "best cell" in this repo.
    """
    return sqrt(max(0.0, sr_variance)) * expected_max_z(n_trials)


def deflated_sharpe(sr: float, n_obs: int, sr_variance: float, n_trials: int,
                    skew: float = 0.0, kurtosis: float = 3.0) -> float:
    """Probabilistic Sharpe measured against the search's own luck threshold.

    Read it as a probability that the strategy's true Sharpe beats what the
    search would have produced from nothing. Above 0.95 is the usual bar.

    At `n_trials=1` the threshold is zero and this returns the plain
    probabilistic Sharpe - the arithmetic reward for pre-registering.
    """
    return probabilistic_sharpe(sr, n_obs, sr_threshold(sr_variance, n_trials),
                                skew, kurtosis)


def effective_trials(returns: np.ndarray) -> float:
    """Trial count corrected for candidates that move together.

    A grid of 8,160 ORB configurations is not 8,160 independent chances - the
    neighbouring cells share most of their trades. Charging the raw count would
    make every sweep unpassable and charging one would make it free.

    `returns` is (T observations, N trials) on a shared axis. The estimate is
    the standard effective sample size under equicorrelation,

        N_eff = N / (1 + (N - 1) * rho_bar)

    with `rho_bar` the mean off-diagonal correlation, floored at zero. Identical
    columns give 1, independent columns give N.

    **THE DISCOUNT NEEDS THE RETURNS.** There is no way to read it off a column
    of Sharpe numbers - a wide spread of Sharpes is equally consistent with many
    independent trials and with a few correlated ones plus noise. An earlier
    draft of this function tried it and returned 2.6 effective trials out of 228,
    which would have handed the next result a bar near zero. Where the returns
    are not on hand, charge the RAW count: over-charging the search is the safe
    direction, and it is the direction this project has never erred in.
    """
    r = np.asarray(returns, dtype=float)
    if r.ndim != 2 or r.shape[1] < 2:
        return float(max(1, r.shape[1] if r.ndim == 2 else 1))
    n = r.shape[1]
    c = np.corrcoef(r, rowvar=False)
    off = c[~np.eye(n, dtype=bool)]
    off = off[np.isfinite(off)]
    if off.size == 0:
        return float(n)
    rho = max(0.0, float(off.mean()))
    return float(n / (1.0 + (n - 1) * rho))


# ---------------------------------------------------------------------------
# Probability of backtest overfitting, by CSCV
# ---------------------------------------------------------------------------
@dataclass
class PBO:
    """Result of a combinatorially symmetric cross-validation."""
    pbo: float
    n_splits: int
    median_oos_rank: float
    n_trials: int

    def __str__(self) -> str:
        return (f"PBO {self.pbo:.3f} over {self.n_splits} splits of "
                f"{self.n_trials} trials, median OOS rank "
                f"{self.median_oos_rank:.2f}")


def pbo_cscv(returns: np.ndarray, n_subsets: int = 8) -> PBO:
    """P(the in-sample winner lands below the median out of sample).

    `returns` is (T observations, N trials) - one column per configuration, on a
    SHARED time axis. Splits T into `n_subsets` contiguous blocks, takes every
    balanced choice of half of them as in-sample, and asks where the in-sample
    winner ranks on the complement.

    Above 0.5 means the selection procedure is worse than picking at random,
    which is the finding that matters: it indicts the SELECTOR, not the
    candidate. This project's selector is `core/pipeline.py`'s train-slice
    profit-factor pick, and it has never been measured this way.

    Needs at least 2 trials and enough rows to split; returns NaN otherwise.
    """
    r = np.asarray(returns, dtype=float)
    if r.ndim != 2 or r.shape[1] < 2:
        return PBO(float("nan"), 0, float("nan"), int(r.shape[1]) if r.ndim == 2 else 0)
    t, n = r.shape
    s = max(2, int(n_subsets) - (int(n_subsets) % 2))
    if t < s * 2:
        return PBO(float("nan"), 0, float("nan"), n)

    blocks = np.array_split(np.arange(t), s)
    half = s // 2
    logits, ranks = [], []
    for pick in combinations(range(s), half):
        rest = [i for i in range(s) if i not in pick]
        is_idx = np.concatenate([blocks[i] for i in pick])
        oos_idx = np.concatenate([blocks[i] for i in rest])
        is_sr = _sharpe_cols(r[is_idx])
        oos_sr = _sharpe_cols(r[oos_idx])
        if not np.isfinite(is_sr).any() or not np.isfinite(oos_sr).any():
            continue
        best = int(np.nanargmax(is_sr))
        # relative rank of the chosen column out of sample, in (0, 1)
        order = np.argsort(np.argsort(oos_sr))
        rel = (order[best] + 1.0) / (n + 1.0)
        ranks.append(rel)
        rel = min(max(rel, 1e-9), 1 - 1e-9)
        logits.append(log(rel / (1.0 - rel)))

    if not logits:
        return PBO(float("nan"), 0, float("nan"), n)
    lg = np.asarray(logits)
    return PBO(float((lg <= 0).mean()), len(lg), float(np.median(ranks)), n)


def _sharpe_cols(block: np.ndarray) -> np.ndarray:
    mu = block.mean(axis=0)
    sd = block.std(axis=0, ddof=1)
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(sd > 0, mu / sd, np.nan)


def n_cscv_splits(n_subsets: int = 8) -> int:
    """How many splits `pbo_cscv` will run. C(S, S/2), so it explodes: 8 -> 70,
    12 -> 924, 16 -> 12,870. Eight is the paper's default and is enough."""
    s = max(2, int(n_subsets) - (int(n_subsets) % 2))
    return comb(s, s // 2)


# ---------------------------------------------------------------------------
# The business arithmetic the board does not do
# ---------------------------------------------------------------------------
def accounts_consumed(pass_rate: float) -> float:
    """Evaluations bought per funded seat. Owed since 2026-09-17.

    `core/scorecard.expected_days` is `median_days / pass_rate`, which prices a
    blown account at ZERO. Any lever that raises trade frequency therefore buys
    apparent speed by spending accounts, and the board scores it as an
    improvement. That is exactly how the withdrawn top-N result reached 8.9 days
    - and how a BTCUSDT configuration whose every cell loses money "resolved" an
    evaluation in 14.5 days against 28.2.

    Report this next to every expected-days figure.
    """
    return float("inf") if not pass_rate else 1.0 / float(pass_rate)


def cost_per_funded(fee: float, pass_rate: float) -> float:
    """Money spent on evaluations per funded seat."""
    return fee * accounts_consumed(pass_rate)


def ev_per_evaluation(fee: float, pass_rate: float, account_size: float,
                      target: float, split: float = 0.9,
                      payout_rate: float = 1.0) -> float:
    """Expected euros from buying ONE evaluation, before any funded-phase blow-up.

    `payout_rate` is the share of funded accounts that actually reach a
    withdrawal. **Leave it at 1.0 only to see the optimistic bound.** The
    industry figure is far lower - roughly 45% of funded accounts see one
    payout, and about 7% of all evaluation buyers ever do - and this project's
    own simulated pass rates (42-64%) sit three to eight times above the
    published 8-15% per-attempt industry rate, a gap nothing here has explained.

    This is deliberately the simplest possible model. It exists so that a number
    in euros appears beside every number in days, because the goal is 10-20
    funded seats and days do not pay for evaluations.
    """
    gross = account_size * target * split
    return pass_rate * payout_rate * gross - fee
