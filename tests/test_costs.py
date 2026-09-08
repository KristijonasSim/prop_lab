"""Cost must behave like cost: monotone, and linear in the multiple.

Two separate claims, and the project leans on both.

MONOTONE. Every headline in this repo is quoted at 1x, 2x and 3x cost. If profit
factor did not fall as cost rose, a sign error somewhere in the fee arithmetic
would be adding money at higher cost and the whole cost-robustness column would
be backwards.

LINEAR. `strategies/vwap/stage18_goldbook.py::reprice` and
`strategies/ribbon/stage11_reprice.py` re-price stored trades ALGEBRAICALLY
rather than re-simulating: `c = r_1x - r_2x` recovers one round trip in R, and
any other cost level follows from it. That is exact only if R really is affine
in the cost multiple. Both hypotheses' MEASURED-cost board numbers - H-002's
143.6 days and H-016's 175.9 - come out of that identity, so it is load-bearing
and had never been tested.
"""
from __future__ import annotations

import numpy as np
import pytest

from tests.kernels import IDS, KERNELS, T_ENTRY_I, T_EXIT_I, T_R

FEE, SLIP = 1.0, 0.5
LEVELS = (0.0, 1.0, 2.0, 3.0)


def pf(r: np.ndarray) -> float:
    w, l = r[r > 0].sum(), -r[r < 0].sum()
    return float(w / l) if l > 0 else float("inf")


def _runs(kernel, bars, cfg):
    """The kernel at each cost multiple, keyed by multiple."""
    return {k: kernel.run(bars, cfg, FEE * k, SLIP * k) for k in LEVELS}


@pytest.mark.parametrize("kernel", KERNELS, ids=IDS)
def test_profit_factor_falls_as_cost_rises(kernel, bars):
    out = _runs(kernel, bars, kernel.cfg)
    pfs = {k: pf(t[:, T_R]) for k, t in out.items() if len(t)}
    if len(pfs) < 2:
        pytest.skip("no trades at this configuration")
    ks = sorted(pfs)
    for a, b in zip(ks, ks[1:]):
        assert pfs[b] <= pfs[a] + 1e-9, (
            f"{kernel.name}: profit factor ROSE from {pfs[a]:.4f} at {a}x cost "
            f"to {pfs[b]:.4f} at {b}x. Cost is being added, not subtracted.")


@pytest.mark.parametrize("kernel", KERNELS, ids=IDS)
def test_total_r_falls_as_cost_rises(kernel, bars):
    """Profit factor can sit flat when a configuration barely trades. Total R is
    the blunter statement of the same thing and cannot."""
    out = _runs(kernel, bars, kernel.cfg)
    tot = {k: float(t[:, T_R].sum()) for k, t in out.items() if len(t)}
    ks = sorted(tot)
    for a, b in zip(ks, ks[1:]):
        assert tot[b] <= tot[a] + 1e-9, (
            f"{kernel.name}: total R rose from {tot[a]:.4f} at {a}x to "
            f"{tot[b]:.4f} at {b}x")


@pytest.mark.parametrize("kernel", KERNELS, ids=IDS)
@pytest.mark.parametrize("cfgname", ["cfg", "cfg_alt"])
def test_r_is_affine_in_the_cost_multiple(kernel, bars, cfgname):
    """The identity `reprice` depends on, stated directly.

    Compared only on trades the kernel takes identically at 1x, 2x and 3x - cost
    feeds the minimum-risk gate, so a marginal setup can drop out as cost rises,
    and that is a different (legitimate) effect from the arithmetic being wrong.
    """
    cfg = getattr(kernel, cfgname)
    r1 = kernel.run(bars, cfg, FEE * 1, SLIP * 1)
    r2 = kernel.run(bars, cfg, FEE * 2, SLIP * 2)
    r3 = kernel.run(bars, cfg, FEE * 3, SLIP * 3)
    if min(len(r1), len(r2), len(r3)) == 0:
        pytest.skip("no trades at this configuration")

    def key(t):
        return {(int(a), int(b)) for a, b in zip(t[:, T_ENTRY_I], t[:, T_EXIT_I])}

    common = key(r1) & key(r2) & key(r3)
    assert common, f"{kernel.name}: no trade survives all three cost levels"

    def series(t):
        d = {(int(a), int(b)): r
             for a, b, r in zip(t[:, T_ENTRY_I], t[:, T_EXIT_I], t[:, T_R])}
        return np.array([d[k] for k in sorted(common)])

    a, b, c = series(r1), series(r2), series(r3)
    one_round_trip = a - b                     # R lost per extra 1x of cost
    np.testing.assert_allclose(
        c, a - 2 * one_round_trip, rtol=0, atol=1e-9,
        err_msg=(f"{kernel.name}: R is not affine in cost. "
                 f"core/../reprice recovers other cost levels algebraically from "
                 f"r_1x - r_2x; if this fails, every MEASURED-cost board number "
                 f"is wrong."))
    assert (one_round_trip >= -1e-12).all(), (
        f"{kernel.name}: a trade GAINED R when cost went up")


@pytest.mark.parametrize("kernel", KERNELS, ids=IDS)
def test_zero_cost_is_the_upper_bound(kernel, bars):
    """Nothing may score better than the frictionless version of itself."""
    free = kernel.run(bars, kernel.cfg, 0.0, 0.0)
    paid = kernel.run(bars, kernel.cfg, FEE, SLIP)
    if len(free) == 0 or len(paid) == 0:
        pytest.skip("no trades")
    assert pf(paid[:, T_R]) <= pf(free[:, T_R]) + 1e-9
