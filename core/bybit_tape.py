"""BYBIT GOLD TAPE -> ONE-MINUTE ORDER FLOW. Kris, 2026-10-12: Kris tab, today.

Bybit publishes every XAUUSDT perpetual trade with its AGGRESSOR side
(public.bybit.com/trading/XAUUSDT/, one gzip csv per day, from 2026-03-09).
Unlike Dukascopy's quoted LP sizes this is a real tape on the venue the bots
trade, and `side` is the taker's side - no tick-rule guessing.

Dukascopy ticks (`core/ticks.py`) cover three years but were throttled to
16+ s per hourly file on 2026-10-12 (about 100 hours for the window), so this
is the order-flow source that exists today. Its limit is history: ~7 months.

Per UTC minute:
    open high low close     trade price
    trades                  number of prints
    buy_vol sell_vol        base size (XAU) taken by buyers / sellers
    buy_n sell_n            the same as counts
    max_print               largest single print (XAU)

    .venv/bin/python core/bybit_tape.py                       # gold, all days
    .venv/bin/python core/bybit_tape.py PAXGUSDT 2023-10-01   # any symbol, from a date
"""
from __future__ import annotations

import io
import re
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SYM = "XAUUSDT"
WORKERS = 8


def base(sym: str = SYM) -> str:
    return f"https://public.bybit.com/trading/{sym}/"


def folder(sym: str = SYM) -> Path:
    return ROOT / "data" / "tape" / sym


def days(sym: str = SYM) -> list[str]:
    html = urllib.request.urlopen(base(sym), timeout=30).read().decode()
    return sorted(set(re.findall(rf"{sym}(\d{{4}}-\d{{2}}-\d{{2}})\.csv\.gz", html)))


def minute_bars(raw: bytes) -> pd.DataFrame:
    t = pd.read_csv(io.BytesIO(raw), compression="gzip",
                    usecols=["timestamp", "side", "size", "price"])
    t.index = pd.to_datetime(t.timestamp, unit="s", utc=True)
    buy = t.side.eq("Buy")
    t["buy_vol"] = t["size"].where(buy, 0.0)
    t["sell_vol"] = t["size"].where(~buy, 0.0)
    t["buy_n"], t["sell_n"] = buy.astype(int), (~buy).astype(int)
    g = t.sort_index().resample("1min")
    out = g["price"].ohlc()
    out["trades"] = g["price"].count()
    for c in ("buy_vol", "sell_vol", "buy_n", "sell_n"):
        out[c] = g[c].sum()
    out["max_print"] = g["size"].max()
    return out[out.trades > 0]


def _day(sym: str, d: str) -> str:
    p = folder(sym) / f"{d}.parquet"
    if p.exists():
        return "cached"
    raw = urllib.request.urlopen(f"{base(sym)}{sym}{d}.csv.gz", timeout=120).read()
    minute_bars(raw).to_parquet(p)
    return d


def pull(sym: str = SYM, since: str = "") -> None:
    folder(sym).mkdir(parents=True, exist_ok=True)
    todo = [d for d in days(sym) if d >= since and not (folder(sym) / f"{d}.parquet").exists()]
    print(f"{sym}: {len(todo)} days to fetch", flush=True)
    with ThreadPoolExecutor(WORKERS) as ex:
        for i, r in enumerate(ex.map(lambda d: _day(sym, d), todo), 1):
            if i % 25 == 0:
                print(f"  {i}/{len(todo)}  {r}", flush=True)
    print("done", flush=True)


def load(sym: str = SYM) -> pd.DataFrame:
    return pd.concat([pd.read_parquet(f) for f in sorted(folder(sym).glob("*.parquet"))]).sort_index()


if __name__ == "__main__":
    sys.exit(pull(*sys.argv[1:]))
