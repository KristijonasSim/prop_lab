"""Combine several strategies into one book on shared capital.

WHY THIS EXISTS
---------------
Every leg tested here resolves far too slowly on its own - 400 to 4,400
trading days to an 8% target, against a phase constraint of one to two weeks.
But N5 as a BOOK reaches +10% in 17.6 days at 2.41 trades/day, and its legs are
the same slow legs. The trades/day comes from breadth, not from trading one
symbol faster, and breadth is the only lever that raises frequency without
raising cost per unit of move. So the thing worth testing is the book.

HOW, WITHOUT TOUCHING CORE
--------------------------
The engine is single-position by design and that is Kris's code. Rather than
change it, this replays the per-leg trade lists the engine already produced,
on one shared equity curve:

  * every trade keeps the R MULTIPLE core computed for it - all fills, fees,
    slippage and funding are core's numbers, untouched;
  * risk is a fixed fraction of the STARTING balance by default, because a
    prop evaluation is a fixed account - you make 8% of what you started with
    before losing 8% of it, and you do not compound your way there. Pass
    compound=True for the separate multi-year question;
  * at most `max_concurrent` positions are open at once. A signal arriving
    with every slot full is DROPPED, not queued - which is what a real account
    out of margin does, and what N5's K=4 cap means.

WHAT IT STILL DOES NOT MODEL
----------------------------
  * One symbol. N5 gets its breadth from nine legs across up to twenty
    symbols; this has leg breadth only, so its trades/day is a FLOOR for what
    the same legs would do multi-symbol, not an estimate of N5.
  * Correlation between legs is only captured through the timing of the
    trades they actually took. Two legs that would have entered the same move
    at slightly different moments still both get counted.
  * Slot allocation is first-come. A real book might prefer the better leg;
    this does not choose, it just fills.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class BookTrade:
    leg: str
    entry_time: pd.Timestamp
    exit_time: pd.Timestamp
    r_multiple: float
    risk: float
    pnl: float
    equity_after: float


def collect(results: dict[str, object]) -> pd.DataFrame:
    """Flatten {leg_name: BacktestResult} into one time-ordered trade table.

    Trades with no defined risk are dropped: a leg with no stop has no R, so
    it cannot be sized as a fraction of book equity and does not belong in a
    risk-parity book at all.
    """
    rows = []
    for leg, res in results.items():
        for t in res.trades:
            r = t.r_multiple
            if r != r or t.initial_risk <= 0:
                continue
            rows.append({"leg": leg, "entry_time": t.entry_time,
                         "exit_time": t.exit_time, "r_multiple": float(r),
                         "bars_held": t.bars_held, "exit_reason": t.exit_reason})
    if not rows:
        return pd.DataFrame(columns=["leg", "entry_time", "exit_time", "r_multiple"])
    return pd.DataFrame(rows).sort_values("entry_time").reset_index(drop=True)


def simulate(trades: pd.DataFrame, *, risk_pct: float = 0.005,
             max_concurrent: int = 4, starting_balance: float = 100_000.0,
             compound: bool = False):
    """Replay the combined trade list on one account.

    `compound=False` is the default and the right setting for the question
    this project asks. A prop evaluation is a FIXED account: you are trying to
    make 8% of the starting balance before losing 8% of it, and you do not get
    to compound your way there. Sizing off a growing equity curve also makes
    "days to target" meaningless over a multi-year window - the late years
    dwarf the early ones, average daily P&L is then dominated by an account
    that has already 100x'd, and the estimate collapses toward zero. Compound
    sizing is still available for the separate question of what the book does
    over years.

    Returns (book_trades, equity_curve, dropped). The curve is indexed by exit
    time, because that is when a trade's P&L actually lands.
    """
    equity = starting_balance
    open_slots: list[pd.Timestamp] = []      # exit times of live positions
    taken: list[BookTrade] = []
    dropped = 0

    for row in trades.itertuples(index=False):
        now = row.entry_time
        # free any slot whose trade has already closed by the time this one opens
        open_slots = [x for x in open_slots if x > now]
        if len(open_slots) >= max_concurrent:
            dropped += 1
            continue
        risk = (equity if compound else starting_balance) * risk_pct
        pnl = risk * row.r_multiple
        equity += pnl
        open_slots.append(row.exit_time)
        taken.append(BookTrade(row.leg, now, row.exit_time, row.r_multiple,
                               risk, pnl, equity))

    if not taken:
        return pd.DataFrame(), pd.Series(dtype=float), dropped

    bt = pd.DataFrame([t.__dict__ for t in taken])
    # P&L lands at the exit, so the curve must be built in exit order
    bt = bt.sort_values("exit_time")
    curve = pd.Series(starting_balance + bt["pnl"].cumsum().to_numpy(),
                      index=pd.DatetimeIndex(bt["exit_time"]))
    return bt, curve, dropped


def metrics(bt: pd.DataFrame, curve: pd.Series, *, starting_balance: float = 100_000.0,
            target_pct: float = 8.0) -> dict:
    """Book-level numbers, including the one that decides the phase question:
    how many trading days to reach the profit target."""
    if bt.empty:
        return {}
    wins = bt[bt["pnl"] > 0]["pnl"].sum()
    losses = -bt[bt["pnl"] < 0]["pnl"].sum()
    span_days = max((bt["exit_time"].max() - bt["entry_time"].min()).days, 1)
    peak = curve.cummax()
    dd = (peak - curve) / peak

    daily = curve.resample("1D").last().ffill().diff().dropna()
    drift = float(daily.mean())
    # with fixed risk this is a straight rate; with compounding it is not, and
    # the caller has been warned in simulate()
    target_cash = starting_balance * target_pct / 100
    days_to_target = target_cash / drift if drift > 0 else float("nan")

    hit = curve[curve >= starting_balance * (1 + target_pct / 100)]
    first_hit = (hit.index[0] - bt["entry_time"].min()).days if len(hit) else None

    return {
        "n_trades": int(len(bt)),
        "legs": int(bt["leg"].nunique()),
        "profit_factor": round(wins / losses, 3) if losses > 0 else float("inf"),
        "win_rate_pct": round(100 * (bt["pnl"] > 0).mean(), 1),
        "avg_r": round(float(bt["r_multiple"].mean()), 4),
        "total_return_pct": round(100 * (curve.iloc[-1] / starting_balance - 1), 2),
        "max_dd_pct": round(100 * float(dd.max()), 2),
        "trades_per_day": round(len(bt) / span_days, 3),
        "span_days": span_days,
        "daily_pnl_mean": round(drift, 2),
        "est_days_to_target": round(days_to_target, 1) if days_to_target == days_to_target else None,
        "first_reached_target_after_days": first_hit,
    }


def per_leg(bt: pd.DataFrame) -> pd.DataFrame:
    """What each leg contributed AFTER the concurrency cap took its cut.

    This is the column that matters for keep/drop decisions: a leg's
    standalone quality is not its book value, because the cap may have thrown
    away exactly the trades it needed.
    """
    g = bt.groupby("leg")
    out = pd.DataFrame({
        "trades": g.size(),
        "pnl": g["pnl"].sum().round(0),
        "avg_r": g["r_multiple"].mean().round(3),
        "win_pct": (g["pnl"].apply(lambda s: 100 * (s > 0).mean())).round(1),
    })
    out["share_of_pnl_pct"] = (100 * out["pnl"] / out["pnl"].sum()).round(1)
    return out.sort_values("pnl", ascending=False)
