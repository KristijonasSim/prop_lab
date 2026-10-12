"""KRIS TAB #2 - FADE THE CROWD ON GOLD. Rules locked 2026-10-12 before the
run, approved by Kris ("run it please").

MECHANISM. Bybit's gold traders are mostly small leveraged crypto accounts.
When the share of accounts long is unusually high for the last 30 days AND
fresh positions have piled in, a small move against them hits stops and forced
closes, which push price further against them. We stand on the other side of
those forced exits. Long is the mirror.

RULES (no tuning after the run):
  crowd    long_share used ONE HOUR LATE (stamp <= decision - 1h).
           cz = z of long_share over the trailing 720 hours.
           oz = z of the 24h % change in open interest over the trailing 720h.
  short    cz >= +Z and oz >= 1.      long   cz <= -Z and oz >= 1.
  entry    next hourly open. stop 2 x ATR14 of COMPLETED 4h bars. target 2R.
           close after 48h. one trade at a time. no entries Fri 21:00-Sun
           22:00 UTC, open trades closed Fri 21:00. exits on 1m bars.
  markets  PAXGUSDT 2023-10 -> now (main, 10 bps rt), XAUUSDT 7 months
           (second check, 5.5 bps rt, a different crowd: corr 0.04).
  versions base Z=2 with OI · loose Z=1.5 with OI · crowd-only Z=2, no OI.
  LUCK     200 seeds, random trades on the same side at the same hour of day,
           same stops/targets - gold's uptrend is in the null too.
  BAR      PF@2x >= 1.3, beats luck, both halves > 0, >= 100 trades, < 30 days.

    .venv/bin/python strategies/kris/crowd.py
"""
from __future__ import annotations

import json
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).parent))

import absorption as A                                                # noqa: E402
from core import bybit_crowd, bybit_tape                              # noqa: E402
from factory import book5                                             # noqa: E402

OUT = ROOT / "backtests" / "kris"
MARKETS = {"PAXGUSDT": (10.0, "2023-10-01", "2025-04-01"),
           "XAUUSDT": (5.5, "2026-03-09", "2026-07-10")}
VERSIONS = {"base": (2.0, True), "loose": (1.5, True), "crowd_only": (2.0, False)}
WIN, STOP_ATR, K, HOLD_H, SEEDS = 720, 2.0, 2.0, 48, 200


def features(sym: str, m1: pd.DataFrame) -> pd.DataFrame:
    h = m1.resample("1h", label="left", closed="left").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last"}).dropna()
    c = bybit_crowd.load(sym).reindex(h.index).ffill()
    # ONE HOUR LATE: bar labelled L closes at L+1h; use the stamp L-1h.
    ls = c.long_share.shift(1)
    oi = c.oi.shift(1)
    roll = ls.rolling(WIN)
    h["cz"] = (ls - roll.mean()) / roll.std()
    oc = oi / oi.shift(24) - 1
    r2 = oc.rolling(WIN)
    h["oz"] = (oc - r2.mean()) / r2.std()
    # ATR14 of COMPLETED 4h bars, as of each hourly bar's close.
    b4 = m1.resample("4h", label="left", closed="left").agg(
        {"high": "max", "low": "min", "close": "last"}).dropna()
    pc = b4.close.shift(1)
    tr = np.maximum(b4.high - b4.low, np.maximum((b4.high - pc).abs(), (b4.low - pc).abs()))
    atr = tr.rolling(14).mean()
    atr.index = atr.index + pd.Timedelta("4h")                # known at completion
    done = pd.DataFrame({"t": h.index + pd.Timedelta("1h")})
    h["atr4"] = pd.merge_asof(done, atr.rename("a").reset_index().rename(columns={atr.index.name or "index": "t"})
                              .sort_values("t"), on="t", direction="backward")["a"].values
    return h


def trade(tp: A.Tape, h: pd.DataFrame, i: int, side: int):
    if i + 1 >= len(h):
        return None
    t_in = h.index[i] + pd.Timedelta("1h")
    i0 = tp.ix.searchsorted(t_in)
    i1 = tp.ix.searchsorted(t_in + pd.Timedelta(hours=HOLD_H)) - 1
    if i0 >= len(tp.ix) or i1 < i0 or tp.cut[i0]:
        return None
    entry, a = tp.o[i0], h.atr4.iat[i]
    if not np.isfinite(a) or a <= 0:
        return None
    risk = STOP_ATR * a
    stop, tgt = entry - side * risk, entry + side * K * risk
    px, j = A.walk(tp.o, tp.h, tp.l, tp.c, tp.cut, i0, i1, side, stop, tgt)
    return tp.ix[i0], tp.ix[j], (px - entry) * side / risk, entry * A.COST_BPS / 1e4 / risk


