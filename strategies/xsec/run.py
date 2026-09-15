"""H-042 — the crowd ratio, cross-sectional and dollar-neutral. Pre-reg: XSEC.md.

Rank eleven coins against each other on the Binance crowd long/short ACCOUNT
ratio, long the least crowded and short the most, equal dollars each side.
H-006 established the signal ranks forward returns monotonically and beats every
block-shuffle null; it died on risk shape, because a time-series reading of a
level says "short" on ten coins at once and that is one levered short on crypto
beta. Ranking the coins against each other removes that beta by construction.

NO CELL IS SELECTED HERE. The twelve cells in the pre-registration are all
reported, with their nulls and controls, and the five pass conditions are scored
as written.

Run: .venv/bin/python strategies/xsec/run.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from core.prop_rules import best_day_share                          # noqa: E402
from strategies.xsec.book import (cost_of, period_return,           # noqa: E402
                                  turnover, weights_from_ranks)

FEEDS = ROOT / "data" / "feeds"
COINS = ["ADAUSDT", "AVAXUSDT", "BNBUSDT", "BTCUSDT", "DOGEUSDT", "DOTUSDT",
         "ETHUSDT", "LINKUSDT", "LTCUSDT", "SOLUSDT", "XRPUSDT"]
CROWD = "count_long_short_ratio"
END = pd.Timestamp("2026-08-31", tz="UTC")
YEARS = 3
BAR_MIN = 5
HOLDS_H = (4, 12, 24)          # pre-registered
KS = (2, 3)                    # pre-registered
WINS = (288, 2016)             # pre-registered: 1 day, 1 week in 5m bars
SEEDS = 25
BLOCK = 288                    # block-shuffle length, one day, as in H-006


def panels() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Aligned open-price and crowd-z panels on one 5-minute index."""
    op, cr = {}, {}
    for c in COINS:
        px = pd.read_parquet(FEEDS / f"{c}_perp_5m.parquet", columns=["open"])
        mx = pd.read_parquet(FEEDS / f"{c}_metrics_5m.parquet", columns=[CROWD])
        j = px.join(mx, how="inner").sort_index()
        j = j[~j.index.duplicated(keep="last")]
        op[c], cr[c] = j["open"], j[CROWD]
    O = pd.DataFrame(op).sort_index()
    C = pd.DataFrame(cr).sort_index()
    start = END - pd.DateOffset(years=YEARS)
    O, C = O.loc[start:END], C.loc[start:END]
    return O, C


