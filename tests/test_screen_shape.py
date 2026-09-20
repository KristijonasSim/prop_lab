"""Pin the two gates added 2026-09-20 — concentration and seat survival.

WHY THEY EXIST. `docs/DIAGNOSIS_2026-09-20.md` measured that H-027, the only
survivor of 48 hypotheses, earns 188.4 R over 634 walk-forward days of which
**two days are 65%**; drop the largest ten and the total is **-24.7 R**. Every
one of the screen's original five checks passes that series, because all five
look at the size and shape of a bucket response and none of them looks at the
series the response implies.

These tests pin the two properties that would have caught it:

  * a handful of decisions must not carry the profit,
  * the seat must be fundable inside a quarter at the risk that survives its
    own worst stretch.

The first test uses H-027's real stored series, so if anybody loosens a bar the
project's own counter-example is what fails.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.screen import (CONC_K, MAX_CONC, MAX_FUND_DAYS, Screen,  # noqa: E402
                         concentration, fund_days, implied_pnl, screen)

DAILY = ROOT / "backtests" / "vwapbreak" / "daily_traded.json"


def h027() -> np.ndarray:
    return np.array(json.loads(DAILY.read_text())["XAUUSD|1h"]["r"])


# ---------------------------------------------------------------------------
# the counter-example the gates were built from


@pytest.mark.skipif(not DAILY.exists(), reason="walk-forward cache absent")
def test_h027_fails_both_new_gates():
    """The project's only survivor is rejected by both, and by a wide margin."""
    r = h027()
    assert r.sum() == pytest.approx(188.4, abs=0.5)

    c = concentration(r)
    assert c > MAX_CONC, "5 best days must still carry over half the profit"
    assert c == pytest.approx(0.89, abs=0.02)

    d = fund_days(r, hold=1)
    assert d > MAX_FUND_DAYS
    assert d == pytest.approx(109, abs=2)


@pytest.mark.skipif(not DAILY.exists(), reason="walk-forward cache absent")
def test_dropping_ten_days_turns_h027_negative():
    """The one fact the whole diagnosis rests on. Pinned so it cannot drift."""
    r = np.sort(h027())[::-1]
    assert r[:2].sum() / r.sum() > 0.6        # two days, most of the profit
    assert r[10:].sum() < 0                    # drop ten of 634 and it loses


# ---------------------------------------------------------------------------
# the gates themselves


def test_concentration_is_a_share_not_a_count():
    """A flat series concentrates nothing; a lottery concentrates everything."""
    flat = np.full(500, 0.10)
    assert concentration(flat) < 0.05

    lottery = np.full(500, -0.10)
    lottery[:CONC_K] = 20.0
    assert concentration(lottery) > MAX_CONC


def test_concentration_rejects_a_series_that_never_made_money():
    """Nothing to concentrate is not a pass. It scores 1.0 and dies."""
    assert concentration(np.full(500, -0.05)) == 1.0
    assert concentration(np.zeros(500)) == 1.0
    assert concentration(np.array([1.0, 2.0])) == 1.0       # fewer rows than k


def test_fund_days_is_independent_of_the_size_traded():
    """Risk per trade cancels in the formula, so scaling must not move it."""
    rng = np.random.default_rng(7)
    pnl = rng.normal(0.05, 1.0, 800)
    a = fund_days(pnl, hold=1)
    b = fund_days(pnl * 37.0, hold=1)
    assert a == pytest.approx(b, rel=1e-9)


def test_fund_days_is_infinite_when_the_seat_is_never_funded():
    assert not np.isfinite(fund_days(np.full(300, -0.10), hold=1))
    assert not np.isfinite(fund_days(np.empty(0), hold=1))


def test_fund_days_is_zero_when_there_is_no_drawdown():
    """The sign error the first draft shipped: no hole must not read as `never`."""
    assert fund_days(np.full(600, 0.10), hold=1) == 0.0