def eligible(h: pd.DataFrame) -> np.ndarray:
    return (h.atr4.notna() & h.cz.notna() & ~A.closed(h.index + pd.Timedelta("1h"))).values


def run_cell(tp, h, side, z, use_oi):
    ok = eligible(h) & ((h.cz >= z) if side < 0 else (h.cz <= -z)).values
    if use_oi:
        ok &= (h.oz >= 1).values
    rows, busy = [], None
    for i in np.flatnonzero(ok):
        if busy is not None and h.index[i] + pd.Timedelta("1h") <= busy:
            continue
        r = trade(tp, h, i, side)
        if r is None:
            continue
        rows.append((*r, i))
        busy = r[1]
    return pd.DataFrame(rows, columns=["t_in", "t", "g", "cpr", "i"])


def null(tp, h, df, side, rng) -> np.ndarray:
    if df.empty:
        return np.full(SEEDS, np.nan)
    el = np.flatnonzero(eligible(h)[:-1])
    by_hour = {k: el[h.index[el].hour == k] for k in range(24)}
    hours = h.index[df.i.values].hour
    out = np.empty(SEEDS)
    for s in range(SEEDS):
        rs = [r[2] - 2 * r[3] for r in (trade(tp, h, int(rng.choice(by_hour[k])), side)
                                         for k in hours) if r]
        out[s] = np.mean(rs) if rs else np.nan
    return out


def main() -> int:
    rng = np.random.default_rng(20261012)
    cells, nulls = [], {}
    for sym, (cost, start, mid) in MARKETS.items():
        A.COST_BPS = cost
        m1 = bybit_tape.load(sym)
        m1 = m1[m1.index >= start]
        tp = A.Tape(m1)
        h = features(sym, m1)
        for vname, (z, use_oi) in VERSIONS.items():
            for side, sname in ((-1, "short"), (1, "long")):
                df = run_cell(tp, h, side, z, use_oi)
                key = f"{sym} {sname} {vname}"
                nm = null(tp, h, df, side, rng)
                nulls[key] = nm
                s2 = A.stats(df, 2)
                real = s2.get("mean_r", np.nan)
                m = pd.Timestamp(mid, tz="UTC")
                halves = [A.stats(df[df.t_in < m], 2).get("mean_r"), A.stats(df[df.t_in >= m], 2).get("mean_r")]
                pace = book5.pace(pd.DataFrame({"t": df.t, "r": df.g - 2 * df.cpr}), band=False) if len(df) >= 10 else {}
                cell = {"cell": key, "x1": A.stats(df, 1), "x2": s2, "x3": A.stats(df, 3),
                        "gross_r": round(df.g.mean(), 3) if len(df) else None, "halves": halves,
                        "p": round(float(np.mean(nm >= real)), 3) if len(df) else None,
                        "null_mean": round(float(np.nanmean(nm)), 3) if len(df) else None, "pace": pace}
                cells.append(cell)
                print(f"{key:28} n {s2.get('n',0):4} tpd {s2.get('tpd')}  PF 1x/2x/3x {cell['x1'].get('pf')}/"
                      f"{s2.get('pf')}/{cell['x3'].get('pf')}  gross {cell['gross_r']}  R2x {real}  "
                      f"null {cell['null_mean']}  p {cell['p']}  halves {halves}  "
                      f"pace {pace.get('days')}d {pace.get('pass_pct')}% {pace.get('accounts')}acc  "
                      f"win {s2.get('win')} dd {s2.get('dd_r')} hold {s2.get('hold_h')}h", flush=True)
    ok = [c for c in cells if c["x2"].get("n", 0) >= 10]
    real_best = max(c["x2"]["mean_r"] for c in ok) if ok else None
    best_null = np.nanmax(np.vstack(list(nulls.values())), axis=0)
    p_grid = float(np.mean(best_null >= real_best)) if ok else None
    (OUT / "crowd.json").write_text(json.dumps(
        {"cells": cells, "best_of_grid": {"real": real_best, "p": p_grid}}, indent=1, default=str))
    print(f"\nbest of {len(cells)} R@2x {real_best}  p {p_grid}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
