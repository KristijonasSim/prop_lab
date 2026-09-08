"""Fixtures for the kernel invariant suite.

Small, fixed slices of real bars. Real because the bugs this project has found
were properties of real data - Dukascopy's padded weekend, a session whose true
sigma is exactly zero - and synthetic bars would not have contained them. Fixed
so a failure is reproducible rather than a function of how much data was
downloaded that week.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# Enough bars for the 200-EMA and the rvol window to be meaningful, few enough
# that the whole suite runs in seconds once numba has compiled.
N_BARS = 4000


def _slice(path: Path, n: int = N_BARS) -> pd.DataFrame:
    if not path.exists():
        pytest.skip(f"{path.name} not in the cache")
    return pd.read_parquet(path).sort_index().iloc[:n]


@pytest.fixture(scope="session")
def gold() -> pd.DataFrame:
    """XAUUSD 1h. Contains Dukascopy's zero-volume weekend padding - 21.5% of the
    full series - which is the input that produced two of this project's bugs."""
    return _slice(ROOT / "data" / "XAUUSD_dukascopy_1h.parquet")


@pytest.fixture(scope="session")
def btc() -> pd.DataFrame:
    """BTCUSDT 15m. A market that never closes: zero padded bars, so any
    difference against `gold` is about the padding and not about the kernel."""
    return _slice(ROOT / "data" / "BTCUSDT_spot_15m.parquet")


@pytest.fixture(scope="session")
def bars(gold) -> pd.DataFrame:
    """The default series for invariants that do not care which market."""
    return gold
