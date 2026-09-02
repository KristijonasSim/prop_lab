"""H-002 VWAP stage 6 — anchored-quarter walk-forward.

The one test in the project with no hindsight in it. Every H-002 number that
exists so far was chosen with knowledge of the data it was scored on; this
removes that.

Method, per market x timeframe:

  * roll quarterly. Train on the trailing 12 months, trade the next 3, roll.
  * the configuration is chosen on the TRAIN slice only, by profit factor with a
    trade-count floor. It is re-chosen every fold and never carried forward.
  * **the filter is re-chosen too.** The H-002 filter set came from a study run
    on overlapping data, so holding it fixed would leave that selection bias in.
    The filter variants are inside the grid, so picking the best train config
    picks its filter with it.
  * the chosen config trades the TEST slice; test trades are stitched end to end
    across every fold and scored as one series.

Two choices that the ORB walk-forward did not make, both reported side by side
rather than picked in advance:

  * **Trade-count floor.** ORB used 100 train trades. The strongest H-002
    configurations trade 0.09-0.28 times a day, so a 100-trade floor over twelve
    months would exclude exactly the configurations stage 3 found. A floor of 30
    keeps them and accepts noisier selection. Neither is obviously right, so both
    run.
  * **Single best vs top ten.** Taking the single highest train profit factor is
    the highest-variance possible choice. Trading the top ten equally weighted is
    the same information with the selection noise averaged down. If the top-ten
    result holds up and the single-best does not, the edge was in the family and
    not in the winner.

Slices are padded at the front so the VWAP and the session state are warm at the
fold boundary; trades entered inside the pad are dropped, so no trade is counted
twice and none starts on a cold indicator.
"""
from __future__ import annotations

import sys, time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from strategies.vwap.sweep import features, run_one, trade_metrics, DEFAULTS  # noqa: E402
from strategies.vwap.engine import T_R, T_ENTRY_I, T_EXIT_I                   # noqa: E402
from strategies.vwap.stage1_grid import ASSETS, OUT                           # noqa: E402
from strategies.vwap.stage3_timeframes import (load_tf, TFS, build_grid,       # noqa: E402
                                               shuffle_market,
                                               shuffle_market_paired, null_seed)

TRAIN_MONTHS, TEST_MONTHS = 12, 3
FLOORS = (30, 100)          # minimum train trades, both reported
TOPN = (1, 10)              # single best vs top ten equally weighted
CFGKEY = ["anchor_hour", "anchor_minute", "mode", "fill_mode", "band_k", "stop_mode",
          "stop_k", "target_mode", "rr", "max_hold_bars", "min_rvol",
          "min_atr_rank", "max_atr_rank", "warmup_bars", "min_risk_bps"]

# FX/metals only reach back to 2023-09, so the first tradeable quarter is
# 2024-09 once a 12-month train window is reserved. BTC has 2017 onward and
# rolls from 2019, which makes it directly comparable to the ORB walk-forward.
FX_FIRST_TEST = "2024-09-01"
BTC_FIRST_TEST = "2019-01-01"
LAST_TEST = "2026-07-01"


def _pf(r: np.ndarray) -> float:
    w, l = r[r > 0].sum(), -r[r < 0].sum()
    return float(w / l) if l > 0 else (np.inf if w > 0 else np.nan)


def _slice_with_pad(df, feats, lo, hi, pad_bars):
    """Return (padded frame, padded features, n_pad) so the indicator is warm at
    `lo`. Trades entered before n_pad are the pad's and get dropped."""
    idx = df.index
    i_lo = int(idx.searchsorted(lo))
    i_hi = int(idx.searchsorted(hi))
    i_pad = max(0, i_lo - pad_bars)
    sub = df.iloc[i_pad:i_hi]
    sub_f = tuple(f[i_pad:i_hi] for f in feats)
    return sub, sub_f, i_lo - i_pad


def _run(df, feats, n_pad, cfg, fee, slip, vw_cache):
    """Trades entered at or after the pad boundary, as (R, exit pos, entry pos).

    `vw_cache` is shared across every config on the same slice — recomputing the
    VWAP for each of 12,960 configs would dominate the runtime."""
    tr = run_one(df, feats, vw_cache, cfg, fee, slip)
    if len(tr) == 0:
        return np.empty(0), np.empty(0, dtype=int), np.empty(0, dtype=int)
    keep = tr[:, T_ENTRY_I] >= n_pad
    tr = tr[keep]
    if len(tr) == 0:
        return np.empty(0), np.empty(0, dtype=int), np.empty(0, dtype=int)
    return tr[:, T_R], tr[:, T_EXIT_I].astype(int), tr[:, T_ENTRY_I].astype(int)


