"""The bar caches are well-formed. Item 4 of the three that were actually needed.

Scoped deliberately narrowly. A full data-quality suite is not warranted: a
one-off scan on 2026-09-08 found every XAUUSD and BTCUSDT cache clean — no
duplicate timestamps, monotonic index, no NaNs, no bar with `high < low`. What
this file does is make sure it STAYS that way, in about two seconds, because the
feeds grow every day from a cron job on Kris's laptop and a silent corruption
there would poison every result downstream without anything failing.

What is NOT tested here, on purpose:

  * the zero-volume share. It is 21.4-21.5% on every XAUUSD timeframe and 0% on
    BTCUSDT, and that is Dukascopy's weekend padding, not a defect. Both kernels
    now refuse to decide, fill or exit on one.
  * feed freshness. Gaps over ~41h in `data/feeds/` are unrecoverable forever
    (Binance serves no history), but that is an operational problem for the
    collector and a VM, not something a test can fix after the fact.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

#: the series the two live board records are actually built on
FILES = [
    "XAUUSD_dukascopy_5min.parquet",
    "XAUUSD_dukascopy_15min.parquet",
    "XAUUSD_dukascopy_30min.parquet",
    "XAUUSD_dukascopy_1h.parquet",
    "XAUUSD_dukascopy_4h.parquet",
    "BTCUSDT_spot_15m.parquet",
]


def _load(name: str) -> pd.DataFrame:
    p = ROOT / "data" / name
    if not p.exists():
        pytest.skip(f"{name} not in the cache")
    return pd.read_parquet(p)


@pytest.mark.parametrize("name", FILES)
def test_index_is_sorted_unique_and_tz_aware(name):
    """An unsorted or duplicated index silently changes every rolling window and
    every session boundary, and nothing else would notice."""
    df = _load(name)
    idx = df.index
    assert idx.is_monotonic_increasing, f"{name}: index is not sorted"
    assert not idx.duplicated().any(), (
        f"{name}: {int(idx.duplicated().sum())} duplicate timestamps")
    assert idx.tz is not None, f"{name}: naive timestamps - UTC is assumed everywhere"


@pytest.mark.parametrize("name", FILES)
def test_ohlc_is_present_and_self_consistent(name):
    """`high < low` or a NaN close means the kernel is resolving trades against
    a bar that cannot exist. Cheap to check, impossible to spot downstream."""
    df = _load(name)
    for col in ("open", "high", "low", "close", "volume"):
        assert col in df.columns, f"{name}: no {col} column"
    ohlc = df[["open", "high", "low", "close"]]
    assert not ohlc.isna().any().any(), f"{name}: NaN in OHLC"
    assert (ohlc > 0).all().all(), f"{name}: a non-positive price"
    bad = ((df.high < df.low) | (df.high < df.close) | (df.high < df.open)
           | (df.low > df.close) | (df.low > df.open))
    assert not bad.any(), f"{name}: {int(bad.sum())} bars where the range does " \
                          f"not contain the open or the close"
    assert (df.volume >= 0).all(), f"{name}: negative volume"


@pytest.mark.parametrize("name", FILES)
def test_the_bar_spacing_is_the_one_the_filename_claims(name):
    """A 30m cache that is really 15m bars would rescale every hold horizon and
    every per-day figure on the board, quietly."""
    want = {"5min": "5min", "15min": "15min", "15m": "15min",
            "30min": "30min", "1h": "1h", "4h": "4h"}
    key = name.replace(".parquet", "").split("_")[-1]
    df = _load(name)
    gaps = df.index.to_series().diff().dropna()
    assert len(gaps), f"{name}: fewer than two bars"
    mode = gaps.mode().iloc[0]
    assert mode == pd.Timedelta(want[key]), (
        f"{name}: most common bar spacing is {mode}, not {want[key]}")


@pytest.mark.parametrize("name", FILES)
def test_no_gap_is_longer_than_a_market_can_be_closed(name):
    """Weekends and holidays are expected; a week-long hole is a download that
    failed silently. FX closes ~48-56h at most (a holiday weekend); crypto never
    closes, so a long gap there is always a collector outage."""
    df = _load(name)
    gaps = df.index.to_series().diff().dropna()
    worst = gaps.max()
    cap = pd.Timedelta("96h") if "dukascopy" in name else pd.Timedelta("48h")
    assert worst <= cap, (
        f"{name}: largest gap is {worst}, past the {cap} this market can "
        f"legitimately be closed for")
