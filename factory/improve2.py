"""STEP 8, ROUND 2 - tune the five deep-dive survivors once more.

Kris, 2026-10-09 (/goal): *"dig deep with these 5 strategies ... make them as
best as you can"*.

PRE-REGISTERED 2026-10-09, before the first run. The base is each idea's
round-1 rule (`deepdive.json`). Same machinery as `improve.py` - timeframe,
one MORE filter, exits; picked on the older half, judged on the newer half,
luck check = the identical search on random entries (40 seeds, 95th pct).

    finer exits   stop 0.75-3 ATR, target 3-10 ATR, hold x0.5-x2
    filters       `improve.FILTERS` plus five new ones below

HONEST CAVEAT, written before the run: the newer half has already been looked
at once (it judged round 1 and chose these five). It is no longer fully blind,
so a round-2 "REAL" is weaker evidence than round 1's, and the older years
(`cells.holdout`) are reported beside it as the only untouched data left.

    python -m factory.improve2          # writes backtests/factory/improve2.json
"""
from __future__ import annotations

import json
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from factory import build, cells, check, improve, queue               # noqa: E402
from factory.rescore import from_record                               # noqa: E402
from factory.tweak import _stats                                      # noqa: E402

OUT = queue.DIR / "improve2.json"
improve.STOPS = (0.75, 1.0, 1.25, 1.5, 2.0, 3.0)
improve.TARGETS = (3.0, 4.0, 5.0, 6.0, 8.0, 10.0)
improve.HOLDS = (0.5, 0.75, 1.0, 1.5, 2.0)
improve.FILTERS = {**improve.FILTERS,
                   "EMA20 over EMA50":     ["ema20 above ema50"],
                   "RSI14 under 70":       ["rsi14 below 70"],
                   "above VWAP48":         ["price above vwap48"],
                   "strong body":          ["body_pct above 50"],
                   "above prev day high":  ["price above prev_day_high"]}


def items() -> list:
    out = []
    for r in json.loads((queue.DIR / "deepdive.json").read_text()):
        m, tf = r["home"].split()
        stop, tgt, hold = (float(r["exits"].split()[0][4:]), float(r["exits"].split()[1][3:]),
                           int(r["exits"].split()[2][4:]))
        s = from_record({"name": r["name"], "idea": r["rule"], "stop_atr": stop,
                         "target_atr": tgt, "max_hold": hold})
        out.append(({"name": r["name"], "by": "round2"}, s, m, tf))
    return out


def _older(s, m, tf) -> dict:
    dated = cells.load(m, tf)
    old = cells.holdout(m, tf)
    old = old[old.index < dated.index[0]].reset_index(drop=True)
    return _stats(np.array([t.r for t in build.run(s, old, cost_bps=cells.cost_bps(m))]))


def main() -> int:
    its = items()
    improve.warm(its)
    with ProcessPoolExecutor(max_workers=check.workers()) as pool:
        res = list(pool.map(improve._real, its))
        jobs = [(it, [], seed) for it in its for seed in range(improve.SEEDS)]
        nul = list(pool.map(improve._null, jobs, chunksize=2))
    for i, (r, it) in enumerate(zip(res, its)):
        arr = np.array([o[0] for o in nul[i * improve.SEEDS:(i + 1) * improve.SEEDS]])
        p95 = float(np.nanpercentile(arr, 95))
        lift = r["lift_grid"]
        bp, tp = r["base"]["pace"], r["grid"]["pace"]
        c3 = (not bp.get("band") or not tp.get("band")
              or tp["band"].get("pass_hi", 1) >= bp["band"].get("pass_lo", 0))
        r["null"] = {"p95": p95, "p": float(np.nanmean(arr >= lift)),
                     "real": bool(lift > 0 and lift > p95 and c3)}
        g = r["grid"]
        s2 = from_record({"name": r["name"], "idea": g["rule"], "stop_atr": g["stop_atr"],
                          "target_atr": g["target_atr"], "max_hold": g["max_hold"]})
        r["older"] = {"round1": _older(it[1], it[2], it[3]), "round2": _older(s2, it[2], g["tf"])}
        b = r["base"]["pace"]
        print(f"{r['name'][:40]:40} {g['tf']} +{g['filter']} {g['exits']:22} "
              f"lift {lift:+.3f} p95 {p95:+.3f} p {r['null']['p']:.2f} REAL={r['null']['real']} | "
              f"pass {b.get('pass_pct')}->{tp.get('pass_pct')} days {b.get('days')}->{tp.get('days')} "
              f"| older pf {r['older']['round1']['pf']}->{r['older']['round2']['pf']}", flush=True)
    OUT.write_text(json.dumps(res, indent=1, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
