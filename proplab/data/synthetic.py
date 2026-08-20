"""Synthetic OHLCV for unit tests and engine smoke tests.

NEVER use this for strategy evaluation - it has no real market structure.
It exists so the pipeline can be tested without network access, and so
engine tests can assert exact known P&L on hand-built price paths.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def random_walk(
    n: int = 2000,
    timeframe: str = "15m",
    start: str = "2024-01-01",
    price0: float = 50_000.0,
    vol_bps: float = 25.0,
    drift_bps: float = 0.0,
    seed: int = 0,
) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    freq = {"15m": "15min", "1h": "h", "4h": "4h", "5m": "5min", "1d": "D"}[timeframe]
    idx = pd.date_range(start, periods=n, freq=freq, tz="UTC")
    rets = rng.normal(drift_bps / 1e4, vol_bps / 1e4, n)
    close = price0 * np.exp(np.cumsum(rets))
    open_ = np.concatenate([[price0], close[:-1]])
    wick = np.abs(rng.normal(0, vol_bps / 1e4, n)) * close
    high = np.maximum(open_, close) + wick
    low = np.minimum(open_, close) - wick
    vol = rng.lognormal(3, 0.5, n)
    return pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close, "volume": vol}, index=idx
    )


def from_closes(closes, timeframe: str = "1h", start: str = "2024-01-01",
                spread: float = 0.0) -> pd.DataFrame:
    """Deterministic bars from a list of closes - for exact-P&L engine tests."""
    freq = {"15m": "15min", "1h": "h", "4h": "4h", "1d": "D"}[timeframe]
    closes = np.asarray(closes, dtype=float)
    idx = pd.date_range(start, periods=len(closes), freq=freq, tz="UTC")
    open_ = np.concatenate([[closes[0]], closes[:-1]])
    high = np.maximum(open_, closes) + spread
    low = np.minimum(open_, closes) - spread
    return pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": closes,
         "volume": np.ones(len(closes))}, index=idx
    )