def test_fund_days_grows_with_drawdown():
    """Same total, a deeper hole first, later funding. The formula's whole point."""
    shallow = np.full(600, 0.10)
    shallow[:20] = -0.10
    shallow[20:40] = 0.30              # total unchanged, a small hole first
    deep = np.full(600, 0.10)
    deep[:20] = -1.00
    deep[20:40] = 1.20                 # total unchanged, a much deeper hole
    assert deep.sum() == pytest.approx(shallow.sum())
    assert fund_days(deep, 1) > fund_days(shallow, 1)


def test_hold_is_applied_so_overlaps_are_not_counted_twice():
    """A 5-day hold is five copies of one decision. implied_pnl samples it once."""
    sig = pd.Series(np.arange(1000, dtype=float))
    fwd = pd.Series(np.arange(1000, dtype=float))
    assert len(implied_pnl(sig, fwd, hold=1)) == 1000
    assert len(implied_pnl(sig, fwd, hold=5)) == 200


# ---------------------------------------------------------------------------
# wired into the screen, in the right order


def _ramp(n=1200, seed=0):
    """A monotone, cheap-to-clear signal: fwd rises with sig."""
    rng = np.random.default_rng(seed)
    s = pd.Series(rng.normal(0, 1, n))
    f = s * 40.0 + pd.Series(rng.normal(0, 5, n))
    return s, f


def test_a_clean_signal_still_passes_all_seven():
    sig, fwd = _ramp()
    out = screen("clean", sig, fwd, round_trip_bps=1.0, hold=1, run_null=False)
    assert out.verdict == "WORK", out.notes
    assert out.conc < MAX_CONC
    assert out.fund_days < MAX_FUND_DAYS


def _lottery(n=1200, seed=1):
    """H-027's shape in miniature.

    A gentle monotone ramp - so the response is real and clears the cost bar,
    the median and the rho - with five enormous winners sitting in the top
    bucket. Every one of the original five checks passes this. It is exactly
    the series the project spent a month failing to reject.
    """
    rng = np.random.default_rng(seed)
    s = pd.Series(rng.normal(0, 1, n))
    f = s * 3.0 + pd.Series(rng.normal(0, 2, n))
    f.loc[s.nlargest(5).index] += 100_000.0
    return s, f


def test_the_original_five_checks_all_pass_the_lottery():
    """Stated as a test because it is the reason the two gates were needed."""
    from core import screen as S
    sig, fwd = _lottery()
    ev = S.independent_events(sig, 1)
    r = S.bucket_response(sig, fwd)
    assert ev >= S.MIN_EVENTS
    assert abs(r["effect"]) >= 1.0 * S.COST_MULT
    assert np.sign(r["effect"]) == np.sign(r["median"])
    assert abs(r["rho"]) >= S.MIN_RHO


def test_the_lottery_dies_on_concentration():
    sig, fwd = _lottery()
    out = screen("lottery", sig, fwd, round_trip_bps=1.0, hold=1,
                 run_null=False)
    assert out.verdict == "DEAD"
    assert out.conc > MAX_CONC
    assert "carry" in " ".join(out.notes)


def test_the_gates_run_before_the_null():
    """Concentration is O(n) and the null is 200 shuffles. Order is the point.

    A concentrated candidate must die without the null ever being computed, so
    `p_null` is still None on the way out.
    """
    sig, fwd = _lottery()
    out = screen("lottery", sig, fwd, round_trip_bps=1.0, hold=1,
                 run_null=True)
    assert out.verdict == "DEAD"
    assert out.p_null is None


def test_header_and_row_stay_aligned():
    """The loop prints these as a table; a silent misalignment is a bug."""
    from core.screen import HEADER
    row = str(Screen(name="x", verdict="DEAD", conc=0.9, fund_days=120.0))
    assert len(row.split("  ")[0]) <= len(HEADER)