def walk_one(sym: str, tf: str, shuffled=False) -> tuple[list[dict], list[dict]]:
    """One market x timeframe. Returns (per-fold rows, per-trade rows).

    `shuffled` runs the identical procedure on a phase-randomised copy of the
    market. The walk-forward is itself a search — 44 combinations x 4 selection
    rules is 176 stitched series — so its survivor count needs a null to be read
    against, exactly as the stage 3 grid did. Every edge is destroyed by
    construction here, so whatever survives is what selection alone produces."""
    try:
        df = load_tf(sym, tf, full_history=True)
    except Exception:
        return [], []
    if len(df) < 5000:
        return [], []
    if shuffled == "paired":
        df = shuffle_market_paired(df, seed=null_seed(sym, tf, "wfp"))
    elif shuffled:
        df = shuffle_market(df, seed=null_seed(sym, tf, "wf"))

    fee, slip, minrisk = ASSETS[sym]
    bph = TFS[tf][1]
    cfgs = build_grid(bph)
    for c in cfgs:
        c["min_risk_bps"] = minrisk

    feats = features(df)                      # computed once on the full history;
                                              # every input is backward-looking
    roll = max(20, int(round(24 * 4 * bph)))  # the rolling-VWAP window for this tf
    pad = int(roll * 2)

    first = BTC_FIRST_TEST if sym == "BTCUSDT" else FX_FIRST_TEST
    starts = pd.date_range(first, LAST_TEST, freq=f"{TEST_MONTHS}MS", tz="UTC")
    starts = starts[starts >= df.index[0] + pd.DateOffset(months=TRAIN_MONTHS)]

    fold_rows, trade_rows = [], []
    for t0 in starts:
        tr_lo = t0 - pd.DateOffset(months=TRAIN_MONTHS)
        te_hi = t0 + pd.DateOffset(months=TEST_MONTHS)
        if te_hi > df.index[-1] + pd.Timedelta(1, unit="D"):
            continue

        train, f_tr, pad_tr = _slice_with_pad(df, feats, tr_lo, t0, pad)
        test, f_te, pad_te = _slice_with_pad(df, feats, t0, te_hi, pad)
        if len(train) < 1000 or len(test) - pad_te < 200:
            continue

        t = time.time()
        vw_tr, vw_te, vw_te2 = {}, {}, {}
        pfs = np.full(len(cfgs), np.nan)
        cnts = np.zeros(len(cfgs), dtype=int)
        for ci, cfg in enumerate(cfgs):
            r, _, _ = _run(train, f_tr, pad_tr, cfg, fee, slip, vw_tr)
            cnts[ci] = len(r)
            if len(r):
                pfs[ci] = _pf(r)

        test_span = (test.index[-1] - test.index[pad_te]).total_seconds() / 86400.0
        cache: dict[int, tuple] = {}

        for floor in FLOORS:
            elig = np.flatnonzero((cnts >= floor) & np.isfinite(pfs))
            if elig.size == 0:
                continue
            order = elig[np.argsort(-pfs[elig])]
            for topn in TOPN:
                pick = order[:topn]
                if pick.size == 0:
                    continue
                rs, ex, en, rs2 = [], [], [], []
                for ci in pick:
                    if ci not in cache:
                        r1, e1, n1 = _run(test, f_te, pad_te, cfgs[ci], fee, slip, vw_te)
                        r2, _, _ = _run(test, f_te, pad_te, cfgs[ci], fee * 2, slip * 2, vw_te2)
                        cache[ci] = (r1, e1, n1, r2)
                    r1, e1, n1, r2 = cache[ci]
                    # equal weight across N legs, so one book's R is comparable
                    # to a single config's R
                    rs.append(r1 / topn); ex.append(e1); en.append(n1); rs2.append(r2 / topn)
                r_all = np.concatenate(rs) if rs else np.empty(0)
                e_all = np.concatenate(ex) if ex else np.empty(0, dtype=int)
                n_all = np.concatenate(en) if en else np.empty(0, dtype=int)
                r2_all = np.concatenate(rs2) if rs2 else np.empty(0)
                o = np.argsort(e_all, kind="stable")
                r_all, e_all, n_all, r2_all = r_all[o], e_all[o], n_all[o], r2_all[o]

                fold_rows.append({
                    "symbol": sym, "tf": tf, "quarter": str(t0.date()),
                    "floor": floor, "topn": topn,
                    "train_pf": round(float(pfs[pick[0]]), 3),
                    "train_trades": int(cnts[pick[0]]),
                    "n_eligible": int(elig.size),
                    "test_trades": int(len(r_all)),
                    "test_pf": round(_pf(r_all), 3) if len(r_all) else np.nan,
                    "test_pf_2x": round(_pf(r2_all), 3) if len(r2_all) else np.nan,
                    "test_total_r": round(float(r_all.sum()), 3),
                    "test_tpd": round(len(r_all) / max(test_span, 1e-9), 3),
                    "test_win": round(float((r_all > 0).mean()), 4) if len(r_all) else np.nan,
                    **{k: cfgs[pick[0]][k] for k in CFGKEY},
                    "filter": cfgs[pick[0]]["filter"],
                })
                if len(r_all):
                    trade_rows.append(pd.DataFrame({
                        "symbol": sym, "tf": tf, "quarter": str(t0.date()),
                        "floor": floor, "topn": topn,
                        "entry_ts": test.index[n_all], "exit_ts": test.index[e_all],
                        "r": r_all, "r_2x": r2_all}))
        print(f"  {sym:8s} {tf:4s} {t0.date()}  [{time.time()-t:.0f}s]", flush=True)

    return fold_rows, trade_rows


