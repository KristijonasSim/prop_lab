"""Dukascopy tick loader for FX and metals, aggregated to 15m bars.

Dukascopy publishes one LZMA-compressed file per instrument per hour. Each tick
is 20 bytes big-endian: ms offset into the hour, ask, bid (both integers scaled
by the instrument's point value), then ask and bid volume as float32.

Bars are built from the MID price, and the mean half-spread of each bar is kept
alongside it. That means the cost model for FX and gold is measured from the
data rather than assumed, which matters: the BTC result died on costs, so a
guessed spread would decide the FX answer by itself.
"""

from __future__ import annotations

import lzma
import struct
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
# One LZMA file per instrument per DAY of 1-minute candles. The per-hour tick
# files carry the spread too, but there are 24x as many of them and this network
# path is slow enough that the tick route would take hours.
URL = "https://datafeed.dukascopy.com/datafeed/{sym}/{y:04d}/{m:02d}/{d:02d}/BID_candles_min_1.bi5"
UA = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120 Safari/537.36",
    "Accept": "*/*",
    "Referer": "https://www.dukascopy.com/",
}

# price integers are scaled by 10**digits
POINT = {
    # 5-decimal majors and crosses
    "EURUSD": 1e5, "GBPUSD": 1e5, "AUDUSD": 1e5, "NZDUSD": 1e5,
    "USDCAD": 1e5, "USDCHF": 1e5, "EURGBP": 1e5, "EURCHF": 1e5,
    "EURAUD": 1e5, "GBPAUD": 1e5, "AUDNZD": 1e5, "USDMXN": 1e5,
    # 3-decimal JPY crosses
    "USDJPY": 1e3, "EURJPY": 1e3, "GBPJPY": 1e3, "AUDJPY": 1e3,
    "CHFJPY": 1e3, "CADJPY": 1e3, "NZDJPY": 1e3,
    # metals
    "XAUUSD": 1e3, "XAGUSD": 1e3,
    # cash index CFDs. Verified against a live day rather than assumed: the
    # raw integers decode to S&P ~7667, Dow ~53543, NDX ~29141 at 1e3, which
    # are the right order of magnitude and wrong at every other scale.
    "SPX500": 1e3, "US30": 1e3, "NAS100": 1e3, "GER40": 1e3,
    # energy
    "WTI": 1e3, "BRENT": 1e3,
}

#: Our name -> Dukascopy's datafeed path segment. FX and metals are identical
#: on both sides; the indices are not.
DUKAS_SYM = {
    "SPX500": "USA500IDXUSD", "US30": "USA30IDXUSD",
    "NAS100": "USATECHIDXUSD", "GER40": "DEUIDXEUR",
    "WTI": "LIGHTCMDUSD", "BRENT": "BRENTCMDUSD",
}
TICK = struct.Struct(">IIIff")          # ms, ask, bid, askvol, bidvol
CANDLE = struct.Struct(">Iiiiif")       # sec-from-midnight, O, C, L, H as ints scaled
                                        # by POINT, then volume as float32. Reading
                                        # OHLC as float32 yields denormals -> zeros.


RAW_DIR = DATA_DIR / "dukascopy_raw"


def _fetch(sym: str, ts: datetime, retries: int = 6) -> bytes | None:
    """Fetch one day, caching the compressed bytes. The decode format took two
    attempts to get right; caching means the second attempt was free."""
    cache = RAW_DIR / sym / f"{ts:%Y%m%d}.bi5"
    if cache.exists():
        return cache.read_bytes()
    url = URL.format(sym=DUKAS_SYM.get(sym, sym), y=ts.year, m=ts.month - 1,
                     d=ts.day)
    for i in range(retries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=45) as r:
                b = r.read()
            cache.parent.mkdir(parents=True, exist_ok=True)
            cache.write_bytes(b)
            return b
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return b""          # no session that day (weekend, holiday)
            time.sleep(0.5 * (i + 1))
        except Exception:
            time.sleep(0.5 * (i + 1))
    return None                      # give up; caller records the gap


