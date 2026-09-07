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


def fx_instrument(symbol: str, price_precision: int = 3,
                  size_precision: int = 8):
    """An instrument whose precision does not destroy the data.

    `add_bars` builds its bars against a BTCUSDT perpetual, which has
    **price_precision 1 and size_precision 3**. That is harmless on a 30,000
    BTC print and ruinous on gold: XAUUSD closes carry three decimals, so
    1939.815 quantises to 1939.8, and the Dukascopy tick-count "volume" of
    0.0216 quantises to 0.022 — a 1.8% error in a number the VWAP uses as its
    weight. A cross-check run on rounded inputs would report mismatches that
    belong to the rounding and not to the kernel.

    Volume scale itself does not matter — VWAP and rvol are both ratios and are
    invariant to it — but volume RESOLUTION does, which is why size_precision
    is 8 rather than the venue's real lot rules. This instrument exists to
    carry data faithfully into a backtest engine, not to model a broker.
    """
    from decimal import Decimal

    from nautilus_trader.model.currencies import USD
    from nautilus_trader.model.identifiers import InstrumentId, Symbol
    from nautilus_trader.model.instruments import CurrencyPair
    from nautilus_trader.model.objects import Currency, Money, Price, Quantity

    base = Currency.from_str("XAU") if symbol.startswith("XAU") else \
        Currency.from_str(symbol[:3])
    quote = Currency.from_str(symbol[-3:])
    return CurrencyPair(
        instrument_id=InstrumentId(symbol=Symbol(symbol), venue=VENUE),
        raw_symbol=Symbol(symbol),
        base_currency=base, quote_currency=quote,
        price_precision=price_precision, size_precision=size_precision,
        price_increment=Price(10 ** -price_precision, price_precision),
        size_increment=Quantity(10 ** -size_precision, size_precision),
        lot_size=None,
        max_quantity=Quantity.from_str("1e7"),
        min_quantity=Quantity(10 ** -size_precision, size_precision),
        max_price=None, min_price=None,
        max_notional=Money(50_000_000.00, USD), min_notional=None,
        margin_init=Decimal("0.03"), margin_maint=Decimal("0.03"),
        maker_fee=Decimal("0"), taker_fee=Decimal("0"),
        ts_event=0, ts_init=0,
    )


def add_bars_for(engine: BacktestEngine, df: pd.DataFrame, instrument,
                 bar_spec: str = "5-MINUTE-LAST"):
    """`add_bars`, but against an instrument the caller chose."""
    engine.add_instrument(instrument)
    bar_type = BarType.from_str(f"{instrument.id}-{bar_spec}-EXTERNAL")
    wrangler = BarDataWrangler(bar_type=bar_type, instrument=instrument)
    ohlcv = df[["open", "high", "low", "close", "volume"]].astype("float64").copy()
    engine.add_data(wrangler.process(ohlcv))
    return instrument, bar_type
