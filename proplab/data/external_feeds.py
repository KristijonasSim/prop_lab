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
RAW = ROOT / "data" / "raw"
OUT = RAW / "futures_BTCUSDT_1h.parquet"

REQUIRED_FEEDS = ("delta", "funding", "buy_ratio", "oi", "dvol", "dvol_pct")

# The DVOL regime gate, locked in trading-bots' bot_upcomers40: skip a TREND
# leg's entry while BTC implied vol sits in the bottom third of its trailing
# 180-day range, on the argument that trends whipsaw in calm markets.
DVOL_WIN, DVOL_MIN_PERIODS = 180, 60


def _read_klines(symbol: str = "BTCUSDT", tf: str = "1h") -> pd.DataFrame:
    df = pd.read_csv(SRC / f"{symbol}_{tf}.csv")
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


def _attach_dvol(df: pd.DataFrame, currency: str = "BTC") -> pd.DataFrame:
    """Deribit DVOL and its trailing percentile, as a DAILY series.

    BTC's DVOL is attached to EVERY symbol on purpose: u40 gates its trend
    legs on BTC implied vol regardless of which coin the leg is trading,
    because it is being used as a read on the whole crypto regime rather than
    on one instrument.

    The percentile is computed on daily closes and then forward-filled onto
    the bars, so a bar carries the rank of the last CLOSED day. Ranking on the
    current, unfinished day would be reading a close that has not happened.
    """
    d = pd.read_csv(SRC / f"{currency}_dvol.csv")
    idx = pd.to_datetime(d["date"], utc=True)
    dv = pd.Series(d["close"].to_numpy(float), index=idx).sort_index()
    dv = dv[~dv.index.duplicated(keep="last")]
    pct = dv.rolling(DVOL_WIN, min_periods=DVOL_MIN_PERIODS).rank(pct=True)
    # shift(1): the rank of days up to and including YESTERDAY's close
    df["dvol"] = dv.shift(1).reindex(df.index, method="ffill").to_numpy()
    df["dvol_pct"] = pct.shift(1).reindex(df.index, method="ffill").to_numpy()
    return df


def build(symbol: str = "BTCUSDT", tf: str = "1h", out: Path | None = None) -> pd.DataFrame:
    df = _read_klines(symbol, tf)
    df = _attach_funding(df, symbol)
    df = _attach_hourly(df, symbol, f"{symbol}_lsr_1h.csv", "buy_ratio")
    df = _attach_hourly(df, symbol, f"{symbol}_oi_1h.csv", "oi")
    df = _attach_dvol(df)

    # quote_volume/trades are not in the source CSV; the engine does not need
    # them, but the loader's REQUIRED set does want volume.
    keep = ["open", "high", "low", "close", "volume", *REQUIRED_FEEDS]
    df = df[[c for c in keep if c in df.columns]]

    dest = out or (RAW / f"futures_{symbol}_{tf}.parquet")
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


# The union of N5's live baskets, and the timeframe each leg needs. Building
# only what a leg actually trades keeps this honest: running a leg on a symbol
# it was never given is a different test, and should be labelled as one.
BASKETS = {
    "1h": ["ADAUSDT", "ATOMUSDT", "AVAXUSDT", "BCHUSDT", "BTCUSDT", "DOGEUSDT",
           "ETHUSDT", "LINKUSDT", "NEARUSDT", "SOLUSDT", "TRXUSDT", "XRPUSDT"],
    "30m": ["BTCUSDT", "ETHUSDT", "XRPUSDT", "LINKUSDT"],
    "4h": ["BTCUSDT", "ETHUSDT"],
}


def build_all(verbose: bool = True) -> list[tuple[str, str, int]]:
    out = []
    for tf, symbols in BASKETS.items():
        for sym in symbols:
            try:
                frame = build(sym, tf)
            except FileNotFoundError as e:
                if verbose:
                    print(f"  skip {sym} {tf}: {e}")
                continue
            out.append((sym, tf, len(frame)))
            if verbose:
                print(f"  {sym:10s} {tf:4s} {len(frame):7d} bars  "
                      f"{frame.index.min().date()} .. {frame.index.max().date()}")
    return out


if __name__ == "__main__":
    print("building N5's baskets")
    rows = build_all()
    print(f"\nwrote {len(rows)} parquet files into {RAW}")
