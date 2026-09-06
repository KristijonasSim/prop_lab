"""DVOL — Deribit's implied-volatility index. The first FORWARD-LOOKING feed here.

WHY THIS EXISTS. Every feed in this repo is backward-looking. Open interest says
who ended up positioned. Taker ratio says who crossed the spread. Depth says what
is resting now. The premium says what leverage has been paying. None of them is a
forecast, and none of them has a counterparty who is being paid to be right about
the future.

DVOL is. It is the crypto VIX: 30-day implied volatility read off the whole
Deribit option smile, where Deribit carries the large majority of listed crypto
option open interest. Somebody quoted those options and is short the risk.

Verified 2026-09-06: the endpoint is public, needs no key, and returns OHLC.

    GET https://www.deribit.com/api/v2/public/get_volatility_index_data
        ?currency=BTC&start_timestamp=..&end_timestamp=..&resolution=3600

    -> [[1784401200000, 35.79, 35.83, 35.73, 35.78], ...]
       ms timestamp, open, high, low, close, in annualised volatility POINTS

History runs from 2021-04. Only BTC and ETH have a DVOL index.

WHAT IT IS FOR, and what it is not for. This is not a strategy. Implied vol does
not say which way price goes; it says how much movement is being paid for. Two
readings, and they are different objects:

    LEVEL              is risk currently cheap or dear
    IMPLIED - REALISED the variance risk premium: is the option market
                       over-charging for the movement that actually arrives

The repo's one reproducible lesson is that the only thing that ever worked was a
GATE built from a feed. There has never been a volatility feed here at all -
verified by grep: no reference to DVOL, Deribit, implied vol or options exists
anywhere in this project. That is the gap this fills.

Resolution note: the API caps how much it will return per call, so history is
fetched in chunks and stitched. Bars are stamped at the START of their interval,
matching every other price series here, so a bar stamped T closes at T + interval
and may be read by a decision taken at that close.

Run:  .venv/bin/python core/deribit_dvol.py            BTC and ETH, hourly
      .venv/bin/python core/deribit_dvol.py BTC
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
FEEDS = ROOT / "data" / "feeds"
FEEDS.mkdir(parents=True, exist_ok=True)

URL = "https://www.deribit.com/api/v2/public/get_volatility_index_data"
DEFAULT = ("BTC", "ETH")
RESOLUTION = 3600                  # one hour
FIRST_MS = 1617235200000           # 2021-04-01, the start of the series
CHUNK_DAYS = 30                    # the endpoint truncates long ranges


def fetch(currency: str, resolution: int = RESOLUTION) -> pd.DataFrame:
    """Every hourly DVOL bar the exchange will serve, stitched."""
    out = FEEDS / f"{currency}_dvol_{resolution}s.parquet"
    step = CHUNK_DAYS * 86400 * 1000
    now = int(time.time() * 1000)
    start = FIRST_MS
    frames, empty_runs = [], 0
    with requests.Session() as s:
        while start < now:
            end = min(start + step, now)
            try:
                r = s.get(URL, params={"currency": currency,
                                       "start_timestamp": start,
                                       "end_timestamp": end,
                                       "resolution": str(resolution)}, timeout=30)
            except requests.RequestException:
                time.sleep(2.0)
                start = end
                continue
            if r.status_code != 200:
                start = end
                continue
            data = (r.json().get("result") or {}).get("data") or []
            if data:
                frames.append(pd.DataFrame(
                    data, columns=["ts", "open", "high", "low", "close"]))
                empty_runs = 0
            else:
                # Before the index existed the API returns nothing. Two months
                # of silence in a row means we started too early, not that the
                # feed is broken.
                empty_runs += 1
            start = end
            time.sleep(0.15)               # polite to a free public endpoint
    if not frames:
        print(f"  {currency}: endpoint returned nothing")
        return pd.DataFrame()
    df = pd.concat(frames, ignore_index=True)
    df["ts"] = pd.to_datetime(df.ts.astype("int64"), unit="ms", utc=True)
    df = df.set_index("ts").sort_index()
    df = df[~df.index.duplicated(keep="last")].astype("float64")
    df = df.rename(columns=lambda c: f"dvol_{c}")
    df.to_parquet(out)
    print(f"  {currency}: {len(df):,} DVOL bars  {df.index[0]:%Y-%m-%d} -> "
          f"{df.index[-1]:%Y-%m-%d}  (empty chunks: {empty_runs})")
    return df


def main(argv: list[str]) -> int:
    cur = argv[1:] or list(DEFAULT)
    print(f"Deribit DVOL -> {FEEDS}")
    for c in cur:
        fetch(c)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
