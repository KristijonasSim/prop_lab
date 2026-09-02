"""H-010 stage 1 — the grid, its null, and the control that decides it.

The hypothesis, from a published TradingView indicator: anchored VWAP with
standard-deviation bands, enter when a bar reaches a band and closes back
against the move, confirmed by volume delta. Rebuilt with honest fills, real
taker data, exits, and this repo's own crowd gate.

THREE THINGS ARE RUN TOGETHER, not one after another, because the first pass on
BTC 1h already showed the shape of the problem and searching harder for a
parameter is how H-005 was nearly believed.

  REVERT   the hypothesis: fade the move back toward the VWAP
  CONTINUE the control: identical setups, taken the other way
  NULL     the same rules on a paired-shuffled market, five deterministic seeds

The control matters more than usual here. H-002's own blind fold choices land on
TREND and BREAK and essentially never on FADE, and the prior repo's `VWAP
std-band fade` backtested at 3.0 and traded at 0.7 on a limit-fill artefact. If
continuation pays where reversion does not, that is a finding about the family
rather than a parameter that was not found.

MINIMUM STOP DISTANCE is a real dimension here, not a hygiene constant. Early in
a session the volume-weighted sigma is tiny, so the bands sit close together and
a two-sigma stop can be narrower than the 14bps round trip - cost alone was 1.4R
on the tightest trades in the first pass. The floor is swept.

Run: .venv/bin/python strategies/vwap_mr/stage1_grid.py [SYMBOLS...]
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

from strategies.vwap_mr import vwap_mr as M                          # noqa: E402
from strategies.vwap_mr.engine import simulate                       # noqa: E402
from strategies.vwap.stage3_timeframes import (shuffle_market_paired,  # noqa: E402
                                               null_seed)

FEEDS = ROOT / "data" / "feeds"
OUT = ROOT / "backtests" / "vwap_mr"
OUT.mkdir(parents=True, exist_ok=True)

SYMS = ("BTCUSDT", "ETHUSDT", "SOLUSDT")
TFS = ("15m", "30m", "1h", "4h")
NSEEDS = 5
WORKERS = 6
GATE = 1.20
COSTS = (0.0, 1.0, 2.0, 3.0)

ANCHORS = ("D", "W", "roll96")
LEVELS = (1, 2, 3)
STOPS = (1.0, 2.0, 3.0)
TARGETS = ((0, 0.0), (1, 1.0), (1, 2.0), (2, 0.0))   # vwap, RR1, RR2, time
MINRISK = (25.0, 50.0, 100.0)
FLOW = (0, 1)
CROWD = (0, 1)
REVERT = (1, 0)


def grid():
    for anc, lvl, stop, (tm, rr), mr, fl, cr, rev in itertools.product(
            ANCHORS, LEVELS, STOPS, TARGETS, MINRISK, FLOW, CROWD, REVERT):
        yield {"anchor": anc, "entry_level": lvl, "stop_k": stop,
               "target_mode": tm, "rr": rr, "min_risk_bps": mr,
               "flow_mode": fl, "crowd_mode": cr, "revert": rev}


def families():
    """Configurations that share an anchor share the expensive VWAP build."""
    fam = {}
    for c in grid():
        fam.setdefault(c["anchor"], []).append(c)
    return fam


_D = {}


def _init(sym, tf):
    _D[(sym, tf)] = M.load(sym, tf, FEEDS)


def _one(df, vw, sd, na, atr, cvd, crowd, cfg):
    tr = simulate(df.open.values, df.high.values, df.low.values, df.close.values,
                  vw.values, sd.values, atr.values, cvd.values, crowd, na.values,
                  1.0, 2.0, 3.0, cfg["entry_level"], 0, cfg["flow_mode"], 0.0,
                  cfg["crowd_mode"], 0.0, 1, 5, cfg["revert"], cfg["stop_k"],
                  cfg["target_mode"], cfg["rr"], 96, 0,
                  M.FEE_BPS, M.SLIP_BPS, cfg["min_risk_bps"])
    return tr


def _job(args):
    sym, tf, anchor, cfgs, seed = args
    df = _D[(sym, tf)]
    if seed is not None:
        base = df[["open", "high", "low", "close", "volume"]]
        sh = shuffle_market_paired(base, seed=null_seed(sym, tf, "h010", seed))
        df = df.assign(open=sh.open, high=sh.high, low=sh.low, close=sh.close,
                       volume=sh.volume)
    vw, sd, na = M.anchored(df, anchor)
    atr = M.atr(df)
    cvd = M.cvd_share(df)
    crowd = df.crowd.values
    span = max((df.index[-1] - df.index[0]).days, 1)
    rows = []
    for cfg in cfgs:
        tr = _one(df, vw, sd, na, atr, cvd, crowd, cfg)
        if len(tr) < 40:
            continue
        gross = tr[:, 5]
        entry, risk = tr[:, 3], tr[:, 8]
        row = {"symbol": sym, "tf": tf, **cfg, "trades": int(len(tr)),
               "tpd": round(len(tr) / span, 3),
               "win_rate": round(float((gross > 0).mean()), 4),
               "avg_r": round(float(gross.mean()), 4)}
        # The kernel prices one round trip. Another cost multiple shifts every
        # trade by the same amount in PRICE, which is a different number of R
        # per trade, so it is repriced from the recorded risk rather than
        # scaled.
        for c in COSTS:
            extra = (c - 1.0) * (M.FEE_BPS + M.SLIP_BPS) * 2.0 / 1e4
            r = gross - extra * entry / risk
            row[f"pf_{c:.0f}x"] = round(M.pf_of(r), 4)
            if c == 2.0:
                row["maxdd_r_2x"] = round(M.max_dd(r), 2)
                row["total_r_2x"] = round(float(r.sum()), 1)
        rows.append(row)
    return rows


def main():
    syms = sys.argv[1:] or list(SYMS)
    real, null = [], []
    fam = families()
    n_cfg = sum(len(v) for v in fam.values())
    for sym in syms:
        for tf in TFS:
            try:
                _init(sym, tf)
            except FileNotFoundError:
                continue
            t0 = time.time()
            tasks = [(sym, tf, a, c, None) for a, c in fam.items()]
            tasks += [(sym, tf, a, c, s) for a, c in fam.items()
                      for s in range(NSEEDS)]
            with ProcessPoolExecutor(WORKERS, initializer=_init,
                                     initargs=(sym, tf)) as ex:
                for (t, rows) in zip(tasks, ex.map(_job, tasks, chunksize=1)):
                    (null if t[4] is not None else real).extend(rows)
            print(f"  {sym} {tf}: {n_cfg} configs x {NSEEDS+1} runs "
                  f"[{time.time()-t0:.0f}s]", flush=True)

    if not real:
        print("nothing ran"); return
    R, N = pd.DataFrame(real), pd.DataFrame(null)
    R.to_csv(OUT / "stage1_real.csv", index=False)
    N.to_csv(OUT / "stage1_null.csv", index=False)

    print("\n" + "=" * 86)
    print("REVERT (the hypothesis) vs CONTINUE (the control) vs NULL")
    print("=" * 86)
    for c in COSTS:
        k = f"pf_{c:.0f}x"
        rev = R[R.revert == 1][k].dropna()
        con = R[R.revert == 0][k].dropna()
        nl = N[N.revert == 1][k].dropna()
        # the null has NSEEDS rows per configuration, so the counts are divided
        # back down - comparing raw counts would flatter the real data fivefold
        print(f"  cost {c:.0f}x   revert med {rev.median():.3f} "
              f">1.0 {(rev > 1).mean():5.1%} clears {int((rev >= GATE).sum()):4d}"
              f"  |  continue med {con.median():.3f} >1.0 {(con > 1).mean():5.1%} "
              f"clears {int((con >= GATE).sum()):4d}"
              f"  |  null med {nl.median():.3f} >1.0 {(nl > 1).mean():5.1%} "
              f"clears {(nl >= GATE).sum()/NSEEDS:6.1f} per seed")

    print("\nREVERT ONLY, best 12 by PF at 2x cost")
    cols = ["symbol", "tf", "anchor", "entry_level", "stop_k", "target_mode", "rr",
            "min_risk_bps", "flow_mode", "crowd_mode", "trades", "tpd", "win_rate",
            "pf_0x", "pf_1x", "pf_2x", "pf_3x", "maxdd_r_2x"]
    print(R[R.revert == 1].sort_values("pf_2x", ascending=False).head(12)[cols]
          .to_string(index=False))
    print("\nCONTINUE ONLY, best 12 by PF at 2x cost")
    print(R[R.revert == 0].sort_values("pf_2x", ascending=False).head(12)[cols]
          .to_string(index=False))

    print("\nWHAT EACH LEVER DOES (revert only, median PF at 2x)")
    for lev in ("anchor", "entry_level", "stop_k", "target_mode", "min_risk_bps",
                "flow_mode", "crowd_mode", "tf"):
        g = R[R.revert == 1].groupby(lev).pf_2x.median().round(3)
        print(f"  {lev:14s} " + "  ".join(f"{k}={v}" for k, v in g.items()))
    print(f"\nwrote {OUT/'stage1_real.csv'}")


if __name__ == "__main__":
    main()
