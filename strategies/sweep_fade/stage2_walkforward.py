"""H-005 walk-forward + board record.

Stage 1 rejected this outright - the null cleared the gate on 19,062
configurations against the real markets' 1,702. The walk-forward is run anyway so
H-005 is scored on exactly the same basis as every other hypothesis and appears
on the board. A rejected idea that is invisible is not part of the denominator.
"""
from __future__ import annotations

import sys, time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from core import board                                                # noqa: E402
from strategies.sweep_fade.sweep import (build_grid, features, run_one,  # noqa: E402
                                         TFS)
from strategies.sweep_fade.engine import T_R, T_ENTRY_I, T_EXIT_I     # noqa: E402
from strategies.sweep_fade.stage1_grid import load_tf, OUT, COSTS, CRYPTO  # noqa: E402

TRAIN_M, TEST_M = 12, 3
FLOORS, TOPN = (30, 100), (1, 10)
GATE = 1.20
# stage 1 showed nothing worked anywhere; walk-forward the combinations that came
# closest so the verdict is not decided by a bad shortlist
COMBOS = [("USDJPY", "4h"), ("NZDUSD", "4h"), ("AUDUSD", "1h"), ("AUDUSD", "4h"),
          ("GBPUSD", "4h"), ("USDJPY", "1h"), ("EURUSD", "4h"), ("XAGUSD", "1h"),
          ("BTCUSDT", "1h"), ("XAUUSD", "1h")]


def _pf(r):
    w, l = r[r > 0].sum(), -r[r < 0].sum()
    return float(w / l) if l > 0 else (np.inf if w > 0 else np.nan)


