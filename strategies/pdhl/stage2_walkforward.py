"""H-011 walk-forward and board record.

Stage 1 did something none of the other fade hypotheses managed: the real market
beat its paired null at EVERY cost level, and the fade beat its own control.

  cost   revert   continue   null      clears 1.20 at 2x
   0x     1.052     0.867    0.926     revert 952 | null 436 per seed
   2x     0.739     0.592    0.658

That is the opposite of H-005, whose null cleared the gate eleven times more
often than the real market did, and of H-010, whose null had a higher median
than the real market. The schelling-point version of "fade the extreme" is not
the same object as the rolling-lookback version.

It is still a median of 0.739 at double cost. This asks the only question that
matters after that: does a configuration chosen BLIND each quarter hold the gate
out of sample, or is the null margin just a better-shaped pile of noise?

Run: .venv/bin/python strategies/pdhl/stage2_walkforward.py
"""
from __future__ import annotations

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

from core import board                                              # noqa: E402
from strategies.pdhl import pdhl as P                               # noqa: E402
from strategies.pdhl.engine import simulate                         # noqa: E402
from strategies.pdhl.stage1_grid import (FEEDS, OUT, SYMS, TFS,     # noqa: E402
                                         grid, GATE, WORKERS)
from strategies.vwap.stage3_timeframes import (shuffle_market_paired,  # noqa: E402
                                               null_seed)

TRAIN_Q, MIN_TRAIN, NSEEDS = 4, 30, 5
CFGKEY = ["level", "min_pen", "max_pen", "close_frac", "conf", "stop_buf",
          "target_mode", "rr", "min_risk_bps"]

_D = {}


def _init(sym, tf):
    _D[(sym, tf)] = P.load(sym, tf, FEEDS)


def _job(args):
    sym, tf, seed, cfgs = args
    df = _D[(sym, tf)]
    if seed is not None:
        base = df[["open", "high", "low", "close", "volume"]]
        sh = shuffle_market_paired(base, seed=null_seed(sym, tf, "h011wf", seed))
        df = df.assign(open=sh.open, high=sh.high, low=sh.low, close=sh.close,
                       volume=sh.volume)
    lv = P.levels(df)
    a, cvd, doi = P.atr(df), P.cvd_share(df), P.d_oi(df, 3)
    o, hh, ll, cc = df.open.values, df.high.values, df.low.values, df.close.values
    crowd = df.crowd.values
    out = []
    for cfg in cfgs:
        if cfg["revert"] != 1:
            continue
        hi = lv.pdh.values if cfg["level"] == "day" else lv.pwh.values
        lo = lv.pdl.values if cfg["level"] == "day" else lv.pwl.values
        conf = cfg["conf"]
        tr = simulate(o, hh, ll, cc, a.values, hi, lo, lv.mid.values, hi, lo,
                      doi.values, cvd.values, crowd, lv.day_i.values,
                      cfg["min_pen"], cfg["max_pen"], cfg["close_frac"],
                      1 if "oi" in conf else 0, 0.0,
                      1 if "flow" in conf else 0,
                      1 if "crowd" in conf else 0,
                      1, 1, cfg["stop_buf"], cfg["target_mode"], cfg["rr"], 96,
                      P.FEE_BPS, P.SLIP_BPS, cfg["min_risk_bps"])
        if len(tr) < 20:
            continue
        entry, risk, gross = tr[:, 3], tr[:, 7], tr[:, 5]
        step = (P.FEE_BPS + P.SLIP_BPS) * 2.0 / 1e4 * entry / risk
        d = pd.DataFrame({"symbol": sym, "tf": tf,
                          "entry_ts": df.index[tr[:, 0].astype(int)],
                          "exit_ts": df.index[tr[:, 1].astype(int)],
                          "r": gross, "r_2x": gross - step, "r_3x": gross - 2 * step})
        for k in CFGKEY:
            d[k] = cfg[k]
        out.append(d)
    return pd.concat(out, ignore_index=True) if out else None


