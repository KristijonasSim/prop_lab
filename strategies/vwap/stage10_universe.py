"""H-002 stage 10 — does the surviving family extend to more markets?

The one scaling lever proven here is adding legs, so this re-runs the same
2x-cost-selected walk-forward over a wider universe: the original nine, plus
silver and the two largest alts. Nothing about the strategy changes; only the
list of markets it is offered.

Selection is by TRAIN profit factor at DOUBLE cost, the fix from stage 9 -
selecting on 1x and checking 2x afterwards is what let four fragile legs into the
book earlier.
"""
from __future__ import annotations

import sys, time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from core import data as crypto_data                               # noqa: E402
from core import fx_data                                           # noqa: E402
from strategies.vwap.stage1_grid import ASSETS, OUT                # noqa: E402
from strategies.vwap.stage3_timeframes import TFS, build_grid      # noqa: E402
from strategies.vwap.stage6_walkforward import (_slice_with_pad, _run, _pf,  # noqa: E402
                                                TRAIN_MONTHS, TEST_MONTHS,
                                                FLOORS, TOPN, CFGKEY)
from strategies.vwap.sweep import features                          # noqa: E402

CRYPTO = {"BTCUSDT": "BTC/USDT", "ETHUSDT": "ETH/USDT", "SOLUSDT": "SOL/USDT"}
EXTRA = {"ETHUSDT": (5.0, 2.0, 10.0), "SOLUSDT": (5.0, 3.0, 12.0),
         "XAGUSD": (1.5, 0.8, 4.0)}
COSTS = dict(ASSETS); COSTS.update(EXTRA)
FX_FIRST, CRYPTO_FIRST, LAST = "2024-09-01", "2019-01-01", "2026-07-01"


def load_tf(sym, tf):
    rule = TFS[tf][0]
    if sym in CRYPTO:
        if tf == "5m":
            return pd.DataFrame()
        base = crypto_data.load(CRYPTO[sym], "15m")
        if tf != "15m":
            base = base.resample(rule, label="left", closed="left").agg(
                {"open": "first", "high": "max", "low": "min",
                 "close": "last", "volume": "sum"}).dropna(subset=["open"])
        return base
    return fx_data.load(sym, rule)


def walk(sym, tf):
    try:
        df = load_tf(sym, tf)
    except Exception:
        return [], []
    if len(df) < 5000:
        return [], []
    fee, slip, minrisk = COSTS[sym]
    bph = TFS[tf][1]
    cfgs = build_grid(bph)
    for c in cfgs:
        c["min_risk_bps"] = minrisk
    feats = features(df)
    roll = max(20, int(round(24 * 4 * bph)))
    pad = int(roll * 2)
    first = CRYPTO_FIRST if sym in CRYPTO else FX_FIRST
    starts = pd.date_range(first, LAST, freq=f"{TEST_MONTHS}MS", tz="UTC")
    starts = starts[starts >= df.index[0] + pd.DateOffset(months=TRAIN_MONTHS)]

    folds, trades = [], []
    for t0 in starts:
        lo, hi = t0 - pd.DateOffset(months=TRAIN_MONTHS), t0 + pd.DateOffset(months=TEST_MONTHS)
        if hi > df.index[-1] + pd.Timedelta(1, unit="D"):
            continue
        # _slice_with_pad returns (frame, sliced features, pad length)
        train, f_tr, ptr = _slice_with_pad(df, feats, lo, t0, pad)
        test, f_te, pte = _slice_with_pad(df, feats, t0, hi, pad)
        if len(train) < 1000 or len(test) - pte < 200:
            continue
        t = time.time()
        vw2, vte, vte2 = {}, {}, {}
        pf2 = np.full(len(cfgs), np.nan)
        cnt = np.zeros(len(cfgs), dtype=int)
        for ci, cfg in enumerate(cfgs):
            r2, _, _ = _run(train, f_tr, ptr, cfg, fee * 2, slip * 2, vw2)
            cnt[ci] = len(r2)
            if len(r2):
                pf2[ci] = _pf(r2)
        span = (test.index[-1] - test.index[pte]).total_seconds() / 86400.0
        cache = {}
        for floor in FLOORS:
            el = np.flatnonzero((cnt >= floor) & np.isfinite(pf2))
            if not el.size:
                continue
            order = el[np.argsort(-pf2[el])]
            for topn in TOPN:
                pick = order[:topn]
                rs, ex, en, rs2 = [], [], [], []
                for ci in pick:
                    if ci not in cache:
                        a = _run(test, f_te, pte, cfgs[ci], fee, slip, vte)
                        b = _run(test, f_te, pte, cfgs[ci], fee * 2, slip * 2, vte2)
                        cache[ci] = (a, b)
                    (r1, e1, n1), (r2b, _, _) = cache[ci]
                    if not len(r1):
                        continue
                    rs.append(r1 / topn); ex.append(e1); en.append(n1)
                    rs2.append(r2b / topn if len(r2b) == len(r1) else r1 / topn)
                if not rs:
                    continue
                ra = np.concatenate(rs); ea = np.concatenate(ex)
                na = np.concatenate(en); r2a = np.concatenate(rs2)
                o = np.argsort(ea, kind="stable")
                ra, ea, na, r2a = ra[o], ea[o], na[o], r2a[o]
                folds.append({"symbol": sym, "tf": tf, "quarter": str(t0.date()),
                              "floor": floor, "topn": topn,
                              "train_pf_2x": round(float(pf2[pick[0]]), 3),
                              "test_trades": int(len(ra)),
                              "test_pf": round(_pf(ra), 3),
                              "test_pf_2x": round(_pf(r2a), 3),
                              **{k: cfgs[pick[0]][k] for k in CFGKEY},
                              "filter": cfgs[pick[0]]["filter"]})
                trades.append(pd.DataFrame({
                    "symbol": sym, "tf": tf, "quarter": str(t0.date()),
                    "floor": floor, "topn": topn,
                    "entry_ts": test.index[na], "exit_ts": test.index[ea],
                    "r": ra, "r_2x": r2a}))
        print(f"  {sym:8s} {tf:4s} {t0.date()} [{time.time()-t:.0f}s]", flush=True)
    return folds, trades


