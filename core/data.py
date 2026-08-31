"""Historical bar loader. Binance via ccxt, cached to parquet in data/.

Downloads 15m only; 1h/4h/1d are resampled from it (CLAUDE.md).
Always drops the still-forming bar — no look-ahead.
"""

from __future__ import annotations

import time
from pathlib import Path

import ccxt
import pandas as pd

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
BASE_TF = "15m"
_RESAMPLE = {"1h": "1h", "4h": "4h", "1d": "1D"}
_AGG = {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}


def _exchange(market: str = "spot") -> ccxt.binance:
    return ccxt.binance({"enableRateLimit": True, "options": {"defaultType": market}})


def download(
    symbol: str = "BTC/USDT",
    since: str = "2019-01-01",
    market: str = "spot",
    force: bool = False,
) -> pd.DataFrame:
    """Fetch 15m bars from `since` to the last CLOSED bar. Cached + incremental."""
    DATA_DIR.mkdir(exist_ok=True)
    path = DATA_DIR / f"{symbol.replace('/', '')}_{market}_{BASE_TF}.parquet"

    cached = pd.DataFrame()
    if path.exists() and not force:
        cached = pd.read_parquet(path)

    ex = _exchange(market)
    want_from = ex.parse8601(f"{since}T00:00:00Z")
    now = ex.milliseconds()

    # Two phases so an earlier `since` backfills instead of being skipped:
    # (1) fill the gap before the cache, (2) top up after it.
    spans: list[tuple[int, int]] = []
    if cached.empty:
        spans.append((want_from, now))
    else:
        cache_start = int(cached.index[0].timestamp() * 1000)
        cache_end = int(cached.index[-1].timestamp() * 1000)
        if want_from < cache_start:
            spans.append((want_from, cache_start))
        spans.append((cache_end + 1, now))

    rows: list[list] = []
    for start, stop in spans:
        while start < stop:
            batch = ex.fetch_ohlcv(symbol, BASE_TF, since=start, limit=1000)
            if not batch:
                break
            batch = [b for b in batch if b[0] < stop]
            if not batch:
                break
            rows += batch
            start = batch[-1][0] + 1
            if len(batch) < 1000:
                break
            time.sleep(ex.rateLimit / 1000)

    if rows:
        new = pd.DataFrame(rows, columns=["ts", "open", "high", "low", "close", "volume"])
        new["ts"] = pd.to_datetime(new.ts, unit="ms", utc=True)
        new = new.set_index("ts")
        cached = pd.concat([cached, new])
        cached = cached[~cached.index.duplicated(keep="last")].sort_index()
        cached.to_parquet(path)

    return _drop_forming(cached, BASE_TF)


def load(symbol: str = "BTC/USDT", timeframe: str = "15m", market: str = "spot") -> pd.DataFrame:
    """Read cached 15m bars and resample. Does not hit the network."""
    path = DATA_DIR / f"{symbol.replace('/', '')}_{market}_{BASE_TF}.parquet"
    if not path.exists():
        raise FileNotFoundError(f"{path} — run core.data.download() first")
    df = pd.read_parquet(path).sort_index()
    if timeframe == BASE_TF:
        return _drop_forming(df, BASE_TF)
    if timeframe not in _RESAMPLE:
        raise ValueError(f"timeframe must be 15m/1h/4h/1d, got {timeframe}")
    out = df.resample(_RESAMPLE[timeframe], label="left", closed="left").agg(_AGG).dropna()
    return _drop_forming(out, timeframe)


def _drop_forming(df: pd.DataFrame, timeframe: str) -> pd.DataFrame:
    """Drop the last bar if its period has not closed yet."""
    if df.empty:
        return df
    delta = pd.Timedelta(_RESAMPLE.get(timeframe, timeframe))
    now = pd.Timestamp.utcnow()
    if df.index[-1] + delta > now:
        return df.iloc[:-1]
    return df
