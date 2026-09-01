"""H-008 beta-residual reversion — the kernel.

MECHANISM (stated before any result, per CLAUDE.md).

BTC is the liquidity centre of crypto. The alts trade mostly as a beta to it —
when BTC moves, they move, and most of any alt's variance is that shared factor.
What is left after removing it, the residual, is the part of the move that is
specific to that coin.

The claim: a large SHORT-HORIZON residual is usually a liquidity event, not
information. Someone had to get out of an illiquid book right now — a market
order sweeping thin depth, a liquidation cascade, one desk repositioning — and
paid whatever the book charged. Nothing about the coin changed, so once the
pressure stops, market makers refill the book and the residual reverts. Who is
on the other side: the trader who could not wait, and the maker who wants paying
for holding inventory they did not choose.

WHY THIS COULD BEAT H-002 VWAP, which is the point of running it:

  * VWAP mean reversion fades an asset from its own volume-weighted average. It
    has no way to tell a liquidity move from an informed one — if BTC drops 3%
    and ETH follows, VWAP sees an ETH overshoot and fades a move that had a
    perfectly good reason to happen. Removing the market factor first is a
    strictly better-conditioned version of the same "fade the overshoot"
    instinct: it fades only the part of the move with no reason to persist.
  * Time to a funded account is `maxDD_in_R / R_per_day`. Four alts each throwing
    signals is more R per day than five single-asset legs, and the residual is
    far less correlated across coins than the raw price is — so the book's
    drawdown should aggregate better than H-002's does.

WHY IT MIGHT FAIL, recorded up front:

  * Cost. H-007 died at a 14bps round trip and this is the same venue. A hedged
    pair pays TWO round trips, so the hedged variant needs twice the edge. Both
    hedged and unhedged are tested for exactly this reason.
  * Beta is unstable in crypto. A residual computed with a stale beta is not a
    residual, it is a lagged market bet wearing a disguise.
  * `RESEARCH_LOG` already killed one fade family (H-005 liquidity sweep) where
    the null mean-reverted MORE readily than the real data. Shuffled series
    revert around their extremes; that is exactly the trap here.

EXIT IS FIXED-HOLD ONLY. No stop, no target. Both would need an intrabar
ordering assumption — which touched first — and this repo has already been
burned once by a fill assumption (the VWAP std-band result that backtested at
PF 3.0 and traded at 0.7). A fixed hold has no fill ambiguity at all. It is the
conservative choice and it understates the strategy; that is the right direction
to be wrong in.

NO LOOKAHEAD. Beta, residual and volatility at bar t use bars up to and
including t. Entry is the OPEN of t+1, exit the OPEN of t+1+H. Trades on a coin
are non-overlapping.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

FACTOR = "BTCUSDT"                       # the market factor, never traded itself
TFS = {"15m": ("15min", 96), "30m": ("30min", 48), "1h": ("1h", 24), "4h": ("4h", 6)}

VOL_WIN = 100          # bars used for the residual volatility estimate
MIN_VOL_BPS = 10.0     # floor, so a quiet stretch cannot fake a huge R


def resample(df: pd.DataFrame, rule: str) -> pd.DataFrame:
    return df.resample(rule, label="left", closed="left").agg(
        {"open": "first", "high": "max", "low": "min",
         "close": "last", "volume": "sum"}).dropna(subset=["open"])


def signals(pan: dict[str, pd.DataFrame], coin: str, *, beta_win: int, L: int,
            H: int) -> tuple[pd.DataFrame, np.ndarray]:
    """Residual z-score and the forward residual move, both as (T,) arrays."""
    close, opn = pan["close"], pan["open"]
    rc = np.log(close[coin] / close[coin].shift(1))
    rb = np.log(close[FACTOR] / close[FACTOR].shift(1))

    # rolling beta of the coin on the factor, history up to and including t
    cov = rc.rolling(beta_win, min_periods=beta_win).cov(rb)
    var = rb.rolling(beta_win, min_periods=beta_win).var()
    beta = (cov / var.replace(0.0, np.nan)).clip(-5, 5)

    # residual move over the last L bars, and its z-score
    Lc = np.log(close[coin] / close[coin].shift(L))
    Lb = np.log(close[FACTOR] / close[FACTOR].shift(L))
    resid = Lc - beta * Lb
    z = (resid - resid.rolling(VOL_WIN, min_periods=VOL_WIN).mean()) / \
        resid.rolling(VOL_WIN, min_periods=VOL_WIN).std().replace(0.0, np.nan)

    # forward move, entry at open t+1, exit at open t+1+H
    fc = np.log(opn[coin].shift(-(1 + H)) / opn[coin].shift(-1))
    fb = np.log(opn[FACTOR].shift(-(1 + H)) / opn[FACTOR].shift(-1))

    # Volatility for R sizing, and it must match what is actually held.
    # A hedged trade's P&L is the residual, so it is sized on residual vol. A
    # naked trade keeps the whole BTC beta, so its P&L carries the coin's TOTAL
    # volatility and must be sized on that. Using residual vol for both would
    # divide the naked variant's losses by a number smaller than the risk it
    # really ran, inflating its R and flattering it against the hedged one.
    step_resid = rc - beta * rb
    sig_h = (step_resid.rolling(VOL_WIN, min_periods=VOL_WIN).std()
             * np.sqrt(H)).clip(lower=MIN_VOL_BPS / 1e4)
    sig_n = (rc.rolling(VOL_WIN, min_periods=VOL_WIN).std()
             * np.sqrt(H)).clip(lower=MIN_VOL_BPS / 1e4)

    return pd.DataFrame({"z": z, "beta": beta, "fc": fc, "fb": fb,
                         "sig_h": sig_h, "sig_n": sig_n}), close.index


def run(pan: dict[str, pd.DataFrame], coins: list[str], *, beta_win: int, L: int,
        H: int, z_thr: float, hedged: bool, cost_bps: float) -> pd.DataFrame:
    """One configuration across every tradeable coin. One row per trade."""
    rows = []
    # a hedged trade crosses two spreads, an unhedged one crosses a single spread
    legs = 2.0 if hedged else 1.0
    cost_r = legs * 2.0 * (cost_bps / 1e4)

    for coin in coins:
        d, idx = signals(pan, coin, beta_win=beta_win, L=L, H=H)
        z, fc, fb, beta = d.z.values, d.fc.values, d.fb.values, d.beta.values
        sig = (d.sig_h if hedged else d.sig_n).values
        first = max(beta_win, L, VOL_WIN)
        last = len(idx) - (1 + H)
        if last <= first:
            continue

        t = np.arange(first, last, H)          # non-overlapping
        ok = (~np.isnan(z[t]) & ~np.isnan(fc[t]) & ~np.isnan(fb[t])
              & ~np.isnan(sig[t]) & ~np.isnan(beta[t]) & (np.abs(z[t]) >= z_thr))
        t = t[ok]
        if t.size == 0:
            continue

        direction = -np.sign(z[t])             # fade the residual
        gross = fc[t] - (beta[t] * fb[t] if hedged else 0.0)
        g = direction * gross
        v = sig[t]

        rows.append(pd.DataFrame({
            "coin": coin,
            "entry_ts": idx[t + 1],
            "exit_ts": idx[np.minimum(t + 1 + H, len(idx) - 1)],
            "z": z[t],
            "r_0x": g / v,
            "r": (g - cost_r) / v,
            "r_2x": (g - 2 * cost_r) / v,
            "r_3x": (g - 3 * cost_r) / v,
        }))
    if not rows:
        return pd.DataFrame()
    return pd.concat(rows, ignore_index=True).sort_values("exit_ts")


def pf_of(r: np.ndarray) -> float:
    g = float(r[r > 0].sum())
    l = float(-r[r < 0].sum())
    return float("inf") if l == 0 else (0.0 if g == 0 else g / l)


def summarise(tr: pd.DataFrame, hold_hours: float, n_books: int) -> dict:
    if tr.empty or len(tr) < 30:
        return {}
    # a book of N coins run in parallel each risks 1/N of the account
    r = tr.r.values / n_books
    span = max((tr.exit_ts.iloc[-1] - tr.exit_ts.iloc[0]).days, 1)
    eq = np.concatenate(([0.0], np.cumsum(r)))
    dd = abs(float((eq - np.maximum.accumulate(eq)).min()))
    rpd = float(r.sum()) / span
    sd = float(r.std(ddof=1))
    return {
        "trades": int(len(r)),
        "span_days": span,
        "tpd": len(r) / span,
        "tpd_per_coin": len(r) / span / n_books,
        "pf_0x": pf_of(tr.r_0x.values),
        "pf": pf_of(tr.r.values),
        "pf_2x": pf_of(tr.r_2x.values),
        "pf_3x": pf_of(tr.r_3x.values),
        "win": float((r > 0).mean()),
        "avg_r": float(r.mean()),
        "total_r": float(r.sum()),
        "max_dd_r": dd,
        "hold_h": hold_hours,
        "sharpe": 0.0 if sd == 0 else float(r.mean() / sd * np.sqrt(365 * len(r) / span)),
        "r_per_day": rpd,
        "est_days": float("inf") if rpd <= 0 else dd / rpd,
    }
