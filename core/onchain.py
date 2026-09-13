"""Exchange flows from the CoinMetrics Community API — the first ON-CHAIN feed here.

H-035. Every other feed in this repo is derived from an order book: open
interest, taker ratio, depth, funding, basis. This one is not. It counts coins
moving onto and off exchanges, measured against known exchange address clusters.

WHAT IS FREE, verified 2026-09-13. No API key. `FlowInExNtv`, `FlowOutExNtv`,
`FlowInExUSD`, `FlowOutExUSD` for BTC and ETH. `FlowNetExNtv` is NOT served on
the community tier, so netflow is computed here as In - Out. Rate limit is 10
requests per 6 seconds per IP.

THREE LIMITS, AND THEY DECIDE HOW THIS MAY BE USED.

  1. DAILY ONLY. `frequency=1h` returns
     `forbidden: not available with supplied credentials`. One observation a day.

  2. PUBLISHED A DAY LATE. The row stamped D 00:00 carries a status-time of
     roughly D+1 01:00-02:00 UTC. It is therefore NOT knowable on day D. This
     module stamps every value at **D + 2 days 00:00 UTC**, which is the first
     moment a trader could act on it with a full day of margin. Late, never
     early - the same rule `strategies/goldfeed` applied to the COT release.

  3. EVERY VALUE IS PROVISIONAL. The API returns `"status":"flash"`, meaning the
     number is revised later, and the API serves only the CURRENT value - the
     original print is not recoverable. **So any backtest on this feed reads
     revised data as though it had been available live, and is optimistic by
     construction.** That cannot be fixed from this source at this price. It is
     stated here because a result on this feed must carry it.

Run:  .venv/bin/python core/onchain.py            BTC and ETH
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

FEEDS = ROOT / "data" / "feeds"
FEEDS.mkdir(parents=True, exist_ok=True)

API = "https://community-api.coinmetrics.io/v4/timeseries/asset-metrics"
METRICS = "FlowInExNtv,FlowOutExNtv,FlowInExUSD,FlowOutExUSD"
ASSETS = {"BTC": "btc", "ETH": "eth"}
START = "2020-01-01"
#: Days added to the observation date before it may be read. See limit 2.
KNOWABLE_LAG_DAYS = 2


def fetch(asset: str, start: str = START) -> pd.DataFrame:
    rows, token, page = [], None, 0
    with requests.Session() as s:
        while True:
            p = {"assets": asset, "metrics": METRICS, "frequency": "1d",
                 "start_time": start, "page_size": 10000}
            if token:
                p["next_page_token"] = token
            r = s.get(API, params=p, timeout=60)
            if r.status_code != 200:
                raise RuntimeError(f"{asset}: HTTP {r.status_code} {r.text[:200]}")
            j = r.json()
            if "error" in j:
                raise RuntimeError(f"{asset}: {j['error']}")
            rows.extend(j.get("data", []))
            token = j.get("next_page_token")
            page += 1
            if not token:
                break
            time.sleep(0.7)             # 10 requests / 6s, stay well under
    df = pd.DataFrame(rows)
    if not len(df):
        raise RuntimeError(f"{asset}: no rows")
    df["time"] = pd.to_datetime(df["time"], utc=True)
    # ONLY the four named metrics. The API returns `<metric>-status` ("flash")
    # and `<metric>-status-time` beside every value, both STRINGS, and a
    # `startswith("Flow")` filter swept them in and died on
    # `could not convert string to float: 'flash'`. Those status columns are the
    # provisional-revision flag described at the top of this file - the thing to
    # read and report, never to cast.
    keep = [c for c in METRICS.split(",") if c in df.columns]
    if not keep:
        raise RuntimeError(f"none of {METRICS} in response columns {list(df.columns)}")
    out = df.set_index("time")[keep].astype("float64").sort_index()
    return out[~out.index.duplicated(keep="last")]


def build(sym: str, force: bool = False) -> pd.DataFrame:
    """Daily exchange flows, stamped at the moment they become KNOWABLE."""
    asset = ASSETS[sym]
    out = FEEDS / f"{sym}_onchain_1d.parquet"
    if out.exists() and not force:
        return pd.read_parquet(out).sort_index()

    df = fetch(asset)
    df["net_ntv"] = df.FlowInExNtv - df.FlowOutExNtv
    df["net_usd"] = df.FlowInExUSD - df.FlowOutExUSD
    df["observed"] = df.index                       # the day it describes
    # THE SHIFT IS THE WHOLE POINT. Move the stamp forward so the index is the
    # first time the value could have been acted on, not the day it describes.
    df.index = df.index + pd.Timedelta(days=int(KNOWABLE_LAG_DAYS))
    df.index.name = "knowable_at"
    df.to_parquet(out)
    print(f"  {sym}: {len(df):,} daily rows, describes "
          f"{df.observed.min():%Y-%m-%d} -> {df.observed.max():%Y-%m-%d}, "
          f"knowable from {df.index.min():%Y-%m-%d}")
    return df


def main(argv: list[str]) -> int:
    for sym in (argv[1:] or list(ASSETS)):
        build(sym, force="--force" in argv)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
