"""Binance OHLCV + funding downloader (public endpoints, no API key needed).

Data is stored as parquet in data/raw/ and is the single source of truth.
We download ONE base timeframe (default 15m) and resample upward, so every
timeframe is guaranteed mutually consistent.
"""
from __future__ import annotations

import time
from pathlib import Path

import pandas as pd
import requests

from .timeframes import parse_timeframe


def _utc_ms(x) -> int:
    """Timestamp -> epoch ms, accepting naive strings and tz-aware values."""
    ts = pd.Timestamp(x)
    ts = ts.tz_localize("UTC") if ts.tzinfo is None else ts.tz_convert("UTC")
    return int(ts.timestamp() * 1000)

# Binance charges request "weight" by page size. limit<=1000 costs 5, limit>1000
# costs 10, and the budget is 2400/min - so 1000 is the efficient page size.
PAGE_LIMIT = 1000
MAX_RETRIES = 5

SPOT_URL = "https://api.binance.com/api/v3/klines"
FUTURES_URL = "https://fapi.binance.com/fapi/v1/klines"
FUNDING_URL = "https://fapi.binance.com/fapi/v1/fundingRate"

RAW_DIR = Path(__file__).resolve().parents[2] / "data" / "raw"

_KLINE_COLS = [
    "open_time", "open", "high", "low", "close", "volume", "close_time",
    "quote_volume", "trades", "taker_buy_base", "taker_buy_quote", "ignore",
]


def _get(url: str, params: dict) -> list:
    """GET with backoff on rate limits and transient errors."""
    delay = 1.0
    for attempt in range(MAX_RETRIES):
        resp = requests.get(url, params=params, timeout=30)
        if resp.status_code in (418, 429, 500, 502, 503, 504):
            wait = float(resp.headers.get("Retry-After", delay))
            time.sleep(min(wait, 60))
            delay *= 2
            continue
        resp.raise_for_status()
        return resp.json()
    resp.raise_for_status()
    return []


def raw_path(symbol: str, timeframe: str, market: str = "futures") -> Path:
    return RAW_DIR / f"{market}_{symbol.upper()}_{timeframe}.parquet"


def fetch_klines(
    symbol: str = "BTCUSDT",
    timeframe: str = "15m",
    start: str = "2019-09-01",
    end: str | None = None,
    market: str = "futures",
    sleep: float = 0.15,
    progress: bool = True,
) -> pd.DataFrame:
    """Page through Binance klines. Returns open-time-indexed UTC OHLCV."""
    url = FUTURES_URL if market == "futures" else SPOT_URL
    start_ms = _utc_ms(start)
    end_ms = _utc_ms(end or pd.Timestamp.utcnow())
    step_ms = int(parse_timeframe(timeframe).total_seconds() * 1000)

    rows: list[list] = []
    cursor = start_ms
    while cursor < end_ms:
        batch = _get(url, {"symbol": symbol.upper(), "interval": timeframe,
                           "startTime": cursor, "endTime": end_ms, "limit": PAGE_LIMIT})
        if not batch:
            break
        rows.extend(batch)
        cursor = batch[-1][0] + step_ms
        if len(batch) < PAGE_LIMIT:
            break
        if progress and len(rows) % (PAGE_LIMIT * 20) == 0:
            print(f"  {len(rows):,} bars ... {pd.to_datetime(cursor, unit='ms', utc=True)}",
                  flush=True)
        time.sleep(sleep)

    if not rows:
        raise RuntimeError(f"No klines returned for {symbol} {timeframe}")

    df = pd.DataFrame(rows, columns=_KLINE_COLS)
    df = df.drop_duplicates(subset="open_time").sort_values("open_time")
    df["open_time"] = pd.to_datetime(df["open_time"], unit="ms", utc=True)
    for c in ("open", "high", "low", "close", "volume", "quote_volume"):
        df[c] = df[c].astype(float)
    df["trades"] = df["trades"].astype("int64")
    out = df.set_index("open_time")[["open", "high", "low", "close", "volume", "quote_volume", "trades"]]
    out.index.name = "open_time"
    return out


def fetch_funding(symbol: str = "BTCUSDT", start: str = "2019-09-01",
                  end: str | None = None, sleep: float = 0.15) -> pd.DataFrame:
    """Realised 8h funding rates for a perp. Index = funding settlement time."""
    start_ms = _utc_ms(start)
    end_ms = _utc_ms(end or pd.Timestamp.utcnow())
    rows: list[dict] = []
    cursor = start_ms
    while cursor < end_ms:
        batch = _get(FUNDING_URL, {"symbol": symbol.upper(), "startTime": cursor,
                                   "endTime": end_ms, "limit": 1000})
        if not batch:
            break
        rows.extend(batch)
        cursor = int(batch[-1]["fundingTime"]) + 1
        if len(batch) < 1000:
            break
        time.sleep(sleep)
    if not rows:
        raise RuntimeError(f"No funding data for {symbol}")
    df = pd.DataFrame(rows)
    df["fundingTime"] = pd.to_datetime(df["fundingTime"], unit="ms", utc=True)
    df["fundingRate"] = df["fundingRate"].astype(float)
    return df.set_index("fundingTime")[["fundingRate"]].sort_index()


def download(symbol: str = "BTCUSDT", timeframe: str = "15m", start: str = "2019-09-01",
             end: str | None = None, market: str = "futures", force: bool = False) -> Path:
    """Download (or extend) the raw parquet for symbol/timeframe. Returns path."""
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    path = raw_path(symbol, timeframe, market)
    existing: pd.DataFrame | None = None
    if path.exists() and not force:
        existing = pd.read_parquet(path)
        if len(existing):
            start = str(existing.index[-1])
    fresh = fetch_klines(symbol, timeframe, start=start, end=end, market=market)
    if existing is not None and len(existing):
        fresh = pd.concat([existing, fresh])
        fresh = fresh[~fresh.index.duplicated(keep="last")].sort_index()
    fresh.to_parquet(path)
    return path
