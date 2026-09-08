"""Both kernels obey the contract in core/KERNEL_CONTRACT.md, stated as code.

`core/strategy.py::conforms` checks the OUTPUT rather than the class, because a
kernel is what it produces and a Protocol can only assert that methods exist.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.strategy import as_frame, conforms                   # noqa: E402
from tests.kernels import IDS, KERNELS                         # noqa: E402


@pytest.mark.parametrize("kernel", KERNELS, ids=IDS)
@pytest.mark.parametrize("cfgname", ["cfg", "cfg_alt"])
def test_output_conforms_to_the_kernel_contract(kernel, bars, cfgname):
    tr = kernel.run(bars, getattr(kernel, cfgname), 1.0, 0.5)
    bad = conforms(tr, len(bars))
    assert not bad, f"{kernel.name} [{cfgname}] violates the contract: {bad}"


@pytest.mark.parametrize("kernel", KERNELS, ids=IDS)
def test_output_conforms_on_a_degenerate_series(kernel, bars):
    """An empty result must still be the right shape - downstream stages index
    into it unconditionally."""
    tr = kernel.run(bars.iloc[:5], kernel.cfg, 1.0, 0.5)
    assert not conforms(tr, 5)


@pytest.mark.parametrize("kernel", KERNELS, ids=IDS)
def test_trades_can_be_timestamped(kernel, bars):
    tr = kernel.run(bars, kernel.cfg, 1.0, 0.5)
    f = as_frame(tr, bars.index)
    assert len(f) == len(tr)
    if len(f):
        assert (f.exit_ts >= f.entry_ts).all()
