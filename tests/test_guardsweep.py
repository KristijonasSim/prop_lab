"""The matched-drop null of H-042 (`research/guardsweep.py`).

THE NULL IS THE WHOLE STUDY. The daily-loss guard removes 38% of the trades on
1h, and less exposure lowers a blow-up rate on its own - so the guard's result
only means something if it beats a control that drops the same trades from the
WRONG days. If the null silently dropped fewer trades than the real guard, or
dropped them from the same days, it would be a control that cannot fail and the
arm would look like a winner whatever it did.

These pin the two properties the control rests on: the count is matched, and the
day information is destroyed.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def gs():
    spec = importlib.util.spec_from_file_location(
        "guardsweep", ROOT / "strategies" / "vwapbreak" / "research" / "guardsweep.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _trades(rows) -> pd.DataFrame:
    return pd.DataFrame({
        "entry_ts": pd.to_datetime([r[0] for r in rows], utc=True),
        "exit_ts": pd.to_datetime([r[1] for r in rows], utc=True),
        "r": [r[2] for r in rows]}).sort_values("entry_ts").reset_index(drop=True)


# Three days, four entries each. Day 1 opens -2R and keeps trading, so a -1%
# guard at 1% risk cuts its last three entries and leaves the other days alone.
ROWS = []
for di, d in enumerate(("2026-01-05", "2026-01-06", "2026-01-07")):
    for h, r in zip((1, 5, 9, 13), ((-2.0, 1.0, 1.0, 1.0) if di == 0 else
                                    (0.5, 0.5, 0.5, 0.5))):
        ROWS.append((f"{d} {h:02d}:00", f"{d} {h+2:02d}:00", r))
TR = _trades(ROWS)


def test_the_guard_cuts_the_bad_day_only(gs):
    kept = gs.apply_guard(TR, 0.01, 0.010)
    assert len(kept) == 9
    d = gs.drops_per_day(TR, kept)
    assert d.loc[pd.Timestamp("2026-01-05", tz="UTC")] == 3
    assert d.drop(pd.Timestamp("2026-01-05", tz="UTC")).sum() == 0


def test_the_null_drops_the_same_number(gs):
    """Matched count. A control that trades more than the arm is not a control."""
    kept = gs.apply_guard(TR, 0.01, 0.010)
    d = gs.drops_per_day(TR, kept)
    for seed in range(20):
        assert len(gs.matched_null(TR, d, seed)) == len(kept)


def test_the_null_moves_the_drop_to_other_days(gs):
    """Day information destroyed: across seeds the cut must land on days the
    real guard left alone, or the permutation is not permuting anything."""
    kept = gs.apply_guard(TR, 0.01, 0.010)
    d = gs.drops_per_day(TR, kept)
    hit = set()
    for seed in range(30):
        n = gs.matched_null(TR, d, seed)
        gone = TR[~TR.index.isin(set(n.index))]
        hit |= set(pd.DatetimeIndex(gone.entry_ts).normalize())
    assert len(hit) >= 2, "the null always cut the same day"


def test_the_null_takes_the_end_of_its_day(gs):
    """Same end-of-day shape as the guard: a cut day keeps its FIRST entries."""
    kept = gs.apply_guard(TR, 0.01, 0.010)
    d = gs.drops_per_day(TR, kept)
    n = gs.matched_null(TR, d, 0)
    for day, grp in n.groupby(pd.DatetimeIndex(n.entry_ts).normalize()):
        hours = sorted(pd.DatetimeIndex(grp.entry_ts).hour)
        assert hours == sorted(hours)[:len(hours)]
        assert hours[0] == 1, "a cut day lost its first entry, not its last"


def test_no_guard_means_no_null_drop(gs):
    d = gs.drops_per_day(TR, gs.apply_guard(TR, 0.01, None))
    assert d.sum() == 0
    assert len(gs.matched_null(TR, d, 0)) == len(TR)


def test_the_day_grid_does_not_shrink_when_trades_are_dropped(gs):
    """An arm that skips the first day must still be scored on the same
    calendar, or it gets a different set of account start days for free."""
    grid = gs.day_grid(TR)
    assert len(grid) == 3
    late = TR[pd.DatetimeIndex(TR.entry_ts).normalize() > pd.Timestamp("2026-01-05", tz="UTC")]
    d = gs.daily(late, grid)
    assert len(d) == 3
    assert d.iloc[0] == 0.0
    assert np.isclose(d.sum(), late.r.sum())


def test_daily_keeps_every_r(gs):
    d = gs.daily(TR, gs.day_grid(TR))
    assert np.isclose(d.sum(), TR.r.sum())