def walk(sym, tf):
    df = load_tf(sym, tf)
    if len(df) < 5000:
        return [], []
    fee, slip, minrisk = COSTS[sym]
    cfgs = build_grid(TFS[tf][1])
    for c in cfgs:
        c["min_risk_bps"] = minrisk
    feats = features(df)
    first = "2019-01-01" if sym in CRYPTO else "2024-09-01"
    starts = pd.date_range(first, "2026-07-01", freq=f"{TEST_M}MS", tz="UTC")
    starts = starts[starts >= df.index[0] + pd.DateOffset(months=TRAIN_M)]
    folds, trades = [], []
    for t0 in starts:
        lo, hi = t0 - pd.DateOffset(months=TRAIN_M), t0 + pd.DateOffset(months=TEST_M)
        if hi > df.index[-1] + pd.Timedelta(1, unit="D"):
            continue
        m_tr = (df.index >= lo) & (df.index < t0)
        m_te = (df.index >= t0) & (df.index < hi)
        if m_tr.sum() < 1000 or m_te.sum() < 300:
            continue
        tr_df, te_df = df[m_tr], df[m_te]
        f_tr = tuple(x[m_tr] for x in feats)
        f_te = tuple(x[m_te] for x in feats)
        t = time.time()
        # select on TRAIN profit factor at DOUBLE cost - the stage-9 fix
        pf2 = np.full(len(cfgs), np.nan); cnt = np.zeros(len(cfgs), dtype=int)
        for ci, cfg in enumerate(cfgs):
            r = run_one(tr_df, f_tr, cfg, fee * 2, slip * 2)[:, T_R]
            cnt[ci] = len(r)
            if len(r):
                pf2[ci] = _pf(r)
        span = (te_df.index[-1] - te_df.index[0]).total_seconds() / 86400.0
        cache = {}
        for floor in FLOORS:
            el = np.flatnonzero((cnt >= floor) & np.isfinite(pf2))
            if not el.size:
                continue
            order = el[np.argsort(-pf2[el])]
            for topn in TOPN:
                rs, ex, en, rs2 = [], [], [], []
                for ci in order[:topn]:
                    if ci not in cache:
                        a = run_one(te_df, f_te, cfgs[ci], fee, slip)
                        b = run_one(te_df, f_te, cfgs[ci], fee * 2, slip * 2)
                        cache[ci] = (a, b)
                    a, b = cache[ci]
                    if not len(a):
                        continue
                    rs.append(a[:, T_R] / topn)
                    ex.append(a[:, T_EXIT_I].astype(int))
                    en.append(a[:, T_ENTRY_I].astype(int))
                    rs2.append(b[:, T_R] / topn if len(b) == len(a) else a[:, T_R] / topn)
                if not rs:
                    continue
                ra = np.concatenate(rs); ea = np.concatenate(ex)
                na = np.concatenate(en); r2a = np.concatenate(rs2)
                o = np.argsort(ea, kind="stable")
                ra, ea, na, r2a = ra[o], ea[o], na[o], r2a[o]
                folds.append({"symbol": sym, "tf": tf, "quarter": str(t0.date()),
                              "floor": floor, "topn": topn,
                              "test_trades": int(len(ra)),
                              "test_pf": round(_pf(ra), 3),
                              "test_pf_2x": round(_pf(r2a), 3)})
                trades.append(pd.DataFrame({
                    "symbol": sym, "tf": tf, "quarter": str(t0.date()),
                    "floor": floor, "topn": topn,
                    "entry_ts": te_df.index[na], "exit_ts": te_df.index[ea],
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
    F, T = [], []
    with ProcessPoolExecutor(max_workers=10) as ex:
        futs = [ex.submit(_job, c) for c in COMBOS]
        for fu in as_completed(futs):
            f, t = fu.result(); F.extend(f); T.extend(t)
    fdf = pd.DataFrame(F); fdf.to_parquet(OUT / "stage2_folds.parquet", index=False)
    tdf = pd.concat(T, ignore_index=True) if T else pd.DataFrame()
    tdf.to_parquet(OUT / "stage2_trades.parquet", index=False)

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
    st = pd.DataFrame(rows).sort_values("pf", ascending=False)
    st.to_csv(OUT / "stage2_stitched.csv", index=False)
    print(st.to_string(index=False))
    print(f"\nmedian {st.pf.median():.3f}  >=1.20 {int((st.pf>=1.2).sum())}/{len(st)}  "
          f"@2x {int((st.pf_2x>=1.2).sum())}")

    best = st.iloc[0]
    g = tdf[(tdf.symbol == best.symbol) & (tdf.tf == best.tf) &
            (tdf.floor == best.floor) & (tdf.topn == best.topn)].sort_values("exit_ts")
    g["entry_ts"] = pd.to_datetime(g.entry_ts, utc=True)
    g["exit_ts"] = pd.to_datetime(g.exit_ts, utc=True)
    fq = fdf[(fdf.symbol == best.symbol) & (fdf.tf == best.tf) &
             (fdf.floor == best.floor) & (fdf.topn == best.topn)]
    grid = [{"label": f"{r.symbol} {r.tf}",
             "cols": [float(st[(st.symbol == r.symbol) & (st.tf == r.tf) &
                               (st.floor == f) & (st.topn == n)].pf.iloc[0])
                      if len(st[(st.symbol == r.symbol) & (st.tf == r.tf) &
                                (st.floor == f) & (st.topn == n)]) else None
                      for f, n in [(30, 1), (30, 10), (100, 1), (100, 10)]],
             "worst": float(st[(st.symbol == r.symbol) & (st.tf == r.tf)].pf.min()),
             "clears": bool(st[(st.symbol == r.symbol) & (st.tf == r.tf)].pf.min() >= GATE)}
            for r in st.drop_duplicates(["symbol", "tf"]).itertuples()]

    board.write_board(
        sid="sweep_fade", hid="H-005", name="Liquidity sweep fade",
        tagline="Fade the stop run: price takes out a range extreme, then closes back inside.",
        period="12 markets 5m-4h, walk-forward 2024-09 → 2026-08 (BTC 2019+)",
        report="", candidate=f"{best.symbol} {best.tf}, config re-chosen blind each quarter",
        legs=board.leg_payload(
            tdf[(tdf.floor == best.floor) & (tdf.topn == best.topn)]
                .rename(columns={"symbol": "sym"}),
            picked=[(str(best.symbol), str(best.tf))], cap=8),
        markets={"traded": [{"sym": str(best.symbol), "tf": str(best.tf),
                             "asset": str(best.symbol)[:3]}],
                 "searched": "12 markets x 5m-4h, 541k backtests",
                 "note": "Walk-forwarded for board parity only. Stage 1 had already "
                         "failed: the null cleared the gate 19,062 times to 1,702."},
        r=g.r.values, r_2x=g.r_2x.values, entry_ts=g.entry_ts, exit_ts=g.exit_ts,
        n_books=int(best.topn), null_margin=0.0, beats_null=False,
        consistency=float((fq.test_pf > 1).mean()) if len(fq) else 0.0,
        grid={"title": "Every market × timeframe, under all four ways of choosing",
              "note": "Stage 1 already failed: the null cleared the gate on 19,062 "
                      "configurations against the real markets' 1,702.",
              "cols": ["floor 30 / best", "floor 30 / top 10",
                       "floor 100 / best", "floor 100 / top 10"],
              "label": "Market", "rows": grid},
        todo=[
            {"t": "Full grid, 541k backtests", "w": "9,600 configs x 12 markets x 5 timeframes x 3 cost levels.", "done": True},
            {"t": "Paired-shuffle null", "w": "Null cleared PF 1.20 on 19,062 configs against the real 1,702 — the null is 11x better.", "done": True},
            {"t": "Cost stress", "w": "1,702 clear at 1x, 465 at 2x, 114 at 3x. Exactly one clears at 1x with a usable trade rate.", "done": True},
            {"t": "Walk-forward", "w": "Run for board parity, not because stage 1 justified it.", "done": True},
        ],
        note=("Rejected at stage 1. A sweep-and-revert rule is EASIER to satisfy on "
              "phase-randomised data than on real data — shuffled series mean-revert "
              "around their extremes more readily than real trending ones — so the null "
              "cleared the gate eleven times more often. This also fails to reproduce the "
              "prior repo's `liquidity_sweep` result, which was never run against a null; "
              "treat that older finding as unverified."),
    )


if __name__ == "__main__":
    main()
