"""BYBIT CROWD POSITIONING, hourly. Kris tab #2, 2026-10-12.

Three public series per symbol from Bybit's v5 market API, paged back to the
start of history:
    account-ratio   buyRatio = share of ACCOUNTS net long (1h)
    open-interest   contracts open (1h)
    funding         8-hourly funding rate

One parquet per symbol under data/crowd/. Read-only, no key.

    .venv/bin/python core/bybit_crowd.py XAUUSDT PAXGUSDT
"""
from __future__ import annotations

import json
import sys
import time
import urllib.request
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DIR = ROOT / "data" / "crowd"
API = "https://api.bybit.com/v5/market/"


def _get(path: str) -> list[dict]:
    for k in range(5):
        try:
            r = json.loads(urllib.request.urlopen(API + path, timeout=30).read())
            if r.get("retCode") == 0:
                return r["result"].get("list", [])
        except Exception:                                     # noqa: BLE001
            pass
        time.sleep(1 + 2 * k)
    raise IOError(path)


def _paged(path: str, ts_key: str, limit: int, cursor_mode: bool = False) -> pd.DataFrame:
    rows, end = [], None
    cursor = ""
    while True:
        q = f"{path}&limit={limit}"
        if cursor_mode and cursor:
            q += f"&cursor={cursor}"
        elif end:
            q += f"&endTime={end}"
        if cursor_mode:
            r = json.loads(urllib.request.urlopen(API + q, timeout=30).read())["result"]
            got, cursor = r.get("list", []), r.get("nextPageCursor", "")
        else:
            got = _get(q)
        if not got:
            break
        rows += got
        oldest = min(int(x[ts_key]) for x in got)
        if cursor_mode:
            if not cursor:
                break
        else:
            if end is not None and oldest >= end:
                break
            end = oldest - 1
            if len(got) < limit:
                break
        time.sleep(0.15)
    df = pd.DataFrame(rows).drop_duplicates(ts_key)
    df.index = pd.to_datetime(df[ts_key].astype("int64"), unit="ms", utc=True)
    return df.sort_index()


def pull(sym: str) -> pd.DataFrame:
    ar = _paged(f"account-ratio?category=linear&symbol={sym}&period=1h", "timestamp", 500)
    oi = _paged(f"open-interest?category=linear&symbol={sym}&intervalTime=1h", "timestamp", 200,
                cursor_mode=True)
    fu = _paged(f"funding/history?category=linear&symbol={sym}", "fundingRateTimestamp", 200)
    out = pd.DataFrame({"long_share": ar.buyRatio.astype(float)})
    out = out.join(oi.openInterest.astype(float).rename("oi"), how="outer")
    out["funding"] = fu.fundingRate.astype(float).reindex(out.index, method="ffill")
    DIR.mkdir(parents=True, exist_ok=True)
    out.to_parquet(DIR / f"{sym}_1h.parquet")
    print(f"{sym}: {len(out)} hours  {out.index.min()} -> {out.index.max()}  "
          f"long_share {out.long_share.notna().sum()}  oi {out.oi.notna().sum()}", flush=True)
    return out


def load(sym: str) -> pd.DataFrame:
    return pd.read_parquet(DIR / f"{sym}_1h.parquet")


if __name__ == "__main__":
    for s in sys.argv[1:] or ["XAUUSDT"]:
        pull(s)
