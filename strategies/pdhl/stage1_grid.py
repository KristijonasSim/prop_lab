"""H-011 stage 1 — the grid, its control, and the null that decides it.

The hypothesis: the previous day's high and low are where resting stops
actually cluster, because they are the one set of levels every trader sees the
same way. Price takes the level out, the stops fire, and once they are gone the
forced flow is finished - so the move gives back.

This is deliberately adjacent to H-005, which is REJECTED. H-005 faded the
extreme of the last 10 to 100 bars: a rolling level nobody else is watching,
whose null cleared the gate 19,062 times against the real market's 1,702. The
claim here is not "price reverts from extremes" - that one is dead - it is that
a SCHELLING POINT behaves differently from an arbitrary one. If it does not,
that closes the family rather than one lookback.

Two things H-005 could not check are in the grid:

  * open interest across the sweep. Contracts CLOSING is stops being run;
    contracts opening is a breakout wearing the same clothes. H-006 showed open
    interest carries nothing directional on its own, but conditioned on a level
    being taken out it separates two events that look identical on price.
  * the H-009 crowd gate.

Run alongside them, always: the CONTROL, which takes every setup the other way
for the same risk, and the NULL, a paired shuffle of the market, five seeds.

Run: .venv/bin/python strategies/pdhl/stage1_grid.py [SYMBOLS...]
"""
from __future__ import annotations

import itertools
import sys
import time
import warnings
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from strategies.pdhl import pdhl as P                                  # noqa: E402
from strategies.pdhl.engine import simulate                            # noqa: E402
from strategies.vwap.stage3_timeframes import (shuffle_market_paired,  # noqa: E402
                                               null_seed)

FEEDS = ROOT / "data" / "feeds"
OUT = ROOT / "backtests" / "pdhl"
OUT.mkdir(parents=True, exist_ok=True)

SYMS = ("BTCUSDT", "ETHUSDT", "SOLUSDT")
TFS = ("15m", "30m", "1h", "4h")
NSEEDS, WORKERS, GATE = 5, 6, 1.20
COSTS = (0.0, 1.0, 2.0, 3.0)

LEVELS = ("day", "week")
MIN_PEN = (0.0, 0.25, 0.5)
MAX_PEN = (0.0, 1.5)
CLOSE_FRAC = (1.0, 0.5)
# one dimension rather than three independent switches, so the grid stays a
# test of the confirmations rather than a search over their combinations
CONF = ("none", "oi", "flow", "crowd", "crowd+oi")
STOP_BUF = (0.1, 0.35)
TARGETS = ((0, 0.0), (1, 1.0), (1, 2.0), (2, 0.0))     # mid, RR1, RR2, time
MIN_RISK = (25.0, 100.0)
REVERT = (1, 0)


def grid():
    for lv, mp, xp, cf, cn, sb, (tm, rr), mr, rev in itertools.product(
            LEVELS, MIN_PEN, MAX_PEN, CLOSE_FRAC, CONF, STOP_BUF, TARGETS,
            MIN_RISK, REVERT):
        yield {"level": lv, "min_pen": mp, "max_pen": xp, "close_frac": cf,
               "conf": cn, "stop_buf": sb, "target_mode": tm, "rr": rr,
               "min_risk_bps": mr, "revert": rev}


_D = {}


def _init(sym, tf):
    _D[(sym, tf)] = P.load(sym, tf, FEEDS)


def _job(args):
    sym, tf, seed, cfgs = args
    df = _D[(sym, tf)]
    if seed is not None:
        base = df[["open", "high", "low", "close", "volume"]]
        sh = shuffle_market_paired(base, seed=null_seed(sym, tf, "h011", seed))
        df = df.assign(open=sh.open, high=sh.high, low=sh.low, close=sh.close,
                       volume=sh.volume)
    lv = P.levels(df)
    a, cvd, doi = P.atr(df), P.cvd_share(df), P.d_oi(df, 3)
    span = max((df.index[-1] - df.index[0]).days, 1)
    o, hh, ll, cc = df.open.values, df.high.values, df.low.values, df.close.values
    crowd = df.crowd.values
    rows = []
    for cfg in cfgs:
        hi = lv.pdh.values if cfg["level"] == "day" else lv.pwh.values
        lo = lv.pdl.values if cfg["level"] == "day" else lv.pwl.values
        conf = cfg["conf"]
        tr = simulate(o, hh, ll, cc, a.values, hi, lo, lv.mid.values, hi, lo,
                      doi.values, cvd.values, crowd, lv.day_i.values,
                      cfg["min_pen"], cfg["max_pen"], cfg["close_frac"],
                      1 if "oi" in conf else 0, 0.0,
                      1 if "flow" in conf else 0,
                      1 if "crowd" in conf else 0,
                      1, cfg["revert"], cfg["stop_buf"], cfg["target_mode"],
                      cfg["rr"], 96, P.FEE_BPS, P.SLIP_BPS, cfg["min_risk_bps"])
        if len(tr) < 40:
            continue
        entry, risk, gross = tr[:, 3], tr[:, 7], tr[:, 5]
        row = {"symbol": sym, "tf": tf, **cfg, "trades": int(len(tr)),
               "tpd": round(len(tr) / span, 3),
               "win_rate": round(float((gross > 0).mean()), 4)}
        for c in COSTS:
            extra = (c - 1.0) * (P.FEE_BPS + P.SLIP_BPS) * 2.0 / 1e4
            r = gross - extra * entry / risk
            row[f"pf_{c:.0f}x"] = round(P.pf_of(r), 4)
            if c == 2.0:
                row["maxdd_r_2x"] = round(P.max_dd(r), 2)
                row["total_r_2x"] = round(float(r.sum()), 1)
        rows.append(row)
    return rows


