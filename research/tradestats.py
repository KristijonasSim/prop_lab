"""The mandatory reporting fields, for a candidate that cleared the screen.

Kris, 2026-09-18: *"for those that work i need tpd DD PF all these stats"*.
`CLAUDE.md` has required them of every backtest since day one; the screen was
reporting a bucket response instead, which answers "is there a signal" and not
"what would trading it have looked like".

WHAT IS COMPUTED. Non-overlapping trades: enter when the signal is above its own
trailing quantile, hold `hold` bars, exit, and do not look for another entry
until it is out. Overlapping entries would inflate trades-per-day several times
over while double-counting the same move, which is exactly the frequency
inflation that withdrew the top-N result on 2026-09-17.

    trades, trades/day, average hold
    win rate, average return, profit factor at 1x / 2x / 3x cost
    max drawdown of the trade equity curve
    Sharpe, annualised from the observed trade rate

WHAT IS NOT COMPUTED, AND WHY NOT. **R multiples, and therefore expected days to
pass an evaluation.** R is a return divided by risk, and risk means a stop. This
rule has no stop - the screen never had one - so every R here would be a number
invented by this file rather than measured. `research/promote.py` is where a
stop gets chosen, pre-registered and paid for, and the prop simulation belongs
after that. A page that showed "expected days" off a stopless rule would be
making up the one number the whole project is steered by.

THE THRESHOLD IS TRAILING. The entry quantile comes from a rolling window that
ends at the decision bar. A whole-sample quantile is a look-ahead that no test
in this repo would catch, because it hides in the feature rather than the trade.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict

import numpy as np
import pandas as pd

#: Entry threshold: the signal's own trailing quantile. Matches the screen's
#: top bucket, so the stats describe the thing that was screened.
TOP_Q = 0.8
WINDOW = 250


@dataclass
class TradeStats:
    trades: int = 0
    trades_per_day: float = 0.0
    trades_per_week: float = 0.0
    avg_hold_bars: float = 0.0
    win_pct: float = 0.0
    avg_bps: float = 0.0
    pf_1x: float = 0.0
    pf_2x: float = 0.0
    pf_3x: float = 0.0
    max_dd_bps: float = 0.0
    sharpe: float = 0.0
    span_days: float = 0.0
    total_bps: float = 0.0

    def as_dict(self) -> dict:
        return {k: (round(v, 4) if isinstance(v, float) else v)
                for k, v in asdict(self).items()}


def _pf(r: np.ndarray) -> float:
    win = r[r > 0].sum()
    loss = -r[r < 0].sum()
    if loss <= 0:
        return float("inf") if win > 0 else 0.0
    return float(win / loss)


def compute(sig: pd.Series, fwd: pd.Series, round_trip_bps: float,
            hold: int, cadence: str = "1d") -> TradeStats:
    """Trade the screened rule and report what it did.

    `fwd` is already the forward return over `hold` bars in bps, so a trade's
    gross result is just `fwd` at the entry bar - no re-simulation, and no
    chance of the two disagreeing.
    """
    d = pd.concat([sig.rename("s"), fwd.rename("f")], axis=1).dropna()
    if len(d) < WINDOW // 2:
        return TradeStats()

    thresh = d.s.rolling(WINDOW, min_periods=60).quantile(TOP_Q)
    fire = (d.s > thresh).values
    f = d.f.values

    # non-overlapping: once in, no new entry until the hold is served
    rows, i, n = [], 0, len(d)
    while i < n:
        if fire[i] and np.isfinite(f[i]):
            rows.append(f[i])
            i += max(1, hold)
        else:
            i += 1
    if not rows:
        return TradeStats()

    gross = np.asarray(rows, dtype=float)
    span = (d.index[-1] - d.index[0]).days or 1
    per_bar = 24 if cadence in ("1h", "1H") else 1

    st = TradeStats(
        trades=len(gross),
        trades_per_day=len(gross) / span,
        trades_per_week=len(gross) / span * 7.0,
        avg_hold_bars=float(hold),
        span_days=float(span),
    )
    for mult, field in ((1, "pf_1x"), (2, "pf_2x"), (3, "pf_3x")):
        setattr(st, field, _pf(gross - round_trip_bps * mult))

    net = gross - round_trip_bps * 2.0          # the repo reports on 2x
    st.win_pct = float(100.0 * (net > 0).mean())
    st.avg_bps = float(net.mean())
    st.total_bps = float(net.sum())

    eq = np.cumsum(net)
    peak = np.maximum.accumulate(np.concatenate([[0.0], eq]))[1:]
    st.max_dd_bps = float(np.max(peak - eq)) if len(eq) else 0.0

    sd = net.std(ddof=1) if len(net) > 1 else 0.0
    if sd > 0:
        per_year = len(gross) / (span / 365.25)
        st.sharpe = float(net.mean() / sd * np.sqrt(max(per_year, 1e-9)))
    return st


def summary_line(st: TradeStats) -> str:
    pf = "inf" if st.pf_2x == float("inf") else f"{st.pf_2x:.2f}"
    return (f"{st.trades} trades · {st.trades_per_day:.2f}/day · "
            f"PF {pf} @2x · win {st.win_pct:.0f}% · "
            f"DD {st.max_dd_bps:.0f} bps · Sharpe {st.sharpe:.2f}")
