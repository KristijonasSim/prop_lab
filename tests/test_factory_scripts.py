"""Every script port (factory/scripts.py) must be causal.

The whole-series form used in the backtest is compared, bar by bar, with the
per-bar reader - which can only see the past through guard.Window. Same float
at every sampled bar means the series form reads nothing from the future.
"""
import numpy as np
import pytest

from factory import cells
from factory.guard import Window, columns
from factory.scripts import PORTS
from factory.spec import INDICATORS, SERIES


@pytest.mark.parametrize("kind", sorted(PORTS))
def test_port_equals_guarded_reader(kind):
    f = cells.load("XAUUSD", "1h").reset_index(drop=True).iloc[:700]
    full = SERIES[kind](columns(f), 0)
    reader = INDICATORS[kind][0]
    for t in range(0, len(f), 7):
        ref = reader(Window(f, t))
        assert (np.isnan(ref) and np.isnan(full[t])) or ref == full[t], (kind, t)


@pytest.mark.parametrize("kind", sorted(PORTS))
def test_port_fires_on_real_data(kind):
    f = cells.load("XAUUSD", "1h")
    assert np.nansum(SERIES[kind](columns(f), 0)) > 5, kind
