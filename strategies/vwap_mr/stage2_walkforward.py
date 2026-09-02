"""H-010 walk-forward and board record.

Stage 1 rejected this outright: the paired null clears the 1.20 gate at double
cost 637 times per seed against the hypothesis's 280, and its median profit
factor is HIGHER than the real market's at every cost level. The walk-forward is
run anyway so H-010 is scored on the same basis as everything else and appears
on the board. A rejected idea that is invisible is not part of the denominator.

Run: .venv/bin/python strategies/vwap_mr/stage2_walkforward.py
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
from strategies.vwap_mr import vwap_mr as M                         # noqa: E402
from strategies.vwap_mr.engine import simulate                      # noqa: E402
from strategies.vwap_mr.stage1_grid import (FEEDS, OUT, SYMS, TFS,  # noqa: E402
                                            grid, families, GATE)

TRAIN_Q, MIN_TRAIN, WORKERS = 4, 30, 6
CFGKEY = ["anchor", "entry_level", "stop_k", "target_mode", "rr",
          "min_risk_bps", "flow_mode", "crowd_mode", "revert"]

_D = {}


def _init(sym, tf):
    _D[(sym, tf)] = M.load(sym, tf, FEEDS)


def _job(args):
    sym, tf, anchor, cfgs = args
    df = _D[(sym, tf)]
    vw, sd, na = M.anchored(df, anchor)
    atr, cvd = M.atr(df), M.cvd_share(df)
    crowd = df.crowd.values
    out = []
    for cfg in cfgs:
        if cfg["revert"] != 1:          # the board scores the hypothesis, not the control
            continue
        tr = simulate(df.open.values, df.high.values, df.low.values, df.close.values,
                      vw.values, sd.values, atr.values, cvd.values, crowd, na.values,
                      1.0, 2.0, 3.0, cfg["entry_level"], 0, cfg["flow_mode"], 0.0,
                      cfg["crowd_mode"], 0.0, 1, 5, 1, cfg["stop_k"],
                      cfg["target_mode"], cfg["rr"], 96, 0,
                      M.FEE_BPS, M.SLIP_BPS, cfg["min_risk_bps"])
        if len(tr) < 20:
            continue
        entry, risk, gross = tr[:, 3], tr[:, 8], tr[:, 5]
        step = (M.FEE_BPS + M.SLIP_BPS) * 2.0 / 1e4 * entry / risk
        d = pd.DataFrame({
            "symbol": sym, "tf": tf,
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
        st = train.groupby(CFGKEY, dropna=False).r_2x.agg(["size", M.pf_of])
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
                       "test_pf": round(M.pf_of(sel.r.values), 4),
                       "test_pf_2x": round(M.pf_of(sel.r_2x.values), 4)})
    return (pd.concat(out, ignore_index=True) if out else pd.DataFrame(),
            pd.DataFrame(picked))


def main():
    fam = families()
    per, folds = {}, []
    for sym in SYMS:
        for tf in TFS:
            try:
                _init(sym, tf)
            except FileNotFoundError:
                continue
            t0 = time.time()
            tasks = [(sym, tf, a, c) for a, c in fam.items()]
            with ProcessPoolExecutor(WORKERS, initializer=_init,
                                     initargs=(sym, tf)) as ex:
                got = [g for g in ex.map(_job, tasks, chunksize=1) if g is not None]
            if not got:
                continue
            st, fd = walkforward(pd.concat(got, ignore_index=True))
            if st.empty:
                continue
            per[f"{sym} {tf}"] = st
            fd["symbol"], fd["tf"] = sym, tf
            folds.append(fd)
            print(f"  {sym} {tf}: {len(st)} out-of-sample trades "
                  f"PF@2x {M.pf_of(st.r_2x.values):.3f} [{time.time()-t0:.0f}s]",
                  flush=True)
    if not per:
        print("no folds resolved"); return
    stitched = pd.concat(per.values(), ignore_index=True).sort_values("exit_ts")
    fdf = pd.concat(folds, ignore_index=True)
    stitched.to_parquet(OUT / "stage2_trades.parquet", index=False)
    fdf.to_csv(OUT / "stage2_folds.csv", index=False)

    n = len(per)
    r, r2 = stitched.r.values / n, stitched.r_2x.values / n
    print(f"\nBOOK of {n} market/timeframes: {len(stitched)} trades  "
          f"PF {M.pf_of(r):.3f}  PF@2x {M.pf_of(r2):.3f}")

    real = pd.read_csv(OUT / "stage1_real.csv")
    null = pd.read_csv(OUT / "stage1_null.csv")
    rc = int((real[real.revert == 1].pf_2x >= GATE).sum())
    nc = (null[null.revert == 1].pf_2x >= GATE).sum() / 5.0
    board.write_board(
        sid="vwap_mr", hid="H-010", name="VWAP band rejection",
        tagline="Price stretches to a standard-deviation band, closes back, and is faded.",
        period="BTC/ETH/SOL perpetuals · 15m-4h · 2020 → 2026-08",
        report="", candidate="config re-chosen blind each quarter on 2x-cost train PF",
        r=r, r_2x=r2, entry_ts=stitched.entry_ts, exit_ts=stitched.exit_ts,
        n_books=n, null_margin=0.0, beats_null=False,
        consistency=float((fdf.test_pf > 1).mean()) if len(fdf) else 0.0,
        markets={"traded": [{"sym": k.split()[0], "tf": k.split()[1],
                             "asset": k[:3]} for k in per],
                 "searched": "3 coins x 4 timeframes x 2,592 configurations",
                 "note": "Rebuilt from a published TradingView indicator with honest "
                         "fills, the exchange's real taker split instead of a "
                         "sign-of-the-bar guess, exits, and a control that takes "
                         "every setup the other way."},
        grid={"title": "The hypothesis against its control and its null",
              "note": "Median profit factor across the whole grid. The null is a "
                      "paired shuffle of the market, five seeds.",
              "cols": ["revert", "continue", "null"], "label": "Cost",
              "rows": [{"label": f"{c:.0f}x cost",
                        "cols": [float(real[real.revert == 1][f"pf_{c:.0f}x"].median()),
                                 float(real[real.revert == 0][f"pf_{c:.0f}x"].median()),
                                 float(null[null.revert == 1][f"pf_{c:.0f}x"].median())],
                        "worst": float(real[real.revert == 1][f"pf_{c:.0f}x"].median()),
                        "clears": False}
                       for c in (0.0, 1.0, 2.0, 3.0)]},
        todo=[
            {"t": "Honest fills", "w": "Market on the next open, never a resting limit at the band — the artefact that killed this family before.", "done": True},
            {"t": "Real taker split", "w": "The exchange's own taker_buy volume, not volume x sign(close-open).", "done": True},
            {"t": "Direction control", "w": "Every setup also taken the other way; continuation scores no better and both sit at the null.", "done": True},
            {"t": "Paired-shuffle null", "w": "The null's median profit factor is HIGHER than the real market's at every cost level.", "done": True},
            {"t": "Walk-forward", "w": "Run for board parity, not because stage 1 justified it.", "done": True},
        ],
        note=(f"Rejected. Across 3 coins x 4 timeframes x 2,592 configurations the "
              f"paired null clears PF {GATE} at double cost {nc:.0f} times per seed "
              f"against the hypothesis's {rc}, and the null's MEDIAN profit factor is "
              f"higher than the real market's at 0x, 1x, 2x and 3x cost. The control "
              f"is as damning: taking every setup the other way scores no worse. And "
              f"the lever table refutes the mechanism directly - exiting at the VWAP, "
              f"which is the whole idea, is the single most harmful choice in the "
              f"grid (median 0.500) while ignoring the VWAP and exiting on time is "
              f"the best (0.816). The best-looking configurations trade 0.018 times a "
              f"day, one every two months, which is search noise and fails the phase "
              f"constraint on its own. This is the same family as the prior repo's "
              f"dead `VWAP std-band fade`, which backtested at 3.0 and traded at 0.7 "
              f"on a limit-fill artefact; with honest fills it does not even reach "
              f"the artefact. One positive: the H-009 crowd gate lifts even this "
              f"(0.659 to 0.712), a third independent confirmation of that finding."))


if __name__ == "__main__":
    main()
