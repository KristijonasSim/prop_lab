"""Historical order-flow feeds from Binance's public archive.

WHY THIS EXISTS. `core/feed_collector.py` records open interest and the taker
buy/sell ratio every 15 minutes because the REST endpoints only serve about two
days of them, and the handoff scheduled the order-flow hypothesis (H-006) for
2026-10 on the strength of that. That was wrong. Binance publishes the same
feeds as daily files at data.binance.vision going back to **2020-09-01**, at the
same 5-minute granularity, free and unauthenticated. Six years of history were
available the whole time.

WHAT EACH COLUMN IS, and why it is not the same thing twice:

    sum_open_interest                 contracts outstanding, in base units
    sum_open_interest_value           the same, marked in USDT
    count_long_short_ratio            long accounts / short accounts, ALL accounts
    count_toptrader_long_short_ratio  the same, restricted to the largest accounts
    sum_toptrader_long_short_ratio    top traders by POSITION SIZE, not headcount
    sum_taker_long_short_vol_ratio    taker buy volume / taker sell volume

The count/sum split is the interesting one. `count_*` weights a 100-dollar
account the same as a 10-million-dollar one, so it is a crowd-sentiment gauge;
`sum_toptrader_long_short_ratio` is size-weighted and large-account only, so the
two disagreeing is the retail-versus-size disagreement people trade on. Taker
ratio is aggression: it counts who crossed the spread, not who is positioned.

`feed_collector.py` stays useful - it records the live present, and this only
goes to yesterday - but nothing has to wait for it any more.

Run:  .venv/bin/python core/binance_metrics.py            BTC, ETH, SOL
      .venv/bin/python core/binance_metrics.py BTCUSDT SOLUSDT
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

BASE = "https://data.binance.vision/data/futures/um"
FIRST = date(2020, 9, 1)          # first day the archive carries metrics
DEFAULT = ("BTCUSDT", "ETHUSDT", "SOLUSDT")
WORKERS = 8                       # polite: this is a free public bucket
CHUNK = 180                       # days per write, so a long run survives a kill

NUMERIC = ["sum_open_interest", "sum_open_interest_value",
           "count_toptrader_long_short_ratio", "sum_toptrader_long_short_ratio",
           "count_long_short_ratio", "sum_taker_long_short_vol_ratio"]


def _day(sym: str, d: date, session: requests.Session) -> pd.DataFrame | None:
    """One day of 5-minute metrics, or None if the archive has no file.

    Missing days are normal - a symbol did not exist yet, or the exchange had an
    outage - and they must stay missing rather than being filled, because a
    forward-filled order-flow reading is a signal that was never observable."""
    url = f"{BASE}/daily/metrics/{sym}/{sym}-metrics-{d:%Y-%m-%d}.zip"
    try:
        r = session.get(url, timeout=30)
    except requests.RequestException:
        return None
    if r.status_code != 200:
        return None
    with zipfile.ZipFile(io.BytesIO(r.content)) as z:
        with z.open(z.namelist()[0]) as f:
            df = pd.read_csv(f)
    if df.empty:
        return None
    df["create_time"] = pd.to_datetime(df.create_time, utc=True)
    df = df.set_index("create_time").sort_index()
    return df[[c for c in NUMERIC if c in df.columns]].astype("float64")


def fetch(sym: str, first: date = FIRST, last: date | None = None) -> pd.DataFrame:
    """Every day the archive has, appended to whatever is already cached."""
    out = FEEDS / f"{sym}_metrics_5m.parquet"
    have = pd.read_parquet(out) if out.exists() else pd.DataFrame()
    last = last or (date.today() - timedelta(days=1))
    days = [first + timedelta(days=i) for i in range((last - first).days + 1)]
    if len(have):
        seen = set(have.index.tz_convert("UTC").date)
        days = [d for d in days if d not in seen]
    if not days:
        print(f"  {sym}: already complete to {have.index[-1]:%Y-%m-%d}")
        return have

    # Written in chunks rather than once at the end. Six years is ~2,200
    # requests at a couple of seconds each; a single write at the end means an
    # interruption three quarters of the way through costs the whole run, which
    # is exactly what happened the first time this was used.
    print(f"  {sym}: fetching {len(days)} days ...")
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
            print(f"    {sym} {part[0]:%Y-%m} .. {part[-1]:%Y-%m}  "
                  f"{len(df):,} rows cached", flush=True)
    if not len(df):
        print(f"  {sym}: archive returned nothing")
        return df
    print(f"  {sym}: {len(df):,} rows  {df.index[0]:%Y-%m-%d} -> {df.index[-1]:%Y-%m-%d}"
          f"  ({added} days added, {missing} not in the archive)")
    return df


def funding(sym: str) -> pd.DataFrame:
    """Funding rate, monthly files, back to 2020-01. One row per 8h settlement."""
    out = FEEDS / f"{sym}_funding.parquet"
    months = pd.period_range("2020-01", pd.Timestamp.utcnow().to_period("M"), freq="M")
    frames = []
    with requests.Session() as s:
        for m in months:
            url = f"{BASE}/monthly/fundingRate/{sym}/{sym}-fundingRate-{m}.zip"
            try:
                r = s.get(url, timeout=30)
            except requests.RequestException:
                continue
            if r.status_code != 200:
                continue
            with zipfile.ZipFile(io.BytesIO(r.content)) as z:
                with z.open(z.namelist()[0]) as f:
                    frames.append(pd.read_csv(f))
    if not frames:
        print(f"  {sym}: no funding history")
        return pd.DataFrame()
    df = pd.concat(frames, ignore_index=True)
    tcol = "calc_time" if "calc_time" in df else df.columns[1]
    df["ts"] = pd.to_datetime(df[tcol], unit="ms", utc=True, errors="coerce")
    if df.ts.isna().all():
        df["ts"] = pd.to_datetime(df[tcol], utc=True, errors="coerce")
    df = df.dropna(subset=["ts"]).set_index("ts").sort_index()
    df = df[~df.index.duplicated(keep="last")]
    keep = [c for c in ("funding_rate", "last_funding_rate", "fundingRate") if c in df]
    df = df[keep].astype("float64")
    df.to_parquet(out)
    print(f"  {sym}: funding {len(df):,} rows  {df.index[0]:%Y-%m-%d} -> {df.index[-1]:%Y-%m-%d}")
    return df


def main():
    syms = sys.argv[1:] or list(DEFAULT)
    print(f"Binance futures metrics archive -> {FEEDS}")
    for sym in syms:
        fetch(sym)
        funding(sym)


if __name__ == "__main__":
    main()


# ---------------------------------------------------------------------------
# Perpetual klines, from the same archive.
#
# The repo's cached crypto bars are SPOT 15m. The order-flow feeds above are
# USDT-margined perpetuals, and that is also the venue this would be traded on,
# so mixing the two would measure a signal on one book against prices from
# another. These are the matching 5-minute perp bars, monthly files back to
# 2020-01. They also carry `taker_buy_base_asset_volume`, which is a true signed
# taker flow - the exchange's own ratio feed above is a summary of it.
# ---------------------------------------------------------------------------

KCOLS = ["open_time", "open", "high", "low", "close", "volume", "close_time",
         "quote_volume", "trades", "taker_buy_base", "taker_buy_quote", "ignore"]


def klines(sym: str, tf: str = "5m", first: str = "2020-01") -> pd.DataFrame:
    """Perp bars: monthly files for the complete months, daily files for the tail.

    The archive publishes monthly klines weeks in arrears, so asking only for
    months silently ends the series a month or two ago - which would quietly
    truncate every backtest built on it. The daily files cover the gap, and the
    boundary is taken from the data actually returned rather than from the
    calendar, because "the last month the archive has" is not knowable up front.
    """
    out = FEEDS / f"{sym}_perp_{tf}.parquet"
    have = pd.read_parquet(out) if out.exists() else pd.DataFrame()

    def one(url, s):
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
                skip = 1 if b"open_time" in head else 0
                return pd.read_csv(f, header=None, names=KCOLS, skiprows=skip)

    def frame(raw: list) -> pd.DataFrame:
        df = pd.concat(raw, ignore_index=True)
        ts = df.open_time.astype("int64")
        # The archive switched from millisecond to microsecond stamps during
        # 2025, and a batch spanning the switch carries BOTH. Deciding the unit
        # from the batch maximum reads every millisecond row as microseconds and
        # dates it to 1970 - which is exactly what happened to the spot series
        # in core/basis_data.py before this was fixed there. Test per row.
        us = ts > 10 ** 15
        df["ts"] = pd.to_datetime(ts.where(us, ts * 1000), unit="us", utc=True)
        return df.set_index("ts")[["open", "high", "low", "close", "volume",
                                   "quote_volume", "trades", "taker_buy_base"]
                                  ].astype("float64")

    yesterday = date.today() - timedelta(days=1)
    start_m = pd.Period(first, freq="M")
    if len(have):
        first_cached = pd.Period(have.index.min().tz_convert("UTC").date(), freq="M")
        last_cached = pd.Period(have.index.max().tz_convert("UTC").date(), freq="M")
        # Resume only if the cache actually reaches back to what was asked for.
        # A cache that starts LATER than `first` is a partial one, and skipping
        # ahead to its end would leave the hole in front of it forever - which
        # is exactly what a stray two-month test file did here once.
        if first_cached <= start_m:
            start_m = max(start_m, last_cached)
        else:
            print(f"  {sym} {tf}: cache starts {first_cached}, later than the "
                  f"requested {start_m} - refetching from the beginning")
    months = pd.period_range(start_m, pd.Period(yesterday, freq="M"), freq="M")

    got, raw = have, []
    with requests.Session() as s, ThreadPoolExecutor(WORKERS) as ex:
        urls = [f"{BASE}/monthly/klines/{sym}/{tf}/{sym}-{tf}-{m}.zip" for m in months]
        print(f"  {sym} {tf}: {len(urls)} months ...", flush=True)
        raw = [g for g in ex.map(lambda u: one(u, s), urls) if g is not None and len(g)]
        if raw:
            got = pd.concat([got, frame(raw)]) if len(got) else frame(raw)

        last = got.index.max().date() if len(got) else (
            pd.Period(first, freq="M").start_time.date() - timedelta(days=1))
        days = [last + timedelta(days=i) for i in range(1, (yesterday - last).days + 1)]
        if days:
            print(f"  {sym} {tf}: {len(days)} daily files for the tail "
                  f"({days[0]:%Y-%m-%d} -> {days[-1]:%Y-%m-%d}) ...", flush=True)
            urls = [f"{BASE}/daily/klines/{sym}/{tf}/{sym}-{tf}-{d:%Y-%m-%d}.zip"
                    for d in days]
            raw = [g for g in ex.map(lambda u: one(u, s), urls)
                   if g is not None and len(g)]
            if raw:
                got = pd.concat([got, frame(raw)])

    if not len(got):
        print(f"  {sym} {tf}: nothing returned")
        return got
    got = got[~got.index.duplicated(keep="last")].sort_index()
    got.to_parquet(out)
    print(f"  {sym} {tf}: {len(got):,} bars  {got.index[0]:%Y-%m-%d} -> "
          f"{got.index[-1]:%Y-%m-%d}")
    return got
