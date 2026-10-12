"""KRIS TAB #1 - ABSORPTION ON THE BYBIT GOLD TAPE. Rules locked 2026-10-12
before the run, approved by Kris ("run").

MECHANISM. Sellers hit the bid far harder than usual and price still closes in
the top half of the bar: a passive buyer with size absorbed every market sell.
When the aggressors are done, the absorber is still there and price lifts.
Short is the mirror. The other side is the aggressor with a deadline.

RULES (no tuning after the run):
  long   delta z <= -Z (sell pressure, trailing 100 bars) and rvol >= 1.5
         (trailing 20) and close in the top half of the bar. Short = mirror.
  entry  next bar's open. stop = signal bar low - 0.25 ATR14 (short: high +).
  target K x risk. time exit after 12 bars. One trade at a time per cell.
  weekend: no entries Fri 21:00 - Sun 22:00 UTC, open trades closed at Fri 21:00.
  exits walked on 1-minute bars; stop first if both hit in one minute; a stop
  gapped through fills at the minute's open.
  costs 5.5 bps round trip at 1x / 2x / 3x.
  grid  TF 15m 30m 1h 4h x side x {base Z2 K2, strict Z2.5 K2, target Z2 K3}.
  LUCK  200 seeds: same count of random bars at the same hour of day, same
        side, same exits. Per-cell p and best-of-grid p on mean R at 2x.
  CONTROL the same rule without the delta condition.
  BAR   pass: PF@2x >= 1.3, beats luck, both halves positive, >= 100 trades,
        < 30 days at 2%.  keeper: PF@2x >= 1.6, <= 14 days, <= 1.5 accounts.

    .venv/bin/python strategies/kris/absorption.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numba
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from core import bybit_tape                                           # noqa: E402
from factory import book5                                             # noqa: E402

OUT = ROOT / "backtests" / "kris"
COST_BPS = 5.5
TFS = {"15m": "15min", "30m": "30min", "1h": "1h", "4h": "4h"}
VARIANTS = {"base": (2.0, 2.0), "strict": (2.5, 2.0), "target3": (2.0, 3.0)}
HOLD, STOP_ATR, RVOL, ZWIN, VWIN = 12, 0.25, 1.5, 100, 20
SEEDS = 200
MID = pd.Timestamp("2026-07-10", tz="UTC")


def closed(ts: pd.DatetimeIndex) -> np.ndarray:
    """Gold CFD closed: Fri 21:00 -> Sun 22:00 UTC, and all of Saturday."""
    d, h = ts.dayofweek, ts.hour
    return ((d == 4) & (h >= 21)) | (d == 5) | ((d == 6) & (h < 22))


def bars(m1: pd.DataFrame, rule: str) -> pd.DataFrame:
    b = m1.resample(rule, label="left", closed="left").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last",
         "buy_vol": "sum", "sell_vol": "sum"}).dropna(subset=["open"])
    b["vol"] = b.buy_vol + b.sell_vol
    b["delta"] = b.buy_vol - b.sell_vol
    prior = b.delta.shift(1).rolling(ZWIN)
    b["z"] = (b.delta - prior.mean()) / prior.std()
    b["rvol"] = b.vol / b.vol.shift(1).rolling(VWIN).mean()
    rng = (b.high - b.low).replace(0, np.nan)
    b["pos"] = (b.close - b.low) / rng
    pc = b.close.shift(1)
    tr = np.maximum(b.high - b.low, np.maximum((b.high - pc).abs(), (b.low - pc).abs()))
    b["atr"] = tr.rolling(14).mean()
    return b


@numba.njit(cache=True)
def walk(o, h, l, c, cut, i0, i_end, side, stop, tgt):
    """Walk 1m bars from i0 to i_end inclusive. Returns (exit_px, exit_idx)."""
    for j in range(i0, i_end + 1):
        if cut[j]:                               # weekend cut: out at last close
            return c[j - 1] if j > i0 else o[j], j
        if side > 0:
            if l[j] <= stop:
                return min(stop, o[j]), j
            if h[j] >= tgt:
                return tgt, j
        else:
            if h[j] >= stop:
                return max(stop, o[j]), j
            if l[j] <= tgt:
                return tgt, j
    return c[i_end], i_end


class Tape:
    def __init__(self, m1: pd.DataFrame):
        self.ix = m1.index
        self.o, self.h = m1.open.values, m1.high.values
        self.l, self.c = m1.low.values, m1.close.values
        self.cut = closed(m1.index)


def trade(tp: Tape, b: pd.DataFrame, i: int, side: int, k: float, tf_rule: str):
    """Trade signal bar i. Returns (entry_t, exit_t, R gross, cost per R) or None."""
    if i + 1 >= len(b):
        return None
    t_in = b.index[i + 1]
    t_end = t_in + pd.Timedelta(tf_rule) * HOLD
    i0 = tp.ix.searchsorted(t_in)
    i1 = tp.ix.searchsorted(t_end) - 1
    if i0 >= len(tp.ix) or i1 < i0 or tp.cut[i0]:
        return None
    entry = tp.o[i0]
    a = b.atr.iat[i]
    stop = b.low.iat[i] - STOP_ATR * a if side > 0 else b.high.iat[i] + STOP_ATR * a
    risk = (entry - stop) * side
    if not np.isfinite(risk) or risk <= 0:
        return None
    tgt = entry + side * k * risk
    px, j = walk(tp.o, tp.h, tp.l, tp.c, tp.cut, i0, i1, side, stop, tgt)
    return tp.ix[i0], tp.ix[j], (px - entry) * side / risk, entry * COST_BPS / 1e4 / risk


def signals(b: pd.DataFrame, side: int, z: float, flow: bool = True) -> np.ndarray:
    ok = (b.rvol >= RVOL) & b.atr.notna() & ~closed(b.index)
    ok &= (b.pos >= 0.5) if side > 0 else (b.pos <= 0.5)
    if flow:
        ok &= (b.z <= -z) if side > 0 else (b.z >= z)
    else:
        ok &= b.z.notna()
    return np.flatnonzero(ok.values)


def run_cell(tp, b, rule, side, z, k, flow=True):
    rows, busy = [], None
    for i in signals(b, side, z, flow):
        if busy is not None and b.index[i + 1 if i + 1 < len(b) else i] <= busy:
            continue
        r = trade(tp, b, i, side, k, rule)
        if r is None:
            continue
        rows.append((*r, i))
        busy = r[1]
    return pd.DataFrame(rows, columns=["t_in", "t", "g", "cpr", "i"])


def stats(df: pd.DataFrame, mult: float) -> dict:
    if df.empty:
        return {"n": 0}
    r = df.g - mult * df.cpr
    win, loss = r[r > 0].sum(), -r[r <= 0].sum()
    eq = r.cumsum()
    days = max((df.t.max() - df.t_in.min()).days, 1)
    daily = pd.Series(r.values, index=pd.DatetimeIndex(df.t)).resample("1D").sum()
    return {"n": len(r), "pf": round(win / loss, 3) if loss > 0 else None,
            "mean_r": round(r.mean(), 3), "win": round((r > 0).mean() * 100, 1),
            "dd_r": round((eq - eq.cummax()).min(), 2),
            "tpd": round(len(r) / days * 7 / 5, 2),
            "hold_h": round((df.t - df.t_in).dt.total_seconds().mean() / 3600, 1),
            "sharpe": round(daily.mean() / daily.std() * np.sqrt(252), 2) if daily.std() > 0 else None}


def null_means(tp, b, rule, df, side, k, rng) -> np.ndarray:
    """Same count, same hours of day, random eligible bars; mean R at 2x."""
    if df.empty:
        return np.full(SEEDS, np.nan)
    elig = np.flatnonzero((b.atr.notna() & ~closed(b.index)).values[:-1])
    by_hour = {h: elig[b.index[elig].hour == h] for h in range(24)}
    hours = b.index[df.i.values].hour
    out = np.empty(SEEDS)
    for s in range(SEEDS):
        rs = []
        for h in hours:
            pool = by_hour[h]
            r = trade(tp, b, int(rng.choice(pool)), side, k, rule)
            if r is not None:
                rs.append(r[2] - 2 * r[3])
        out[s] = np.mean(rs) if rs else np.nan
    return out


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    m1 = bybit_tape.load()
    tp = Tape(m1)
    rng = np.random.default_rng(20261012)
    cells, nulls = [], {}
    for tf, rule in TFS.items():
        b = bars(m1, rule)
        for side, sname in ((1, "long"), (-1, "short")):
            ctrl = run_cell(tp, b, rule, side, 0, VARIANTS["base"][1], flow=False)
            for vname, (z, k) in VARIANTS.items():
                df = run_cell(tp, b, rule, side, z, k)
                key = f"{tf} {sname} {vname}"
                nm = null_means(tp, b, rule, df, side, k, rng)
                nulls[key] = nm
                s2 = stats(df, 2)
                real = s2.get("mean_r", np.nan)
                halves = [stats(df[df.t_in < MID], 2).get("mean_r"),
                          stats(df[df.t_in >= MID], 2).get("mean_r")]
                pace = book5.pace(pd.DataFrame({"t": df.t, "r": df.g - 2 * df.cpr})) if len(df) >= 10 else {}
                cell = {"cell": key, "x1": stats(df, 1), "x2": s2, "x3": stats(df, 3),
                        "halves": halves,
                        "p": round(float(np.mean(nm >= real)), 3) if len(df) else None,
                        "null_p95": round(float(np.nanpercentile(nm, 95)), 3) if len(df) else None,
                        "control_x2": stats(ctrl, 2) if vname == "base" else None,
                        "pace": pace}
                cells.append(cell)
                print(f"{key:22} n {s2.get('n',0):4}  PF2x {s2.get('pf')}  meanR {real}  "
                      f"p {cell['p']}  halves {halves}  pace {pace.get('days')}d "
                      f"{pace.get('pass_pct')}% @{pace.get('risk_pct')}%", flush=True)
    real_best = max((c["x2"].get("mean_r") or -9) for c in cells if c["x2"].get("n", 0) >= 10)
    mat = np.vstack([v for v in nulls.values()])
    best_null = np.nanmax(mat, axis=0)
    p_grid = float(np.mean(best_null >= real_best))
    res = {"cells": cells, "best_of_grid": {"real": real_best, "p": round(p_grid, 3),
                                            "null_p95": round(float(np.nanpercentile(best_null, 95)), 3)},
           "data": [str(m1.index.min()), str(m1.index.max())]}
    (OUT / "absorption.json").write_text(json.dumps(res, indent=1, default=str))
    print(f"\nbest of grid meanR@2x {real_best}  p {p_grid:.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
