"""H-047 gate 2 — what a new Binance listing actually pays, gross.

PRE-REGISTRATION: `PREREG.md`. Median, not mean; the bar is 20 bps.

Data is `data.binance.vision`, which archives **every symbol that ever traded**,
delisted ones included - so the population is not the 481 survivors but the 733
pairs that have existed. Entry is the close of the first COMPLETED hour, never
the first print, because no retail order reaches that.

Run: .venv/bin/python strategies/listings/listing_event.py
"""
from __future__ import annotations

import io
import json
import sys
import urllib.request
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
SCRATCH = Path("/tmp/claude-1000/-home-kris-prop-lab/"
               "a54afd6b-68d3-4206-8eca-b5b047b2da9d/scratchpad")
URL = ("https://data.binance.vision/data/spot/monthly/klines/"
       "{s}/1h/{s}-1h-{m}.zip")
HORIZONS = [1, 4, 12, 24, 72]
WINDOW_FROM = "2023-08"
FEE_BAR_BPS = 20.0          # Binance spot taker round trip, no BNB discount


def first_month(sym: str, month: str) -> pd.DataFrame | None:
    """The symbol's first archived month of 1h bars."""
    try:
        raw = urllib.request.urlopen(URL.format(s=sym, m=month), timeout=40).read()
    except Exception:
        return None
    try:
        z = zipfile.ZipFile(io.BytesIO(raw))
        df = pd.read_csv(z.open(z.namelist()[0]), header=None,
                         usecols=[0, 1, 2, 3, 4, 5],
                         names=["ts", "open", "high", "low", "close", "vol"])
    except Exception:
        return None
    if not len(df):
        return None
    # the archive switched from ms to us epochs partway through its history
    unit = "us" if df.ts.iloc[0] > 1e14 else "ms"
    df.index = pd.to_datetime(df.ts, unit=unit, utc=True)
    return df.sort_index()


def event(sym: str, month: str) -> dict | None:
    """Forward returns from the close of the first completed hour."""
    df = first_month(sym, month)
    if df is None or len(df) < 2:
        return None
    entry = float(df.close.iloc[0])
    if not np.isfinite(entry) or entry <= 0:
        return None
    out = {"sym": sym, "listed": str(df.index[0].date()),
           "year": df.index[0].year, "bars": len(df)}
    for h in HORIZONS:
        out[f"r{h}"] = ((float(df.close.iloc[h]) / entry - 1.0) * 1e4
                        if len(df) > h else np.nan)
    # what a taker actually crosses in that first hour, as a floor on cost
    out["hl_bps"] = float((df.high.iloc[0] / df.low.iloc[0] - 1.0) * 1e4)
    return out


def main() -> int:
    life = json.loads((SCRATCH / "lifespans.json").read_text())
    live = set(json.loads((SCRATCH / "listing_dates.json").read_text()))
    todo = [(s, v["first"]) for s, v in life.items() if v["first"] >= WINDOW_FROM]
    print(f"{len(todo)} USDT listings since {WINDOW_FROM} "
          f"({sum(1 for s, _ in todo if s not in live)} of them already delisted)",
          flush=True)

    with ThreadPoolExecutor(16) as ex:
        rows = list(ex.map(lambda t: event(*t), todo))
    df = pd.DataFrame([r for r in rows if r])
    print(f"{len(df)} events with usable first-month data\n", flush=True)

    cols = [f"r{h}" for h in HORIZONS]
    print(f"{'horizon':>8}{'n':>6}{'MEDIAN':>10}{'mean':>10}{'q25':>9}"
          f"{'q75':>9}{'pos%':>7}   verdict vs 20bps")
    print("-" * 78)
    res = {}
    for h in HORIZONS:
        x = df[f"r{h}"].dropna()
        if not len(x):
            continue
        med, mean = x.median(), x.mean()
        res[h] = {"n": int(len(x)), "median": round(med, 1),
                  "mean": round(mean, 1), "q25": round(x.quantile(.25), 1),
                  "q75": round(x.quantile(.75), 1),
                  "pos_pct": round(float((x > 0).mean() * 100), 1)}
        v = "PASS" if med > FEE_BAR_BPS else "fail"
        flag = "  <- MEAN passes, MEDIAN does not" if (med <= FEE_BAR_BPS
                                                       and mean > FEE_BAR_BPS) else ""
        print(f"{h:>6}h{len(x):>6}{med:>10.1f}{mean:>10.1f}"
              f"{x.quantile(.25):>9.1f}{x.quantile(.75):>9.1f}"
              f"{(x > 0).mean()*100:>7.1f}   {v}{flag}", flush=True)

    print(f"\nfirst-hour high/low range, a FLOOR on what a taker crosses: "
          f"median {df.hl_bps.median():.0f} bps, q75 {df.hl_bps.quantile(.75):.0f} bps")

    print("\nby listing year (median bps), the decay check:")
    hdr = f"{'year':>6}{'n':>5}" + "".join(f"{'r'+str(h):>9}" for h in HORIZONS)
    print(hdr)
    yr = {}
    for y, g in df.groupby("year"):
        yr[int(y)] = {f"r{h}": round(float(g[f'r{h}'].median()), 1) for h in HORIZONS}
        print(f"{y:>6}{len(g):>5}" + "".join(f"{g[f'r{h}'].median():>9.1f}"
                                             for h in HORIZONS), flush=True)

    dest = ROOT / "backtests" / "listings"
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "listing_event.json").write_text(json.dumps(
        {"bar_bps": FEE_BAR_BPS, "n_events": len(df), "horizons": res,
         "by_year": yr, "hl_median_bps": round(float(df.hl_bps.median()), 1)},
        indent=1))
    df.to_csv(dest / "listing_events.csv", index=False)
    print(f"\nwrote {(dest / 'listing_event.json').relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
