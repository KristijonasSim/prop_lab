"""H-017 stage 20 - the non-crypto legs the wide book never had.

H-017 reaches 28.5 expected days and the target is 14, so the gap is 2x on K.
K scales as sqrt(number of INDEPENDENT legs) - stage 1 measured the exponent at
0.441 - and the wide book is **entirely crypto perps**. Eleven coins that all
trade the same risk appetite are not eleven independent bets; HANDOFF records
the crypto/gold leg correlation at **0.023**, effectively zero, which is a far
better diversifier than an eleventh altcoin.

So this runs the identical kernel, the identical walk-forward and the identical
top-1/3/10 widths on everything that is NOT a crypto perp: gold, silver, oil,
the three US indices and six FX majors, on five timeframes. Nothing is
re-tuned. These legs get no crowd gate, because no positioning feed exists for
them - which also means they cannot inherit whatever the gate is fitting.

Stage 3 already ran a version of this on 5m and 15m and found only 2 of 26 legs
clearing PF 1.20. That was at top-10 width, where each trade's R is divided by
ten; at top-1 the per-trade edge is 12x larger and the picture may differ. If
it does not, that is the answer and the wide book stays crypto-only.

Output: backtests/xpos/stage20_trades.parquet, stage20_legs.csv
"""
from __future__ import annotations

import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from core import fx_data                                            # noqa: E402
from strategies.vwap.stage6_walkforward import (TEST_MONTHS,        # noqa: E402
                                                TRAIN_MONTHS, _pf,
                                                _slice_with_pad)
from strategies.vwap.sweep import features                          # noqa: E402
from strategies.xpos.stage10_wide import _run_dir                   # noqa: E402
from strategies.xpos.stage3_fastbook import COSTS, fast_grid        # noqa: E402

OUT = ROOT / "backtests" / "xpos"
TFS = {"15min": 4.0, "30min": 2.0, "1h": 1.0, "2h": 0.5, "4h": 0.25}
MARKETS = list(COSTS)                      # metals, oil, indices, FX majors
FLOOR, TOPNS = 100, (1, 3, 10)


def _panel(args):
    sym, tf = args
    try:
        df = fx_data.build_tf(sym, tf)
    except Exception as e:                                  # noqa: BLE001
        return None, f"{sym} {tf}: {e}"
    if len(df) < 5000:
        return None, f"{sym} {tf}: {len(df)} bars"

    bph = TFS[tf]
    fee, slip, minrisk = COSTS[sym]
    cfgs = fast_grid(bph)
    for c in cfgs:
        c["min_risk_bps"] = minrisk
    feats = features(df)
    pad = int(6 * 24 * bph)

    q0 = (df.index[0] + pd.DateOffset(months=TRAIN_MONTHS))
    q0 = (q0 + pd.offsets.QuarterBegin(startingMonth=1)).normalize()
    out = []
    for t0 in pd.date_range(q0, df.index[-1], freq="QS", tz="UTC"):
        te_hi = t0 + pd.DateOffset(months=TEST_MONTHS)
        if te_hi > df.index[-1]:
            break
        train, f_tr, p_tr = _slice_with_pad(
            df, feats, t0 - pd.DateOffset(months=TRAIN_MONTHS), t0, pad)
        test, f_te, p_te = _slice_with_pad(df, feats, t0, te_hi, pad)
        if len(train) < 3000 or len(test) - p_te < 300:
            continue

        vw = {}
        pfs = np.full(len(cfgs), np.nan)
        cnt = np.zeros(len(cfgs), dtype=int)
        for ci, cfg in enumerate(cfgs):
            r, _, _, _ = _run_dir(train, f_tr, p_tr, cfg, fee * 2, slip * 2, vw)
            cnt[ci] = len(r)
            if len(r):
                pfs[ci] = _pf(r)
        el = np.flatnonzero((cnt >= FLOOR) & np.isfinite(pfs))
        if not el.size:
            continue
        order = el[np.argsort(-pfs[el])]

        v1, v2, cache = {}, {}, {}
        for topn in TOPNS:
            pick = order[:topn]
            rs, r2s, ex, en, ds = [], [], [], [], []
            for ci in pick:
                if ci not in cache:
                    a = _run_dir(test, f_te, p_te, cfgs[ci], fee, slip, v1)
                    b, _, _, _ = _run_dir(test, f_te, p_te, cfgs[ci], fee * 2,
                                          slip * 2, v2)
                    cache[ci] = (a, b)
                (r1c, e1, n1, d1), r2c = cache[ci]
                if not len(r1c) or len(r2c) != len(r1c):
                    continue
                rs.append(r1c / len(pick)); r2s.append(r2c / len(pick))
                ex.append(e1); en.append(n1); ds.append(d1)
            if not rs:
                continue
            r1 = np.concatenate(rs); r2 = np.concatenate(r2s)
            e = np.concatenate(ex); n = np.concatenate(en)
            dv = np.concatenate(ds)
            o = np.argsort(e, kind="stable")
            out.append(pd.DataFrame({
                "symbol": sym, "tf": tf, "topn": topn,
                "quarter": str(t0.date()),
                "entry_ts": test.index[n[o]], "exit_ts": test.index[e[o]],
                "direction": dv[o], "r": r1[o], "r_2x": r2[o]}))

    if not out:
        return None, f"{sym} {tf}: no folds"
    tr = pd.concat(out, ignore_index=True)
    tr["crowd_z"] = np.nan          # no positioning feed for these markets
    one = tr[tr.topn == 1]
    return tr, (f"{sym} {tf}: {len(one)} top-1 trades, "
                f"PF2x {_pf(one.r_2x.values):.3f}")


def main() -> int:
    combos = [(s, tf) for s in MARKETS for tf in TFS]
    frames, t0 = [], time.time()
    with ProcessPoolExecutor(max_workers=14) as ex:
        futs = {ex.submit(_panel, c): c for c in combos}
        for fu in as_completed(futs):
            tr, msg = fu.result()
            if tr is not None:
                frames.append(tr)
            print(f"  [{time.time()-t0:5.0f}s] {msg}", flush=True)

    tr = pd.concat(frames, ignore_index=True)
    tr.to_parquet(OUT / "stage20_trades.parquet")

    rows = []
    for (s, tf, topn), g in tr.groupby(["symbol", "tf", "topn"]):
        r = g.r_2x.values
        eq = np.concatenate(([0.0], np.cumsum(r)))
        dd = float((eq - np.maximum.accumulate(eq)).min())
        span = max((g.exit_ts.max() - g.entry_ts.min()).days, 1)
        rows.append({"symbol": s, "tf": tf, "topn": topn, "trades": len(g),
                     "pf_2x": round(_pf(r), 3), "avg_r": round(float(r.mean()), 4),
                     "tpd": round(len(g) / span, 3), "max_dd_r": round(dd, 2),
                     "K": round((r.sum() / span) / abs(dd), 5)
                     if dd < 0 and r.sum() > 0 else np.nan})
    legs = pd.DataFrame(rows)
    legs.to_csv(OUT / "stage20_legs.csv", index=False)
    print(f"\n{len(legs)} leg x width rows, {time.time()-t0:.0f}s")
    for tn in TOPNS:
        d = legs[legs.topn == tn]
        print(f"  topn={tn}: {(d.pf_2x >= 1.2).sum()}/{len(d)} clear PF 1.20 | "
              f"median avg_R {d.avg_r.median():.4f} | median K {d.K.median():.5f}")
    top = legs[legs.topn == 1].nlargest(15, "K")
    print("\nbest top-1 non-crypto legs by K:")
    print(top.to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
