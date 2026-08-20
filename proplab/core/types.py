"""=== CORE BACKTEST MATH - OWNER: kris. Strategy code must not modify. ===

Value objects shared by the engine, metrics and prop-rule checker.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pandas as pd

LONG, SHORT, FLAT = 1, -1, 0


@dataclass(frozen=True)
class Bar:
    time: pd.Timestamp     # bar OPEN time
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass
class OrderIntent:
    """A decision made on the close of bar i, to be executed on bar i+1."""

    direction: int                 # LONG / SHORT / FLAT(=close)
    stop: float | None = None
    target: float | None = None
    risk_pct: float | None = None      # fraction of equity risked to the stop
    notional_pct: float | None = None  # fraction of equity as position notional
    max_bars: int | None = None        # time stop, in primary bars
    tag: str = ""
    reason: str = ""


@dataclass
class Position:
    direction: int
    qty: float
    entry_price: float
    entry_time: pd.Timestamp
    entry_bar: int
    stop: float | None = None
    target: float | None = None
    max_bars: int | None = None
    tag: str = ""
    entry_fee: float = 0.0
    funding_paid: float = 0.0
    mae: float = 0.0   # worst adverse excursion, in price terms
    mfe: float = 0.0
    initial_risk: float = 0.0  # |entry - stop| * qty, for R multiples

    @property
    def is_long(self) -> bool:
        return self.direction == LONG

    def unrealised(self, price: float) -> float:
        return (price - self.entry_price) * self.qty * self.direction


@dataclass
class Trade:
    entry_time: pd.Timestamp
    exit_time: pd.Timestamp
    direction: int
    qty: float
    entry_price: float
    exit_price: float
    gross_pnl: float
    fees: float
    funding: float
    net_pnl: float
    r_multiple: float
    bars_held: int
    exit_reason: str
    tag: str
    mae: float
    mfe: float
    equity_before: float
    equity_after: float

    def to_row(self) -> dict[str, Any]:
        d = self.__dict__.copy()
        d["entry_time"] = str(self.entry_time)
        d["exit_time"] = str(self.exit_time)
        d["side"] = "long" if self.direction == LONG else "short"
        return d


@dataclass
class BacktestResult:
    trades: list[Trade] = field(default_factory=list)
    equity: pd.Series = field(default_factory=lambda: pd.Series(dtype=float))
    equity_low: pd.Series = field(default_factory=lambda: pd.Series(dtype=float))
    metrics: dict = field(default_factory=dict)
    prop: dict = field(default_factory=dict)
    meta: dict = field(default_factory=dict)
    logs: list[str] = field(default_factory=list)

    @property
    def n_trades(self) -> int:
        return len(self.trades)

    def trades_df(self) -> pd.DataFrame:
        if not self.trades:
            return pd.DataFrame()
        return pd.DataFrame([t.to_row() for t in self.trades])