def zscore(C: pd.DataFrame, win: int) -> pd.DataFrame:
    """Rolling z per coin. The baseline is shifted so the current bar is never
    in its own mean - the same convention as `orderflow._z`."""
    m = C.rolling(win, min_periods=win // 2).mean().shift(1)
    v = C.rolling(win, min_periods=win // 2).std(ddof=0).shift(1)
    return (C - m) / v.replace(0.0, np.nan)


def block_shuffle_panel(Z: pd.DataFrame, seed: int) -> pd.DataFrame:
    """Each coin's z-series cut into day-long blocks and reordered.

    Per coin and independently, so the cross-section is destroyed while each
    coin's own autocorrelation survives - the null H-006 was measured against.
    """
    rng = np.random.default_rng(seed)
    out = {}
    for c in Z.columns:
        v = Z[c].values
        nb = len(v) // BLOCK
        head = v[:nb * BLOCK].reshape(nb, BLOCK)
        idx = rng.permutation(nb)
        out[c] = np.concatenate([head[idx].ravel(), v[nb * BLOCK:]])
    return pd.DataFrame(out, index=Z.index)


def simulate(O: pd.DataFrame, Z: pd.DataFrame, hold_h: int, k: int,
             rank_rng=None) -> dict:
    """One cell. Decide on bar i, fill at bar i+1's OPEN, exit `hold_h` later.

    `rank_rng` replaces the signal ranking with a random one of the same shape -
    the control that separates "the ranking is informative" from "rebalancing a
    neutral crypto book makes money".
    """
    step = hold_h * 60 // BAR_MIN
    idx = np.arange(0, len(O) - step - 1, step)
    if len(idx) < 30:
        return {}
    prev = pd.Series(0.0, index=O.columns)
    rows, turns = [], []
    for i in idx:
        z = Z.iloc[i]
        if rank_rng is not None:
            z = pd.Series(rank_rng.permutation(z.values), index=z.index)
        w = weights_from_ranks(z, k)
        # fill at the NEXT bar's open, exit at the open `step` bars later
        p0, p1 = O.iloc[i + 1], O.iloc[i + 1 + step]
        rets = (p1 / p0 - 1.0).replace([np.inf, -np.inf], np.nan)
        t = turnover(prev, w)
        rows.append({"ts": O.index[i + 1 + step],
                     "gross": period_return(w, rets), "turn": t})
        turns.append(t)
        prev = w
    df = pd.DataFrame(rows).set_index("ts")
    out = {"periods": int(len(df)), "hold_h": hold_h, "k": k,
           "turn_per_period": round(float(np.mean(turns)), 3),
           "gross_bps": round(float(df.gross.mean()) * 1e4, 2)}
    for mult in (0, 1, 2, 3):
        net = df.gross - df.turn.map(lambda t: cost_of(t, mult))
        pos, neg = net[net > 0].sum(), -net[net < 0].sum()
        out[f"bps_{mult}x"] = round(float(net.mean()) * 1e4, 2)
        out[f"pf_{mult}x"] = round(float(pos / neg), 3) if neg > 0 else None
        if mult == 2:
            out["_net2x"] = net
    return out


def quantile_monotone(O: pd.DataFrame, Z: pd.DataFrame, hold_h: int,
                      buckets: int = 5) -> list:
    """Mean forward return by signal bucket. A ranking signal must RANK."""
    step = hold_h * 60 // BAR_MIN
    idx = np.arange(0, len(O) - step - 1, step)
    acc = [[] for _ in range(buckets)]
    for i in idx:
        z = Z.iloc[i].dropna()
        if len(z) < buckets:
            continue
        p0, p1 = O.iloc[i + 1], O.iloc[i + 1 + step]
        r = (p1 / p0 - 1.0)
        order = z.sort_values().index
        parts = np.array_split(np.arange(len(order)), buckets)
        for b, part in enumerate(parts):
            acc[b].extend(r[order[part]].dropna().tolist())
    return [round(float(np.mean(a)) * 1e4, 2) if a else None for a in acc]


def main() -> int:
    O, C = panels()
    print(f"{len(COINS)} coins, {O.index[0].date()} -> {O.index[-1].date()}, "
          f"{len(O):,} 5m bars\n")

    zs = {w: zscore(C, w) for w in WINS}

    print("MONOTONICITY - mean forward return by crowd bucket, bps "
          "(least crowded -> most)\n")
    mono = {}
    for w in WINS:
        for h in HOLDS_H:
            q = quantile_monotone(O, zs[w], h)
            mono[f"win{w}|h{h}"] = q
            ok = all(q[i] is not None for i in range(len(q))) and q[0] > q[-1]
            print(f"  win {w:>4}  hold {h:>2}h   " +
                  "  ".join(f"{x:+7.2f}" if x is not None else "   n/a" for x in q) +
                  f"   spread {q[0]-q[-1]:+7.2f}  {'ordered' if ok else ''}",
                  flush=True)

    print("\nTHE TWELVE CELLS\n")
    hdr = (f"{'cell':22}{'per':>6}{'turn':>7}{'gross':>8}{'1x':>8}{'2x':>8}"
           f"{'3x':>8}{'PF2x':>7}{'null2x p10-p90':>18}{'ctrl2x':>9}")
    print(hdr); print("-" * len(hdr))
    rows = []
    for w in WINS:
        Z = zs[w]
        for h in HOLDS_H:
            for k in KS:
                r = simulate(O, Z, h, k)
                if not r:
                    continue
                net2x = r.pop("_net2x")
                nulls = []
                for s in range(SEEDS):
                    rn = simulate(O, block_shuffle_panel(Z, s), h, k)
                    if rn:
                        rn.pop("_net2x", None)
                        nulls.append(rn["bps_2x"])
                ctrls = []
                for s in range(SEEDS):
                    rc = simulate(O, Z, h, k, rank_rng=np.random.default_rng(1000 + s))
                    if rc:
                        rc.pop("_net2x", None)
                        ctrls.append(rc["bps_2x"])
                daily = net2x.resample("1D").sum()
                yrs = net2x.groupby(net2x.index.year).sum()
                r.update({"win": w,
                          "null_p10": round(float(np.percentile(nulls, 10)), 2),
                          "null_med": round(float(np.median(nulls)), 2),
                          "null_p90": round(float(np.percentile(nulls, 90)), 2),
                          "ctrl_med": round(float(np.median(ctrls)), 2),
                          "year_bps": {int(y): round(float(v) * 1e4, 1)
                                       for y, v in yrs.items()},
                          "same_sign_all_years": bool(
                              len(set(np.sign(yrs.values))) == 1),
                          "best_day": best_day_share(daily, 1.0, 30)})
                rows.append(r)
                tag = f"w{w} h{h}h k{k}"
                nullrange = f"{r['null_p10']:+.1f} to {r['null_p90']:+.1f}"
                print(f"{tag:22}{r['periods']:>6}{r['turn_per_period']:>7.2f}"
                      f"{r['gross_bps']:>8.2f}{r['bps_1x']:>8.2f}"
                      f"{r['bps_2x']:>8.2f}{r['bps_3x']:>8.2f}"
                      f"{(r['pf_2x'] or 0):>7.3f}{nullrange:>18}"
                      f"{r['ctrl_med']:>9.2f}", flush=True)

    dest = ROOT / "backtests" / "xsec"
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "h042.json").write_text(json.dumps(
        {"coins": COINS, "monotone": mono, "cells": rows}, indent=1, default=str))
    print(f"\nwrote backtests/xsec/h042.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
