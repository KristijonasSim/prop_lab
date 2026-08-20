"""Renko brick construction from time bars.

Renko throws away time: a brick appears only when price moves far enough, so
one brick can span minutes or days. That is the whole appeal and also the
whole danger.

THE LOOKAHEAD TRAP, AND HOW IT IS AVOIDED HERE
A brick's "close" is the price level it completes at - but you do not know the
brick completed until the source bar finishes. Charting packages draw the brick
at the moment price crossed the level, which is mid-bar, and a backtest that
acts there is trading on information it did not have. Every brick built here
therefore carries `close_time` = the CLOSE time of the 15m bar that completed
it, and the engine only exposes bricks whose close_time has passed. A brick is
actionable strictly after the bar that produced it.

Bricks are built from closes, and a reversal needs `reversal` bricks' worth of
movement (2 by default, matching TradingView's Traditional Renko).
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def build(df: pd.DataFrame, brick_size: float, reversal: int = 2) -> pd.DataFrame:
    """Bricks from an OHLCV frame indexed by bar OPEN time.

    Returns one row per brick with open/high/low/close/volume plus:
      close_time  when the brick became KNOWN (the source bar's close time)
      direction   +1 up, -1 down
      source_bar  index of the bar that completed it
    """
    if brick_size <= 0:
        raise ValueError("brick_size must be positive")
    closes = df["close"].to_numpy(float)
    vols = df["volume"].to_numpy(float) if "volume" in df else np.zeros(len(df))
    step = _infer_step(df)

    rows = []
    anchor = float(np.floor(closes[0] / brick_size) * brick_size)
    direction = 0
    pending_vol = 0.0

    for i in range(len(df)):
        price = closes[i]
        pending_vol += vols[i]
        while True:
            up_needed = brick_size if direction >= 0 else brick_size * reversal
            dn_needed = brick_size if direction <= 0 else brick_size * reversal
            if price >= anchor + up_needed:
                n = int((price - anchor) // brick_size)
                if direction < 0:
                    # a reversal consumes `reversal` bricks of movement before
                    # the first new brick prints
                    n = int((price - anchor - brick_size * (reversal - 1)) // brick_size)
                n = max(n, 1)
                for _ in range(n):
                    o, c = anchor, anchor + brick_size
                    rows.append((df.index[i] + step, o, c, max(o, c), min(o, c),
                                 pending_vol, 1, i))
                    pending_vol = 0.0
                    anchor = c
                direction = 1
            elif price <= anchor - dn_needed:
                n = int((anchor - price) // brick_size)
                if direction > 0:
                    n = int((anchor - price - brick_size * (reversal - 1)) // brick_size)
                n = max(n, 1)
                for _ in range(n):
                    o, c = anchor, anchor - brick_size
                    rows.append((df.index[i] + step, o, c, max(o, c), min(o, c),
                                 pending_vol, -1, i))
                    pending_vol = 0.0
                    anchor = c
                direction = -1
            else:
                break

    if not rows:
        raise ValueError(
            f"brick_size {brick_size} produced no bricks over {len(df)} bars - "
            f"price range was {closes.min():.2f}..{closes.max():.2f}")

    out = pd.DataFrame(rows, columns=["close_time", "open", "close", "high",
                                      "low", "volume", "direction", "source_bar"])
    # Index on close_time: for a renko series the only honest timestamp is when
    # the brick became known.
    out = out.set_index("close_time")
    out.index.name = "open_time"
    out["close_time"] = out.index
    return out


def atr_brick_size(df: pd.DataFrame, n: int = 14) -> float:
    """Brick size from average true range, the usual alternative to a fixed size."""
    high, low, close = df["high"].to_numpy(float), df["low"].to_numpy(float), df["close"].to_numpy(float)
    tr = np.maximum(high[1:] - low[1:],
                    np.maximum(np.abs(high[1:] - close[:-1]), np.abs(low[1:] - close[:-1])))
    if len(tr) < n:
        raise ValueError(f"need >= {n + 1} bars for an ATR brick size")
    return float(np.mean(tr[-n:]))


def summarise(bricks: pd.DataFrame) -> dict:
    d = bricks["direction"].to_numpy()
    flips = int((d[1:] != d[:-1]).sum()) if len(d) > 1 else 0
    gaps = pd.Series(bricks.index).diff().dropna()
    return {
        "bricks": int(len(bricks)),
        "up": int((d > 0).sum()),
        "down": int((d < 0).sum()),
        "flips": flips,
        "median_minutes_per_brick": round(float(gaps.median().total_seconds() / 60), 1) if len(gaps) else None,
        "max_hours_between_bricks": round(float(gaps.max().total_seconds() / 3600), 1) if len(gaps) else None,
    }


def _infer_step(df: pd.DataFrame) -> pd.Timedelta:
    diffs = pd.Series(df.index).diff().dropna()
    return pd.Timedelta(diffs.mode().iloc[0])
