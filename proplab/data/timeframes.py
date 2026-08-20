"""Timeframe parsing and resampling.

Bar convention used everywhere in proplab:
  - The DataFrame index is the bar's OPEN time (UTC, tz-aware).
  - A bar labelled 12:00 on '15m' covers [12:00, 12:15) and is only *known*
    at 12:15. `close_time` = open_time + duration.
This convention is what makes the higher-timeframe views lookahead-safe.
"""
from __future__ import annotations

import re

import pandas as pd

_TF_RE = re.compile(r"^(\d+)(m|h|d|w)$")

_PANDAS_UNIT = {"m": "min", "h": "h", "d": "D", "w": "W"}


def to_utc(x) -> pd.Timestamp:
    """Coerce anything timestamp-like to a UTC-aware Timestamp.

    pandas 3 refuses `Timestamp(already_aware, tz=...)`, so localise vs convert
    has to be decided explicitly. Every date the user supplies goes through here.
    """
    ts = pd.Timestamp(x)
    return ts.tz_localize("UTC") if ts.tzinfo is None else ts.tz_convert("UTC")


def parse_timeframe(tf: str) -> pd.Timedelta:
    """'15m' -> Timedelta('0 days 00:15:00'). Raises on anything unsupported."""
    m = _TF_RE.match(tf.strip().lower())
    if not m:
        raise ValueError(f"Unsupported timeframe {tf!r}. Use e.g. 5m, 15m, 1h, 4h, 1d.")
    n, unit = int(m.group(1)), m.group(2)
    if n <= 0:
        raise ValueError(f"Timeframe must be positive: {tf!r}")
    return pd.Timedelta(n, unit=_PANDAS_UNIT[unit])


def timeframe_rule(tf: str) -> str:
    """Pandas resample rule string for a timeframe."""
    m = _TF_RE.match(tf.strip().lower())
    if not m:
        raise ValueError(f"Unsupported timeframe {tf!r}")
    return f"{int(m.group(1))}{_PANDAS_UNIT[m.group(2)]}"


def is_multiple_of(higher: str, lower: str) -> bool:
    """True if `higher` bars tile exactly onto `lower` bars."""
    h, l = parse_timeframe(higher), parse_timeframe(lower)
    return h >= l and (h % l) == pd.Timedelta(0)


OHLCV_AGG = {
    "open": "first",
    "high": "max",
    "low": "min",
    "close": "last",
    "volume": "sum",
}


def resample(df: pd.DataFrame, tf: str) -> pd.DataFrame:
    """Resample open-time-indexed OHLCV to a higher timeframe.

    Uses closed='left', label='left' so the output index stays an OPEN time.
    Incomplete trailing bars are dropped: a partially-formed bar would leak
    information about a period that has not finished yet.
    """
    _require_ohlcv(df)
    rule = timeframe_rule(tf)
    out = df.resample(rule, closed="left", label="left", origin="epoch").agg(OHLCV_AGG)
    out = out.dropna(subset=["open", "high", "low", "close"])

    # Drop a trailing partial bar: keep only bars whose full span is covered
    # by the source data.
    step = parse_timeframe(tf)
    src_step = infer_step(df)
    last_covered = df.index[-1] + src_step
    out = out[out.index + step <= last_covered]
    return out


def infer_step(df: pd.DataFrame) -> pd.Timedelta:
    """Most common spacing between bars (robust to gaps)."""
    if len(df) < 2:
        raise ValueError("Need >= 2 bars to infer the bar size.")
    diffs = pd.Series(df.index).diff().dropna()
    return pd.Timedelta(diffs.mode().iloc[0])


def close_times(index: pd.DatetimeIndex, tf: str) -> pd.DatetimeIndex:
    return index + parse_timeframe(tf)


def _require_ohlcv(df: pd.DataFrame) -> None:
    missing = {"open", "high", "low", "close", "volume"} - set(df.columns)
    if missing:
        raise ValueError(f"DataFrame missing OHLCV columns: {sorted(missing)}")
    if not isinstance(df.index, pd.DatetimeIndex):
        raise ValueError("DataFrame index must be a DatetimeIndex of bar OPEN times.")
    if df.index.tz is None:
        raise ValueError("DataFrame index must be timezone-aware (UTC).")
    if not df.index.is_monotonic_increasing:
        raise ValueError("DataFrame index must be sorted ascending.")
