"""KRIS TAB #6 - KRIS'S OWN ORB: FIRST CANDLE, BREAK, RETEST. Kris 2026-10-12:
*"i wait london session or ny session and i wait first 5m or 15m candle to
close then i wait for other candle to close over that 1st candle and wait for
retest thats it and it works 70% of a time"*.

RULES, as he trades it (fixed before the run):
  range    the FIRST 5m or 15m candle of the session (London 08:00 Europe/
           London, NY 09:30 America/New_York).
  break    a later candle of the same size CLOSES above its high (long) or
           below its low (short). First break only, inside the first 150 min.
  retest   after that close, price comes back to the broken level. Entry = a
           limit at the level, filled when a 5m bar touches it. Must happen
           within the first 150 min; cancelled if price first closes back past
           the OTHER side of the first candle.
  stop / target - Kris did not say, so every common choice is run:
           stop  "side"  other side of the first candle
                 "mid"   middle of the first candle
           target 1R · 2R · the first candle's height
  exits    5m bars. On the fill bar a stop touch counts (conservative), a target
           does not. Stop gapped through fills at the open. Flat at session close.
  costs    gold 1.83, NAS100 1.5 bps rt, x1/2/3. A limit fill on a touch is
           OPTIMISTIC (queue position) - flagged, not modelled.
  LUCK     the same entries in the opposite direction, coin-flipped, 1000 seeds.

    .venv/bin/python strategies/kris/orb3.py
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

import orb as O                                                       # noqa: E402
from factory import book5                                             # noqa: E402

MARKETS = {"XAUUSD": 1.83, "NAS100": 1.5}
CANDLES = (5, 15)
STOPS = ("side", "mid")
TARGETS = (("1R", "R", 1.0), ("2R", "R", 2.0), ("candle height", "range", 1.0))
CUTOFF_MIN = 150


def walk_from_fill(f, k, s, entry, stop, tgt):
    o, h, l, c = f.open.values, f.high.values, f.low.values, f.close.values
    # fill bar: a stop touch after the fill counts, a target does not
    if (s > 0 and l[k] <= stop) or (s < 0 and h[k] >= stop):
        return stop, k
    for j in range(k + 1, len(f)):
        if s > 0:
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


def setup(o, f, cmin):
    """Return (side, level, hi, lo, fill index k) or None."""
    first = f[f.index < o + pd.Timedelta(minutes=cmin)]
    rest = f[f.index >= o + pd.Timedelta(minutes=cmin)]
    if len(first) < max(1, cmin // 5 - 1) or len(rest) < 3:
        return None
    hi, lo = first.high.max(), first.low.min()
    cut = o + pd.Timedelta(minutes=CUTOFF_MIN)
    grp = ((rest.index - o) // pd.Timedelta(minutes=cmin)).values
    closes = rest.close.groupby(grp).last()
    last5 = rest.index.to_series().groupby(grp).max()
    side, t_brk = 0, None
    for g, cl in closes.items():
        t_end = last5.loc[g] + pd.Timedelta("5min")
        if t_end > cut:
            return None
        if cl > hi or cl < lo:
            side, t_brk = (1 if cl > hi else -1), last5.loc[g]
            break
    if side == 0:
        return None
    level = hi if side > 0 else lo
    other = lo if side > 0 else hi
    k = f.index.searchsorted(t_brk, side="right")
    o_, h_, l_, c_ = f.open.values, f.high.values, f.low.values, f.close.values
    for j in range(k, len(f)):
        if f.index[j] + pd.Timedelta("5min") > cut:
            return None
        touched = l_[j] <= level if side > 0 else h_[j] >= level
        if touched:
            return side, level, hi, lo, j
        if (side > 0 and c_[j] < other) or (side < 0 and c_[j] > other):
            return None
    return None


def main() -> int:
    rng = np.random.default_rng(20261012)
    cells, nulls = [], {}
    for sym, rt in MARKETS.items():
        m = O.load(sym)
        for sname, (zone, t0, t1) in O.SESSIONS.items():
            sess = list(O.sessions(m, zone, t0, t1))
            for cmin in CANDLES:
                sets = [(f, setup(o, f, cmin)) for o, c, f in sess]
                sets = [(f, s) for f, s in sets if s]
                for stop_kind in STOPS:
                    for tname, tkind, tval in TARGETS:
                        rows = []
                        for f, (side, level, hi, lo, k) in sets:
                            entry = level
                            stop0 = (lo if side > 0 else hi) if stop_kind == "side" else (hi + lo) / 2
                            risk = (entry - stop0) * side
                            if risk <= entry * O.MIN_RISK_BPS / 1e4:
                                continue
                            out = {"t_in": f.index[k], "side": side}
                            for s in (1, -1):
                                stop = entry - s * risk
                                tgt = entry + s * (tval * risk if tkind == "R" else tval * (hi - lo))
                                px, j = walk_from_fill(f, k, s, entry, stop, tgt)
                                out[s] = ((px - entry) * s / risk, entry / risk, f.index[j])
                            rows.append(out)
                        if len(rows) < 10:
                            continue
                        g = np.array([x[x["side"]][0] for x in rows])
                        gf = np.array([x[-x["side"]][0] for x in rows])
                        cpr = np.array([x[x["side"]][1] for x in rows]) * rt / 1e4
                        t_in = pd.DatetimeIndex([x["t_in"] for x in rows])
                        t_out = pd.DatetimeIndex([x[x["side"]][2] for x in rows])
                        r2 = g - 2 * cpr
                        flips = rng.random((O.SEEDS, len(rows))) < 0.5
                        nm = (np.where(flips, gf, g) - 2 * cpr).mean(axis=1)
                        key = f"{sym} {sname} {cmin}m stop-{stop_kind} tgt-{tname}"
                        nulls[key] = nm
                        h1 = t_in < O.MID
                        pace = book5.pace(pd.DataFrame({"t": t_out, "r": r2}), band=False)
                        cell = {"cell": key, "sym": sym, "session": sname, "candle": cmin,
                                "stop": stop_kind, "target": tname, "setups": len(sets),
                                "x0": O.stats(g, t_in, t_out), "x1": O.stats(g - cpr, t_in, t_out),
                                "x2": O.stats(r2, t_in, t_out), "x3": O.stats(g - 3 * cpr, t_in, t_out),
                                "gross_r": round(float(g.mean()), 3), "fee_r": round(float(cpr.mean()), 3),
                                "halves": [round(float(r2[h1].mean()), 3) if h1.any() else None,
                                           round(float(r2[~h1].mean()), 3) if (~h1).any() else None],
                                "p": round(float(np.mean(nm >= r2.mean())), 3), "pace": pace}
                        cells.append(cell)
                        x0, x1, x2 = cell["x0"], cell["x1"], cell["x2"]
                        print(f"{key:46} n {x2['n']:4} tpd {x2['tpd']:4}  win {x0['win']:4}%  gross {cell['gross_r']:+.3f}  "
                              f"fee {cell['fee_r']:.3f}  PF 0x/1x/2x {x0['pf']}/{x1['pf']}/{x2['pf']}  p {cell['p']}  "
                              f"halves {cell['halves']}  {pace.get('days')}d {pace.get('pass_pct')}% {pace.get('accounts')}acc",
                              flush=True)
    best = max(cells, key=lambda c: c["x2"]["mean_r"])
    best_null = np.max(np.vstack(list(nulls.values())), axis=0)
    p_grid = float(np.mean(best_null >= best["x2"]["mean_r"]))
    (O.OUT / "orb3.json").write_text(json.dumps({"cells": cells, "best_of_grid": {
        "cell": best["cell"], "real": best["x2"]["mean_r"], "p": p_grid}}, indent=1, default=str))
    print(f"\nbest of {len(cells)}: {best['cell']}  R2x {best['x2']['mean_r']}  best-of-grid p {p_grid:.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
