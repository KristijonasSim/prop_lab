"""Glue between our parquet bars and a NautilusTrader BacktestEngine."""

from __future__ import annotations

import pandas as pd
from nautilus_trader.backtest.engine import BacktestEngine, BacktestEngineConfig
from nautilus_trader.config import LoggingConfig
from nautilus_trader.model.currencies import USDT
from nautilus_trader.model.data import BarType
from nautilus_trader.model.enums import AccountType, OmsType
from nautilus_trader.model.identifiers import Venue
from nautilus_trader.model.objects import Money
from nautilus_trader.persistence.wranglers import BarDataWrangler
from nautilus_trader.test_kit.providers import TestInstrumentProvider

VENUE = Venue("BINANCE")

# Binance USDT-M perpetual: 0.05%/side taker. Report at 1x, 2x, 3x (CLAUDE.md).
TAKER_FEE = 0.0005


def make_engine(
    starting_equity: float = 100_000,
    fee_mult: float = 1.0,
    log_level: str = "ERROR",
) -> BacktestEngine:
    engine = BacktestEngine(
        config=BacktestEngineConfig(
            trader_id="BACKTESTER-001",
            logging=LoggingConfig(log_level=log_level),
        )
    )
    # MARGIN, not CASH: a spot cash account silently rejects every short, which
    # turns a two-sided strategy into a long-only one without saying so.
    engine.add_venue(
        venue=VENUE,
        oms_type=OmsType.NETTING,
        account_type=AccountType.MARGIN,
        base_currency=USDT,
        starting_balances=[Money(starting_equity, USDT)],
    )
    return engine


def add_bars(
    engine: BacktestEngine,
    df: pd.DataFrame,
    bar_spec: str = "15-MINUTE-LAST",
):
    """df: our OHLCV frame, UTC index. Returns (instrument, bar_type)."""
    instrument = TestInstrumentProvider.btcusdt_perp_binance()
    engine.add_instrument(instrument)

    bar_type = BarType.from_str(f"{instrument.id}-{bar_spec}-EXTERNAL")
    wrangler = BarDataWrangler(bar_type=bar_type, instrument=instrument)
    # parquet-backed arrays are read-only; the wrangler needs writable buffers
    ohlcv = df[["open", "high", "low", "close", "volume"]].astype("float64").copy()
    bars = wrangler.process(ohlcv)
    engine.add_data(bars)
    return instrument, bar_type
