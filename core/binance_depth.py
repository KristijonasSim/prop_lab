"""Order-book DEPTH from Binance's public archive — the feed nobody here has used.

WHY THIS EXISTS. Every hypothesis in this project so far has been built on price
(dead, ~10 times) or on the `metrics` feed — open interest, taker ratio, crowd
long/short (H-006, H-009, H-017). The standing pattern is that only feeds ever
worked. `data.binance.vision` publishes a THIRD feed that has never been touched
here: `bookDepth`, the resting order book itself.

WHAT IT IS, verified against the archive on 2026-09-06:

    columns     timestamp, percentage, depth, notional
    cadence     ~every 30 seconds  (2,880 snapshots per day)
    levels      +/- 0.2, 1, 2, 3, 4, 5 percent from the mid
    coverage    2023-01-01 -> yesterday, for all eleven coins the metrics
                archive covers. About 550 KB compressed per coin-day.

`depth` is base units, `notional` is USDT. Negative `percentage` is the BID side,
positive is the ASK side. The numbers are CUMULATIVE — the -5% row contains the
-1% row inside it — which was checked, not assumed: on 2026-09-01 the BTCUSDT
bid side reads 6,391 / 8,967 / 10,267 base at 3 / 4 / 5 percent.

WHY IT SHOULD CARRY SOMETHING. The metrics feed says who is POSITIONED (open
interest) and who is AGGRESSING (taker ratio). Neither says what is standing in
the way. Depth is resting supply and demand — the thing a market order has to eat
through. Two claims follow, and they are different objects:

  * IMBALANCE. More resting bid than ask within a band is a directional read on
    where the next move is cheap. The microstructure literature ranks top-of-book
    imbalance as the single most informative feature it has, though it measures
    it at 3-second horizons, which is not a horizon anything here can trade.
    Whether it survives aggregation to 15m-4h is exactly the open question.
  * COST. This is the part that matters even if the signal fails. Every number in
    this repo rests on an ASSUMED 14bps round trip. Depth at +/-0.2% and +/-1%
    says what a given clip would actually have paid, minute by minute, for three
    and a half years. That turns the project's largest assumption into a
    measurement.

NO LOOKAHEAD. Snapshots are stamped at the instant they were taken, so a bar is
built only from snapshots inside it and is knowable at its close. Bars are left
MISSING rather than forward-filled when the archive has no file: a filled depth
reading is a book nobody ever saw.

Run:  .venv/bin/python core/binance_depth.py                 BTC, ETH, SOL
      .venv/bin/python core/binance_depth.py BTCUSDT LINKUSDT
"""
from __future__ import annotations

import io
import sys
import zipfile
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
FEEDS = ROOT / "data" / "feeds"
FEEDS.mkdir(parents=True, exist_ok=True)

BASE = "https://data.binance.vision/data/futures/um"
FIRST = date(2023, 1, 1)          # first day the archive carries bookDepth
DEFAULT = ("BTCUSDT", "ETHUSDT", "SOLUSDT")
WORKERS = 8                       # polite: this is a free public bucket
CHUNK = 120                       # days per write, so a long run survives a kill
BANDS = (0.2, 1.0, 2.0, 3.0, 4.0, 5.0)
BAR = "5min"                      # the metrics feed's grid, so the two join


def _snapshot_features(df: pd.DataFrame) -> pd.DataFrame:
    """One row per snapshot: imbalance per band, and the book's total size.

    Pivoted rather than grouped: a snapshot is 12 rows and there are 2,880 of
    them a day, so a groupby-apply over a year is minutes of pure overhead.
    """
    p = df.pivot_table(index="timestamp", columns="percentage",
                       values="notional", aggfunc="last")
    out = {}
    for b in BANDS:
        if -b not in p.columns or b not in p.columns:
            continue
        bid, ask = p[-b].to_numpy(float), p[b].to_numpy(float)
        tot = bid + ask
        with np.errstate(invalid="ignore", divide="ignore"):
            out[f"imb_{b:g}"] = np.where(tot > 0, (bid - ask) / tot, np.nan)
        out[f"dep_{b:g}"] = tot
    f = pd.DataFrame(out, index=p.index)
    # Book SHAPE: how much of the five-percent book sits in the first one.
    # A book that is deep far away but hollow up close is a different market
    # from one that is uniformly thin, and total depth alone cannot tell them
    # apart.
    if "dep_1" in f and "dep_5" in f:
        with np.errstate(invalid="ignore", divide="ignore"):
            f["hollow"] = np.where(f["dep_5"] > 0, f["dep_1"] / f["dep_5"], np.nan)
    return f


