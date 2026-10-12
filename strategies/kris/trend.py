"""KRIS TAB #7 - SIMPLE TREND-FOLLOWING SWING TRADING: ONE ENTRY, SIX EXITS.
Kris 2026-10-12 (/goal): *"trend following swing trading, make it super simple
everything here depends not on entry rules but exit rules i think"*.

MECHANISM. Trends persist longer than a random walk because information and
positioning arrive slowly (CTA literature, time-series momentum). A trend
follower loses small and often and is paid by a few long runs, so HOW the
trade is closed decides whether the long runs are kept.

RULES (fixed before the run):
  entry  ONE rule for everything: close above the highest high of the prior
         20 bars -> long at the next open; below the lowest low -> short.
         One position at a time per market. ATR14 at the signal bar.
  exits  X1 fixed 2R           stop 2 ATR, target 4 ATR
         X2 turtle             stop 2 ATR, out when close breaks the 10-bar
                               low (long) / high (short), next open
         X3 ATR trail          stop 3 ATR, trailed 3 ATR behind the best close
         X4 time 20 bars       stop 2 ATR, out at the 20th bar's close
         X5 EMA20 close        stop 2 ATR, out when close crosses EMA20 back
         X6 breakeven + trail  stop 2 ATR; at +1R the stop goes to entry,
                               then trails 3 ATR behind the best close
         every trade is closed after 200 bars at most. Stops are checked on
         the bar's high/low, stop first; a gap through the stop fills at the
         open. Trailing stops move on the CLOSE, used from the next bar.
  data   4h and daily (UTC days from 4h). XAUUSD XAGUSD EURUSD GBPUSD USDJPY
         Dukascopy 5-year caches 2021-09 -> 2026-08; BTCUSDT Binance perp, same
         window; NAS100 3 years only (no 5-year cache) - said in every row.
  costs  core/markets taker round trip per market, x1/2/3.
  TESTS  (1) does the ENTRY matter: the same exit on random entries (same
             count, coin-flip side), 200 seeds -> p.
         (2) does the EXIT matter (Kris's claim): the six exits compared on
             the real entries AND on random entries.
         (3) the 7-market BOOK per exit and timeframe, pace at 2% risk.

    .venv/bin/python strategies/kris/trend.py
"""
from __future__ import annotations

import json
import sys
import warnings
from pathlib import Path

import numba
import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import core.markets as M                                              # noqa: E402
from factory import book5                                             # noqa: E402

OUT = ROOT / "backtests" / "kris"
START, END = "2021-09-01", "2026-08-25"
SYMS = ["XAUUSD", "XAGUSD", "EURUSD", "GBPUSD", "USDJPY", "BTCUSDT", "NAS100"]
EXITS = {1: "X1 fixed 2R", 2: "X2 turtle 10-bar", 3: "X3 ATR trail 3", 4: "X4 time 20 bars",
         5: "X5 EMA20 close", 6: "X6 breakeven + trail"}
N_ENTRY, N_EXIT, MAX_HOLD, SEEDS = 20, 10, 200, 200
MID = pd.Timestamp("2024-03-01", tz="UTC")


def load(sym: str, tf: str) -> pd.DataFrame:
    if sym == "BTCUSDT":
        d = pd.read_parquet(ROOT / "data" / "feeds" / "BTCUSDT_perp_5m.parquet")
        if d.index.tz is None:
            d.index = d.index.tz_localize("UTC")
        d = d.resample("4h").agg({"open": "first", "high": "max", "low": "min",
                                  "close": "last", "volume": "sum"}).dropna()
    elif sym == "NAS100":
        d = pd.read_parquet(ROOT / "data" / "NAS100_dukascopy_4h.parquet")
    else:
        d = pd.read_parquet(ROOT / "data" / f"{sym}_dukascopy5y_4h.parquet")
    d = d[(d.index >= START) & (d.index <= END)]
    if "volume" in d:
        d = d[d.volume > 0]                       # never decide or fill on a dead bar
    if tf == "1d":
        d = d.resample("1D").agg({"open": "first", "high": "max", "low": "min",
                                  "close": "last"}).dropna()
    return d[["open", "high", "low", "close"]]


