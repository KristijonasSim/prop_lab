"""Indicator helpers for strategy code.

Strategy-side, not core: these are part of what a strategy is allowed to
express, and Claude may edit them. They take plain arrays that Context has
already sliced at the current bar, so they cannot see the future - an
indicator here simply has no access to anything beyond what it is handed.

Every function returns a scalar for the CURRENT bar, computed from the tail of
the series, and returns nan when there is not enough history.
"""
from __future__ import annotations

import numpy as np


def sma(values: np.ndarray, n: int) -> float:
    """Simple moving average of the last n values."""
    if len(values) < n:
        return float("nan")
    return float(np.mean(values[-n:]))


def true_range(high: np.ndarray, low: np.ndarray, close: np.ndarray) -> np.ndarray:
    """Wilder's true range. Element i uses close[i-1], so the first is high-low."""
    hl = high - low
    if len(close) < 2:
        return hl
    prev_close = close[:-1]
    hc = np.abs(high[1:] - prev_close)
    lc = np.abs(low[1:] - prev_close)
    tr = np.empty_like(hl)
    tr[0] = hl[0]
    tr[1:] = np.maximum(hl[1:], np.maximum(hc, lc))
    return tr


def atr(high: np.ndarray, low: np.ndarray, close: np.ndarray, n: int) -> float:
    """Average true range over the last n bars (simple mean, not Wilder's EMA)."""
    if len(high) < n + 1:
        return float("nan")
    return float(np.mean(true_range(high, low, close)[-n:]))


def donchian_high(high: np.ndarray, n: int, exclude_current: bool = True) -> float:
    """Highest high of the prior n bars.

    `exclude_current` drops the bar we are standing on. Without it, "close >
    highest high of the last n bars" can never be true, because the current
    bar's own high is >= its close - the breakout test would silently never
    fire.
    """
    series = high[:-1] if exclude_current else high
    if len(series) < n:
        return float("nan")
    return float(np.max(series[-n:]))


def donchian_low(low: np.ndarray, n: int, exclude_current: bool = True) -> float:
    """Lowest low of the prior n bars. See donchian_high for the exclusion."""
    series = low[:-1] if exclude_current else low
    if len(series) < n:
        return float("nan")
    return float(np.min(series[-n:]))


def realised_vol(closes: np.ndarray, n: int, periods_per_year: float) -> float:
    """Annualised realised volatility from the last n log returns."""
    if len(closes) < n + 1:
        return float("nan")
    rets = np.diff(np.log(closes[-(n + 1):]))
    sd = float(np.std(rets, ddof=1))
    return sd * np.sqrt(periods_per_year)
