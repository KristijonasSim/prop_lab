"""`core.probe`'s null must draw from the SAME HOUR as the events it scores.

THE BUG THIS PINS, found 2026-09-13 and fixed 2026-09-14. The null shifted
events by any offset at all, so an event that always fires at 00:00 UTC was
compared against a population drawn from every hour of the day. Gold's hours are
not interchangeable - the forward return after the 00:00 bar is a different
object from the forward return after the NY open - so the null was drawing from
a different population than the real events and was easier to beat than it
should have been. NEXT.md priced it at about 5bps for a short-side daily arm,
and every screen run through this module before the fix is affected.

`test_the_old_free_shift_would_have_promoted_it` is the test that fails if the
fix is ever reverted: it builds a market whose ONLY structure is an hour-of-day
effect - no event edge at all - and shows the free shift calls it a 100th
percentile finding.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from core.probe import forward_bps, hour_matched_shifts, probe

HOURS = 24 * 120        # 120 days of hourly bars


def _market(seed: int = 0) -> pd.DataFrame:
    """A market with NO event edge and ONE hour-of-day effect.

    The 00:00 -> 01:00 -> 02:00 leg carries a +10bps drift; every other
    hour is noise, so a midnight event inherits an edge it did not earn.
    Nothing here knows about any event.
    """
    idx = pd.date_range("2026-01-01", periods=HOURS, freq="1h", tz="UTC")
    rng = np.random.default_rng(seed)
    step = np.where(idx.hour == 2, 10.0, 0.0) + rng.normal(0, 4.0, HOURS)
    open_ = 2000.0 * np.exp(np.cumsum(step) / 1e4)
    return pd.DataFrame({"open": open_, "high": open_, "low": open_,
                         "close": open_, "volume": 1.0}, index=idx)


def _midnight(df: pd.DataFrame) -> np.ndarray:
    return np.asarray(df.index.hour == 0)


def test_shifts_exist_on_an_hourly_grid(df=None):
    df = _market()
    idx = np.flatnonzero(_midnight(df))
    s = hour_matched_shifts(df.index, idx)
    assert len(s) > 50
    assert all(x % 24 == 0 for x in s)


def test_every_shift_keeps_the_time_of_day():
    df = _market()
    idx = np.flatnonzero(_midnight(df))
    mod = (df.index.hour * 60 + df.index.minute).values
    for s in hour_matched_shifts(df.index, idx):
        assert np.array_equal(mod[(idx + s) % len(df)], mod[idx])


def test_a_grid_that_cannot_divide_a_day_falls_back():
    """A 7-hour bar cannot preserve the hour by shifting whole days, so the
    function says so rather than returning a shift that quietly does not."""
    idx = pd.date_range("2026-01-01", periods=300, freq="7h", tz="UTC")
    assert len(hour_matched_shifts(idx, np.arange(0, 300, 11))) == 0


def test_the_hour_matched_null_does_not_promote_an_hour_of_day_artifact():
    """THE FIX. The event carries no edge - only the 01:00 hour does - so a null
    drawn from the same hour must find the event unremarkable."""
    df = _market()
    r = probe(df, _midnight(df), [1], "XAUUSD", "midnight", n_null=300)
    assert bool(r.null_hour_matched.iloc[0])
    assert r.pctile.iloc[0] < 95.0, "an hour-of-day artifact was promoted"


def test_the_old_free_shift_would_have_promoted_it():
    """The counterfactual, so the value of the fix is measured and not asserted.

    Same market, same events, null shifted freely - which is what the module did
    until 2026-09-14.
    """
    df = _market()
    ev = _midnight(df)
    fwd = forward_bps(df, 1)
    real = float(np.nanmean(fwd[ev]))
    idx = np.flatnonzero(ev)
    rng = np.random.default_rng(0)
    n = len(df)
    free = np.array([np.nanmean(fwd[(idx + rng.integers(1, n)) % n])
                     for _ in range(300)])
    free_pct = float((free < real).mean() * 100)

    matched = probe(df, ev, [1], "XAUUSD", "midnight", n_null=300).pctile.iloc[0]
    # A free shift lands on the event hour only 1 bar in 24, so the ceiling for
    # this market is about 95.8 and the test is written just under it.
    assert free_pct >= 94.0, "the counterfactual no longer reproduces the bug"
    assert matched < free_pct - 20, (
        f"the fix changed nothing: free {free_pct:.1f} vs matched {matched:.1f}")
