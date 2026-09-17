"""Two-sided volume for Dukascopy instruments — the feed this repo said gold did not have.

WHAT THIS IS. Dukascopy publishes one file per instrument per hour holding every
tick as `>IIIff`: milliseconds into the hour, ask, bid, **ask volume, bid
volume**. `core/fx_spread.py` has been downloading these files since 2026-09-07
to measure the spread, and unpacks the two volume fields into `_, _`. This module
keeps them.

WHAT IT IS NOT, AND THIS TRAVELS WITH EVERY NUMBER BUILT ON IT. Spot gold has no
central exchange, so this is **Dukascopy's own liquidity-provider volume**, not a
consolidated tape. There is nothing to validate it against. Whether `askVolume`
is size that TRADED at the ask or size QUOTED there decides whether a delta built
from it is aggressor flow (the H-006 family) or a liquidity imbalance (the H-024
family, which was real and cleared its cost in 0 of 935 cells). `reconcile()`
answers that by checking the tick volumes against the cached candle volume.

WHY VECTORISED. A Python loop over `struct.unpack_from` runs about 25k ticks a
second, and one gold hour holds up to 25k ticks - a day is a minute, three years
is a week. `np.frombuffer` with a big-endian record dtype does the same work in
one pass and makes the full download an afternoon.

Run:  .venv/bin/python core/gold_flow.py XAUUSD 2025-05-14 2025-05-15
"""
from __future__ import annotations

import lzma
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.fx_data import POINT                                      # noqa: E402
from core.fx_spread import _fetch                                   # noqa: E402

#: one tick record, big-endian, 20 bytes
DT = np.dtype([("ms", ">u4"), ("ask", ">u4"), ("bid", ">u4"),
               ("askvol", ">f4"), ("bidvol", ">f4")])
CACHE = ROOT / "data" / "flow"
WORKERS = 16


