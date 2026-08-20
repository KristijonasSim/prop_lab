"""Dataset assembly: load raw bars, slice, resample, and integrity-check."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from .binance import raw_path
from .timeframes import is_multiple_of, parse_timeframe, resample, to_utc

REQUIRED = ["open", "high", "low", "close", "volume"]


@dataclass
class Dataset:
    """Everything a backtest run needs from the data side."""

    symbol: str
    primary_timeframe: str
    primary: pd.DataFrame
    higher: dict[str, pd.DataFrame] = field(default_factory=dict)
    integrity: dict = field(default_factory=dict)

    @property
    def start(self) -> pd.Timestamp:
        return self.primary.index[0]

    @property
    def end(self) -> pd.Timestamp:
        return self.primary.index[-1]

    @property
    def n_bars(self) -> int:
        return len(self.primary)

    def hash(self) -> str:
        """Stable fingerprint of the exact bars used, for run reproducibility."""
        h = hashlib.sha256()
        h.update(f"{self.symbol}|{self.primary_timeframe}".encode())
        idx = self.primary.index
        h.update(str(idx[0]).encode())
        h.update(str(idx[-1]).encode())
        h.update(str(len(idx)).encode())
        h.update(pd.util.hash_pandas_object(self.primary["close"], index=False).values.tobytes())
        return h.hexdigest()[:16]

    def split(self, at: str) -> tuple["Dataset", "Dataset"]:
        """Chronological in-sample / out-of-sample split at a timestamp."""
        ts = to_utc(at)
        return self.slice(end=ts), self.slice(start=ts)

    def slice(self, start=None, end=None) -> "Dataset":
        p = self.primary
        if start is not None:
            p = p[p.index >= to_utc(start)]
        if end is not None:
            p = p[p.index < to_utc(end)]
        higher = {tf: resample(p, tf) for tf in self.higher}
        return Dataset(self.symbol, self.primary_timeframe, p, higher,
                       integrity=check_integrity(p, self.primary_timeframe))


def load(
    symbol: str = "BTCUSDT",
    primary_timeframe: str = "15m",
    higher_timeframes: tuple[str, ...] | list[str] = (),
    start: str | None = None,
    end: str | None = None,
    base_timeframe: str = "15m",
    market: str = "futures",
    path: str | Path | None = None,
    renko: dict | None = None,
) -> Dataset:
    """Load a Dataset from the raw parquet store.

    `base_timeframe` is what was downloaded; primary/higher are resampled from
    it so all timeframes agree bar-for-bar.
    """
    src = Path(path) if path else raw_path(symbol, base_timeframe, market)
    if not src.exists():
        raise FileNotFoundError(
            f"No raw data at {src}. Run:  python -m proplab.cli fetch "
            f"--symbol {symbol} --timeframe {base_timeframe}"
        )
    raw = pd.read_parquet(src)
    raw = raw[[c for c in REQUIRED if c in raw.columns] +
              [c for c in raw.columns if c not in REQUIRED]]
    raw = raw.sort_index()
    raw = raw[~raw.index.duplicated(keep="last")]

    if start is not None:
        raw = raw[raw.index >= to_utc(start)]
    if end is not None:
        raw = raw[raw.index < to_utc(end)]
    if len(raw) < 2:
        raise ValueError(f"Only {len(raw)} bars after slicing {start}..{end}")

    primary = raw if primary_timeframe == base_timeframe else resample(raw, primary_timeframe)

    higher: dict[str, pd.DataFrame] = {}
    for tf in higher_timeframes:
        if tf == "renko":
            continue          # built below; it is not a fixed timeframe
        if not is_multiple_of(tf, primary_timeframe):
            raise ValueError(
                f"Higher timeframe {tf} is not an exact multiple of primary "
                f"{primary_timeframe}; alignment would be ambiguous."
            )
        higher[tf] = resample(raw, tf)

    if renko or "renko" in higher_timeframes:
        renko = renko or {}
        from .renko import atr_brick_size, build
        size = renko.get("brick_size")
        if size in (None, "atr"):
            size = atr_brick_size(primary, renko.get("atr_len", 14))
        higher["renko"] = build(primary, float(size), renko.get("reversal", 2))

    return Dataset(symbol, primary_timeframe, primary, higher,
                   integrity=check_integrity(primary, primary_timeframe))


def check_integrity(df: pd.DataFrame, timeframe: str) -> dict:
    """Cheap data-quality report. Surfaced in the dashboard next to results.

    A strategy that looks great on data with 400 missing bars and 3 price
    spikes is not a result, it's a data artefact.
    """
    step = parse_timeframe(timeframe)
    gaps = pd.Series(df.index).diff().dropna()
    missing = int(((gaps / step).round() - 1).clip(lower=0).sum())
    bad_ohlc = int(
        ((df["high"] < df["low"])
         | (df["high"] < df[["open", "close"]].max(axis=1))
         | (df["low"] > df[["open", "close"]].min(axis=1))).sum()
    )
    ret = df["close"].pct_change()
    return {
        "bars": int(len(df)),
        "first_bar": str(df.index[0]),
        "last_bar": str(df.index[-1]),
        "missing_bars": missing,
        "missing_pct": round(100 * missing / max(len(df) + missing, 1), 3),
        "duplicate_index": int(df.index.duplicated().sum()),
        "zero_volume_bars": int((df["volume"] <= 0).sum()) if "volume" in df else 0,
        "bad_ohlc_bars": bad_ohlc,
        "max_abs_bar_return_pct": round(float(ret.abs().max() * 100), 3),
        "extreme_bars_gt_10pct": int((ret.abs() > 0.10).sum()),
    }
