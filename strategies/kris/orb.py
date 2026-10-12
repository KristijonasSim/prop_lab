"""KRIS TAB #4 - OPENING RANGE BREAKOUT, SIMPLE. Kris 2026-10-12 (/goal):
*"lets start with ORB ... simple patterns on 5m 15m and 1h ... gold and nas100
... only on NY and London sessions"*.

MECHANISM (Kris's): the session open is where the day's order flow arrives;
the first move out of the opening range is the side that won the open, and it
tends to run for the rest of the session.

RULES (fixed before the run):
  sessions  London 08:00-16:30 Europe/London, NY 09:30-16:00 America/New_York
            (daylight saving handled by the zone, not by a fixed UTC hour).
  range     high/low of the first OR minutes: 5m and 15m charts OR 15 or 30,
            1h chart OR 60. Bars are built FROM the session open.
  entry     first chart bar after the range that CLOSES above the high (long)
            or below the low (short); fill at the next 5m open. One trade per
            session. Skipped if the stop is under 3 bps of price.
  patterns  P1 stop = other side of the range, target 2R, else out at close.
            P2 stop = middle of the range, target 2R, else out at close.
            P3 stop = other side of the range, no target, out at the close.
  exits     walked on 5m bars; stop first if both in one bar; a stop gapped
            through fills at the bar open. Zero-volume bars are skipped.
  costs     gold 1.83 bps rt (measured), NAS100 3.3 bps rt (assumed), x1/2/3.
  window    Dukascopy 5m, 2023-09-01 -> 2026-08-30, 3 years.
  LUCK      same day, same entry time, same stop distance, same target rule,
            COIN-FLIP direction, 1000 seeds: does the breakout's direction
            carry information? Per cell and best-of-grid.
  BAR       pass: PF@2x >= 1.3, beats luck, both halves > 0, >= 100 trades,
            < 30 days at 2%.  keeper: PF@2x >= 1.6, <= 14 days, <= 1.5 accounts.

    .venv/bin/python strategies/kris/orb.py
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

from factory import book5                                             # noqa: E402

OUT = ROOT / "backtests" / "kris"
MARKETS = {"XAUUSD": 1.83, "NAS100": 3.3}
SESSIONS = {"London": ("Europe/London", "08:00", "16:30"),
            "NY": ("America/New_York", "09:30", "16:00")}
CHARTS = [("5m", 5, 15), ("5m", 5, 30), ("15m", 15, 15), ("15m", 15, 30), ("1h", 60, 60)]
PATTERNS = {"P1 other side, 2R": ("side", 2.0), "P2 mid, 2R": ("mid", 2.0),
            "P3 other side, hold to close": ("side", None)}
MIN_RISK_BPS, SEEDS = 3.0, 1000
MID = pd.Timestamp("2025-03-01", tz="UTC")


def load(sym: str) -> pd.DataFrame:
    return pd.read_parquet(ROOT / "data" / f"{sym}_dukascopy_5min.parquet")


def sessions(m: pd.DataFrame, zone: str, t0: str, t1: str):
    """Yield (open_utc, close_utc, frame of live 5m bars inside the session)."""
    days = pd.Index(m.index.tz_convert(zone).normalize().unique())
    for d in days:
        if d.dayofweek >= 5:
            continue
        o = pd.Timestamp(f"{d.date()} {t0}", tz=zone).tz_convert("UTC")
        c = pd.Timestamp(f"{d.date()} {t1}", tz=zone).tz_convert("UTC")
        f = m.loc[o: c - pd.Timedelta("5min")]
        f = f[f.volume > 0]
        if len(f) < 12 or f.index[0] > o + pd.Timedelta("10min"):
            continue                                   # holiday / late open
        yield o, c, f


def walk(f: pd.DataFrame, k0: int, side: int, stop: float, tgt: float | None):
    o, h, l, c = f.open.values, f.high.values, f.low.values, f.close.values
    for j in range(k0, len(f)):
        if side > 0:
            if l[j] <= stop:
                return min(stop, o[j]), j
            if tgt is not None and h[j] >= tgt:
                return tgt, j
        else:
            if h[j] >= stop:
                return max(stop, o[j]), j
            if tgt is not None and l[j] <= tgt:
                return tgt, j
    return c[-1], len(f) - 1


def one_session(o, f, tf_min, or_min, kind, k):
    """Return dict with both-side outcomes for the session's first breakout."""
    rng = f[f.index < o + pd.Timedelta(minutes=or_min)]
    rest = f[f.index >= o + pd.Timedelta(minutes=or_min)]
    if len(rng) < max(1, or_min // 5 - 1) or len(rest) < 2:
        return None
    hi, lo = rng.high.max(), rng.low.min()
    # chart bars built from the session open
    grp = ((rest.index - o) // pd.Timedelta(minutes=tf_min)).values
    bars = rest.groupby(grp).agg(close=("close", "last"))
    ends = rest.index.to_series().groupby(grp).max().tolist()    # last 5m bar of each chart bar
    for n, cl in enumerate(bars.close.values):
        side = 1 if cl > hi else -1 if cl < lo else 0
        if side == 0:
            continue
        k0 = f.index.searchsorted(ends[n], side="right")
        if k0 >= len(f):
            return None
        entry = f.open.values[k0]
        stop0 = (lo if side > 0 else hi) if kind == "side" else (hi + lo) / 2
        risk = (entry - stop0) * side
        if risk <= entry * MIN_RISK_BPS / 1e4:
            return None
        out = {"t_in": f.index[k0], "side": side}
        for s in (1, -1):        # the real side and its coin-flip mirror, same distance
            stop = entry - s * risk
            tgt = entry + s * k * risk if k else None
            px, j = walk(f, k0, s, stop, tgt)
            out[s] = ((px - entry) * s / risk, entry / risk, f.index[j])
        return out
    return None


def stats(r: np.ndarray, t_in, t_out) -> dict:
    if len(r) == 0:
        return {"n": 0}
    win, loss = r[r > 0].sum(), -r[r <= 0].sum()
    eq = np.cumsum(r)
    span = max((t_out.max() - t_in.min()).days, 1)
    daily = pd.Series(r, index=pd.DatetimeIndex(t_out)).resample("1D").sum()
    return {"n": int(len(r)), "pf": round(win / loss, 3) if loss > 0 else None,
            "mean_r": round(float(r.mean()), 3), "win": round(float((r > 0).mean() * 100), 1),
            "dd_r": round(float((eq - np.maximum.accumulate(eq)).min()), 2),
            "tpd": round(len(r) / span * 7 / 5, 2),
            "hold_h": round(float(np.mean((t_out - t_in).total_seconds()) / 3600), 2),
            "sharpe": round(float(daily.mean() / daily.std() * np.sqrt(252)), 2) if daily.std() > 0 else None}


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(20261012)
    cells, nulls = [], {}
    for sym, rt in MARKETS.items():
        m = load(sym)
        for sname, (zone, t0, t1) in SESSIONS.items():
            sess = list(sessions(m, zone, t0, t1))
            for tf, tf_min, or_min in CHARTS:
                for pname, (kind, k) in PATTERNS.items():
                    rows = [x for x in (one_session(o, f, tf_min, or_min, kind, k) for o, c, f in sess) if x]
                    if not rows:
                        continue
                    side = np.array([x["side"] for x in rows])
                    g_real = np.array([x[x["side"]][0] for x in rows])
                    g_flip = np.array([x[-x["side"]][0] for x in rows])
                    cpr = np.array([x[x["side"]][1] for x in rows]) * rt / 1e4
                    t_in = pd.DatetimeIndex([x["t_in"] for x in rows])
                    t_out = pd.DatetimeIndex([x[x["side"]][2] for x in rows])
                    key = f"{sym} {sname} {tf} OR{or_min} {pname}"
                    r2 = g_real - 2 * cpr
                    flips = rng.random((SEEDS, len(rows))) < 0.5
                    nm = (np.where(flips, g_flip, g_real) - 2 * cpr).mean(axis=1)
                    nulls[key] = nm
                    h1 = t_in < MID
                    pace = book5.pace(pd.DataFrame({"t": t_out, "r": r2}), band=False)
                    cell = {"cell": key, "sym": sym, "session": sname, "tf": tf, "or": or_min,
                            "pattern": pname,
                            "x1": stats(g_real - cpr, t_in, t_out), "x2": stats(r2, t_in, t_out),
                            "x3": stats(g_real - 3 * cpr, t_in, t_out),
                            "gross_r": round(float(g_real.mean()), 3),
                            "long_share": round(float((side > 0).mean()), 2),
                            "halves": [round(float(r2[h1].mean()), 3) if h1.any() else None,
                                       round(float(r2[~h1].mean()), 3) if (~h1).any() else None],
                            "p": round(float(np.mean(nm >= r2.mean())), 3),
                            "null_mean": round(float(nm.mean()), 3), "pace": pace}
                    cells.append(cell)
                    x2 = cell["x2"]
                    print(f"{key:48} n {x2['n']:4} tpd {x2['tpd']:4}  PF 1x/2x/3x {cell['x1']['pf']}/{x2['pf']}/"
                          f"{cell['x3']['pf']}  win {x2['win']}  R2x {x2['mean_r']:+.3f}  p {cell['p']}  "
                          f"halves {cell['halves']}  {pace.get('days')}d {pace.get('pass_pct')}% "
                          f"{pace.get('accounts')}acc", flush=True)
    best = max(cells, key=lambda c: c["x2"]["mean_r"])
    best_null = np.max(np.vstack(list(nulls.values())), axis=0)
    p_grid = float(np.mean(best_null >= best["x2"]["mean_r"]))
    (OUT / "orb.json").write_text(json.dumps({"cells": cells, "best_of_grid": {
        "cell": best["cell"], "real": best["x2"]["mean_r"], "p": p_grid}}, indent=1, default=str))
    print(f"\nbest of {len(cells)}: {best['cell']}  R2x {best['x2']['mean_r']}  best-of-grid p {p_grid:.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
