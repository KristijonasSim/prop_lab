"""H-003 stage 2 — walk-forward, the test that decides.

Stage 1 says the family fails: across the whole search the real markets have a
LOWER median profit factor than phase-randomised copies of themselves. But a
handful of combinations - gold at 30m and 1h most clearly - do beat their own
null on the median, the maximum and the count above the gate, so the family gets
the same blind test H-001 and H-002 got before it is closed.

Same shape as strategies/vwap/stage6_walkforward.py so the numbers are directly
comparable: quarterly folds, 12 months train / 3 months test, the configuration
re-chosen on the train slice alone every fold and never carried forward. Both
trade-count floors and both single-best / top-ten selection rules run, because
neither choice is obviously right and a real edge should not care much which is
used.
"""
from __future__ import annotations

import sys, time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from strategies.vwap.stage1_grid import ASSETS                       # noqa: E402
from strategies.ema_vwap.sweep import (build_grid, features, run_one,  # noqa: E402
                                       vwap_for, TFS)
from strategies.ema_vwap.engine import T_R, T_ENTRY_I, T_EXIT_I      # noqa: E402
from strategies.ema_vwap.stage1_grid import load_tf, OUT, EMAS, ANCHORS  # noqa: E402
from strategies.vwap.stage3_timeframes import (shuffle_market,          # noqa: E402
                                               shuffle_market_paired, null_seed)

TRAIN_MONTHS, TEST_MONTHS = 12, 3
FLOORS = (30, 100)
TOPN = (1, 10)
FX_FIRST_TEST, BTC_FIRST_TEST, LAST_TEST = "2024-09-01", "2019-01-01", "2026-07-01"


def _pf(r):
    w, l = r[r > 0].sum(), -r[r < 0].sum()
    return float(w / l) if l > 0 else (np.inf if w > 0 else np.nan)


def _slice(df, lo, hi, pad):
    idx = df.index
    i_lo, i_hi = int(idx.searchsorted(lo)), int(idx.searchsorted(hi))
    i_pad = max(0, i_lo - pad)
    return df.iloc[i_pad:i_hi], i_lo - i_pad


def _run(df, feats, vw, sess, n_pad, cfg, fee, slip):
    tr = run_one(df, feats, vw, sess, cfg, fee, slip)
    if len(tr) == 0:
        return np.empty(0), np.empty(0, int), np.empty(0, int)
    tr = tr[tr[:, T_ENTRY_I] >= n_pad]
    if len(tr) == 0:
        return np.empty(0), np.empty(0, int), np.empty(0, int)
    return tr[:, T_R], tr[:, T_EXIT_I].astype(int), tr[:, T_ENTRY_I].astype(int)


