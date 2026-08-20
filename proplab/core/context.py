"""=== CORE BACKTEST MATH - OWNER: kris. Strategy code must not modify. ===

The Context is the ONLY thing a strategy sees. It is a hard wall against
lookahead bias: every accessor slices the underlying arrays at the current
bar, so future data is not merely discouraged - it is not reachable.

Higher-timeframe access follows the same rule: a 4h bar becomes visible only
once its close_time <= the close_time of the current primary bar.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from ..data.timeframes import parse_timeframe
from .types import FLAT, LONG, SHORT, Bar, OrderIntent, Position


class TimeframeView:
    """Read-only, lookahead-safe view of one higher timeframe."""

    def __init__(self, tf: str, df: pd.DataFrame):
        self.tf = tf
        self._df = df
        self._close_times = (df.index + parse_timeframe(tf)).values
        self._arrays = {c: df[c].to_numpy(dtype=float) for c in
                        ("open", "high", "low", "close", "volume") if c in df}
        self._n = 0  # number of bars closed as of "now"

    def _sync(self, now: np.datetime64) -> None:
        self._n = int(np.searchsorted(self._close_times, now, side="right"))

    @property
    def ready(self) -> bool:
        return self._n > 0

    @property
    def n_closed(self) -> int:
        return self._n

    def series(self, col: str = "close", n: int | None = None) -> np.ndarray:
        """Last `n` CLOSED bars of `col` (oldest -> newest). Never future."""
        a = self._arrays[col][: self._n]
        return a if n is None else a[-n:]

    def last(self, col: str = "close", offset: int = 0) -> float:
        """Most recent closed value; offset=1 is the one before it."""
        idx = self._n - 1 - offset
        if idx < 0:
            return float("nan")
        return float(self._arrays[col][idx])

    def bar(self, offset: int = 0) -> Bar | None:
        idx = self._n - 1 - offset
        if idx < 0:
            return None
        return Bar(
            time=self._df.index[idx],
            open=float(self._arrays["open"][idx]),
            high=float(self._arrays["high"][idx]),
            low=float(self._arrays["low"][idx]),
            close=float(self._arrays["close"][idx]),
            volume=float(self._arrays["volume"][idx]),
        )

    def frame(self, n: int = 200) -> pd.DataFrame:
        """Copy of the last n closed bars. Copy, so strategies can't mutate data."""
        return self._df.iloc[max(0, self._n - n): self._n].copy()


class Context:
    """Per-bar strategy interface. Constructed once, re-pointed each bar."""

    def __init__(self, primary: pd.DataFrame, higher: dict[str, pd.DataFrame],
                 timeframe: str, params: dict):
        self._df = primary
        self._index = primary.index
        self._cols = {c: primary[c].to_numpy(dtype=float) for c in
                      ("open", "high", "low", "close", "volume") if c in primary}
        self._close_index = primary.index + parse_timeframe(timeframe)
        self._close_times = self._close_index.values
        self._views = {tf: TimeframeView(tf, df) for tf, df in higher.items()}
        self.timeframe = timeframe
        self.params = dict(params)
        self.state: dict = {}

        self.i = 0
        self.equity = 0.0
        self.cash = 0.0
        self.position: Position | None = None
        self.intent: OrderIntent | None = None
        self._logs: list[str] = []

    # ---- engine-side plumbing -------------------------------------------
    def _advance(self, i: int, equity: float, cash: float, position: Position | None) -> None:
        self.i = i
        self.equity = equity
        self.cash = cash
        self.position = position
        self.intent = None
        now = self._close_times[i]
        for v in self._views.values():
            v._sync(now)

    # ---- time -----------------------------------------------------------
    @property
    def time(self) -> pd.Timestamp:
        """OPEN time of the bar that just closed."""
        return self._index[self.i]

    @property
    def now(self) -> pd.Timestamp:
        """Decision time = CLOSE time of the current bar. Use this for sessions."""
        return self._close_index[self.i]

    @property
    def bars_seen(self) -> int:
        return self.i + 1

    # ---- primary-timeframe data ----------------------------------------
    @property
    def bar(self) -> Bar:
        i = self.i
        return Bar(self._index[i], float(self._cols["open"][i]), float(self._cols["high"][i]),
                   float(self._cols["low"][i]), float(self._cols["close"][i]),
                   float(self._cols["volume"][i]))

    @property
    def close(self) -> float:
        return float(self._cols["close"][self.i])

    def series(self, col: str = "close", n: int | None = None) -> np.ndarray:
        """Values up to AND INCLUDING the current bar. Slicing forbids the future."""
        a = self._cols[col][: self.i + 1]
        return a if n is None else a[-n:]

    def value(self, col: str = "close", offset: int = 0) -> float:
        idx = self.i - offset
        if idx < 0:
            return float("nan")
        return float(self._cols[col][idx])

    def frame(self, n: int = 200) -> pd.DataFrame:
        return self._df.iloc[max(0, self.i + 1 - n): self.i + 1].copy()

    def tf(self, timeframe: str) -> TimeframeView:
        if timeframe not in self._views:
            raise KeyError(
                f"Timeframe {timeframe!r} not loaded. Declare it in the "
                f"strategy's `higher_timeframes` and in BacktestConfig."
            )
        return self._views[timeframe]

    # ---- order intents ---------------------------------------------------
    def buy(self, *, stop=None, target=None, risk_pct=None, notional_pct=None,
            max_bars=None, tag="", reason="") -> None:
        self.intent = OrderIntent(LONG, stop, target, risk_pct, notional_pct,
                                  max_bars, tag, reason)

    def sell(self, *, stop=None, target=None, risk_pct=None, notional_pct=None,
             max_bars=None, tag="", reason="") -> None:
        self.intent = OrderIntent(SHORT, stop, target, risk_pct, notional_pct,
                                  max_bars, tag, reason)

    def close_position(self, reason: str = "signal") -> None:
        self.intent = OrderIntent(FLAT, reason=reason)

    def move_stop(self, price: float) -> None:
        """Adjust the stop of an open position (trailing stops)."""
        if self.position is not None:
            self.position.stop = float(price)

    def log(self, msg: str) -> None:
        self._logs.append(f"{self.now} | {msg}")