def _job(args):
    sym, tf, shuffled = args
    try:
        return walk_one(sym, tf, shuffled)
    except Exception as e:                      # one bad combo must not kill the run
        print(f"  !! {sym} {tf}: {type(e).__name__}: {e}", flush=True)
        return [], []


def main():
    if "--shuffled-paired" in sys.argv:
        shuffled, tag = "paired", "_shuffled_paired"
    elif "--shuffled" in sys.argv:
        shuffled, tag = True, "_shuffled"
    else:
        shuffled, tag = False, ""
    combos = [(s, tf, shuffled) for s in ASSETS for tf in TFS
              if not (s == "BTCUSDT" and tf == "5m")]   # 15m base cannot go finer
    print(f"{len(combos)} market x timeframe combinations"
          f"{' — SHUFFLED (null benchmark)' if shuffled else ''}", flush=True)

    folds, trades = [], []
    t0 = time.time()
    with ProcessPoolExecutor(max_workers=14) as ex:
        futs = {ex.submit(_job, c): c for c in combos}
        for fu in as_completed(futs):
            f, tr = fu.result()
            folds.extend(f); trades.extend(tr)
            print(f"[{time.time()-t0:.0f}s] done {futs[fu][:2]}  "
                  f"({len(folds)} fold rows)", flush=True)

    fdf = pd.DataFrame(folds)
    fdf.to_parquet(OUT / f"stage6_folds{tag}.parquet", index=False)
    fdf.to_csv(OUT / f"stage6_folds{tag}.csv", index=False)

    tdf = pd.concat(trades, ignore_index=True) if trades else pd.DataFrame()
    tdf.to_parquet(OUT / f"stage6_trades{tag}.parquet", index=False)

    print(f"\nsaved {len(fdf)} fold rows, {len(tdf)} stitched trades", flush=True)
    summarise(fdf, tdf, tag)


def summarise(fdf: pd.DataFrame, tdf: pd.DataFrame, tag: str = ""):
    """Stitched out-of-sample series per market x timeframe x selection rule."""
    if tdf.empty:
        print("no trades"); return
    rows = []
    for (sym, tf, floor, topn), g in tdf.groupby(["symbol", "tf", "floor", "topn"]):
        g = g.sort_values("exit_ts")
        r = g.r.values
        span = (g.exit_ts.iloc[-1] - g.exit_ts.iloc[0]).total_seconds() / 86400.0
        fq = fdf[(fdf.symbol == sym) & (fdf.tf == tf) &
                 (fdf.floor == floor) & (fdf.topn == topn)]
        eq = np.concatenate(([0.0], np.cumsum(r)))
        rows.append({
            "symbol": sym, "tf": tf, "floor": floor, "topn": topn,
            "quarters": len(fq), "q_above_1": int((fq.test_pf > 1).sum()),
            "trades": len(r), "pf": round(_pf(r), 3),
            "pf_2x": round(_pf(g.r_2x.values), 3),
            "win": round(float((r > 0).mean()), 4),
            "avg_r": round(float(r.mean()), 4),
            "total_r": round(float(r.sum()), 2),
            "tpd": round(len(r) / max(span, 1e-9), 3),
            "max_dd_r": round(float((eq - np.maximum.accumulate(eq)).min()), 2),
            "train_pf_med": round(float(fq.train_pf.median()), 3),
        })
    s = pd.DataFrame(rows).sort_values("pf", ascending=False)
    s.to_csv(OUT / f"stage6_stitched{tag}.csv", index=False)
    with pd.option_context("display.width", 200, "display.max_rows", 300):
        print(s.to_string(index=False))
    print("saved", OUT / f"stage6_stitched{tag}.csv")


if __name__ == "__main__":
    main()
