"""H-002 VWAP stage 9 - select folds by train PF at 2x cost.

The previous improvement pass accidentally selected legs on 1x cost and only
checked 2x after building the book. This stage tests the direct fix: make the
fold selector optimise the same 2x-cost gate the project uses for acceptance.
It is intentionally narrow, covering the current survivor legs plus the faster
legs that failed the correction.
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

from core import board, riskladder as RL                   # noqa: E402
from strategies.vwap.engine import T_ENTRY_I, T_EXIT_I, T_R  # noqa: E402
from strategies.vwap.stage1_grid import ASSETS, OUT          # noqa: E402
from strategies.vwap.stage3_timeframes import (                    # noqa: E402
    TFS,
    build_grid,
    load_tf,
    shuffle_market_paired,
    null_seed,
)
from strategies.vwap.stage6_walkforward import (             # noqa: E402
    BTC_FIRST_TEST,
    CFGKEY,
    FX_FIRST_TEST,
    LAST_TEST,
    TEST_MONTHS,
    TOPN,
    TRAIN_MONTHS,
    _pf,
    _run,
    _slice_with_pad,
    summarise,
)
from strategies.vwap.sweep import features                  # noqa: E402


TARGETS = (
    ("BTCUSDT", "15m"), ("BTCUSDT", "30m"), ("BTCUSDT", "1h"), ("BTCUSDT", "4h"),
    ("XAUUSD", "5m"), ("XAUUSD", "30m"),
    ("XAGUSD", "15m"), ("XAGUSD", "1h"),
)
COMMON_START = pd.Timestamp("2024-09-01", tz="UTC")
GATE_PF = 1.20


def walk_one_2x(sym: str, tf: str, shuffled_paired: bool = False) -> tuple[list[dict], list[pd.DataFrame]]:
    try:
        df = load_tf(sym, tf, full_history=True)
    except Exception:
        return [], []
    if len(df) < 5000:
        return [], []
    if shuffled_paired:
        df = shuffle_market_paired(df, seed=null_seed(sym, tf, "stage9"))

    fee, slip, minrisk = ASSETS[sym]
    bph = TFS[tf][1]
    cfgs = build_grid(bph)
    for c in cfgs:
        c["min_risk_bps"] = minrisk

    feats = features(df)
    roll = max(20, int(round(24 * 4 * bph)))
    pad = int(roll * 2)

    first = BTC_FIRST_TEST if sym == "BTCUSDT" else FX_FIRST_TEST
    starts = pd.date_range(first, LAST_TEST, freq=f"{TEST_MONTHS}MS", tz="UTC")
    starts = starts[starts >= df.index[0] + pd.DateOffset(months=TRAIN_MONTHS)]

    fold_rows: list[dict] = []
    trade_rows: list[pd.DataFrame] = []
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
        vw_tr_2x, vw_te, vw_te2 = {}, {}, {}
        pfs_2x = np.full(len(cfgs), np.nan)
        cnts = np.zeros(len(cfgs), dtype=int)
        for ci, cfg in enumerate(cfgs):
            r2, _, _ = _run(train, f_tr, pad_tr, cfg, fee * 2, slip * 2, vw_tr_2x)
            cnts[ci] = len(r2)
            if len(r2):
                pfs_2x[ci] = _pf(r2)

        test_span = (test.index[-1] - test.index[pad_te]).total_seconds() / 86400.0
        cache: dict[int, tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]] = {}
        for floor in (30, 100):
            elig = np.flatnonzero((cnts >= floor) & np.isfinite(pfs_2x))
            if elig.size == 0:
                continue
            order = elig[np.argsort(-pfs_2x[elig])]
            for topn in TOPN:
                pick = order[:topn]
                rs, ex, en, rs2 = [], [], [], []
                for ci in pick:
                    if ci not in cache:
                        r1, e1, n1 = _run(test, f_te, pad_te, cfgs[ci], fee, slip, vw_te)
                        r2, _, _ = _run(test, f_te, pad_te, cfgs[ci], fee * 2, slip * 2, vw_te2)
                        cache[ci] = (r1, e1, n1, r2)
                    r1, e1, n1, r2 = cache[ci]
                    rs.append(r1 / topn)
                    ex.append(e1)
                    en.append(n1)
                    rs2.append(r2 / topn)

                r_all = np.concatenate(rs) if rs else np.empty(0)
                e_all = np.concatenate(ex) if ex else np.empty(0, dtype=int)
                n_all = np.concatenate(en) if en else np.empty(0, dtype=int)
                r2_all = np.concatenate(rs2) if rs2 else np.empty(0)
                o = np.argsort(e_all, kind="stable")
                r_all, e_all, n_all, r2_all = r_all[o], e_all[o], n_all[o], r2_all[o]

                fold_rows.append({
                    "symbol": sym, "tf": tf, "quarter": str(t0.date()),
                    "floor": floor, "topn": topn,
                    "selector": "train_pf_2x",
                    "train_pf": round(float(pfs_2x[pick[0]]), 3),
                    "train_pf_2x": round(float(pfs_2x[pick[0]]), 3),
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
                        "selector": "train_pf_2x",
                        "entry_ts": test.index[n_all],
                        "exit_ts": test.index[e_all],
                        "r": r_all,
                        "r_2x": r2_all,
                    }))
        print(f"  {sym:8s} {tf:4s} {t0.date()}  [{time.time()-t:.0f}s]", flush=True)

    return fold_rows, trade_rows


def _job(args):
    try:
        return walk_one_2x(*args)
    except Exception as e:
        print(f"  !! {args[0]} {args[1]}: {type(e).__name__}: {e}", flush=True)
        return [], []


def main():
    shuffled_paired = "--shuffled-paired" in sys.argv
    tag = "_2xselect_shuffled_paired" if shuffled_paired else "_2xselect"
    folds, trades = [], []
    t0 = time.time()
    with ProcessPoolExecutor(max_workers=8) as ex:
        futs = {ex.submit(_job, (*c, shuffled_paired)): c for c in TARGETS}
        for fu in as_completed(futs):
            f, tr = fu.result()
            folds.extend(f)
            trades.extend(tr)
            print(f"[{time.time()-t0:.0f}s] done {futs[fu]}  ({len(folds)} fold rows)", flush=True)

    fdf = pd.DataFrame(folds)
    tdf = pd.concat(trades, ignore_index=True) if trades else pd.DataFrame()
    fdf.to_parquet(OUT / f"stage9_folds{tag}.parquet", index=False)
    fdf.to_csv(OUT / f"stage9_folds{tag}.csv", index=False)
    tdf.to_parquet(OUT / f"stage9_trades{tag}.parquet", index=False)
    print(f"\nsaved {len(fdf)} fold rows, {len(tdf)} stitched trades")
    summarise(fdf, tdf, tag)


def write_board_json():
    """Promote the best tradeable 2x-selected book to the strategy board."""
    st = pd.read_csv(OUT / "stage6_stitched_2xselect.csv")
    tr = pd.read_parquet(OUT / "stage9_trades_2xselect.parquet")
    tr["entry_ts"] = pd.to_datetime(tr.entry_ts, utc=True)
    tr["exit_ts"] = pd.to_datetime(tr.exit_ts, utc=True)

    piv = st.pivot_table(index=["symbol", "tf"], columns=["floor", "topn"], values="pf")
    robust = list(piv[piv.min(axis=1) >= GATE_PF].index)

    null_s = 0
    nullp = OUT / "stage6_stitched_2xselect_shuffled_paired.csv"
    if nullp.exists():
        n = pd.read_csv(nullp)
        npiv = n.pivot_table(index=["symbol", "tf"], columns=["floor", "topn"], values="pf")
        null_s = int((npiv.min(axis=1) >= GATE_PF).sum())
    real_s = len(robust)
    null_margin = 0.0 if not real_s else max(0.0, (real_s - null_s) / real_s)

    def book_trades(legs, floor, topn):
        sel = tr[(tr.floor == floor) & (tr.topn == topn) & (tr.exit_ts >= COMMON_START)]
        sel = sel[[(s, t) in legs for s, t in zip(sel.symbol, sel.tf)]]
        return sel.sort_values("exit_ts")

    import itertools
    cands = []
    for k in range(1, len(robust) + 1):
        for sub in itertools.combinations(robust, k):
            for floor in (30, 100):
                topn = 1
                sel = book_trades(list(sub), floor, topn)
                if sel.empty:
                    continue
                r = sel.r.values / len(sub)
                r2 = sel.r_2x.values / len(sub)
                pf2x = board.pf_of(r2)
                if pf2x < GATE_PF:
                    continue
                _rows, pick = RL.from_trades(r, sel.exit_ts)
                if pick["expected_days"] is None:
                    continue
                cands.append({
                    "sub": list(sub), "floor": floor, "topn": topn, "sel": sel,
                    "pf2x": pf2x, "days": pick["expected_days"],
                })
    if not cands:
        print("no 2x-selected tradeable subset clears the 2x gate")
        return
    cands.sort(key=lambda c: c["days"])
    best = cands[0]
    legs, floor, topn, sel = best["sub"], best["floor"], best["topn"], best["sel"]
    n_legs = len(legs)
    print(f"  stage 9 board pick: {' + '.join(f'{a} {b}' for a, b in legs)} "
          f"(floor {floor}, top {topn}, PF@2x {best['pf2x']:.3f})")

    fold = pd.read_parquet(OUT / "stage9_folds_2xselect.parquet")
    fold["quarter_ts"] = pd.to_datetime(fold.quarter, utc=True)
    fl = fold[(fold.floor == floor) & (fold.topn == topn) & (fold.quarter_ts >= COMMON_START)]
    fl = fl[[(s, t) in legs for s, t in zip(fl.symbol, fl.tf)]]
    consistency = float((fl.test_pf > 1).mean()) if len(fl) else 0.0

    grid_rows = []
    piv2 = st.pivot_table(index=["symbol", "tf"], columns=["floor", "topn"], values="pf_2x")
    for sym, tf in piv.index:
        cols = [piv.loc[(sym, tf)].get((30, 1)), piv.loc[(sym, tf)].get((30, 10)),
                piv.loc[(sym, tf)].get((100, 1)), piv.loc[(sym, tf)].get((100, 10))]
        cols2 = [piv2.loc[(sym, tf)].get((30, 1)), piv2.loc[(sym, tf)].get((30, 10)),
                 piv2.loc[(sym, tf)].get((100, 1)), piv2.loc[(sym, tf)].get((100, 10))]
        grid_rows.append({
            "label": f"{sym} {tf}",
            "cols": [None if pd.isna(x) else round(float(x), 3) for x in cols],
            "worst": round(float(min(cols)), 3),
            "pf2x": [None if pd.isna(x) else round(float(x), 3) for x in cols2],
            "clears": (sym, tf) in robust,
        })

    board.write_board(
        sid="vwap", hid="H-002", name="VWAP",
        tagline="Five model families around the volume-weighted average price.",
        period="FX & metals 2023-09 -> 2026-08 · BTC from 2017",
        report="https://claude.ai/code/artifact/cb748842-7d3b-45f7-9d69-827e00ba82f4",
        candidate=(" + ".join(f"{a} {b}" for a, b in legs)
                   + ", equal weight, configs chosen by 2x-cost train PF each quarter"),
        r=sel.r.values / n_legs, r_2x=sel.r_2x.values / n_legs,
        n_books=n_legs * topn,
        entry_ts=sel.entry_ts, exit_ts=sel.exit_ts,
        null_margin=null_margin, beats_null=(real_s > null_s),
        consistency=consistency,
        grid={
            "title": "2x-cost selector on the current VWAP candidate set",
            "note": ("Each fold chooses the best configuration by train profit factor at "
                     "double cost, then trades the next quarter blind. The board candidate "
                     "is the fastest tradeable subset that still clears PF 1.20 at 2x."),
            "cols": ["floor 30 / best", "floor 30 / top 10",
                     "floor 100 / best", "floor 100 / top 10"],
            "label": "Market", "rows": grid_rows,
        },
        todo=[
            {"t": "Fill realism", "w": "Whether the result needs a limit fill nobody can guarantee.", "done": True},
            {"t": "Cost stress to 2x and 3x", "w": "Whether the edge is bigger than the spread difference between an ECN and a prop firm.", "done": True},
            {"t": "Null benchmark", "w": "Whether the profit factor beats what the same search finds in data with no edge in it.", "done": True},
            {"t": "Walk-forward", "w": "Chosen blind every quarter. The 2x-cost selector is a targeted refinement, not a new family.", "done": True},
            {"t": "Paired-volume null", "w": "Same 2x selector on shuffled return/volume pairs: 0 robust survivors.", "done": True},
            {"t": "Prop challenge on walk-forward output", "w": "Pass and breach rates across the full risk ladder, on blind-chosen configs.", "done": True},
            {"t": "NautilusTrader cross-check", "w": "Whether an independent matching engine agrees with the kernel.", "done": False},
            {"t": "Silver (XAGUSD)", "w": "Tested on 15m and 1h in the 2x selector; no robust survivor.", "done": True},
        ],
    )


if __name__ == "__main__":
    if "--write-board-only" in sys.argv:
        write_board_json()
    else:
        main()
        if "--shuffled-paired" not in sys.argv:
            write_board_json()
