"""The five-year caches must share the three-year caches' clock.

2026-10-09: `scripts/build_5y.py` decoded every raw day from 23:00, so the deep
cache - every factory number - was 23 hours late against the 3-year cache and
against Bybit. Same bars, same timestamps, or this fails.
"""
import numpy as np
import pandas as pd
import pytest

from core import markets
from factory.cells import DEEP_SUFFIX, MARKETS


@pytest.mark.parametrize("sym", [m for m in MARKETS if m not in markets.CRYPTO])
def test_deep_cache_on_the_same_clock(sym):
    p = markets.DATA / f"{sym}_{DEEP_SUFFIX}_1h.parquet"
    if not p.exists():
        pytest.skip("no deep cache")
    deep = pd.read_parquet(p).close
    base = markets.load(sym, "1h").close
    j = pd.concat([deep, base], axis=1, join="inner").dropna().tail(5000)
    assert len(j) > 1000
    assert np.allclose(j.iloc[:, 0], j.iloc[:, 1], rtol=1e-6)
