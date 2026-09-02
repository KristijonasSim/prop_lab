"""Perp-versus-spot feeds from Binance's public archive: premium and spot flow.

WHY THIS EXISTS. Everything this repo has traded so far is measured on ONE book.
H-002/H-009 run on perp bars; H-006's positioning feeds are perp-only; H-004 used
the 8-hourly funding settlement, which is a smoothed, lagged summary of the perp's
dislocation rather than the dislocation itself. Nothing here has ever compared the
derivative against the cash market it is supposed to track.

Two free series make that comparison, both 5-minute, both back to 2020-01, for
every USDT-M symbol:

    premiumIndexKlines   (perp mark - spot index) / spot index, per bar.
                         The instantaneous basis. Funding is an 8h TWAP of this
                         with a clamp on top, so this is the same economic
                         quantity at ~100x the resolution H-004 had.

    spot klines          the cash market's own bars, carrying taker_buy_base -
                         a true signed aggressor flow on SPOT. The perp
                         equivalent is already cached by binance_metrics.klines,
                         so the pair gives perp aggression against cash
                         aggression on the same clock.

The point of both is the same question: is a move being paid for in cash, or is
it leverage alone? A named counterparty sits on each side - leveraged takers push
the perp away from the index, basis arbitrageurs and the funding transfer pull it
back - which is the property every leg that has ever worked in this project had,
and no price pattern has.

Run:  .venv/bin/python core/basis_data.py                  BTC, ETH, SOL
      .venv/bin/python core/basis_data.py BTCUSDT SOLUSDT
"""
from __future__ import annotations

import io
import sys
import zipfile
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
FEEDS = ROOT / "data" / "feeds"
FEEDS.mkdir(parents=True, exist_ok=True)

UM = "https://data.binance.vision/data/futures/um"
SPOT = "https://data.binance.vision/data/spot"
DEFAULT = ("BTCUSDT", "ETHUSDT", "SOLUSDT")
WORKERS = 8
FIRST = "2020-01"

KCOLS = ["open_time", "open", "high", "low", "close", "volume", "close_time",
         "quote_volume", "trades", "taker_buy_base", "taker_buy_quote", "ignore"]


def _zip_csv(url: str, s: requests.Session) -> pd.DataFrame | None:
    """One archive file, or None if it is not published.

    Missing files are normal and must stay missing: the symbol did not exist
    yet, or the exchange had an outage. Forward-filling a basis reading would
    invent a dislocation nobody could have seen.
    """
    try:
        r = s.get(url, timeout=60)
    except requests.RequestException:
        return None
    if r.status_code != 200:
        return None
    with zipfile.ZipFile(io.BytesIO(r.content)) as z:
        with z.open(z.namelist()[0]) as f:
            head = f.readline()
            f.seek(0)
            return pd.read_csv(f, header=None, names=KCOLS,
                               skiprows=1 if b"open_time" in head else 0)


def _frame(raw: list[pd.DataFrame], cols: list[str]) -> pd.DataFrame:
    df = pd.concat(raw, ignore_index=True)
    ts = df.open_time.astype("int64")
    # The archive switched from millisecond to microsecond stamps during 2025,
    # and a batch spanning the switch carries BOTH. Deciding the unit from the
    # batch maximum reads every millisecond row as microseconds and dates it to
    # 1970, which is how this was caught: the spot series claimed to start
    # 1970-01-19. The test has to be per row.
    us = ts > 10 ** 15
    df["ts"] = pd.to_datetime(ts.where(us, ts * 1000), unit="us", utc=True)
    return df.set_index("ts")[cols].astype("float64")


def fetch(sym: str, base: str, dataset: str, out_name: str,
          cols: list[str], tf: str = "5m", first: str = FIRST) -> pd.DataFrame:
    """Monthly files for the complete months, daily files for the tail.

    Monthly archives lag by weeks, so months alone silently end the series a
    month or two ago - which would quietly truncate every backtest built on it.
    """
    out = FEEDS / out_name
    have = pd.read_parquet(out) if out.exists() else pd.DataFrame()
    yesterday = date.today() - timedelta(days=1)

    start_m = pd.Period(first, freq="M")
    if len(have):
        first_cached = pd.Period(have.index.min().tz_convert("UTC").date(), freq="M")
        last_cached = pd.Period(have.index.max().tz_convert("UTC").date(), freq="M")
        if first_cached <= start_m:
            start_m = max(start_m, last_cached)
        else:
            print(f"  {sym} {dataset}: cache starts {first_cached}, later than "
                  f"{start_m} - refetching from the beginning")
    months = pd.period_range(start_m, pd.Period(yesterday, freq="M"), freq="M")

    got = have
    with requests.Session() as s, ThreadPoolExecutor(WORKERS) as ex:
        urls = [f"{base}/monthly/{dataset}/{sym}/{tf}/{sym}-{tf}-{m}.zip" for m in months]
        print(f"  {sym} {dataset}: {len(urls)} months ...", flush=True)
        raw = [g for g in ex.map(lambda u: _zip_csv(u, s), urls) if g is not None and len(g)]
        if raw:
            got = pd.concat([got, _frame(raw, cols)]) if len(got) else _frame(raw, cols)

        last = got.index.max().date() if len(got) else (
            pd.Period(first, freq="M").start_time.date() - timedelta(days=1))
        days = [last + timedelta(days=i) for i in range(1, (yesterday - last).days + 1)]
        if days:
            print(f"  {sym} {dataset}: {len(days)} daily files for the tail ...", flush=True)
            urls = [f"{base}/daily/{dataset}/{sym}/{tf}/{sym}-{tf}-{d:%Y-%m-%d}.zip"
                    for d in days]
            raw = [g for g in ex.map(lambda u: _zip_csv(u, s), urls)
                   if g is not None and len(g)]
            if raw:
                got = pd.concat([got, _frame(raw, cols)])

    if not len(got):
        print(f"  {sym} {dataset}: nothing returned")
        return got
    got = got[~got.index.duplicated(keep="last")].sort_index()
    got.to_parquet(out)
    print(f"  {sym} {dataset}: {len(got):,} bars  {got.index[0]:%Y-%m-%d} -> "
          f"{got.index[-1]:%Y-%m-%d}", flush=True)
    return got


def premium(sym: str, tf: str = "5m") -> pd.DataFrame:
    """(mark - index) / index, OHLC per bar. Volume columns are zero by design."""
    return fetch(sym, UM, "premiumIndexKlines", f"{sym}_premium_{tf}.parquet",
                 ["open", "high", "low", "close"], tf)


def spot(sym: str, tf: str = "5m") -> pd.DataFrame:
    """Cash-market bars with signed taker flow, the counterpart to the perp's."""
    return fetch(sym, SPOT, "klines", f"{sym}_spot_{tf}.parquet",
                 ["open", "high", "low", "close", "volume", "quote_volume",
                  "trades", "taker_buy_base"], tf)


def main():
    syms = sys.argv[1:] or list(DEFAULT)
    print(f"Binance perp-premium and spot-flow archive -> {FEEDS}")
    for sym in syms:
        premium(sym)
        spot(sym)


if __name__ == "__main__":
    main()
