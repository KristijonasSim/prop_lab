"""GOLD TICKS -> ONE-MINUTE ORDER FLOW. Downloaded fresh, Kris 2026-10-09:
*"get order flow data and tick data ... do everything from 0"*.

Dukascopy publishes one file per hour of ticks: ms offset, ask, bid, ask volume,
bid volume (20 bytes big-endian). This pulls every hour of the factory's
five-year window for XAUUSD and keeps, per UTC minute:

    open high low close      MID price
    ticks                    number of ticks (activity)
    ask_vol bid_vol          quoted size summed over the minute's ticks
    up_vol dn_vol            size on ticks where the mid ROSE / FELL - the
                             tick rule, the standard proxy for who was the
                             aggressor when there is no trade tape
    up_ticks dn_ticks        the same as counts
    spread                   mean ask-bid, in price

WHAT IT IS NOT: a central-exchange tape. Spot gold has none; these sizes are
Dukascopy's liquidity providers. It is a proxy, and every result says so.

One parquet per day under data/ticks/XAUUSD/, so a stopped pull resumes where it
left off. `load()` stitches them.

    .venv/bin/python core/ticks.py                 # the whole window
    .venv/bin/python core/ticks.py --from 2026-08-01
"""
from __future__ import annotations

import argparse
import lzma
import random
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.fx_data import POINT, UA                                  # noqa: E402

SYM = "XAUUSD"
DIR = ROOT / "data" / "ticks" / SYM
URL = ("https://datafeed.dukascopy.com/datafeed/{sym}/{y:04d}/{m:02d}/{d:02d}/"
       "{h:02d}h_ticks.bi5")
DT = np.dtype([("ms", ">u4"), ("ask", ">u4"), ("bid", ">u4"),
               ("askv", ">f4"), ("bidv", ">f4")])
START, END = "2021-09-01", "2026-09-14"
#: Dukascopy throttles: 24 parallel requests got 14 refusals of 24 on
#: 2026-10-09. Six at a time with backoff, newest days first (the 3-year test
#: window matters most; the older two years only feed step 6's re-check).
WORKERS = 2


def _fetch(t: datetime, retries: int = 6) -> bytes | None:
    url = URL.format(sym=SYM, y=t.year, m=t.month - 1, d=t.day, h=t.hour)
    for k in range(retries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA),
                                        timeout=30) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return b""
            # 503 = throttled. Hammering it got the IP refused for minutes on
            # 2026-10-09; back off hard instead.
            time.sleep((20 if e.code in (429, 503) else 1.5) * 2 ** k + random.random())
        except Exception:                                     # noqa: BLE001
            time.sleep(1.5 * 2 ** k + random.random())
    return None


def _hour(t: datetime) -> pd.DataFrame | None:
    raw = _fetch(t)
    if raw is None:
        raise IOError(f"failed {t}")
    if not raw:
        return None
    buf = lzma.decompress(raw)
    a = np.frombuffer(buf[: len(buf) // 20 * 20], dtype=DT)
    if not len(a):
        return None
    p = POINT[SYM]
    ask, bid = a["ask"] / p, a["bid"] / p
    mid = (ask + bid) / 2
    ok = (bid > 0) & (ask >= bid)
    a, ask, bid, mid = a[ok], ask[ok], bid[ok], mid[ok]
    if not len(a):
        return None
    vol = a["askv"].astype(float) + a["bidv"].astype(float)
    d = np.sign(np.diff(mid, prepend=mid[0]))
    ts = pd.to_datetime(t) + pd.to_timedelta(a["ms"].astype("int64"), unit="ms")
    df = pd.DataFrame({"mid": mid, "ask_vol": a["askv"].astype(float),
                       "bid_vol": a["bidv"].astype(float),
                       "up_vol": np.where(d > 0, vol, 0.0), "dn_vol": np.where(d < 0, vol, 0.0),
                       "up_ticks": (d > 0).astype(int), "dn_ticks": (d < 0).astype(int),
                       "spread": ask - bid}, index=ts)
    g = df.resample("1min")
    out = g["mid"].ohlc()
    out["ticks"] = g["mid"].count()
    for c in ("ask_vol", "bid_vol", "up_vol", "dn_vol", "up_ticks", "dn_ticks"):
        out[c] = g[c].sum()
    out["spread"] = g["spread"].mean()
    return out[out.ticks > 0]


def _day(day: pd.Timestamp) -> str:
    p = DIR / f"{day:%Y%m%d}.parquet"
    if p.exists():
        return "cached"
    hours = [day.to_pydatetime().replace(hour=h, tzinfo=timezone.utc) for h in range(24)]
    frames = []
    for t in hours:
        f = _hour(t)
        time.sleep(0.2)                      # politeness between files
        if f is not None:
            frames.append(f)
    df = pd.concat(frames) if frames else pd.DataFrame()
    df.to_parquet(p)
    return f"{len(df)} min"


def pull(start: str = START, end: str = END) -> None:
    DIR.mkdir(parents=True, exist_ok=True)
    days = [d for d in pd.date_range(start, end, freq="D", tz="UTC") if d.dayofweek != 5]
    todo = [d for d in days if not (DIR / f"{d:%Y%m%d}.parquet").exists()][::-1]
    print(f"{len(days)} days in window, {len(todo)} to fetch", flush=True)
    done = 0
    with ThreadPoolExecutor(WORKERS) as ex:
        futs = {ex.submit(_day, d): d for d in todo}
        for f in futs:
            try:
                f.result()
            except Exception as e:                                 # noqa: BLE001
                print(f"  {futs[f]:%Y-%m-%d} FAILED {e} - rerun to retry", flush=True)
            done += 1
            if done % 50 == 0:
                print(f"  {done}/{len(todo)} days", flush=True)
    print("done", flush=True)


def load() -> pd.DataFrame:
    fs = sorted(DIR.glob("*.parquet"))
    return pd.concat([pd.read_parquet(f) for f in fs]).sort_index()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="start", default=START)
    ap.add_argument("--to", dest="end", default=END)
    a = ap.parse_args()
    pull(a.start, a.end)
