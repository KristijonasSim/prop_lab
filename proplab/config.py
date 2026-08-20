"""Configuration objects: costs, prop-firm rules, backtest settings.

These are *inputs* to the engine. Edit the defaults here (or pass overrides)
rather than editing engine internals.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any


@dataclass(frozen=True)
class CostModel:
    """Crypto-perp style cost model. All rates in basis points of notional."""

    taker_fee_bps: float = 4.5      # Binance USDT-M taker ~0.045%
    maker_fee_bps: float = 1.8      # unused unless a strategy uses limit entries
    slippage_bps: float = 2.0       # adverse price move per fill, on top of fees
    stop_slippage_bps: float = 5.0  # stops fill worse: they trade into the move
    funding_bps_per_8h: float = 1.0 # avg long-pays-short funding; sign-aware
    apply_funding: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class PropFirmRules:
    """Evaluation-account constraints. Checked *inside* every backtest.

    Targets set by Kris (2026-08-20), firm not yet chosen: 4% daily loss,
    8% max loss, 8% profit target.

    NOTE on the 8%: "max loss" was not specified as static or trailing, so BOTH
    are enforced at 8%. That is the stricter reading - a strategy that survives
    it would pass either style of firm. If the chosen firm only uses one, relax
    the other and re-run; results will improve, never worsen.

    min_trading_days and max_single_day_profit_share were not specified and keep
    common evaluation values. Revisit once a firm is picked.
    """

    starting_balance: float = 100_000.0

    # Hard breach rules
    daily_loss_limit_pct: float = 4.0      # max loss in one calendar day (UTC)
    max_drawdown_pct: float = 8.0          # from starting balance (static)
    trailing_drawdown_pct: float = 8.0     # from equity high-water mark
    trailing_locks_at_start: bool = True   # trailing DD stops trailing once above start+target

    # Soft / qualification rules
    profit_target_pct: float = 8.0
    min_trading_days: int = 5
    max_single_day_profit_share: float = 0.40  # no day > 40% of total profit

    # Behaviour rules
    forbid_martingale: bool = True
    martingale_size_ratio: float = 1.5  # size-up > 1.5x after a loss = flagged

    # Whether drawdown is measured on closed balance or intraday equity.
    # Most firms use intraday equity (worse for us) -> default True.
    intraday_equity_basis: bool = True

    day_boundary_tz: str = "UTC"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class BacktestConfig:
    symbol: str = "BTCUSDT"
    primary_timeframe: str = "15m"
    higher_timeframes: tuple[str, ...] = ()
    start: str | None = None
    end: str | None = None
    split: str = "full"            # full | is | oos  (bookkeeping label)
    max_leverage: float = 3.0      # cap on notional / equity
    allow_shorts: bool = True
    close_at_end: bool = True      # force-flat on the final bar
    costs: CostModel = field(default_factory=CostModel)
    rules: PropFirmRules = field(default_factory=PropFirmRules)
    seed: int = 7

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["higher_timeframes"] = list(self.higher_timeframes)
        return d