def _day(sym: str, d: date, session: requests.Session) -> pd.DataFrame | None:
    """One day of depth, already reduced to 5-minute bars.

    The raw file is thrown away deliberately. Three and a half years of 30-second
    snapshots for eleven coins is tens of gigabytes and none of it is needed
    twice — the bar-level aggregate is what every study will read.
    """
    url = f"{BASE}/daily/bookDepth/{sym}/{sym}-bookDepth-{d:%Y-%m-%d}.zip"
    try:
        r = session.get(url, timeout=60)
    except requests.RequestException:
        return None
    if r.status_code != 200:
        return None
    with zipfile.ZipFile(io.BytesIO(r.content)) as z:
        with z.open(z.namelist()[0]) as f:
            raw = pd.read_csv(f)
    if raw.empty:
        return None
    raw["timestamp"] = pd.to_datetime(raw.timestamp, utc=True)
    snaps = _snapshot_features(raw)
    if snaps.empty:
        return None
    # Mean over the snapshots inside each bar, plus a count so a bar built from
    # two snapshots instead of ten can be recognised and dropped later.
    g = snaps.resample(BAR)
    bars = g.mean()
    bars["n_snap"] = g.size()
    return bars[bars.n_snap > 0]


def fetch(sym: str, first: date = FIRST, last: date | None = None) -> pd.DataFrame:
    """Every day the archive has, appended to whatever is already cached."""
    out = FEEDS / f"{sym}_depth_5m.parquet"
    have = pd.read_parquet(out) if out.exists() else pd.DataFrame()
    last = last or (date.today() - timedelta(days=1))
    days = [first + timedelta(days=i) for i in range((last - first).days + 1)]
    if len(have):
        seen = set(have.index.tz_convert("UTC").date)
        days = [d for d in days if d not in seen]
    if not days:
        print(f"  {sym}: already complete to {have.index[-1]:%Y-%m-%d}")
        return have

    print(f"  {sym}: fetching {len(days)} days of bookDepth ...", flush=True)
    df, added, missing = have, 0, 0
    with requests.Session() as sess, ThreadPoolExecutor(WORKERS) as ex:
        for i in range(0, len(days), CHUNK):
            part = days[i:i + CHUNK]
            got = list(ex.map(lambda d: _day(sym, d, sess), part))
            frames = [g for g in got if g is not None and len(g)]
            added += len(frames)
            missing += len(part) - len(frames)
            if not frames:
                continue
            df = pd.concat([df, *frames]) if len(df) else pd.concat(frames)
            df = df[~df.index.duplicated(keep="last")].sort_index()
            df.to_parquet(out)
            print(f"    {sym} {part[0]:%Y-%m-%d} .. {part[-1]:%Y-%m-%d}  "
                  f"{len(df):,} bars cached", flush=True)
    if not len(df):
        print(f"  {sym}: archive returned nothing")
        return df
    print(f"  {sym}: {len(df):,} bars  {df.index[0]:%Y-%m-%d} -> "
          f"{df.index[-1]:%Y-%m-%d}  ({added} days added, {missing} missing)")
    return df


def main(argv: list[str]) -> int:
    syms = argv[1:] or list(DEFAULT)
    print(f"bookDepth -> {FEEDS}")
    for s in syms:
        fetch(s)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