def _decode(raw: bytes, sym: str, day: datetime) -> pd.DataFrame | None:
    """One day of 1-minute candles -> a DataFrame. Prices are already floats in
    these files; only the tick files use scaled integers."""
    if not raw:
        return None
    try:
        buf = lzma.decompress(raw)
    except lzma.LZMAError:
        return None
    n = len(buf) // CANDLE.size
    if n == 0:
        return None
    rows = np.empty((n, 6), dtype=np.float64)
    for i in range(n):
        rows[i] = CANDLE.unpack_from(buf, i * CANDLE.size)
    p = POINT[sym]
    ts = pd.to_datetime(day.timestamp() + rows[:, 0], unit="s", utc=True)
    df = pd.DataFrame({"open": rows[:, 1] / p, "close": rows[:, 2] / p,
                       "low": rows[:, 3] / p, "high": rows[:, 4] / p,
                       "volume": rows[:, 5]}, index=ts)
    df = df[df.open > 0]                 # empty minutes are written as zeros
    return df[["open", "high", "low", "close", "volume"]] if len(df) else None


AGG = {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}


def download(sym: str, start: str, end: str, workers: int = 48, force: bool = False) -> pd.DataFrame:
    """15m bars resampled from Dukascopy 1-minute candles. Cached to parquet."""
    DATA_DIR.mkdir(exist_ok=True)
    path = DATA_DIR / f"{sym}_dukascopy_15m.parquet"
    if path.exists() and not force:
        return pd.read_parquet(path)

    t0 = datetime.fromisoformat(start).replace(tzinfo=timezone.utc)
    t1 = datetime.fromisoformat(end).replace(tzinfo=timezone.utc)
    days = []
    t = t0
    while t < t1:
        if t.weekday() != 5:                 # Saturday is always empty
            days.append(t)
        t += timedelta(days=1)

    frames, failures, done = [], 0, 0
    with ThreadPoolExecutor(max_workers=workers) as ex:
        for day, raw in zip(days, ex.map(lambda d: _fetch(sym, d), days)):
            done += 1
            if raw is None:
                failures += 1
                continue
            d = _decode(raw, sym, day)
            if d is not None:
                frames.append(d)
            if done % 100 == 0:
                print(f"  {sym} {done}/{len(days)} days, {failures} failed", flush=True)

    if not frames:
        raise RuntimeError(f"{sym}: no data downloaded")
    m1 = pd.concat(frames).sort_index()
    m1 = m1[~m1.index.duplicated(keep="last")]
    df = m1.resample("15min", label="left", closed="left").agg(AGG).dropna(subset=["open"])
    df.to_parquet(path)
    print(f"{sym}: {len(df)} bars 15m  {df.index[0]} -> {df.index[-1]}  "
          f"({failures} failed days)", flush=True)
    return df


def build_tf(sym: str, tf: str, start: str = "2023-09-01", end: str = "2026-09-01",
             force: bool = False) -> pd.DataFrame:
    """Rebuild any timeframe from the cached 1-minute .bi5 files.

    The raw cache is already on disk, so this costs no downloads — which is the
    whole reason it is committed to the repo.
    """
    path = DATA_DIR / f"{sym}_dukascopy_{tf}.parquet"
    if path.exists() and not force:
        return pd.read_parquet(path).sort_index()

    t0 = datetime.fromisoformat(start).replace(tzinfo=timezone.utc)
    t1 = datetime.fromisoformat(end).replace(tzinfo=timezone.utc)
    frames = []
    t = t0
    while t < t1:
        cache = RAW_DIR / sym / f"{t:%Y%m%d}.bi5"
        if cache.exists():
            d = _decode(cache.read_bytes(), sym, t)
            if d is not None:
                frames.append(d)
        t += timedelta(days=1)
    if not frames:
        raise FileNotFoundError(f"no cached raw files for {sym}")
    m1 = pd.concat(frames).sort_index()
    m1 = m1[~m1.index.duplicated(keep="last")]
    df = m1.resample(tf, label="left", closed="left").agg(AGG).dropna(subset=["open"])
    df.to_parquet(path)
    return df


def load(sym: str, tf: str = "15m") -> pd.DataFrame:
    path = DATA_DIR / f"{sym}_dukascopy_{tf}.parquet"
    if not path.exists():
        if tf != "15m":
            return build_tf(sym, tf)
        raise FileNotFoundError(f"{path} — run core.fx_data.download() first")
    return pd.read_parquet(path).sort_index()
