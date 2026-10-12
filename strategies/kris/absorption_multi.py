"""KRIS TAB #1b - THE 4H ABSORPTION RULE ON MORE MARKETS. Kris 2026-10-12:
*"what if we would use those 4h on not only gold but also ... multiple pairs?
maybe that would ... have at least 0.5tpd"*.

THE RULE IS `absorption.py`'s, UNCHANGED, at 4h only. Only markets are added,
each with REAL aggressor data:
    XAUUSDT  Bybit gold perp tape, 7 months          5.5 bps rt, weekend skip
    PAXGUSDT Bybit gold-token tape, 3 years          10 bps rt (5.5 fee + $1 tick ~4bps), weekend skip
    XAGUSDT  Bybit silver perp tape, 7 months        5.5 bps rt, weekend skip
    BTCUSDT  Binance USD-M 5m bars, taker buy vol    10.1 bps rt taker, trades weekends
    ETHUSDT  Binance USD-M 5m bars, taker buy vol    10.3 bps rt taker, trades weekends
Crypto exits walk 5-minute bars, not 1-minute (that is what is on disk).
Forex is absent on purpose: Bybit's FX tapes start 2026-09-08 with ~400 prints
a day, and Dukascopy has no aggressor side.

LUCK: best-of-30 (5 markets x 2 sides x 3 variants), 200 seeds, hour-matched.
POOL, fixed before the run: the BASE variant, both sides, on PAXG + silver +
BTC + ETH (PAXG stands for gold - XAUUSDT is the same asset and would count
gold twice). Pool PF, trades/day and pace at 2% on the HOUSE spec.

    .venv/bin/python strategies/kris/absorption_multi.py
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
from core import bybit_tape                                           # noqa: E402
from factory import book5                                             # noqa: E402

START = "2023-09-01"
GOLD_CLOSED = A.closed


def never(ts: pd.DatetimeIndex) -> np.ndarray:
    return np.zeros(len(ts), bool)


def binance(sym: str) -> pd.DataFrame:
    d = pd.read_parquet(ROOT / "data" / "feeds" / f"{sym}_perp_5m.parquet")
    d = d[d.index >= START]
    if d.index.tz is None:
        d.index = d.index.tz_localize("UTC")
    d = d.rename(columns={"taker_buy_base": "buy_vol"})
    d["sell_vol"] = d.volume - d.buy_vol
    return d[["open", "high", "low", "close", "buy_vol", "sell_vol"]]


MARKETS = {
    "XAUUSDT": (lambda: bybit_tape.load("XAUUSDT"), 5.5, GOLD_CLOSED),
    "PAXGUSDT": (lambda: bybit_tape.load("PAXGUSDT"), 10.0, GOLD_CLOSED),
    "XAGUSDT": (lambda: bybit_tape.load("XAGUSDT"), 5.5, GOLD_CLOSED),
    "BTCUSDT": (lambda: binance("BTCUSDT"), 10.1, never),
    "ETHUSDT": (lambda: binance("ETHUSDT"), 10.3, never),
}
POOL = ("PAXGUSDT", "XAGUSDT", "BTCUSDT", "ETHUSDT")


def main() -> int:
    rng = np.random.default_rng(20261012)
    cells, nulls, pool_tr, pool_null = [], {}, [], []
    rule = "4h"
    for mkt, (load, cost, closed) in MARKETS.items():
        A.COST_BPS, A.closed = cost, closed
        m1 = load()
        tp = A.Tape(m1)
        b = A.bars(m1, rule)
        for side, sname in ((1, "long"), (-1, "short")):
            for vname, (z, k) in A.VARIANTS.items():
                df = A.run_cell(tp, b, rule, side, z, k)
                key = f"{mkt} {sname} {vname}"
                nm = A.null_means(tp, b, rule, df, side, k, rng)
                nulls[key] = nm
                s2 = A.stats(df, 2)
                real = s2.get("mean_r", np.nan)
                halves = [A.stats(df[df.t_in < A.MID if mkt in ("XAUUSDT", "XAGUSDT")
                                     else df.t_in < pd.Timestamp("2025-03-01", tz="UTC")], 2).get("mean_r"),
                          A.stats(df[df.t_in >= A.MID if mkt in ("XAUUSDT", "XAGUSDT")
                                     else df.t_in >= pd.Timestamp("2025-03-01", tz="UTC")], 2).get("mean_r")]
                pace = book5.pace(pd.DataFrame({"t": df.t, "r": df.g - 2 * df.cpr}), band=False) if len(df) >= 10 else {}
                cell = {"cell": key, "x1": A.stats(df, 1), "x2": s2, "x3": A.stats(df, 3),
                        "gross_r": round(df.g.mean(), 3) if len(df) else None,
                        "halves": halves, "pace": pace,
                        "p": round(float(np.mean(nm >= real)), 3) if len(df) else None}
                cells.append(cell)
                print(f"{key:24} n {s2.get('n',0):4} tpd {s2.get('tpd')}  PF2x {s2.get('pf')}  "
                      f"gross {cell['gross_r']}  meanR2x {real}  p {cell['p']}  halves {halves}  "
                      f"pace {pace.get('days')}d {pace.get('pass_pct')}%", flush=True)
                if mkt in POOL and vname == "base" and len(df):
                    pool_tr.append(pd.DataFrame({"t": df.t, "t_in": df.t_in,
                                                 "g": df.g, "cpr": df.cpr}))
                    pool_null.append((len(df), nm))
    real_best = max((c["x2"].get("mean_r") or -9) for c in cells if c["x2"].get("n", 0) >= 10)
    best_null = np.nanmax(np.vstack(list(nulls.values())), axis=0)
    p_grid = float(np.mean(best_null >= real_best))
    pool = pd.concat(pool_tr).sort_values("t_in")
    w = np.array([n for n, _ in pool_null], float)
    pn = np.nansum(np.vstack([nm * n for n, nm in pool_null]), axis=0) / w.sum()
    ps = A.stats(pool, 2)
    pp = book5.pace(pd.DataFrame({"t": pool.t, "r": pool.g - 2 * pool.cpr}))
    p_pool = float(np.mean(pn >= ps["mean_r"]))
    res = {"cells": cells, "best_of_grid": {"real": real_best, "p": round(p_grid, 3)},
           "pool": {"x1": A.stats(pool, 1), "x2": ps, "x3": A.stats(pool, 3),
                    "gross_r": round(pool.g.mean(), 3), "pace": pp, "p": round(p_pool, 3)}}
    (A.OUT / "absorption_multi.json").write_text(json.dumps(res, indent=1, default=str))
    print(f"\nbest of 30 meanR@2x {real_best}  p {p_grid:.3f}")
    print(f"POOL n {ps['n']} tpd {ps['tpd']} PF 1x/2x/3x {res['pool']['x1']['pf']}/{ps['pf']}/"
          f"{res['pool']['x3']['pf']} gross {res['pool']['gross_r']} p {p_pool:.3f} pace {pp}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
