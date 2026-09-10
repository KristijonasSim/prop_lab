"""TASK 2 — measure the real FX and metals spread, instead of assuming it.

WHY THIS EXISTS. `core/fx_data.py` opens with this claim:

    "Bars are built from the MID price, and the mean half-spread of each bar is
     kept alongside it. That means the cost model for FX and gold is measured
     from the data rather than assumed, which matters: the BTC result died on
     costs, so a guessed spread would decide the FX answer by itself."

**None of that is true of the code as it stands.** It downloads
`BID_candles_min_1.bi5` — bid-only one-minute candles — and the cached parquets
carry exactly `open, high, low, close, volume`. There is no spread column and
never was. A comment further down admits the tick files were skipped because
there are 24x as many of them.

So the FX and metals cost model is an assumption, exactly like the crypto one:

    XAUUSD   1.00 bps fee + 0.50 bps slippage per side  = 3.0 bps round trip
    EURUSD   0.45 + 0.30                                = 1.5 bps round trip

This matters more than it did last week. After the 2026-09-06 engine fix, **gold
is the only market left on the board.** Its entire case rests on a number nobody
has checked, on bars that are bid-only rather than mid — which biases a long
entry by the full spread, because you buy at the ask and the bar says bid.

WHAT THIS DOES. Downloads Dukascopy's hourly TICK files, which do carry both
sides, for a stratified sample of days, and measures the actual spread: median,
by hour of day, and by year. Sampling rather than downloading everything is
deliberate — the point is the distribution of the spread, and a few hundred days
pins that far more tightly than the assumption it replaces.

TICK FORMAT. 20 bytes big-endian per tick: ms offset into the hour, ask, bid
(integers scaled by the instrument's point value), then ask and bid volume as
float32. Same POINT scaling as `core/fx_data.py`.

Run:  .venv/bin/python core/fx_spread.py                XAUUSD and EURUSD
      .venv/bin/python core/fx_spread.py XAUUSD --days 200
"""
from __future__ import annotations

import lzma
import struct
import time
import random
import sys
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
OUT = ROOT / "backtests" / "propfirms"
OUT.mkdir(parents=True, exist_ok=True)

from core.fx_data import POINT, UA                                  # noqa: E402

URL = ("https://datafeed.dukascopy.com/datafeed/{sym}/{y:04d}/{m:02d}/{d:02d}/"
       "{h:02d}h_ticks.bi5")
TICK = struct.Struct(">IIIff")            # ms, ask, bid, askvol, bidvol
DEFAULT = ("XAUUSD", "EURUSD")
START, END = "2023-09-01", "2026-08-31"
N_DAYS = 150
#: hours sampled from each chosen day, UTC. Spread is strongly time-of-day
#: dependent, so a sample that only looked at London would flatter it.
HOURS = (1, 5, 9, 13, 17, 21)
WORKERS = 24
#: the assumption each instrument is currently scored on, bps per side
ASSUMED = {"XAUUSD": 1.50, "XAGUSD": 2.25, "EURUSD": 0.75, "GBPUSD": 0.80}


