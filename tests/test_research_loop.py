"""Pin the research loop's safety properties.

This loop is meant to run unattended, so the things that would quietly ruin it
have to fail loudly here instead. Three of them:

  * a signal that reads the future,
  * a proposer that re-tests what the ledger already paid for,
  * a feed tested in both directions, which is a free second attempt.

The first is the one that statistics cannot catch - arXiv 2608.27734 planted an
oracle with Sharpe 34.7 and the deflated Sharpe scored it 1.00.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from research import propose as P                                  # noqa: E402
from research import run as R                                      # noqa: E402
from research import vocab as V                                    # noqa: E402


# ---------------------------------------------------------------------------
# the registry tells the truth
# ---------------------------------------------------------------------------
def test_every_feed_declares_its_lag_and_its_sign():
    for f in V.FEEDS.values():
        assert f.lag_floor >= 1, f"{f.name} would be readable same-day"
        assert f.lag_reason, f"{f.name} has no stated reason for its lag"
        if f.prior_sign:
            assert f.sign_reason, f"{f.name} claims a sign with no mechanism"
            assert f.prior_sign in (1, -1)


def test_every_feed_loads():
    for f in V.FEEDS.values():
        s = f.load()
        assert len(s) > 100, f"{f.name} has only {len(s)} rows"
        assert s.index.is_monotonic_increasing


def test_transforms_are_backward_looking():
    """A transform may not use a value dated later than the row it fills.

    Built by feeding a step function: everything before the step is identical,
    so any transform that peeked at the future would differ BEFORE the step.
    """
    idx = pd.date_range("2020-01-01", periods=400, freq="D", tz="UTC")
    a = pd.Series(np.zeros(400), index=idx)
    b = a.copy()
    b.iloc[300:] = 1000.0                     # a shock only in the tail
    for name, (fn, needs_w) in V.TRANSFORMS.items():
        w = 20 if needs_w else 0
        ta, tb = fn(a, w), fn(b, w)
        head_a, head_b = ta.iloc[:300], tb.iloc[:300]
        same = ((head_a.isna() & head_b.isna()) |
                np.isclose(head_a.fillna(0), head_b.fillna(0)))
        assert same.all(), f"transform '{name}' leaks the future"


# ---------------------------------------------------------------------------
# the runner applies the lag, and the forward return starts after the decision
# ---------------------------------------------------------------------------
def test_signal_is_shifted_by_the_declared_lag(monkeypatch):
    """The value used on day d must be the feed's value from d - lag."""
    idx = pd.date_range("2022-01-03", periods=300, freq="D", tz="UTC")
    feed = pd.Series(np.arange(300.0), index=idx, name="RAMP")
    bars = pd.DataFrame(
        {"open": np.linspace(100, 130, 300),
         "close": np.linspace(100, 130, 300),
         "volume": np.ones(300)}, index=idx)

    spec = V.FeedSpec(name="RAMP", desc="test ramp", lag_floor=2,
                      lag_reason="test", prior_sign=1, sign_reason="test",
                      loader=lambda: feed)
    monkeypatch.setitem(V.FEEDS, "RAMP", spec)
    monkeypatch.setattr(R, "daily_frame", lambda m: bars)

    c = P.Candidate(feed="RAMP", transform="level", window=0, lag=2,
                    market="XAUUSD", hold=3, direction=1, mechanism="test")
    sig, fwd, _ = R.build_signal(c)

    # level transform, lag 2: the signal on day i is the raw value from day i-2
    day = idx[50]
    assert sig.loc[day] == pytest.approx(feed.iloc[48])
    # and the forward return must look strictly forward
    assert fwd.loc[day] == pytest.approx(
        (bars.open.iloc[53] / bars.open.iloc[50] - 1) * 1e4)


def test_lag_below_the_floor_is_refused():
    with pytest.raises(P.ProposalError, match="below the floor"):
        P.validate({"feed": "DFII10", "transform": "level", "market": "XAUUSD",
                    "hold": 5, "lag": 0, "direction": -1,
                    "mechanism": "x" * 50})


# ---------------------------------------------------------------------------
# the search cannot cheat
# ---------------------------------------------------------------------------
def test_a_feed_is_tested_in_one_direction_only():
    space = P.enumerate_space()
    seen: dict[str, int] = {}
    for c in space:
        seen.setdefault(c.feed, c.direction)
        assert seen[c.feed] == c.direction, (
            f"{c.feed} appears in both directions - that is a free second "
            "attempt at the same question")


