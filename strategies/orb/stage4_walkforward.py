"""ORB stage 4 — anchored-quarter walk-forward.

Train on the trailing 12 months, pick the best config by profit factor (with a
trade-count floor), trade it for the next 3 months, roll. Nothing is chosen with
knowledge of the quarter it is traded in. This is the test that a single
top-of-the-grid IS number cannot fake.
"""
from __future__ import annotations

import sys, time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from core import data                                          # noqa: E402
from strategies.orb.sweep import sweep, features, run_one, trade_metrics  # noqa: E402
from strategies.orb.deep_test import build_grid, FEE_BPS, SLIP_BPS, OUT   # noqa: E402

TRAIN_MONTHS, TEST_MONTHS = 12, 3
MIN_TRAIN_TRADES = 100


def main():
    df = data.load("BTC/USDT", "15m")
    cfgs = build_grid()
    print(f"configs {len(cfgs)}", flush=True)

    starts = pd.date_range("2019-01-01", "2026-07-01", freq=f"{TEST_MONTHS}MS", tz="UTC")
    rows, picks = [], []

    for t0 in starts:
        tr_lo = t0 - pd.DateOffset(months=TRAIN_MONTHS)
        te_hi = t0 + pd.DateOffset(months=TEST_MONTHS)
        train = df[(df.index >= tr_lo) & (df.index < t0)]
        test = df[(df.index >= t0) & (df.index < te_hi)]
        if len(train) < 1000 or len(test) < 500:
            continue

        t = time.time()
        r = sweep(train, cfgs, fee_bps=FEE_BPS, slip_bps=SLIP_BPS, label="train")
        elig = r[(r.trades >= MIN_TRAIN_TRADES) & r.pf.notna()]
        if elig.empty:
            continue
        best = elig.sort_values("pf", ascending=False).iloc[0]
        cfg = {k: best[k] for k in cfgs[0]}

        feats = features(test)
        tr_arr = run_one(test, feats, cfg, FEE_BPS, SLIP_BPS)
        span = (test.index[-1] - test.index[0]).total_seconds() / 86400.0
        m = trade_metrics(tr_arr, test.index, span)

        row = dict(cfg)
        row.update({f"test_{k}": v for k, v in m.items()})
        row.update(quarter=str(t0.date()), train_pf=best.pf, train_trades=int(best.trades))
        rows.append(row)
        picks.append(tr_arr[:, 5] if len(tr_arr) else np.array([]))
        print(f"{t0.date()}  train pf {best.pf:.2f} -> test pf "
              f"{m['pf']:.2f} ({m['trades']} trades)  [{time.time()-t:.0f}s]", flush=True)

    wf = pd.DataFrame(rows)
    wf.to_csv(OUT / "stage4_walkforward.csv", index=False)

    all_r = np.concatenate([p for p in picks if len(p)]) if any(len(p) for p in picks) else np.array([])
    if len(all_r):
        wins, losses = all_r[all_r > 0].sum(), -all_r[all_r < 0].sum()
        print(f"\nSTITCHED OOS: {len(all_r)} trades  PF {wins/losses if losses else float('inf'):.3f}  "
              f"win {100*(all_r>0).mean():.1f}%  total {all_r.sum():.1f}R  "
              f"quarters PF>1: {int((wf.test_pf > 1).sum())}/{len(wf)}")
    print("saved", OUT / "stage4_walkforward.csv")


if __name__ == "__main__":
    main()
