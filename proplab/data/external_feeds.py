"""Build a BTCUSDT 1h dataset carrying the extra feeds N5's legs need.

Four N5 legs are not expressible from OHLCV alone:

    ff                funding
    lsr               Bybit account long/short ratio (buy_ratio)
    oi                buy_ratio + open interest
    delta_absorption  taker delta + funding

All four feeds already exist as CSVs in the trading-bots repo, so this copies
them into proplab's own store rather than reaching across to another project at
run time - a backtest that depends on a sibling checkout is not reproducible.

The output is `data/raw/futures_BTCUSDT_1h.parquet` with the usual OHLCV plus
`delta`, `funding`, `buy_ratio` and `oi`. Loaded with `--timeframe 1h
--base-timeframe 1h` it passes straight through, extra columns intact, and a
strategy reads them through `ctx.frame()`, which is sliced at the current bar
like everything else.

ALIGNMENT, which is where lookahead would get in:

  * `delta` is part of the kline row itself - it describes the bar it sits on,
    and proplab decides at that bar's CLOSE, so it is known.
  * `funding` settles every 8h and is forward-filled onto bar starts, so a bar
    carries the last rate that had actually settled. Never the next one.
  * `buy_ratio` and `oi` are hourly rows joined on bar start, matching the
    reference builders (`px.merge(r, left_on="start", right_on="ts")`). Each
    row summarises the hour at or before the bar's close, and proplab acts at
    the close, so this is if anything stricter than the source bots, which act
    on the same value at the bar's open.

Usage:  python -m proplab.data.external_feeds
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

SRC = Path("/home/kris/trading-bots/scalping/data")
ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "raw" / "futures_BTCUSDT_1h.parquet"

REQUIRED_FEEDS = ("delta", "funding", "buy_ratio", "oi")


def _read_klines(symbol: str = "BTCUSDT") -> pd.DataFrame:
    df = pd.read_csv(SRC / f"{symbol}_1h.csv")
    df["time"] = pd.to_datetime(df["start"], unit="ms", utc=True)
    df = df.set_index("time").drop(columns=["start"]).sort_index()
    return df[~df.index.duplicated(keep="last")]


def _attach_funding(df: pd.DataFrame, symbol: str) -> pd.DataFrame:
    f = pd.read_csv(SRC / f"{symbol}_funding.csv")
    fr = pd.Series(f["fundingRate"].to_numpy(float),
                   index=pd.to_datetime(f["fundingTime"], unit="ms", utc=True)).sort_index()
    fr = fr[~fr.index.duplicated(keep="last")]
    # ffill: a bar carries the last rate that had already settled
    df["funding"] = fr.reindex(df.index, method="ffill").to_numpy()
    return df


def _attach_hourly(df: pd.DataFrame, symbol: str, fname: str, col: str) -> pd.DataFrame:
    s = pd.read_csv(SRC / fname)
    ser = pd.Series(s[col].to_numpy(float),
                    index=pd.to_datetime(s["ts"], unit="ms", utc=True)).sort_index()
    ser = ser[~ser.index.duplicated(keep="last")]
    df[col] = ser.reindex(df.index).to_numpy()      # exact join, as the bots do
    return df


def build(symbol: str = "BTCUSDT", out: Path | None = None) -> pd.DataFrame:
    df = _read_klines(symbol)
    df = _attach_funding(df, symbol)
    df = _attach_hourly(df, symbol, f"{symbol}_lsr_1h.csv", "buy_ratio")
    df = _attach_hourly(df, symbol, f"{symbol}_oi_1h.csv", "oi")

    # quote_volume/trades are not in the source CSV; the engine does not need
    # them, but the loader's REQUIRED set does want volume.
    keep = ["open", "high", "low", "close", "volume", *REQUIRED_FEEDS]
    df = df[[c for c in keep if c in df.columns]]

    dest = out or OUT
    dest.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(dest)
    return df


def coverage(df: pd.DataFrame) -> str:
    lines = [f"{len(df)} bars  {df.index.min()} .. {df.index.max()}"]
    for c in REQUIRED_FEEDS:
        ok = df[c].notna()
        if ok.any():
            lines.append(f"  {c:10s} {int(ok.sum()):6d} bars  "
                         f"{df.index[ok][0]} .. {df.index[ok][-1]}")
        else:
            lines.append(f"  {c:10s} EMPTY")
    return "\n".join(lines)


if __name__ == "__main__":
    frame = build()
    print(f"wrote {OUT}")
    print(coverage(frame))