def test_flipping_a_declared_sign_is_refused():
    spec = V.FEEDS["DFII10"]
    with pytest.raises(P.ProposalError, match="declared prior sign"):
        P.validate({"feed": "DFII10", "transform": "level", "market": "XAUUSD",
                    "hold": 5, "direction": -spec.prior_sign,
                    "mechanism": "x" * 50})


def test_unknown_feeds_and_transforms_are_refused():
    for bad, match in [
        ({"feed": "MADE_UP", "transform": "level"}, "unknown feed"),
        ({"feed": "DFII10", "transform": "neural"}, "unknown transform"),
    ]:
        with pytest.raises(P.ProposalError, match=match):
            P.validate({**bad, "market": "XAUUSD", "hold": 5,
                        "direction": -1, "mechanism": "x" * 50})


def test_known_dead_feeds_are_refused_with_the_reason():
    """The model is told WHY, so the next attempt is corrected not repeated."""
    assert "COT" in P.KNOWN_DEAD
    assert "H-030" in P.KNOWN_DEAD["COT"]


def test_a_mechanism_is_mandatory():
    with pytest.raises(P.ProposalError, match="mechanism"):
        P.validate({"feed": "DFII10", "transform": "level", "market": "XAUUSD",
                    "hold": 5, "direction": -1, "mechanism": "looks good"})


def test_hold_and_window_must_come_from_the_enum():
    with pytest.raises(P.ProposalError, match="hold must be"):
        P.validate({"feed": "DFII10", "transform": "level", "market": "XAUUSD",
                    "hold": 7, "direction": -1, "mechanism": "x" * 50})
    with pytest.raises(P.ProposalError, match="needs a window"):
        P.validate({"feed": "DFII10", "transform": "zscore", "window": 33,
                    "market": "XAUUSD", "hold": 5, "direction": -1,
                    "mechanism": "x" * 50})


def test_candidate_key_ignores_the_story():
    """Two different rationales for the same test are the same test."""
    kw = dict(feed="DFII10", transform="level", window=0, lag=1,
              market="XAUUSD", hold=5, direction=-1)
    assert (P.Candidate(**kw, mechanism="one story").key ==
            P.Candidate(**kw, mechanism="a different story").key)


def test_the_proposer_spreads_across_feeds():
    """Breadth-first, not depth-first: eight candidates must not all be the
    same feed with different windows. That pattern closed eight axes of H-027
    and produced nothing."""
    got = P.propose_library(8)
    assert len({c.feed for c in got}) >= 4


# ---------------------------------------------------------------------------
# the event count must not depend on a signal's units
# ---------------------------------------------------------------------------
def test_event_count_works_on_strictly_positive_signals():
    """A percentile, a VIX level, a spread and a tick count never change sign.

    Counting crossings with `np.sign` scored them ONE episode however long they
    ran, so they were killed at the first gate for a property of their units
    rather than of their information. 12 of 219 loop trials died this way before
    2026-09-18, and every `level` and `pctile` candidate was affected.
    """
    from core.screen import independent_events

    rng = np.random.default_rng(0)
    pct = pd.Series(rng.random(1000))          # strictly positive, oscillating
    centred = pd.Series(rng.normal(size=1000))
    assert independent_events(pct, 1) > 400
    assert independent_events(centred, 1) > 400

    # shifting a signal must not change how many episodes it has
    assert (independent_events(centred + 1000.0, 1)
            == independent_events(centred, 1))
    # nor must rescaling it
    assert (independent_events(centred * 37.0, 1)
            == independent_events(centred, 1))


def test_event_count_still_rejects_genuinely_slow_signals():
    """The gate exists to kill H-051 (794 rows, three swings). It still must.

    The three-block case counts 1 rather than 3 because the median coincides
    with one of only two levels - an under-count, which errs toward rejecting.
    That is the safe direction and the one this file argues for everywhere else.
    """
    from core.screen import independent_events
    slow = pd.Series(np.repeat([1.0, 2.0, 1.0], 300))
    assert independent_events(slow, 1) <= 3
    assert independent_events(pd.Series([5.0] * 100), 1) == 1
    # the overlap cap is unaffected
    rng = np.random.default_rng(1)
    assert independent_events(pd.Series(rng.random(1000)), 20) == 50
