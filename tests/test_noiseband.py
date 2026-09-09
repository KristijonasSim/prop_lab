"""The band, pinned — and the rule that stops the board ranking through it.

`core/noiseband.py` exists because of what happened on 2026-09-08: six gates
carrying no information scored between 13.3 and 26.5 expected days through the
full machine, and every real candidate that day landed inside that spread. The
band is now printed next to every ranked number, so it has to be exactly as
trustworthy as the number it brackets.

The tests that matter here are:

  * the vectorised simulator IS `riskladder.run_accounts`, account for account.
    A band computed under different rules from the point estimate it brackets
    would be worse than no band;
  * a resample preserves the shape of the series it came from;
  * bands are deterministic given a seed, because a number that moves when you
    look again cannot be quoted;
  * `rank_tiers` refuses to separate rows whose bands overlap, and does not
    chain a whole table into one tier through a run of wide ones.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core import noiseband as NB                                # noqa: E402
from core import scorecard as SC                                # noqa: E402
from core.prop_rules import ONE_STEP                            # noqa: E402
from core.riskladder import run_accounts                        # noqa: E402


def _series(seed: int = 7, n: int = 730, edge: float = 0.03) -> pd.Series:
    """A lumpy daily-R series with no-trade days, like a real walk-forward."""
    rng = np.random.default_rng(seed)
    r = rng.standard_normal(n) * 0.9 + edge
    r[rng.random(n) < 0.35] = 0.0
    return pd.Series(r, index=pd.date_range("2024-01-01", periods=n,
                                            freq="D", tz="UTC"))


# --- the simulator is the same simulator ---------------------------------- #

def test_vectorised_matches_riskladder_exactly():
    """Every outcome share and the median days, at three sizes. This is the one
    that must never be relaxed: it is what makes the band comparable to the
    headline it sits under."""
    d = _series()
    for risk in (0.005, 0.02, 0.05):
        ref = run_accounts(d, risk)
        out, day = NB._states(d.values[None, :] * risk, ONE_STEP[0], 400)
        rate, med = NB._per_row(out, day)
        # riskladder rounds its shares to 4dp for the record; compare there
        assert round(float(rate[0]), 4) == ref["pass_rate"]
        assert round(float((out == 2).mean()), 4) == ref["fail_max"]
        assert round(float((out == 3).mean()), 4) == ref["fail_daily"]
        assert round(float((out == 0).mean()), 4) == ref["still_open"]
        assert med[0] == ref["median_days"]


def test_breach_is_a_breach():
    """A losing series kills accounts rather than shrinking them - the standing
    rule in CLAUDE.md against a risk manager that fakes a 0% fail rate."""
    d = _series(edge=-0.25)
    out, _ = NB._states(d.values[None, :] * 0.03, ONE_STEP[0], 400)
    # a few accounts still pass on variance - that is the point of simulating
    # every start day - but the overwhelming majority are killed outright
    assert (out == 1).mean() < 0.15
    assert ((out == 2) | (out == 3)).mean() > 0.80


# --- the resample ---------------------------------------------------------- #

def test_resample_is_stationary_and_in_range():
    rng = np.random.default_rng(0)
    idx = NB._resample_index(200, 50, rng, mean_block=10)
    assert idx.shape == (50, 200)
    assert idx.min() >= 0 and idx.max() < 200
    # blocks, not noise: consecutive indices should mostly advance by one
    step = np.diff(idx, axis=1)
    assert float((step == 1).mean()) > 0.75


def test_longer_blocks_keep_more_autocorrelation():
    """The point of a block bootstrap: a bad fortnight survives as a fortnight."""
    d = _series()
    rng = np.random.default_rng(1)
    short = d.values[NB._resample_index(len(d), 40, rng, 1)]
    long_ = d.values[NB._resample_index(len(d), 40, rng, 30)]

    def ac1(x):
        a, b = x[:, :-1], x[:, 1:]
        return float(np.mean([np.corrcoef(u, v)[0, 1] for u, v in zip(a, b)]))

    assert abs(ac1(long_)) >= abs(ac1(short))


# --- the band -------------------------------------------------------------- #

def test_band_is_ordered_and_deterministic():
    d = _series()
    a = NB.band(d, 0.02, resamples=60)
    b = NB.band(d, 0.02, resamples=60)
    assert a == b                                   # same seed, same answer
    assert a["days_lo"] <= a["days_med"] <= a["days_hi"]
    assert a["pass_lo"] <= a["pass_med"] <= a["pass_hi"]
    assert a["days_lo"] < a["days_hi"]              # a real band, not a point


def test_band_brackets_the_point_estimate():
    """The headline should land inside its own band. Not guaranteed for every
    series - a bootstrap is not centred by construction - but a systematic miss
    would mean the two are not measuring the same thing."""
    d = _series()
    ref = run_accounts(d, 0.02)
    point = ref["median_days"] / ref["pass_rate"]
    b = NB.band(d, 0.02, resamples=200)
    assert b["days_lo"] <= point <= b["days_hi"]


def test_band_declines_to_answer_on_a_short_series():
    assert NB.band(_series(n=40), 0.02) is None


def test_more_risk_moves_the_whole_band():
    """The risk ladder is the one lever not subject to the noise floor, so the
    band has to move with it rather than swamp it."""
    d = _series()
    lo = NB.band(d, 0.005, resamples=120)
    hi = NB.band(d, 0.03, resamples=120)
    assert hi["days_hi"] < lo["days_lo"]


# --- what may be ranked ---------------------------------------------------- #

def test_overlap_treats_a_missing_band_as_unknown():
    a = {"days_lo": 1.0, "days_hi": 2.0}
    assert NB.overlap(a, None) is True
    assert NB.overlap(None, None) is True
    assert NB.overlap(a, {"days_lo": 3.0, "days_hi": 4.0}) is False
    assert NB.overlap(a, {"days_lo": 1.5, "days_hi": 4.0}) is True


def test_rank_tiers_groups_the_indistinguishable():
    rows = [{"n": "fast", "days_to_pass": 11.7, "band": {"days_lo": 9, "days_hi": 20}},
            {"n": "mid", "days_to_pass": 16.6, "band": {"days_lo": 13, "days_hi": 25}},
            {"n": "slow", "days_to_pass": 60.0, "band": {"days_lo": 45, "days_hi": 90}}]
    tiers = [[r["n"] for r in t] for t in SC.rank_tiers(rows)]
    assert tiers == [["fast", "mid"], ["slow"]]


def test_rank_tiers_compares_against_the_leader_not_the_neighbour():
    """Overlap is not transitive. A chain of wide bands must not merge a whole
    table into one tier - each row is judged against the tier LEADER."""
    rows = [{"n": "a", "days_to_pass": 10.0, "band": {"days_lo": 9, "days_hi": 12}},
            {"n": "b", "days_to_pass": 13.0, "band": {"days_lo": 11, "days_hi": 30}},
            {"n": "c", "days_to_pass": 20.0, "band": {"days_lo": 18, "days_hi": 40}}]
    tiers = [[r["n"] for r in t] for t in SC.rank_tiers(rows)]
    assert tiers == [["a", "b"], ["c"]]


def test_rank_tiers_never_claims_anything_about_an_unmeasured_row():
    rows = [{"n": "a", "days_to_pass": 10.0, "band": None},
            {"n": "b", "days_to_pass": 90.0, "band": None},
            {"n": "c", "days_to_pass": None, "band": None}]
    tiers = [[r["n"] for r in t] for t in SC.rank_tiers(rows)]
    assert tiers == [["a", "b"], ["c"]]


def test_noise_floor_is_the_measured_one():
    """The reference line the whole rule is read against, pinned to the numbers
    in CLAUDE.md so it cannot drift silently."""
    assert NB.FLOOR_DAYS == (13.3, 26.5)
    assert NB.inside_floor(16.6) and not NB.inside_floor(11.0)


# --- the TradingView indicator each hypothesis ships ----------------------- #

def test_pine_is_an_indicator_and_fully_substituted():
    """Kris pastes this into TradingView. Two things must hold: every
    placeholder is filled (a stray `{{THR}}` is a compile error in his editor,
    not here), and it is an INDICATOR - a Pine *strategy* would print a profit
    factor that would then be compared with the board's, which is not a valid
    comparison. See core/pine.py."""
    import json

    from core import pine

    for name in ("vwapbreak", "vwap"):
        path = ROOT / "backtests" / name / "hypothesis.json"
        if not path.exists():
            continue
        p = pine.for_record(json.loads(path.read_text()))
        assert p is not None, f"{name} ships no indicator.pine"
        assert "{{" not in p["text"]
        assert "indicator(" in p["text"]
        assert "strategy(" not in p["text"]
        assert "//@version=5" in p["text"]
        assert p["params"], "no defaults were pulled from the folds"
