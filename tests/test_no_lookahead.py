"""The truncation test. The single most valuable test in this repo.

Cut the series short, rerun, and every trade that had already closed must come
back byte-identical. A kernel that peeks at a future bar cannot satisfy this,
because the future bar is no longer there.

WHY THIS EXISTS. Three look-aheads were found in `strategies/vwap/engine.py` on
2026-09-05 by reading the code line by line. They had been there for weeks and
they killed every crypto result in the project: walk-forward cells clearing
PF 1.20 at 2x went 11 to 0 on BTCUSDT, best cell 2.305 to 0.882. This test would
have caught all three the moment they were written, in under a second.

`strategies/ribbon/test_parity.py` had a version of this for ribbon's INDICATORS
only. It existed, it worked, and nobody generalised it to the kernels.
"""
from __future__ import annotations

import numpy as np
import pytest

from tests.kernels import IDS, KERNELS, T_EXIT_I

# Where to cut. Several, because a kernel can be honest at one boundary and not
# at another - a session anchor, a rolling window edge, an open position.
CUTS = (0.55, 0.70, 0.85, 0.95)


def _closed_before(trades: np.ndarray, cut: int) -> np.ndarray:
    """Trades that had genuinely finished before the cut.

    Two exclusions, and only two:

    * exit at or after the cut - the truncated run has no bars left to close the
      position on, so a difference there says nothing about look-ahead;
    * exit on the LAST bar of the truncated run. Both kernels force-close an open
      position at the end of the data (`R_EOD`), so truncating manufactures one
      extra "closed" trade that the full run has no reason to produce. That is an
      artifact of where the series ends, not of the kernel reading forward - it
      was the one failure this test found on its first run, on ribbon's alternate
      configuration, 126 trades against 127.

    Everything else must match to the bit.
    """
    if len(trades) == 0:
        return trades
    return trades[trades[:, T_EXIT_I] < cut - 1]


@pytest.mark.parametrize("kernel", KERNELS, ids=IDS)
@pytest.mark.parametrize("frac", CUTS)
def test_truncation_does_not_change_closed_trades(kernel, bars, frac):
    cut = int(len(bars) * frac)
    full = kernel.run(bars, kernel.cfg, 1.0, 0.5)
    short = kernel.run(bars.iloc[:cut], kernel.cfg, 1.0, 0.5)

    a, b = _closed_before(full, cut), _closed_before(short, cut)
    assert len(a) == len(b), (
        f"{kernel.name}: {len(a)} trades closed before bar {cut} on the full "
        f"series, {len(b)} on the truncated one. The kernel is using bars that "
        f"had not closed yet.")
    if len(a):
        np.testing.assert_array_equal(
            a, b, err_msg=f"{kernel.name}: a closed trade changed when later "
                          f"bars were removed. That is a look-ahead.")


@pytest.mark.parametrize("kernel", KERNELS, ids=IDS)
def test_truncation_holds_on_a_second_configuration(kernel, bars):
    """One parameter set passing is not evidence about the kernel. `cfg_alt`
    turns on a different exit path - ATR stops, a target, a hold limit - because
    that is where a look-ahead most easily hides."""
    cut = int(len(bars) * 0.75)
    a = _closed_before(kernel.run(bars, kernel.cfg_alt, 1.0, 0.5), cut)
    b = _closed_before(kernel.run(bars.iloc[:cut], kernel.cfg_alt, 1.0, 0.5), cut)
    assert len(a) == len(b)
    if len(a):
        np.testing.assert_array_equal(a, b)


@pytest.mark.parametrize("kernel", KERNELS, ids=IDS)
def test_appending_future_bars_changes_nothing_already_decided(kernel, bars):
    """The same invariant from the other end: run on the first 70%, then on the
    whole thing, and the early trades must be identical. Equivalent in principle
    to truncation, but it fails differently when a feature is computed over the
    whole array and then indexed - a normalisation over the full series, say,
    which is the classic silent look-ahead."""
    cut = int(len(bars) * 0.70)
    early = kernel.run(bars.iloc[:cut], kernel.cfg, 1.0, 0.5)
    later = kernel.run(bars, kernel.cfg, 1.0, 0.5)
    a, b = _closed_before(early, cut), _closed_before(later, cut)
    assert len(a) == len(b)
    if len(a):
        np.testing.assert_array_equal(a, b)
