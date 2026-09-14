"""`core.search_cost` - the price of a screen, owed since 2026-09-13 (NEXT.md D2).

The arithmetic is trivial; these exist so the NUMBERS IN THE DOCS stay true. The
96-tests-at-95th figure is quoted in NEXT.md and the 16-cells-at-90th figure is
the kill criterion of H-042/H-043, so both are pinned here rather than left to be
recomputed by hand the next time someone needs them.
"""
from __future__ import annotations

import pytest

from core.search_cost import (expected_false, resolvable, sidak_pctile, verdict)


def test_the_number_next_md_quotes():
    """NEXT.md item D2: 96 tests at a 95th percentile expect 4.8 false passes."""
    assert expected_false(96, 95.0) == 4.8


def test_the_number_h042_closed_an_axis_on():
    """H-042 measured 16 cells against a 10th-percentile null and exactly one
    cleared it. 1.6 is what 16 cells produce by construction."""
    assert expected_false(16, 90.0) == 1.6
    assert expected_false(28, 90.0) == 2.8       # H-043's 16 + 12


def test_a_single_test_costs_its_own_alpha():
    assert expected_false(1, 95.0) == 0.05
    assert expected_false(0, 95.0) == 0.0


def test_sidak_tightens_with_the_number_of_tests():
    a, b, c = sidak_pctile(1), sidak_pctile(16), sidak_pctile(96)
    assert a < b < c < 100.0
    assert a == pytest.approx(95.0, abs=0.01)


def test_a_200_resample_null_cannot_express_a_wide_screen_s_bar():
    """The point of `resolvable`: a screen can be too wide to rescue by raising
    its own bar, and saying so is the honest output."""
    assert resolvable(1, 200)
    assert not resolvable(16, 200)
    assert not resolvable(96, 200)


def test_the_verdict_line_says_when_the_null_is_too_coarse():
    v = verdict(96, 95.0, 200)
    assert "4.8 false passes" in v
    assert "cannot resolve" in v
    assert "cannot resolve" not in verdict(1, 95.0, 200)


@pytest.mark.parametrize("bad", [(-1, 95.0), (10, -1.0), (10, 101.0)])
def test_nonsense_is_refused(bad):
    with pytest.raises(ValueError):
        expected_false(*bad)
