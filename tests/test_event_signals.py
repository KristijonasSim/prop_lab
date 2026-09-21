"""The 2026-09-21 fix: the pipeline can now see an INTERMITTENT signal.

`research/poscontrol.py` planted twenty edges that were real and tradeable.
Screened the way the loop screened before today, seven were found. Thirteen
were missed, and every one of them was a signal that carries information on a
small fraction of bars - which is what most trading rules are, and the shape of
H-027 itself.

Two defects, one root:
  * `core.screen` bucketed EVERY bar, diluting a 5%-live signal twentyfold.
  * `research.vocab` had four transforms and all four were continuous, so an
    event signal could not be expressed in the first place.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from core.screen import bucket_response, screen
from research import propose, vocab


@pytest.fixture
def planted():
    """A real edge that only speaks on 5% of bars. Noise the rest of the time."""
    rng = np.random.default_rng(0)
    n = 6000
    noise = pd.Series(rng.standard_normal(n) * 20.0)     # 20bps bars
    sig = pd.Series(rng.standard_normal(n))
    live = pd.Series(rng.random(n) < 0.02)               # speaks 2% of the time
    fwd = noise + 25.0 * sig * live
    # On its own events this is enormous - tens of bps against a 3.3bps bar.
    # Spread over every bar it is 2% of that, which is the whole problem.
    return sig, fwd, live


def test_the_old_way_misses_a_real_edge(planted):
    sig, fwd, live = planted
    out = screen("all bars", sig, fwd, round_trip_bps=1.64, hold=1, run_null=False)
    assert out.verdict == "DEAD", (
        "if this now passes, the dilution defect is gone and this test is stale")


def test_the_fix_finds_the_same_edge(planted):
    sig, fwd, live = planted
    out = screen("its events", sig, fwd, round_trip_bps=1.64, hold=1,
                 run_null=False, fires=live)
    assert out.verdict == "WORK", out.notes


def test_the_fix_does_not_manufacture_an_edge_from_noise():
    """The mask must not become a way of passing. Same shape, no planted edge."""
    rng = np.random.default_rng(1)
    n = 6000
    sig = pd.Series(rng.standard_normal(n))
    fwd = pd.Series(rng.standard_normal(n) * 20.0)
    live = pd.Series(rng.random(n) < 0.05)
    out = screen("noise", sig, fwd, round_trip_bps=1.64, hold=1, fires=live)
    assert out.verdict == "DEAD"


def test_the_mask_shrinks_the_sample_it_measures(planted):
    sig, fwd, live = planted
    all_bars = bucket_response(sig, fwd)
    events = bucket_response(sig, fwd, fires=live)
    assert events["rows"] < all_bars["rows"] / 10
    assert abs(events["effect"]) > abs(all_bars["effect"]) * 5


def test_an_event_count_is_events_not_bars(planted):
    sig, fwd, live = planted
    out = screen("x", sig, fwd, round_trip_bps=1.64, hold=1, run_null=False,
                 fires=live)
    assert out.events == pytest.approx(int(live.sum()), rel=0.01)


# ------------------------------------------------- the vocabulary can say it
@pytest.mark.parametrize("name", sorted(vocab.EVENT_TRANSFORMS))
def test_every_event_transform_is_intermittent(name):
    fn, _ = vocab.EVENT_TRANSFORMS[name]
    s = pd.Series(np.random.default_rng(2).standard_normal(2000).cumsum())
    values, fires = fn(s, 60)
    assert fires.dtype == bool
    assert len(fires) == len(s)
    assert 0 < fires.mean() < 0.35, f"{name} fires on {fires.mean():.0%} of bars"


def test_an_extreme_fires_on_entry_not_throughout():
    """A signal that fires on every bar of one long excursion counts one
    episode as fifty events and flatters every count downstream."""
    s = pd.Series(np.r_[np.zeros(300), np.full(300, 10.0)])
    _, fires = vocab.EVENT_TRANSFORMS["extreme_high"][0](s, 60)
    assert fires.sum() < 10, "an extreme must fire on entry, not while it stays"


def test_the_proposer_offers_event_transforms():
    space = propose.enumerate_space()
    offered = {c.transform for c in space}
    assert set(vocab.EVENT_TRANSFORMS) <= offered