def main():
    syms = sys.argv[1:] or list(SYMS)
    cfgs = list(grid())
    chunks = [cfgs[i::WORKERS] for i in range(WORKERS)]
    real, null = [], []
    for sym in syms:
        for tf in TFS:
            try:
                _init(sym, tf)
            except FileNotFoundError:
                continue
            t0 = time.time()
            tasks = [(sym, tf, None, ch) for ch in chunks]
            tasks += [(sym, tf, s, ch) for s in range(NSEEDS) for ch in chunks]
            with ProcessPoolExecutor(WORKERS, initializer=_init,
                                     initargs=(sym, tf)) as ex:
                for t, rows in zip(tasks, ex.map(_job, tasks, chunksize=1)):
                    (null if t[2] is not None else real).extend(rows)
            print(f"  {sym} {tf}: {len(cfgs)} configs x {NSEEDS+1} runs "
                  f"[{time.time()-t0:.0f}s]", flush=True)

    if not real:
        print("nothing ran"); return
    R, N = pd.DataFrame(real), pd.DataFrame(null)
    R.to_csv(OUT / "stage1_real.csv", index=False)
    N.to_csv(OUT / "stage1_null.csv", index=False)

    print("\n" + "=" * 92)
    print("REVERT (the hypothesis) vs CONTINUE (control) vs NULL")
    print("=" * 92)
    for c in COSTS:
        k = f"pf_{c:.0f}x"
        rev = R[R.revert == 1][k].dropna()
        con = R[R.revert == 0][k].dropna()
        nl = N[N.revert == 1][k].dropna()
        print(f"  cost {c:.0f}x  revert med {rev.median():.3f} >1.0 {(rev>1).mean():5.1%} "
              f"clears {int((rev>=GATE).sum()):4d}  |  continue med {con.median():.3f} "
              f">1.0 {(con>1).mean():5.1%} clears {int((con>=GATE).sum()):4d}  |  "
              f"null med {nl.median():.3f} >1.0 {(nl>1).mean():5.1%} "
              f"clears {(nl>=GATE).sum()/NSEEDS:6.1f} per seed")

    print("\nDOES THE SCHELLING POINT BEAT THE ARBITRARY ONE? (revert, PF at 2x)")
    print(R[R.revert == 1].groupby("level").pf_2x.agg(
        ["size", "median", "max"]).round(3).to_string())

    print("\nWHAT EACH LEVER DOES (revert only, median PF at 2x)")
    for lev in ("conf", "min_pen", "max_pen", "close_frac", "stop_buf",
                "target_mode", "min_risk_bps", "tf"):
        g = R[R.revert == 1].groupby(lev).pf_2x.median().round(3)
        print(f"  {lev:13s} " + "  ".join(f"{k}={v}" for k, v in g.items()))

    cols = ["symbol", "tf", "level", "min_pen", "max_pen", "close_frac", "conf",
            "stop_buf", "target_mode", "rr", "min_risk_bps", "trades", "tpd",
            "win_rate", "pf_0x", "pf_1x", "pf_2x", "pf_3x", "maxdd_r_2x"]
    print("\nREVERT ONLY, best 10 by PF at 2x cost")
    print(R[R.revert == 1].sort_values("pf_2x", ascending=False).head(10)[cols]
          .to_string(index=False))
    print(f"\nwrote {OUT/'stage1_real.csv'}")


if __name__ == "__main__":
    main()