def _job(a):
    try:
        return walk(*a)
    except Exception as e:
        print(f"  !! {a}: {type(e).__name__}: {e}", flush=True)
        return [], []


def main():
    syms = list(ASSETS) + ["ETHUSDT", "SOLUSDT", "XAGUSD"]
    combos = [(s, tf) for s in syms for tf in TFS
              if not (s in CRYPTO and tf == "5m")]
    print(f"{len(combos)} combinations", flush=True)
    F, T = [], []
    with ProcessPoolExecutor(max_workers=12) as ex:
        futs = [ex.submit(_job, c) for c in combos]
        for fu in as_completed(futs):
            f, t = fu.result(); F.extend(f); T.extend(t)
    fdf = pd.DataFrame(F); fdf.to_parquet(OUT / "stage10_folds.parquet", index=False)
    tdf = pd.concat(T, ignore_index=True) if T else pd.DataFrame()
    tdf.to_parquet(OUT / "stage10_trades.parquet", index=False)
    rows = []
    for (s, tf, fl, tn), g in tdf.groupby(["symbol", "tf", "floor", "topn"]):
        g = g.sort_values("exit_ts")
        fq = fdf[(fdf.symbol == s) & (fdf.tf == tf) & (fdf.floor == fl) & (fdf.topn == tn)]
        sp = (g.exit_ts.iloc[-1] - g.exit_ts.iloc[0]).total_seconds() / 86400.0
        rows.append({"symbol": s, "tf": tf, "floor": fl, "topn": tn,
                     "quarters": len(fq), "q_above_1": int((fq.test_pf > 1).sum()),
                     "trades": len(g), "pf": round(_pf(g.r.values), 3),
                     "pf_2x": round(_pf(g.r_2x.values), 3),
                     "tpd": round(len(g) / max(sp, 1e-9), 3)})
    st = pd.DataFrame(rows).sort_values("pf_2x", ascending=False)
    st.to_csv(OUT / "stage10_stitched.csv", index=False)
    print(st.head(25).to_string(index=False))
    p = st.pivot_table(index=["symbol", "tf"], columns=["floor", "topn"], values="pf_2x")
    print(f"\ncombos clearing 1.20 AT 2x under all four rules: "
          f"{int((p.min(axis=1) >= 1.2).sum())} of {len(p)}")


if __name__ == "__main__":
    main()
