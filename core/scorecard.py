"""One 0-10 score, computed the same way for every hypothesis.

The point of this file is that the score is *auditable*. Every component is a
named function of a measured number, with a stated curve, so a strategy cannot
score well for a reason nobody can see. If a weight is wrong, change it here and
every hypothesis is re-scored on the same basis.

Kris set the priority: everything counts, and **speed to pass a challenge counts
most**, because a strategy that cannot resolve inside the current phase window
cannot be traded now no matter how good it looks.

    component        weight   what it measures
    ---------------  ------   ------------------------------------------------
    speed              30     median days for a simulated account to reach 8%
    pass rate          18     share of simulated accounts that pass
    breach safety      12     share that blow the 8% max-loss cap (inverted)
    drawdown           10     peak drawdown against the 8% cap
    evidence           20     walk-forward PF, cost robustness, null margin,
                              quarter-by-quarter consistency
    raw profit         10     profit factor and Sharpe

A score is only comparable between strategies if both were measured the same
way, so every input here comes from a walk-forward or a prop simulation, never
from a fitted backtest. Where a strategy has no walk-forward number at all the
evidence component scores zero rather than being skipped.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# component -> weight. They sum to 100 and the total is rescaled to 0-10.
WEIGHTS = {
    "speed": 30,
    "pass_rate": 18,
    "breach": 12,
    "drawdown": 10,
    "evidence": 20,
    "profit": 10,
}

PHASE_DAYS = 14.0      # the current phase constraint
DEAD_DAYS = 180.0      # past here, speed scores zero
DD_CAP = 0.08          # the prop max-loss cap
BREACH_DEAD = 0.30     # a 30% breach rate scores zero on safety
EVIDENCE_GATE = 0.25   # below this the walk-forward record is effectively absent
EVIDENCE_CAP = 3.0     # and the total cannot exceed this, whatever else it scores
NULL_CAP = 4.0         # a strategy that does not beat its own null benchmark
                       # cannot exceed this, however good its numbers look


def _clip(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def _ramp(x: float, zero_at: float, one_at: float) -> float:
    """Linear 0..1 between two named points, in either direction."""
    if one_at == zero_at:
        return 0.0
    return _clip((x - zero_at) / (one_at - zero_at))


def expected_days(median_days: float | None, pass_rate: float | None) -> float | None:
    """Days per *funded account*, not days per passing account.

    `median_days_to_pass` is measured only over the accounts that passed, so a
    strategy that blows up two accounts out of three and squeaks the third
    through quickly reads as fast. Dividing by the pass rate gives the number
    that actually matters to the business: how long until you hold a funded
    account, including the attempts that died on the way."""
    if median_days is None:
        return None
    if not pass_rate:
        return None                 # never passes: no finite expectation
    return median_days / pass_rate


def score_speed(median_days: float | None, pass_rate: float | None = None) -> float:
    """1.0 at or inside the phase window, decaying to 0 at DEAD_DAYS.

    Scored on expected days per funded account (see `expected_days`). A strategy
    with no measured time-to-pass has not been simulated and scores zero -
    absence of the number is not neutral."""
    d = expected_days(median_days, pass_rate)
    if d is None:
        return 0.0
    if d <= PHASE_DAYS:
        return 1.0
    return _ramp(d, DEAD_DAYS, PHASE_DAYS)


def score_pass_rate(pass_rate: float | None) -> float:
    return 0.0 if pass_rate is None else _clip(pass_rate)


def score_breach(fail_max: float | None, fail_daily: float | None = None) -> float:
    """Share of accounts killed by ANY breach, inverted.

    Both breach types have to count. Scoring only the 8% max-loss breach left a
    hole: pushing risk to 4-5% per trade moves the deaths from the max-loss cap
    to the *daily* cap, so the scored breach rate falls while more accounts die
    than ever. The score went up as the strategy got worse. A dead account is a
    dead account whichever rule killed it."""
    if fail_max is None and fail_daily is None:
        return 0.0
    total = (fail_max or 0.0) + (fail_daily or 0.0)
    return _clip(1.0 - total / BREACH_DEAD)


def score_drawdown(max_dd: float | None) -> float:
    """Peak drawdown against the cap. Half the cap is a full mark; twice the cap
    is zero. Sitting exactly on the cap deliberately scores middling, because a
    strategy whose drawdown equals the limit has no margin for a bad run."""
    if max_dd is None:
        return 0.0
    dd = abs(max_dd)
    return _ramp(dd, DD_CAP * 2, DD_CAP / 2)


def score_evidence(wf_pf: float | None, wf_pf_2x: float | None,
                   null_margin: float | None, consistency: float | None) -> float:
    """Does the blind walk-forward make money, does it hold at double cost, does
    it beat what the same search finds in shuffled data, and is it positive
    period after period rather than in one lucky burst.

    The null margin carries double the weight of the others. Four equal parts was
    wrong: it let H-003 - whose phase-randomised null produced MORE gate-clearing
    cells than the real data - still score 0.75 on evidence off a high profit
    factor and a perfect quarter count. Beating the null is not one consideration
    among four; it is the one that decides whether the other three mean
    anything."""
    parts = [
        (_ramp(wf_pf or 0.0, 0.9, 1.5), 1.0),        # 0.9 -> 0, 1.5 -> 1
        (_ramp(wf_pf_2x or 0.0, 0.9, 1.3), 1.0),     # holding at 2x cost is the hard one
        (_clip(null_margin or 0.0), 2.0),            # the one that decides
        (_clip(consistency or 0.0), 1.0),            # share of quarters above breakeven
    ]
    return sum(v * w for v, w in parts) / sum(w for _v, w in parts)


def score_profit(pf: float | None, sharpe: float | None) -> float:
    return (_ramp(pf or 0.0, 1.0, 2.0) + _ramp(sharpe or 0.0, 0.0, 2.0)) / 2


@dataclass
class Scorecard:
    components: dict = field(default_factory=dict)   # name -> 0..1
    total: float = 0.0                               # 0..10
    evidence_capped: bool = False
    null_capped: bool = False

    def as_dict(self) -> dict:
        return {
            "total": round(self.total, 1),
            "verdict": verdict(self.total),
            "evidence_capped": self.evidence_capped,
            "null_capped": self.null_capped,
            "components": [
                {"name": k, "weight": WEIGHTS[k],
                 "score": round(v, 3),
                 "points": round(v * WEIGHTS[k] / 10.0, 2)}
                for k, v in self.components.items()
            ],
        }


def verdict(total: float) -> str:
    """Plain words, and deliberately conservative at the top.

    Nothing in this project gets called good, ready, or worth real money on the
    strength of a backtest - not even a walk-forward one that beats its null. The
    top band therefore says what the number actually means (this is the best
    evidence produced so far) rather than what to do about it. "Trade it" was the
    original label and it was wrong: a score is a summary of tests already
    passed, never a recommendation."""
    if total >= 8.0:
        return "Best evidence so far - still not proven live"
    if total >= 6.5:
        return "Strong candidate"
    if total >= 5.0:
        return "Worth more work"
    if total >= 3.5:
        return "Weak - something real, but not tradeable as it stands"
    if total >= 2.0:
        return "Failing"
    return "Dead"


def compute(m: dict) -> Scorecard:
    """`m` is the measured-numbers dict assembled per strategy. Missing keys are
    treated as absent, which scores zero for that component."""
    c = {
        "speed": score_speed(m.get("median_days_pass"), m.get("pass_rate")),
        "pass_rate": score_pass_rate(m.get("pass_rate")),
        "breach": score_breach(m.get("fail_max"), m.get("fail_daily")),
        "drawdown": score_drawdown(m.get("max_dd")),
        "evidence": score_evidence(m.get("wf_pf"), m.get("wf_pf_2x"),
                                   m.get("null_margin"), m.get("consistency")),
        "profit": score_profit(m.get("pf"), m.get("sharpe")),
    }
    total = sum(c[k] * WEIGHTS[k] for k in WEIGHTS) / sum(WEIGHTS.values()) * 10.0

    # Evidence gate. The project's standing rule is that a strategy without a
    # blind walk-forward record is not a candidate, whatever else it scores.
    # Without this an idea that churns accounts quickly banks most of the speed
    # weight while having no demonstrated edge at all - which is exactly what
    # ORB does. The cap is applied last and is reported, not hidden.
    capped = False
    if c["evidence"] < EVIDENCE_GATE and total > EVIDENCE_CAP:
        total, capped = EVIDENCE_CAP, True

    # Null gate. The project's method rule is that any large search is scored
    # against the same search run on phase-randomised data. A strategy whose null
    # matched or beat it has not been shown to differ from noise, and a headline
    # profit factor cannot buy its way past that - H-003's best cell walk-forwards
    # to 2.356 while its null produced more gate-clearing cells than it did.
    null_capped = False
    if m.get("beats_null") is not True and total > NULL_CAP:
        total, null_capped = NULL_CAP, True
    return Scorecard(components=c, total=total, evidence_capped=capped,
                     null_capped=null_capped)
