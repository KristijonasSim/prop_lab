"""Cross-checking a strategy against an independent implementation.

An engine that only ever agrees with itself proves nothing. This runs a
strategy under a cost model a third-party platform (TradingView) can reproduce
exactly, and exports the trade list so the two can be diffed trade by trade.

Parity settings, and why each one is forced:
  funding OFF     - proplab charges perp funding at 00/08/16 UTC; Pine cannot
                    model it at all, so it is the largest avoidable difference.
  slippage 0      - Pine slippage is denominated in ticks, proplab's in bps.
                    Zero is the only value both express identically.
  taker 4.5bps    - set as commission_value=0.045 (percent) in the Pine script.

What still differs, and cannot be removed:
  - percent-of-equity sizing is computed by Pine at signal time and by proplab
    at fill time, so quantities differ slightly and compound over a long run.
  - TradingView's feed is its own; it is normally identical to Binance klines
    but is not guaranteed to be.
So compare trade TIMING and DIRECTION first - those must match exactly - and
treat P&L agreement as a looser check.
"""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pandas as pd

from .config import BacktestConfig, CostModel
from .core.types import LONG


def parity_config(base: BacktestConfig | None = None, taker_fee_bps: float = 4.5,
                  **overrides) -> BacktestConfig:
    """A BacktestConfig a TradingView strategy can reproduce."""
    cfg = base or BacktestConfig()
    costs = CostModel(taker_fee_bps=taker_fee_bps, maker_fee_bps=taker_fee_bps,
                      slippage_bps=0.0, stop_slippage_bps=0.0,
                      funding_bps_per_8h=0.0, apply_funding=False)
    return replace(cfg, costs=costs, **overrides)


def export_trades(result, path: str | Path, tz: str = "America/New_York") -> Path:
    """Write the trade list in a shape that lines up with TradingView's export.

    Times are written in the session timezone as well as UTC: TradingView's
    "List of Trades" is shown in chart time, and comparing UTC to New York time
    is the easiest way to conclude two identical runs disagree.
    """
    path = Path(path)
    rows = []
    for i, t in enumerate(result.trades, start=1):
        entry = pd.Timestamp(t.entry_time)
        exit_ = pd.Timestamp(t.exit_time)
        rows.append({
            "n": i,
            "side": "long" if t.direction == LONG else "short",
            "entry_utc": entry.strftime("%Y-%m-%d %H:%M"),
            "entry_local": entry.tz_convert(tz).strftime("%Y-%m-%d %H:%M"),
            "exit_utc": exit_.strftime("%Y-%m-%d %H:%M"),
            "exit_local": exit_.tz_convert(tz).strftime("%Y-%m-%d %H:%M"),
            "entry_price": round(t.entry_price, 2),
            "exit_price": round(t.exit_price, 2),
            "qty": round(t.qty, 6),
            "net_pnl": round(t.net_pnl, 2),
            "fees": round(t.fees, 2),
            "bars_held": t.bars_held,
            "exit_reason": t.exit_reason,
        })
    df = pd.DataFrame(rows)
    df.to_csv(path, index=False)
    return path


def summary(result) -> dict:
    """The handful of numbers to compare against TradingView's performance tab."""
    m = result.metrics
    return {
        "trades": m.get("n_trades"),
        "net_profit": m.get("net_profit"),
        "return_pct": m.get("total_return_pct"),
        "win_rate_pct": m.get("win_rate_pct"),
        "profit_factor": m.get("profit_factor"),
        "max_drawdown_pct": m.get("max_drawdown_pct"),
        "total_fees": m.get("total_fees"),
        "gross_profit": m.get("gross_profit"),
        "gross_loss": m.get("gross_loss"),
    }