def prep(d: pd.DataFrame) -> dict:
    h, l, c = d.high, d.low, d.close
    pc = c.shift(1)
    tr = np.maximum(h - l, np.maximum((h - pc).abs(), (l - pc).abs()))
    return {"o": d.open.values, "h": h.values, "l": l.values, "c": c.values,
            "atr": tr.rolling(14).mean().values,
            "hh": h.shift(1).rolling(N_ENTRY).max().values, "ll": l.shift(1).rolling(N_ENTRY).min().values,
            "xh": h.rolling(N_EXIT).max().values, "xl": l.rolling(N_EXIT).min().values,
            "ema": c.ewm(span=20, adjust=False).mean().values}


@numba.njit(cache=True)
def walk(o, h, l, c, atr, xh, xl, ema, i, side, mode):
    """Signal on bar i's close, fill at o[i+1]. Returns (R, exit bar)."""
    n = len(o)
    k = i + 1
    if k >= n:
        return np.nan, -1
    a = atr[i]
    entry = o[k]
    m = 3.0 if mode == 3 else 2.0
    risk = m * a
    stop = entry - side * risk
    tgt = entry + side * 2.0 * risk
    best = entry
    be = False
    for j in range(k, min(n, k + MAX_HOLD)):
        # stop (and target) on this bar's range
        if side > 0:
            if l[j] <= stop:
                return (min(stop, o[j]) - entry) / risk, j
            if mode == 1 and h[j] >= tgt:
                return (tgt - entry) / risk, j
        else:
            if h[j] >= stop:
                return (entry - max(stop, o[j])) / risk, j
            if mode == 1 and l[j] <= tgt:
                return (entry - tgt) / risk, j
        # close-based exits, filled at the next open
        out = False
        if mode == 2:
            out = (c[j] <= xl[j - 1]) if side > 0 else (c[j] >= xh[j - 1])
        elif mode == 4:
            out = j - k + 1 >= 20
        elif mode == 5:
            out = (c[j] < ema[j]) if side > 0 else (c[j] > ema[j])
        if out:
            px = o[j + 1] if (j + 1 < n and mode != 4) else c[j]
            return (px - entry) * side / risk, j
        # trailing, on the close, effective from the next bar
        if side > 0:
            best = max(best, c[j])
        else:
            best = min(best, c[j])
        if mode == 6 and not be and (best - entry) * side >= risk:
            be = True
            stop = entry
        if mode == 3 or (mode == 6 and be):
            trail = best - side * 3.0 * atr[j]
            stop = max(stop, trail) if side > 0 else min(stop, trail)
    j = min(n, k + MAX_HOLD) - 1
    return (c[j] - entry) * side / risk, j


def run(P, mode, entries, sides):
    rows, busy = [], -1
    for i, s in zip(entries, sides):
        if i <= busy:
            continue
        r, j = walk(P["o"], P["h"], P["l"], P["c"], P["atr"], P["xh"], P["xl"], P["ema"], i, s, mode)
        if j < 0 or not np.isfinite(r):
            continue
        rows.append((i, j, s, r))
        busy = j
    return rows


def real_entries(P):
    c, hh, ll, a = P["c"], P["hh"], P["ll"], P["atr"]
    ok = np.isfinite(hh) & np.isfinite(a) & (a > 0)
    sig = np.where(ok & (c > hh), 1, np.where(ok & (c < ll), -1, 0))
    idx = np.flatnonzero(sig)
    return idx, sig[idx]