def _fetch(sym: str, t: datetime, retries: int = 4) -> bytes | None:
    url = URL.format(sym=sym, y=t.year, m=t.month - 1, d=t.day, h=t.hour)
    for _ in range(retries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None                  # weekend or holiday
            # 429/503: retrying with no delay is what gets the client blocked
            time.sleep(1.5 * (2 ** _) + random.random())
        except Exception:
            time.sleep(1.5 * (2 ** _) + random.random())
    return None


def _hour(sym: str, t: datetime) -> pd.DataFrame | None:
    raw = _fetch(sym, t)
    if not raw:
        return None
    try:
        buf = lzma.decompress(raw)
    except lzma.LZMAError:
        return None
    n = len(buf) // TICK.size
    if n == 0:
        return None
    a = np.empty(n); b = np.empty(n); ms = np.empty(n)
    for i in range(n):
        ms[i], ai, bi, _, _ = TICK.unpack_from(buf, i * TICK.size)
        a[i], b[i] = ai, bi
    p = POINT[sym]
    ask, bid = a / p, b / p
    mid = (ask + bid) / 2.0
    ok = (bid > 0) & (ask >= bid) & (mid > 0)
    if not ok.any():
        return None
    # spread in bps of mid — the only unit comparable across price levels, and
    # gold ran from ~1900 to ~4500 over this sample
    spread_bps = (ask[ok] - bid[ok]) / mid[ok] * 1e4
    return pd.DataFrame({"ts": t, "hour": t.hour, "year": t.year,
                         "ticks": int(ok.sum()),
                         "median_bps": float(np.median(spread_bps)),
                         "mean_bps": float(np.mean(spread_bps)),
                         "p90_bps": float(np.percentile(spread_bps, 90))},
                        index=[0])


def measure(sym: str, n_days: int = N_DAYS) -> pd.DataFrame:
    days = pd.date_range(START, END, freq="D", tz="UTC")
    days = days[days.dayofweek < 5]                  # skip weekends
    pick = days[np.linspace(0, len(days) - 1, n_days).astype(int)]
    jobs = [d.to_pydatetime().replace(hour=h, tzinfo=timezone.utc)
            for d in pick for h in HOURS]
    print(f"  {sym}: sampling {len(jobs)} hours across {n_days} days ...",
          flush=True)
    frames = []
    with ThreadPoolExecutor(WORKERS) as ex:
        for got in ex.map(lambda t: _hour(sym, t), jobs):
            if got is not None:
                frames.append(got)
    if not frames:
        print(f"  {sym}: nothing downloaded")
        return pd.DataFrame()
    df = pd.concat(frames, ignore_index=True)
    df["sym"] = sym
    return df


def main(argv: list[str]) -> int:
    args = [a for a in argv[1:] if not a.startswith("--")]
    n = N_DAYS
    if "--days" in argv:
        n = int(argv[argv.index("--days") + 1])
    syms = args or list(DEFAULT)

    all_rows = []
    for sym in syms:
        df = measure(sym, n)
        if len(df):
            all_rows.append(df)
    if not all_rows:
        print("nothing measured")
        return 1
    out = pd.concat(all_rows, ignore_index=True)
    out.to_csv(OUT / "fx_spread_measured.csv", index=False)

    print(f"\n{'=' * 88}\nMEASURED SPREAD vs THE ASSUMPTION IT REPLACES "
          f"(bps of mid)\n{'=' * 88}")
    print(f"{'sym':9} {'hours':>6} {'median':>8} {'mean':>8} {'p90':>8} "
          f"{'half':>8} {'assumed':>9}  verdict")
    for sym, g in out.groupby("sym"):
        med = g.median_bps.median()
        half = med / 2.0
        asm = ASSUMED.get(sym, np.nan)
        verdict = ("assumption is CONSERVATIVE" if half < asm
                   else "assumption is TOO LOW")
        print(f"{sym:9} {len(g):6d} {med:8.3f} {g.mean_bps.median():8.3f} "
              f"{g.p90_bps.median():8.3f} {half:8.3f} {asm:9.2f}  {verdict}")

    print(f"\n-- median spread by UTC hour (bps of mid) --")
    print(out.pivot_table(index="sym", columns="hour",
                          values="median_bps", aggfunc="median")
          .round(3).to_string())

    print(f"\n-- median spread by year (bps of mid) --")
    print(out.pivot_table(index="sym", columns="year",
                          values="median_bps", aggfunc="median")
          .round(3).to_string())

    print("\nThe repo charges fee + slippage per SIDE. Half the round-trip\n"
          "spread is the part a market order pays on each side, so compare the\n"
          "'half' column against 'assumed'. Commission is on top of both and is\n"
          "a published number: cTrader raw is about $6 round turn per lot,\n"
          "which on a 100oz gold lot at $4,000 is 0.15bps round trip.")
    print(f"\nwrote {OUT / 'fx_spread_measured.csv'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
