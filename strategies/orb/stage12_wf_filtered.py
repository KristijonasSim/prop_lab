"""ORB stage 12 — walk-forward the FILTERED family.

Stage 11 found a configuration that is positive in eight of nine years and in
both directions. It is also the best of 11,583 paired configurations, so its
year-by-year record is post-hoc. The only way to know whether the filtered ORB
is choosable in advance is to choose it in advance, every quarter, blind.
"""
from __future__ import annotations

import sys, time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from core import data as crypto_data                            # noqa: E402
from strategies.orb.sweep import sweep, features, run_one, trade_metrics  # noqa: E402
from strategies.orb.deep_test import OUT                        # noqa: E402
from strategies.orb.stage7_assets import ASSETS                 # noqa: E402
from strategies.orb.stage11_combine import combos, KEYS         # noqa: E402
from strategies.orb.stage9_anchors import base_grid             # noqa: E402

ANCHORS = [(13, 0), (13, 30)]
MIN_TRAIN_TRADES = 40


def build():
    cfgs = []
    for h, m in ANCHORS:
        for base in base_grid(h, m):
            for over in combos():
                c = dict(base)
                c.update(over)
                c["min_risk_bps"] = ASSETS["BTCUSDT"][2]
                cfgs.append(c)
    return cfgs


def main():
    fee, slip, _ = ASSETS["BTCUSDT"]
    df = crypto_data.load("BTC/USDT", "15m")
    df = df[df.index >= "2018-01-01"]
    cfgs = build()
    print(f"{len(cfgs)} filtered configs", flush=True)

    starts = pd.date_range("2019-01-01", "2026-07-01", freq="3MS", tz="UTC")
    rows, all_r = [], []
    for t0 in starts:
        train = df[(df.index >= t0 - pd.DateOffset(months=12)) & (df.index < t0)]
        test = df[(df.index >= t0) & (df.index < t0 + pd.DateOffset(months=3))]
        if len(train) < 1000 or len(test) < 500:
            continue
        t = time.time()
        r = sweep(train, cfgs, fee_bps=fee, slip_bps=slip)
        elig = r[(r.trades >= MIN_TRAIN_TRADES) & r.pf.notna()]
        if elig.empty:
            continue
        best = elig.sort_values("pf", ascending=False).iloc[0]
        cfg = {k: best[k] for k in cfgs[0]}
        feats = features(test)
        tr = run_one(test, feats, cfg, fee, slip)
        span = (test.index[-1] - test.index[0]).total_seconds() / 86400.0
        mt = trade_metrics(tr, test.index, span)
        rows.append({"quarter": str(t0.date()), "train_pf": round(float(best.pf), 3),
                     "train_trades": int(best.trades), **{f"test_{k}": v for k, v in mt.items()}})
        if len(tr):
            all_r.append(tr[:, 5])
        print(f"{t0.date()}  train {best.pf:.2f} -> test {mt['pf']:.2f} "
              f"({mt['trades']} trades)  [{time.time()-t:.0f}s]", flush=True)

    wf = pd.DataFrame(rows)
    wf.to_csv(OUT / "stage12_wf_filtered.csv", index=False)
    r = np.concatenate([x for x in all_r if len(x)]) if all_r else np.array([])
    if len(r):
        w, l = r[r > 0].sum(), -r[r < 0].sum()
        print(f"\nSTITCHED: {len(r)} trades  PF {w/l if l else float('inf'):.3f}  "
              f"win {100*(r>0).mean():.1f}%  total {r.sum():+.1f}R  "
              f"quarters PF>1: {int((wf.test_pf > 1).sum())}/{len(wf)}", flush=True)


if __name__ == "__main__":
    main()
