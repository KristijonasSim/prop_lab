"""=== CORE BACKTEST MATH - OWNER: kris. Strategy code must not modify. ===

Bar-by-bar execution engine.

EXECUTION MODEL (deliberately pessimistic - assume you get the worse fill):

  1. `on_bar(ctx)` is called AFTER bar i has closed. The strategy sees bars
     0..i only. Decision time = close time of bar i.
  2. A market intent from bar i fills at the OPEN of bar i+1, plus slippage.
     There is no same-bar-close entry anywhere in this engine.
  3. Protective stop/target are evaluated intrabar from the fill bar onward:
       - gap through the stop  -> fill at the bar OPEN (worse than the stop)
       - stop touched intrabar -> fill at stop price + stop slippage
       - if one bar's range contains BOTH stop and target, the STOP is
         assumed to hit first. We cannot see tick order, so we take the
         unfavourable branch.
  4. Funding is charged at 00/08/16 UTC on open notional (perp convention).
     KNOWN OPTIMISM: a target is treated as filled when the bar's range merely
     touches it. A real limit order at that price might not be filled if price
     only tags the level and reverses. Targets are therefore slightly generous;
     stops are slightly harsh. Net effect on results is conservative-ish but
     not provably so - worth remembering when a strategy lives or dies on
     target fills.
  5. Position size is computed at FILL time from the actual fill price, so
     the risked amount is exact rather than estimated.

Anything that would need to know the future is unreachable: the strategy is
handed a Context that can only slice backwards.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from ..config import BacktestConfig
from ..data.loader import Dataset
from .context import Context
from .types import FLAT, LONG, SHORT, BacktestResult, Position, Trade

FUNDING_HOURS = (0, 8, 16)


def run(strategy, data: Dataset, config: BacktestConfig | None = None,
        funding: pd.Series | None = None) -> BacktestResult:
    """Execute `strategy` over `data`. Returns raw result (metrics added later)."""
    cfg = config or BacktestConfig()
    rules, costs = cfg.rules, cfg.costs

    df = data.primary
    n = len(df)
    if n < 2:
        raise ValueError("Need at least 2 bars to run a backtest.")

    o = df["open"].to_numpy(float)
    h = df["high"].to_numpy(float)
    l = df["low"].to_numpy(float)
    c = df["close"].to_numpy(float)
    index = df.index

    ctx = Context(df, data.higher, cfg.primary_timeframe, getattr(strategy, "params", {}))
    if hasattr(strategy, "on_start"):
        strategy.on_start(ctx)

    cash = rules.starting_balance
    position: Position | None = None
    trades: list[Trade] = []
    equity_curve = np.empty(n)
    equity_low_curve = np.empty(n)  # worst intrabar equity, for prop DD checks
    pending = None  # OrderIntent carried from previous bar

    fee_rate = costs.taker_fee_bps / 1e4
    slip = costs.slippage_bps / 1e4
    stop_slip = costs.stop_slippage_bps / 1e4

    for i in range(n):
        bar_o, bar_h, bar_l, bar_c = o[i], h[i], l[i], c[i]

        # ---- 1. execute pending intent at this bar's open -----------------
        if pending is not None:
            equity_now = cash + (position.unrealised(bar_o) if position else 0.0)

            if pending.direction == FLAT and position is not None:
                cash, trade = _close(position, bar_o, index[i], i, cash, fee_rate,
                                     slip, pending.reason or "signal", equity_now)
                trades.append(trade)
                position = None

            elif pending.direction in (LONG, SHORT):
                if position is not None and position.direction != pending.direction:
                    cash, trade = _close(position, bar_o, index[i], i, cash, fee_rate,
                                         slip, "reverse", equity_now)
                    trades.append(trade)
                    position = None
                if position is None:
                    if pending.direction == SHORT and not cfg.allow_shorts:
                        pass
                    else:
                        position = _open(pending, bar_o, index[i], i, cash, fee_rate,
                                         slip, cfg)
                        if position is not None:
                            cash -= position.entry_fee
            pending = None

        # ---- 2. funding on open notional ---------------------------------
        ts = index[i]
        is_settlement = (ts.hour in FUNDING_HOURS and ts.minute == 0 and ts.second == 0)
        if costs.apply_funding and position is not None and is_settlement:
            rate = (float(funding.asof(ts)) if funding is not None
                    else costs.funding_bps_per_8h / 1e4)
            pay = rate * abs(position.qty) * bar_o * position.direction
            cash -= pay
            position.funding_paid += pay

        # ---- 3. protective exits, intrabar --------------------------------
        if position is not None:
            _track_excursion(position, bar_h, bar_l)
            exit_price, reason = _protective_exit(position, bar_o, bar_h, bar_l, stop_slip)
            if exit_price is not None:
                eq_before = cash + position.unrealised(bar_o)
                cash, trade = _close(position, exit_price, index[i], i, cash, fee_rate,
                                     0.0, reason, eq_before)  # slip already applied
                trades.append(trade)
                position = None

        # ---- 4. time stop --------------------------------------------------
        if position is not None and position.max_bars is not None \
                and (i - position.entry_bar) >= position.max_bars:
            eq_before = cash + position.unrealised(bar_c)
            cash, trade = _close(position, bar_c, index[i], i, cash, fee_rate,
                                 slip, "time_stop", eq_before)
            trades.append(trade)
            position = None

        # ---- 5. mark equity (close, and worst intrabar) --------------------
        equity = cash + (position.unrealised(bar_c) if position else 0.0)
        if position is None:
            worst = equity
        else:
            adverse = bar_l if position.is_long else bar_h
            worst = cash + position.unrealised(adverse)
        equity_curve[i] = equity
        equity_low_curve[i] = min(worst, equity)

        # ---- 6. strategy decision for the NEXT bar -------------------------
        is_last = (i == n - 1)
        if not is_last:
            ctx._advance(i, equity, cash, position)
            strategy.on_bar(ctx)
            pending = ctx.intent
        elif position is not None and cfg.close_at_end:
            eq_before = equity
            cash, trade = _close(position, bar_c, index[i], i, cash, fee_rate,
                                 slip, "end_of_test", eq_before)
            trades.append(trade)
            position = None
            equity_curve[i] = cash
            equity_low_curve[i] = min(equity_low_curve[i], cash)

    result = BacktestResult(
        trades=trades,
        equity=pd.Series(equity_curve, index=index, name="equity"),
        equity_low=pd.Series(equity_low_curve, index=index, name="equity_low"),
        logs=ctx._logs,
        meta={
            "symbol": data.symbol,
            "timeframe": cfg.primary_timeframe,
            "higher_timeframes": list(data.higher),
            "bars": n,
            "start": str(index[0]),
            "end": str(index[-1]),
            "data_hash": data.hash(),
            "integrity": data.integrity,
            "config": cfg.to_dict(),
            "strategy": getattr(strategy, "name", type(strategy).__name__),
            "params": dict(getattr(strategy, "params", {})),
        },
    )
    return result


# ---------------------------------------------------------------------------
# execution helpers
# ---------------------------------------------------------------------------

def _open(intent, price: float, ts, bar_i: int, cash: float, fee_rate: float,
          slip: float, cfg: BacktestConfig) -> Position | None:
    """Fill an entry at `price` (next bar's open) with adverse slippage."""
    d = intent.direction
    fill = price * (1 + slip * d)
    equity = cash

    if intent.risk_pct is not None and intent.stop is not None:
        risk_per_unit = abs(fill - intent.stop)
        if risk_per_unit <= 0:
            return None
        qty = (equity * intent.risk_pct) / risk_per_unit
    elif intent.notional_pct is not None:
        qty = (equity * intent.notional_pct) / fill
    else:
        raise ValueError(
            "Entry needs either risk_pct (+stop) or notional_pct. "
            "Unsized entries are not allowed - sizing is part of the strategy."
        )

    # leverage cap
    max_qty = (equity * cfg.max_leverage) / fill
    qty = min(qty, max_qty)
    if qty <= 0 or not np.isfinite(qty):
        return None

    # a stop on the wrong side of the fill would be an instant exit -> reject
    if intent.stop is not None:
        if (d == LONG and intent.stop >= fill) or (d == SHORT and intent.stop <= fill):
            return None

    fee = fill * qty * fee_rate
    return Position(
        direction=d, qty=qty, entry_price=fill, entry_time=ts, entry_bar=bar_i,
        stop=intent.stop, target=intent.target, max_bars=intent.max_bars,
        tag=intent.tag, entry_fee=fee,
        initial_risk=abs(fill - intent.stop) * qty if intent.stop else 0.0,
    )


def _protective_exit(pos: Position, bar_o: float, bar_h: float, bar_l: float,
                     stop_slip: float):
    """Return (fill_price, reason) if stop/target hit this bar, else (None, '')."""
    d = pos.direction
    stop_hit = pos.stop is not None and (bar_l <= pos.stop if d == LONG else bar_h >= pos.stop)
    tgt_hit = pos.target is not None and (bar_h >= pos.target if d == LONG else bar_l <= pos.target)

    if stop_hit:  # pessimistic: stop wins any same-bar ambiguity
        gapped = (bar_o <= pos.stop) if d == LONG else (bar_o >= pos.stop)
        raw = bar_o if gapped else pos.stop
        return raw * (1 - stop_slip * d), "stop"
    if tgt_hit:
        gapped = (bar_o >= pos.target) if d == LONG else (bar_o <= pos.target)
        return (bar_o if gapped else pos.target), "target"
    return None, ""


def _close(pos: Position, price: float, ts, bar_i: int, cash: float, fee_rate: float,
           slip: float, reason: str, equity_before: float) -> tuple[float, Trade]:
    d = pos.direction
    fill = price * (1 - slip * d)
    gross = (fill - pos.entry_price) * pos.qty * d
    exit_fee = fill * pos.qty * fee_rate
    fees = pos.entry_fee + exit_fee
    # entry fee and funding were already deducted from cash as they occurred
    cash += gross - exit_fee
    r = (gross - fees - pos.funding_paid) / pos.initial_risk if pos.initial_risk > 0 else float("nan")
    trade = Trade(
        entry_time=pos.entry_time, exit_time=ts, direction=d, qty=pos.qty,
        entry_price=pos.entry_price, exit_price=fill, gross_pnl=gross, fees=fees,
        funding=pos.funding_paid, net_pnl=gross - fees - pos.funding_paid,
        r_multiple=r, bars_held=bar_i - pos.entry_bar, exit_reason=reason,
        tag=pos.tag, mae=pos.mae, mfe=pos.mfe,
        equity_before=equity_before, equity_after=cash,
        initial_risk=pos.initial_risk,
    )
    return cash, trade


def _track_excursion(pos: Position, bar_h: float, bar_l: float) -> None:
    if pos.is_long:
        pos.mae = min(pos.mae, (bar_l - pos.entry_price) * pos.qty)
        pos.mfe = max(pos.mfe, (bar_h - pos.entry_price) * pos.qty)
    else:
        pos.mae = min(pos.mae, (pos.entry_price - bar_h) * pos.qty)
        pos.mfe = max(pos.mfe, (pos.entry_price - bar_l) * pos.qty)