def parse_hour(raw: bytes) -> np.ndarray | None:
    """Decompress and parse one hourly tick file. None if empty or corrupt."""
    if not raw:
        return None
    try:
        buf = lzma.decompress(raw)
    except lzma.LZMAError:
        return None
    if len(buf) < DT.itemsize:
        return None
    return np.frombuffer(buf, dtype=DT, count=len(buf) // DT.itemsize)


def hour_frame(sym: str, t: datetime) -> pd.DataFrame | None:
    """One hour of ticks as a frame: ts, ask, bid, askvol, bidvol."""
    a = parse_hour(_fetch(sym, t))
    if a is None or not len(a):
        return None
    p = POINT[sym]
    ask = a["ask"].astype(np.float64) / p
    bid = a["bid"].astype(np.float64) / p
    ok = (bid > 0) & (ask >= bid)
    if not ok.any():
        return None
    base = pd.Timestamp(t)
    base = base.tz_localize("UTC") if base.tzinfo is None else base.tz_convert("UTC")
    ts = base + pd.to_timedelta(a["ms"][ok].astype(np.int64), unit="ms")
    return pd.DataFrame({"ask": ask[ok], "bid": bid[ok],
                         "askvol": a["askvol"][ok].astype(np.float64),
                         "bidvol": a["bidvol"][ok].astype(np.float64)}, index=ts)


def ticks(sym: str, start: str, end: str, workers: int = WORKERS) -> pd.DataFrame:
    """Every tick in [start, end). Hours are fetched in parallel, kept in order."""
    t0 = pd.Timestamp(start, tz="UTC").to_pydatetime()
    t1 = pd.Timestamp(end, tz="UTC").to_pydatetime()
    hours, t = [], t0
    while t < t1:
        hours.append(t)
        t += timedelta(hours=1)
    with ThreadPoolExecutor(workers) as ex:
        parts = list(ex.map(lambda h: hour_frame(sym, h), hours))
    parts = [p for p in parts if p is not None and len(p)]
    if not parts:
        return pd.DataFrame(columns=["ask", "bid", "askvol", "bidvol"])
    return pd.concat(parts).sort_index()


def bars(tk: pd.DataFrame, tf: str = "1h") -> pd.DataFrame:
    """Aggregate ticks into footprint bars.

    `delta` is the raw two-sided difference and `imb` the same thing normalised
    to [-1, 1], which is the comparable one across sessions of different size.
    `mid` prices the bar so nothing depends on which side of the book the last
    tick of the bar happened to land on.
    """
    mid = (tk.ask + tk.bid) / 2.0
    g = mid.resample(tf)
    out = pd.DataFrame({
        "open": g.first(), "high": g.max(), "low": g.min(), "close": g.last(),
        "ticks": g.count(),
        "askvol": tk.askvol.resample(tf).sum(),
        "bidvol": tk.bidvol.resample(tf).sum(),
        "spread_bps": ((tk.ask - tk.bid) / mid * 1e4).resample(tf).mean(),
    }).dropna(subset=["close"])
    out["vol"] = out.askvol + out.bidvol
    out["delta"] = out.askvol - out.bidvol
    with np.errstate(invalid="ignore", divide="ignore"):
        out["imb"] = np.where(out.vol > 0, out.delta / out.vol, 0.0)
    return out


def reconcile(sym: str, day: str) -> pd.DataFrame:
    """GATE 1. Do the tick volumes reproduce the cached candle volume?

    A stable ratio with high correlation means the two volume fields decompose
    the volume every backtest here already uses, by side. A poor one means they
    measure different things, and any `delta` built from them needs re-framing
    before it is called order flow.
    """
    from core.markets import load
    nxt = str(pd.Timestamp(day).date() + timedelta(days=1))
    tk = ticks(sym, day, nxt)
    if not len(tk):
        return pd.DataFrame()
    b = bars(tk, "1h")
    c = load(sym, "1h")
    c = c[(c.index >= b.index[0]) & (c.index <= b.index[-1])][["volume"]]
    j = b[["ticks", "askvol", "bidvol", "vol"]].join(c, how="inner")
    j["ratio"] = j.volume / j.vol
    return j


def cache_day(sym: str, day: pd.Timestamp, tf: str = "1min") -> int:
    """Download one day and store it as footprint bars. Returns rows written.

    RESUMABLE BY DESIGN, because Dukascopy rate-limits hard enough that a
    three-year pull is an overnight job: a day already on disk is skipped, so
    the driver can be killed and restarted without losing work. A day that is a
    real weekend or holiday writes an EMPTY marker file rather than nothing, or
    every restart would retry all 24 of its missing hours forever.
    """
    CACHE.mkdir(parents=True, exist_ok=True)
    dest = CACHE / sym / f"{day:%Y%m%d}.parquet"
    if dest.exists():
        return -1
    dest.parent.mkdir(parents=True, exist_ok=True)
    tk = ticks(sym, str(day.date()), str((day + timedelta(days=1)).date()))
    b = bars(tk, tf) if len(tk) else pd.DataFrame(
        columns=["open", "high", "low", "close", "ticks", "askvol", "bidvol",
                 "spread_bps", "vol", "delta", "imb"])
    b.to_parquet(dest)
    return len(b)


def download(sym: str, start: str, end: str, tf: str = "1min") -> None:
    """Every day in [start, end). Prints progress; safe to kill and rerun."""
    days = pd.date_range(start, end, freq="D", tz="UTC")
    done = wrote = 0
    for d in days:
        if d.weekday() == 5:                       # Saturday never trades
            continue
        n = cache_day(sym, d, tf)
        done += 1
        if n >= 0:
            wrote += 1
            print(f"  {d:%Y-%m-%d}  {n:5d} bars   ({wrote} new / {done} seen)",
                  flush=True)


def load_flow(sym: str, tf: str = "1h") -> pd.DataFrame:
    """Every cached day, re-aggregated to `tf`. Empty days drop out on their own."""
    d = CACHE / sym
    files = sorted(d.glob("*.parquet")) if d.exists() else []
    parts = [pd.read_parquet(f) for f in files]
    parts = [p for p in parts if len(p)]
    if not parts:
        return pd.DataFrame()
    m = pd.concat(parts).sort_index()
    if tf in ("1min", "1T"):
        return m
    g = m.resample(tf)
    out = pd.DataFrame({
        "open": g.open.first(), "high": g.high.max(), "low": g.low.min(),
        "close": g.close.last(), "ticks": g.ticks.sum(),
        "askvol": g.askvol.sum(), "bidvol": g.bidvol.sum(),
        "spread_bps": g.spread_bps.mean(),
    }).dropna(subset=["close"])
    out["vol"] = out.askvol + out.bidvol
    out["delta"] = out.askvol - out.bidvol
    with np.errstate(invalid="ignore", divide="ignore"):
        out["imb"] = np.where(out.vol > 0, out.delta / out.vol, 0.0)
    return out


def main() -> int:
    if len(sys.argv) > 1 and sys.argv[1] == "download":
        download(sys.argv[2], sys.argv[3], sys.argv[4])
        return 0
    sym = sys.argv[1] if len(sys.argv) > 1 else "XAUUSD"
    start = sys.argv[2] if len(sys.argv) > 2 else "2025-05-14"
    end = sys.argv[3] if len(sys.argv) > 3 else "2025-05-15"
    j = reconcile(sym, start)
    if not len(j):
        print("no ticks")
        return 1
    print(j.to_string(float_format=lambda x: f"{x:11.3f}"))
    print(f"\ncorr(tick volume, candle volume) = {j.vol.corr(j.volume):.4f}")
    print(f"ratio  mean {j.ratio.mean():.4f}  std {j.ratio.std():.4f}  "
          f"cv {j.ratio.std() / j.ratio.mean():.4f}")
    tk = ticks(sym, start, end)
    print(f"\n{len(tk):,} ticks {start} -> {end}")
    b = bars(tk, "1h")
    print(b[["ticks", "vol", "delta", "imb", "spread_bps"]]
          .to_string(float_format=lambda x: f"{x:10.3f}"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