def walkforward(tr):
    if tr is None or tr.empty:
        return pd.DataFrame(), pd.DataFrame()
    tr = tr.sort_values("exit_ts").copy()
    tr["quarter"] = tr.exit_ts.dt.to_period("Q")
    qs = sorted(tr.quarter.unique())
    picked, out = [], []
    for qi in range(TRAIN_Q, len(qs)):
        q = qs[qi]
        train, test = tr[tr.quarter < q], tr[tr.quarter == q]
        if train.empty or test.empty:
            continue
        st = train.groupby(CFGKEY, dropna=False).r_2x.agg(["size", P.pf_of])
        st.columns = ["n", "pf2x"]
        st = st[st.n >= MIN_TRAIN]
        if st.empty:
            continue
        best = st.pf2x.idxmax()
        sel = test
        for k, v in zip(CFGKEY, best):
            sel = sel[sel[k] == v]
        if sel.empty:
            continue
        out.append(sel)
        picked.append({"quarter": str(q), **dict(zip(CFGKEY, best)),
                       "train_pf_2x": round(float(st.pf2x.max()), 4),
                       "test_trades": len(sel),
                       "test_pf": round(P.pf_of(sel.r.values), 4),
                       "test_pf_2x": round(P.pf_of(sel.r_2x.values), 4)})
    return (pd.concat(out, ignore_index=True) if out else pd.DataFrame(),
            pd.DataFrame(picked))


def run_panel(sym, tf, cfgs, seed=None):
    chunks = [cfgs[i::WORKERS] for i in range(WORKERS)]
    tasks = [(sym, tf, seed, ch) for ch in chunks]
    with ProcessPoolExecutor(WORKERS, initializer=_init, initargs=(sym, tf)) as ex:
        got = [g for g in ex.map(_job, tasks, chunksize=1) if g is not None]
    if not got:
        return pd.DataFrame(), pd.DataFrame()
    return walkforward(pd.concat(got, ignore_index=True))


