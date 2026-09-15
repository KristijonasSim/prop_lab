"""The daily-loss guard's overlay logic (H-041, `research/dailyguard.py`).

The guard drops entries taken after the UTC day's realised loss passed a limit.
The only way it can be wrong is by knowing something it should not: if it used
the day's FINAL total rather than the losses already booked at the moment of the
entry, it would skip trades on the strength of losses that had not happened yet
and every number it produced would be inflated.

That is the same class of bug as the three look-aheads found in
`strategies/vwap/engine.py` on 2026-09-05, and it is invisible in the output -
a look-ahead guard just looks like a good guard.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def guard():
    spec = importlib.util.spec_from_file_location(
        "dailyguard", ROOT / "strategies" / "vwapbreak" / "research" / "dailyguard.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m.apply_guard


def _trades(rows) -> pd.DataFrame:
    return pd.DataFrame({
        "entry_ts": pd.to_datetime([r[0] for r in rows], utc=True),
        "exit_ts": pd.to_datetime([r[1] for r in rows], utc=True),
        "r": [r[2] for r in rows]})


DAY = _trades([
    ("2026-01-05 01:00", "2026-01-05 04:00", -1.5),   # books -1.5% at 1% risk
    ("2026-01-05 05:00", "2026-01-05 09:00", +2.0),   # entered after that
    ("2026-01-05 06:00", "2026-01-05 10:00", +3.0),
    ("2026-01-06 01:00", "2026-01-06 05:00", -0.5),   # next day
])


def test_no_guard_keeps_everything(guard):
    assert len(guard(DAY, 0.01, None)) == 4


def test_the_guard_stops_entries_once_the_day_is_down(guard):
    kept = guard(DAY, 0.01, 0.010)
    assert [str(x)[5:16] for x in kept.entry_ts] == ["01-05 01:00", "01-06 01:00"]


def test_a_limit_the_day_never_reaches_changes_nothing(guard):
    assert len(guard(DAY, 0.01, 0.020)) == 4


def test_the_day_resets(guard):
    """The 06th's trade survives a guard that closed the 05th."""
    kept = guard(DAY, 0.01, 0.010)
    assert pd.Timestamp("2026-01-06 01:00", tz="UTC") in set(kept.entry_ts)


def test_a_trade_is_never_stopped_by_its_own_loss(guard):
    """THE LOOK-AHEAD TEST. The first trade of the day loses 1.5%, which is past
    every limit here - but it was ENTERED before that was known, so it must
    survive at any threshold."""
    for lim in (0.001, 0.005, 0.010, 0.020):
        kept = guard(DAY, 0.01, lim)
        assert pd.Timestamp("2026-01-05 01:00", tz="UTC") in set(kept.entry_ts)


def test_only_trades_closed_before_the_entry_count(guard):
    """A loser that is still OPEN when the next entry is decided cannot have
    booked anything yet, so it must not gate that entry."""
    overlap = _trades([
        ("2026-01-05 01:00", "2026-01-05 23:00", -3.0),   # closes at the END of day
        ("2026-01-05 05:00", "2026-01-05 09:00", +2.0),   # decided while it is open
    ])
    kept = guard(overlap, 0.01, 0.010)
    assert len(kept) == 2, "an unrealised loss gated an entry - that is a look-ahead"


def test_risk_scales_the_threshold(guard):
    """The same -1.5R day is -1.5% at 1% risk and -3.0% at 2%, so a -2% guard
    bites at the higher risk and not at the lower."""
    assert len(guard(DAY, 0.01, 0.020)) == 4
    assert len(guard(DAY, 0.02, 0.020)) == 2


# --------------------------------------------------------------------------- #
# H-041b's day-shuffled control (`research/dailyguard2.py`).
#
# The control is the decisive instrument in H-041b: the guard can only REMOVE
# trades, and removing trades cuts blow-ups on its own, so the whole question is
# whether the account signal beats a block of days chosen at random. If the
# control removes a different AMOUNT or a different SHAPE of trading than the
# guard it is measuring, the comparison is rigged in whichever direction the
# mismatch runs, and nothing in the output would show it.
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="module")
def dg2():
    spec = importlib.util.spec_from_file_location(
        "dailyguard2", ROOT / "strategies" / "vwapbreak" / "research" / "dailyguard2.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


SPREAD = _trades([
    ("2026-01-05 01:00", "2026-01-05 04:00", -1.5),
    ("2026-01-05 05:00", "2026-01-05 09:00", +2.0),
    ("2026-01-06 01:00", "2026-01-06 05:00", -0.5),
    ("2026-01-07 01:00", "2026-01-07 05:00", +1.0),
])


def test_blocked_days_counts_days_not_trades(dg2, guard):
    """Two trades dropped on one day is ONE blocked day. Counting trades would
    let the control remove several scattered days for one clustered one."""
    kept = guard(SPREAD, 0.01, 0.010)
    assert dg2.blocked_days(SPREAD, kept) == 1


def test_a_guard_that_bites_nothing_blocks_no_days(dg2, guard):
    assert dg2.blocked_days(SPREAD, guard(SPREAD, 0.01, None)) == 0
    assert dg2.blocked_days(SPREAD, guard(SPREAD, 0.01, 0.50)) == 0


def test_the_control_removes_whole_days(dg2):
    """Same shape as the guard: a blocked day loses every entry on it, not a
    sample of them."""
    rng = __import__("numpy").random.default_rng(0)
    kept = dg2.shuffle_days(SPREAD, 1, rng)
    days = pd.DatetimeIndex(kept.entry_ts).normalize().nunique()
    assert days == 2, "the control did not remove a whole day"


def test_the_control_blocks_the_number_of_days_it_is_given(dg2):
    """The match that makes the comparison fair. Checked across seeds, because
    one seed agreeing proves nothing about the draw."""
    np = __import__("numpy")
    for seed in range(10):
        kept = dg2.shuffle_days(SPREAD, 2, np.random.default_rng(seed))
        assert pd.DatetimeIndex(kept.entry_ts).normalize().nunique() == 1


def test_the_control_with_no_days_to_block_changes_nothing(dg2):
    np = __import__("numpy")
    assert len(dg2.shuffle_days(SPREAD, 0, np.random.default_rng(0))) == len(SPREAD)


def test_spearman_is_signed_the_way_the_criterion_reads_it(dg2):
    """The pre-registered bar is rho >= +0.7 between the THRESHOLD VALUE and the
    blow-up rate: a looser guard (bigger threshold) should blow up more. A sign
    error here would invert the kill criterion."""
    assert dg2.spearman([0.005, 0.010, 0.015, 0.020], [40, 45, 50, 55]) == pytest.approx(1.0)
    assert dg2.spearman([0.005, 0.010, 0.015, 0.020], [55, 50, 45, 40]) == pytest.approx(-1.0)