def stats(r, t_in, t_out):
    if len(r) == 0:
        return {"n": 0}
    win, loss = r[r > 0].sum(), -r[r <= 0].sum()
    eq = np.cumsum(r)
    span = max((t_out.max() - t_in.min()).days, 1)
    return {"n": int(len(r)), "pf": round(float(win / loss), 3) if loss > 0 else None,
            "mean_r": round(float(r.mean()), 3), "win": round(float((r > 0).mean() * 100), 1),
            "dd_r": round(float((eq - np.maximum.accumulate(eq)).min()), 2),
            "tpd": round(len(r) / span * 7 / 5, 3),
            "hold_d": round(float(np.mean((t_out - t_in).total_seconds()) / 86400), 1)}


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(20261012)
    cells, book = [], {}
    for tf in ("4h", "1d"):
        for sym in SYMS:
            d = load(sym, tf)
            P = prep(d)
            rt = M.COSTS[sym].round_trip("taker")
            idx, sd = real_entries(P)
            elig = np.flatnonzero(np.isfinite(P["atr"]) & (P["atr"] > 0) & np.isfinite(P["hh"]))[:-1]
            for mode, name in EXITS.items():
                rows = run(P, mode, idx, sd)
                if len(rows) < 5:
                    continue
                i_, j_, s_, g = (np.array(x) for x in zip(*rows))
                atr_i = P["atr"][i_]
                m = 3.0 if mode == 3 else 2.0
                cpr = P["o"][i_ + 1] / (m * atr_i) * rt / 1e4
                t_in, t_out = d.index[i_ + 1], d.index[j_]
                r2 = g - 2 * cpr
                # random entries, same count, coin-flip side, same exit
                nm = np.empty(SEEDS)
                for s in range(SEEDS):
                    pick = np.sort(rng.choice(elig, size=len(rows) * 3, replace=False))
                    rr = run(P, mode, pick, rng.choice([-1, 1], size=len(pick)))[:len(rows)]
                    gi = np.array([x[3] for x in rr])
                    ci = np.array([P["o"][x[0] + 1] / (m * P["atr"][x[0]]) for x in rr]) * rt / 1e4
                    nm[s] = (gi - 2 * ci).mean() if len(rr) else np.nan
                h1 = t_in < MID
                cell = {"cell": f"{sym} {tf} {name}", "sym": sym, "tf": tf, "exit": name,
                        "x0": stats(g, t_in, t_out), "x1": stats(g - cpr, t_in, t_out),
                        "x2": stats(r2, t_in, t_out), "x3": stats(g - 3 * cpr, t_in, t_out),
                        "fee_r": round(float(cpr.mean()), 3),
                        "halves": [round(float(r2[h1].mean()), 3) if h1.any() else None,
                                   round(float(r2[~h1].mean()), 3) if (~h1).any() else None],
                        "random_mean_r2x": round(float(np.nanmean(nm)), 3),
                        "p": round(float(np.nanmean(nm >= r2.mean())), 3),
                        "short_years": sym == "NAS100"}
                cells.append(cell)
                book.setdefault((tf, name), []).append(pd.DataFrame({"t": t_out, "r": r2}))
                x0, x2 = cell["x0"], cell["x2"]
                print(f"{cell['cell']:36} n {x2['n']:4} tpd {x2['tpd']:5}  win {x0['win']:4}  hold {x0['hold_d']:5}d  "
                      f"PF 0x/2x {x0['pf']}/{x2['pf']}  R2x {x2['mean_r']:+.3f}  random {cell['random_mean_r2x']:+.3f}  "
                      f"p {cell['p']}  halves {cell['halves']}", flush=True)
    print("\nBOOKS - all seven markets, one exit, one timeframe")
    books = []
    for (tf, name), parts in book.items():
        df = pd.concat(parts).sort_values("t")
        r = df.r.values
        pace = book5.pace(df, band=False)
        b = {"tf": tf, "exit": name, "n": len(r), "pf2x": round(float(r[r > 0].sum() / -r[r <= 0].sum()), 3),
             "mean_r2x": round(float(r.mean()), 3), "pace": pace}
        books.append(b)
        print(f"{tf} {name:22} n {len(r):4}  PF@2x {b['pf2x']}  R2x {b['mean_r2x']:+.3f}  "
              f"pace {pace.get('days')}d {pace.get('pass_pct')}% {pace.get('accounts')}acc tpd {pace.get('tpd')}")
    (OUT / "trend.json").write_text(json.dumps({"cells": cells, "books": books}, indent=1, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
