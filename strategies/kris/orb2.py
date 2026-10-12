"""KRIS TAB #5 - ORB THE WAY IT IS ACTUALLY TRADED. Kris 2026-10-12 (/goal):
*"research on internet how ORB must work ... what is way to trade with ORB on
prop firms and redo code"*.

WHAT THE RESEARCH SAID, AND WHAT #4 (`orb.py`) GOT WRONG:
  * Zarattini & Aziz 2023 (SSRN 4416622): the direction of the FIRST 5-MINUTE
    CANDLE, entry at the second candle's open, stop at the other end of the
    first candle, target 10R or the close. ~24% hit, +0.13R gross on QQQ/NQ.
  * Zarattini, Barbon & Aziz 2024 (SSRN 4729284): the same rule only on stocks
    "in play" - opening-range volume >= 100% of its 14-day average for that
    window, ranked top 20. The filter is where the paper's edge comes from.
  * Prop-firm NQ practice: 9:30-9:45 range, a 5m CLOSE outside it, stop on the
    other side, target the range height (measured move), flat by the close.
  * Gold ORB script (TradingView): same range, stop at the MIDDLE of the range,
    target 2x the stop, no entries after 12:00 ET.
  * #4 allowed breakouts all session - late breaks are the weak ones - and
    charged NAS100 3.3 bps where NQ actually costs ~2.5 points (~1.2 bps).

VERSIONS (fixed before the run), on London 08:00 and NY 09:30 opens:
  A   first 5m candle direction, stop its other end, 10R or close (Zarattini)
  B   15m range, 5m close outside, stop other side, target = range height
  C   15m range, 5m close outside, stop mid-range, target 2x stop (gold script)
  D   15m range, 5m close outside, stop other side, no target, hold to close
  A+, B+, C+  the same with the IN-PLAY filter: opening-range volume >= 1.5x
      its average over the prior 14 sessions, same window.
  entries only in the first 150 minutes (NY: before 12:00 ET).
  costs  gold 1.83 bps rt (measured), NAS100 1.5 bps rt (~3 NQ points), x1/2/3.
  LUCK   coin-flip direction, same entry/stop distance/target, 1000 seeds;
         best-of-grid over all 28 cells.

    .venv/bin/python strategies/kris/orb2.py
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
CUTOFF_MIN, RVOL_MIN, RVOL_LB = 150, 1.5, 14
VERSIONS = {
    "A first-candle 10R": dict(rng=5, entry="dir", stop="side", tgt=("R", 10.0), rv=False),
    "B 15m, stop side, target range": dict(rng=15, entry="close", stop="side", tgt=("range", 1.0), rv=False),
    "C 15m, stop mid, 2x stop": dict(rng=15, entry="close", stop="mid", tgt=("R", 2.0), rv=False),
    "D 15m, stop side, hold to close": dict(rng=15, entry="close", stop="side", tgt=None, rv=False),
    "A+ in-play": dict(rng=5, entry="dir", stop="side", tgt=("R", 10.0), rv=True),
    "B+ in-play": dict(rng=15, entry="close", stop="side", tgt=("range", 1.0), rv=True),
    "C+ in-play": dict(rng=15, entry="close", stop="mid", tgt=("R", 2.0), rv=True),
}


def session_trade(o, f, v, rvol):
    if v["rv"] and not (rvol >= RVOL_MIN):
        return None
    rng = f[f.index < o + pd.Timedelta(minutes=v["rng"])]
    rest = f[f.index >= o + pd.Timedelta(minutes=v["rng"])]
    if len(rng) < max(1, v["rng"] // 5 - 1) or len(rest) < 2:
        return None
    hi, lo = rng.high.max(), rng.low.min()
    if v["entry"] == "dir":
        c0, o0 = rng.close.iloc[-1], rng.open.iloc[0]
        side = 1 if c0 > o0 else -1 if c0 < o0 else 0
        if side == 0:
            return None
        k0 = f.index.searchsorted(rest.index[0])
    else:
        cut = o + pd.Timedelta(minutes=CUTOFF_MIN)
        side, k0 = 0, None
        for t, cl in rest.close.items():
            if t + pd.Timedelta("5min") > cut:
                break
            if cl > hi or cl < lo:
                side = 1 if cl > hi else -1
                k0 = f.index.searchsorted(t, side="right")
                break
        if side == 0 or k0 is None or k0 >= len(f):
            return None
    entry = f.open.values[k0]
    stop0 = (lo if side > 0 else hi) if v["stop"] == "side" else (hi + lo) / 2
    risk = (entry - stop0) * side
    if risk <= entry * O.MIN_RISK_BPS / 1e4:
        return None
    out = {"t_in": f.index[k0], "side": side}
    for s in (1, -1):
        stop = entry - s * risk
        if v["tgt"] is None:
            tgt = None
        elif v["tgt"][0] == "R":
            tgt = entry + s * v["tgt"][1] * risk
        else:
            tgt = entry + s * v["tgt"][1] * (hi - lo)
        px, j = O.walk(f, k0, s, stop, tgt)
        out[s] = ((px - entry) * s / risk, entry / risk, f.index[j])
    return out


def main() -> int:
    rng = np.random.default_rng(20261012)
    cells, nulls = [], {}
    for sym, rt in MARKETS.items():
        m = O.load(sym)
        for sname, (zone, t0, t1) in O.SESSIONS.items():
            sess = list(O.sessions(m, zone, t0, t1))
            # in-play: opening-range volume against its own prior 14 sessions
            vol5 = np.array([f[f.index < o + pd.Timedelta("5min")].volume.sum() for o, c, f in sess])
            vol15 = np.array([f[f.index < o + pd.Timedelta("15min")].volume.sum() for o, c, f in sess])
            def rv(arr):
                s = pd.Series(arr)
                return (s / s.shift(1).rolling(RVOL_LB).mean()).values
            rv5, rv15 = rv(vol5), rv(vol15)
            for vname, v in VERSIONS.items():
                rvs = rv5 if v["rng"] == 5 else rv15
                rows = [x for x in (session_trade(o, f, v, rvs[i]) for i, (o, c, f) in enumerate(sess)) if x]
                if len(rows) < 10:
                    continue
                side = np.array([x["side"] for x in rows])
                g = np.array([x[x["side"]][0] for x in rows])
                gf = np.array([x[-x["side"]][0] for x in rows])
                cpr = np.array([x[x["side"]][1] for x in rows]) * rt / 1e4
                t_in = pd.DatetimeIndex([x["t_in"] for x in rows])
                t_out = pd.DatetimeIndex([x[x["side"]][2] for x in rows])
                r2 = g - 2 * cpr
                flips = rng.random((O.SEEDS, len(rows))) < 0.5
                nm = (np.where(flips, gf, g) - 2 * cpr).mean(axis=1)
                key = f"{sym} {sname} {vname}"
                nulls[key] = nm
                h1 = t_in < O.MID
                pace = book5.pace(pd.DataFrame({"t": t_out, "r": r2}), band=False)
                cell = {"cell": key, "sym": sym, "session": sname, "version": vname,
                        "x1": O.stats(g - cpr, t_in, t_out), "x2": O.stats(r2, t_in, t_out),
                        "x3": O.stats(g - 3 * cpr, t_in, t_out), "gross_r": round(float(g.mean()), 3),
                        "fee_r": round(float(cpr.mean()), 3),
                        "halves": [round(float(r2[h1].mean()), 3) if h1.any() else None,
                                   round(float(r2[~h1].mean()), 3) if (~h1).any() else None],
                        "p": round(float(np.mean(nm >= r2.mean())), 3),
                        "edge_vs_coin": round(float(g.mean() - gf.mean()), 3) / 2, "pace": pace}
                cells.append(cell)
                x1, x2 = cell["x1"], cell["x2"]
                print(f"{key:44} n {x2['n']:4} tpd {x2['tpd']:4}  gross {cell['gross_r']:+.3f}  fee {cell['fee_r']:.3f}  "
                      f"PF 1x/2x/3x {x1['pf']}/{x2['pf']}/{cell['x3']['pf']}  win {x2['win']}  p {cell['p']}  "
                      f"halves {cell['halves']}  {pace.get('days')}d {pace.get('pass_pct')}% {pace.get('accounts')}acc",
                      flush=True)
    best = max(cells, key=lambda c: c["x2"]["mean_r"])
    best_null = np.max(np.vstack(list(nulls.values())), axis=0)
    p_grid = float(np.mean(best_null >= best["x2"]["mean_r"]))
    (O.OUT / "orb2.json").write_text(json.dumps({"cells": cells, "best_of_grid": {
        "cell": best["cell"], "real": best["x2"]["mean_r"], "p": p_grid}}, indent=1, default=str))
    print(f"\nbest of {len(cells)}: {best['cell']}  R2x {best['x2']['mean_r']}  best-of-grid p {p_grid:.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