def walk_one(sym: str, tf: str, shuffled=False, seed_off: int = 0):
    """`shuffled` runs the identical procedure on a phase-randomised copy.

    Necessary, not optional: 52 combinations x 4 selection rules is 208 stitched
    series, which is a search. In H-002 the single combination that cleared the
    gate under every selection rule on SHUFFLED data was gold at 1h - the same
    market and timeframe that tops this table. A high walk-forward profit factor
    is not evidence until it is scored against that."""
    try:
        df = load_tf(sym, tf)
    except Exception:
        return [], []
    if len(df) < 5000:
        return [], []
    if shuffled == "paired":
        # keeps each bar's volume with its own return, so a participation filter
        # cannot win just by having a volume/return link the null lacks
        df = shuffle_market_paired(
            df, seed=null_seed(sym, tf, "h003p", seed_off))
    elif shuffled:
        df = shuffle_market(
            df, seed=null_seed(sym, tf, "h003wf", seed_off))
    fee, slip, minrisk = ASSETS[sym]
    bph = TFS[tf][1]
    base = build_grid(bph)
    for c in base:
        c["min_risk_bps"] = minrisk
    roll = max(20, int(round(24 * 4 * bph)))
    pad = int(roll * 2)

    # the EMA length and the VWAP anchor are part of what gets chosen blind
    variants = [(e, a) for e in EMAS for a in ANCHORS]

    first = BTC_FIRST_TEST if sym == "BTCUSDT" else FX_FIRST_TEST
    starts = pd.date_range(first, LAST_TEST, freq=f"{TEST_MONTHS}MS", tz="UTC")
    starts = starts[starts >= df.index[0] + pd.DateOffset(months=TRAIN_MONTHS)]

    folds, trades = [], []
    for t0 in starts:
        tr_lo, te_hi = t0 - pd.DateOffset(months=TRAIN_MONTHS), t0 + pd.DateOffset(months=TEST_MONTHS)
        if te_hi > df.index[-1] + pd.Timedelta(1, unit="D"):
            continue
        train, pad_tr = _slice(df, tr_lo, t0, pad)
        test, pad_te = _slice(df, t0, te_hi, pad)
        if len(train) < 1000 or len(test) - pad_te < 200:
            continue
        t = time.time()

        cand = []          # (train pf, n trades, variant index, cfg)
        cache_tr, cache_te = {}, {}
        for vi, (ema_len, anchor) in enumerate(variants):
            f_tr = features(train, ema_len); vw_tr, s_tr = vwap_for(train, anchor, roll)
            f_te = features(test, ema_len); vw_te, s_te = vwap_for(test, anchor, roll)
            cache_tr[vi] = (f_tr, vw_tr, s_tr)
            cache_te[vi] = (f_te, vw_te, s_te)
            for cfg in base:
                r, _, _ = _run(train, f_tr, vw_tr, s_tr, pad_tr, cfg, fee, slip)
                if len(r):
                    cand.append((_pf(r), len(r), vi, cfg))

        span = (test.index[-1] - test.index[pad_te]).total_seconds() / 86400.0
        seen = {}
        for floor in FLOORS:
            elig = [c for c in cand if c[1] >= floor and np.isfinite(c[0])]
            if not elig:
                continue
            elig.sort(key=lambda x: -x[0])
            for topn in TOPN:
                pick = elig[:topn]
                rs, ex, en, rs2 = [], [], [], []
                for pf_tr, ntr, vi, cfg in pick:
                    key = (vi, id(cfg))
                    if key not in seen:
                        f, vw, ss = cache_te[vi]
                        r1, e1, n1 = _run(test, f, vw, ss, pad_te, cfg, fee, slip)
                        r2, _, _ = _run(test, f, vw, ss, pad_te, cfg, fee * 2, slip * 2)
                        seen[key] = (r1, e1, n1, r2)
                    r1, e1, n1, r2 = seen[key]
                    rs.append(r1 / topn); ex.append(e1); en.append(n1); rs2.append(r2 / topn)
                r_all = np.concatenate(rs) if rs else np.empty(0)
                if not len(r_all):
                    continue
                e_all = np.concatenate(ex); n_all = np.concatenate(en)
                r2_all = np.concatenate(rs2)
                o = np.argsort(e_all, kind="stable")
                r_all, e_all, n_all, r2_all = r_all[o], e_all[o], n_all[o], r2_all[o]
                folds.append({
                    "symbol": sym, "tf": tf, "quarter": str(t0.date()),
                    "floor": floor, "topn": topn,
                    "train_pf": round(pick[0][0], 3), "train_trades": int(pick[0][1]),
                    "ema_len": EMAS[pick[0][2] // len(ANCHORS)],
                    "anchor": ANCHORS[pick[0][2] % len(ANCHORS)],
                    "exit_mode": int(pick[0][3]["exit_mode"]),
                    "test_trades": int(len(r_all)),
                    "test_pf": round(_pf(r_all), 3),
                    "test_pf_2x": round(_pf(r2_all), 3),
                    "test_tpd": round(len(r_all) / max(span, 1e-9), 3),
                })
                trades.append(pd.DataFrame({
                    "symbol": sym, "tf": tf, "quarter": str(t0.date()),
                    "floor": floor, "topn": topn,
                    "entry_ts": test.index[n_all], "exit_ts": test.index[e_all],
                    "r": r_all, "r_2x": r2_all}))
        print(f"  {sym:8s} {tf:4s} {t0.date()}  [{time.time()-t:.0f}s]", flush=True)
    return folds, trades


def _job(a):
    try:
        return walk_one(*a)
    except Exception as e:
        print(f"  !! {a}: {type(e).__name__}: {e}", flush=True)
        return [], []


def main():
    if "--shuffled-paired" in sys.argv:
        shuffled, tag = "paired", "_shuffled_paired"
    elif "--shuffled" in sys.argv:
        shuffled, tag = True, "_shuffled"
    else:
        shuffled, tag = False, ""
    seed_off = 0
    for a in sys.argv:
        if a.startswith("--seed="):
            seed_off = int(a.split("=", 1)[1])
    if seed_off:
        tag = f"{tag}_s{seed_off}"
    combos = [(s, tf, shuffled, seed_off) for s in ASSETS for tf in TFS
              if not (s == "BTCUSDT" and tf in ("3m", "5m")) and tf != "1d"]
    print(f"{len(combos)} combinations{' — SHUFFLED (null)' if shuffled else ''}", flush=True)
    F, T = [], []
    t0 = time.time()
    with ProcessPoolExecutor(max_workers=12) as ex:
        futs = {ex.submit(_job, c): c for c in combos}
        for fu in as_completed(futs):
            f, t = fu.result()
            F.extend(f); T.extend(t)
            print(f"[{time.time()-t0:.0f}s] done {futs[fu][:2]} ({len(F)} folds)", flush=True)
    fdf = pd.DataFrame(F); fdf.to_parquet(OUT / f"stage2_folds{tag}.parquet", index=False)
    tdf = pd.concat(T, ignore_index=True) if T else pd.DataFrame()
    tdf.to_parquet(OUT / f"stage2_trades{tag}.parquet", index=False)
    print(f"\nsaved {len(fdf)} folds, {len(tdf)} stitched trades", flush=True)

    rows = []
    for (s, tf, fl, tn), g in tdf.groupby(["symbol", "tf", "floor", "topn"]):
        g = g.sort_values("exit_ts")
        fq = fdf[(fdf.symbol == s) & (fdf.tf == tf) & (fdf.floor == fl) & (fdf.topn == tn)]
        sp = (g.exit_ts.iloc[-1] - g.exit_ts.iloc[0]).total_seconds() / 86400.0
        rows.append({"symbol": s, "tf": tf, "floor": fl, "topn": tn,
                     "quarters": len(fq), "q_above_1": int((fq.test_pf > 1).sum()),
                     "trades": len(g), "pf": round(_pf(g.r.values), 3),
                     "pf_2x": round(_pf(g.r_2x.values), 3),
                     "tpd": round(len(g) / max(sp, 1e-9), 3),
                     "total_r": round(float(g.r.sum()), 2)})
    st = pd.DataFrame(rows).sort_values("pf", ascending=False)
    st.to_csv(OUT / f"stage2_stitched{tag}.csv", index=False)
    print(st.head(20).to_string(index=False))
    print(f"\nmedian stitched PF {st.pf.median():.3f}   >=1.20: "
          f"{int((st.pf >= 1.2).sum())}/{len(st)}   >=1.20 at 2x: {int((st.pf_2x >= 1.2).sum())}")


if __name__ == "__main__":
    main()