def main():
    cfgs = [c for c in grid() if c["revert"] == 1]
    per, folds = {}, []
    for sym in SYMS:
        for tf in TFS:
            try:
                _init(sym, tf)
            except FileNotFoundError:
                continue
            t0 = time.time()
            st, fd = run_panel(sym, tf, cfgs)
            if st.empty:
                continue
            per[f"{sym} {tf}"] = st
            fd["symbol"], fd["tf"] = sym, tf
            folds.append(fd)
            print(f"  {sym} {tf}: {len(st)} out-of-sample  "
                  f"PF@2x {P.pf_of(st.r_2x.values):.3f} [{time.time()-t0:.0f}s]",
                  flush=True)
    if not per:
        print("no folds resolved"); return
    stitched = pd.concat(per.values(), ignore_index=True).sort_values("exit_ts")
    fdf = pd.concat(folds, ignore_index=True)
    stitched.to_parquet(OUT / "stage2_trades.parquet", index=False)
    fdf.to_csv(OUT / "stage2_folds.csv", index=False)

    # the tradeable subset, chosen the way stage 11 chooses H-002's: keep a
    # panel only if it holds the gate at DOUBLE cost on its own
    keep = [k for k, v in per.items() if P.pf_of(v.r_2x.values) >= GATE]
    print(f"\npanels holding PF {GATE} at 2x on their own: {len(keep)} of {len(per)}"
          f"  {keep}")
    use = keep if keep else list(per)
    sel = pd.concat([per[k] for k in use], ignore_index=True).sort_values("exit_ts")
    n = len(use)
    r, r2 = sel.r.values / n, sel.r_2x.values / n
    print(f"BOOK of {n}: {len(sel)} trades  PF {P.pf_of(r):.3f}  "
          f"PF@2x {P.pf_of(r2):.3f}  maxDD {P.max_dd(r):.2f}R")

    null_pf2 = []
    for seed in range(NSEEDS):
        parts = []
        for k in use:
            s2, _f = run_panel(k.split()[0], k.split()[1], cfgs, seed=seed)
            if not s2.empty:
                parts.append(s2)
        if parts:
            s2 = pd.concat(parts, ignore_index=True)
            p = P.pf_of(s2.r_2x.values / len(parts))
            null_pf2.append(p)
            print(f"  null seed {seed}: PF@2x {p:.3f} ({len(s2)} trades)", flush=True)
    real2 = P.pf_of(r2)
    beats = bool(null_pf2) and real2 > max(null_pf2)
    margin = 0.0 if not null_pf2 or real2 <= 0 else max(
        0.0, (real2 - float(np.median(null_pf2))) / real2)
    print(f"\nreal PF@2x {real2:.3f} vs null median "
          f"{np.median(null_pf2) if null_pf2 else float('nan'):.3f} / "
          f"best {max(null_pf2) if null_pf2 else float('nan'):.3f}")
    print(f"beats every null seed: {beats}")

    g1 = pd.read_csv(OUT / "stage1_real.csv")
    n1 = pd.read_csv(OUT / "stage1_null.csv")
    board.write_board(
        sid="pdhl", hid="H-011", name="Previous day/week high-low reversal",
        tagline="Fade the sweep of the one level every trader sees the same way.",
        period="BTC/ETH/SOL perpetuals · 15m-4h · 2020 → 2026-08",
        report="", candidate="config re-chosen blind each quarter on 2x-cost train PF",
        r=r, r_2x=r2, entry_ts=sel.entry_ts, exit_ts=sel.exit_ts, n_books=n,
        null_margin=margin, beats_null=beats,
        consistency=float((fdf.test_pf > 1).mean()) if len(fdf) else 0.0,
        legs=board.leg_payload(
            sel.assign(sym=sel.symbol)[["sym", "tf", "exit_ts", "r", "r_2x"]],
            picked=[(k.split()[0], k.split()[1]) for k in use], cap=None),
        markets={"traded": [{"sym": k.split()[0], "tf": k.split()[1],
                             "asset": k[:3]} for k in use],
                 "searched": "3 coins x 4 timeframes x 3,840 configurations",
                 "note": "The level is the previous day's or week's high and low - "
                         "the one set of prices every trader sees identically, which "
                         "is where resting stops actually sit. H-005 faded a rolling "
                         "10-100 bar extreme instead and lost badly to its null."},
        grid={"title": "The hypothesis, its control and its null",
              "note": "Median profit factor across the whole grid. CONTINUE takes "
                      "every setup the other way for the same risk; the null is a "
                      "paired shuffle of the market, five seeds.",
              "cols": ["revert", "continue", "null"], "label": "Cost",
              "rows": [{"label": f"{c:.0f}x cost",
                        "cols": [float(g1[g1.revert == 1][f"pf_{c:.0f}x"].median()),
                                 float(g1[g1.revert == 0][f"pf_{c:.0f}x"].median()),
                                 float(n1[n1.revert == 1][f"pf_{c:.0f}x"].median())],
                        "worst": float(g1[g1.revert == 1][f"pf_{c:.0f}x"].median()),
                        "clears": bool(g1[g1.revert == 1][f"pf_{c:.0f}x"].median() >= GATE)}
                       for c in (0.0, 1.0, 2.0, 3.0)]},
        todo=[
            {"t": "Schelling-point level", "w": "Previous day and week extremes, not a rolling lookback — the difference from the rejected H-005.", "done": True},
            {"t": "Direction control", "w": "Every setup taken the other way for the same risk; the fade beats it at every cost level.", "done": True},
            {"t": "Paired-shuffle null", "w": "Real beats null at 0x, 1x, 2x and 3x — the first fade hypothesis here to manage it.", "done": True},
            {"t": "Open interest across the sweep", "w": "Contracts closing means stops ran; contracts opening means a breakout.", "done": True},
            {"t": "Walk-forward", "w": "Config chosen blind each quarter on 2x-cost train PF.", "done": True},
            {"t": "NautilusTrader cross-check", "w": "No second engine has verified this kernel.", "done": False},
        ],
        note=None)


if __name__ == "__main__":
    main()
