"""H-017 - select on K, not profit factor, and only on markets that are cheap.

THE HYPOTHESIS, and it is a claim about METHOD as much as about markets.

Stage 0: days to a funded account is `1.625 / K` where `K = R_per_day /
|maxDD_R|`. Stage 1: K scales like sqrt(number of legs) with a measured
exponent of 0.441, but per-leg K on the incumbent book is ~0.003, so no
reachable universe closes a 2.2x gap by width alone. Stage 2: every flow
feature this project owns fails to clear even a 14bps round trip below the
8-hour horizon, so a fast CRYPTO book is impossible - the fee is fatal.

That leaves exactly one route, and it has two halves:

  1. TRADE WHERE IT IS CHEAP. Gold is 3bps round trip and the FX majors are
     1.5bps, against crypto's 14. A 5-minute edge of 5bps is untradeable on a
     perp and comfortable on EURUSD. Every market here is one of the cheap
     ones, and three of them - the US indices - plus oil have never been run
     through this kernel at all.

  2. SELECT ON THE RIGHT NUMBER. Every walk-forward in this project has chosen
     each fold's configuration on profit factor. **Profit factor is not what
     the goal is made of.** It is blind to frequency and blind to drawdown
     shape, and it systematically prefers slow configurations: fewer trades
     mechanically raise PF. A config with PF 1.3 taking 6 trades a day reaches
     a funded account far sooner than one with PF 2.0 taking 0.3, and the
     selection rule this repo uses would pick the second one every time.

So the test is PAIRED and it is the honest form: identical folds, identical
grid, identical kernel, and the ONLY difference is whether the fold ranks
candidates by PF at 2x cost or by K at 2x cost. Anything else that changed
would confound the answer.

Selection happens strictly inside the training window; the test quarter is
scored on the choice and never consulted.

Output: backtests/xpos/stage3_folds.csv, stage3_trades.parquet
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

from core import fx_data                                              # noqa: E402
from strategies.vwap.stage3_timeframes import ANCHORS, DEFAULTS       # noqa: E402
from strategies.vwap.stage6_walkforward import (TEST_MONTHS,          # noqa: E402
                                                TRAIN_MONTHS, _pf,
                                                _run, _slice_with_pad)
from strategies.vwap.sweep import features                            # noqa: E402

OUT = ROOT / "backtests" / "xpos"

#: (fee_bps, slip_bps, min_risk_bps) per side. Metals and FX come from H-002's
#: measured table. Indices and oil are charged GOLD's cost, which overstates
#: their real spread (US30's ~2 points on 53,000 is 0.38bps against gold's
#: 1.00), so a result here cannot be accused of a flattering fee.
COSTS = {
    "XAUUSD": (1.00, 0.50, 3.0), "XAGUSD": (1.50, 0.75, 5.0),
    "EURUSD": (0.45, 0.30, 2.0), "GBPUSD": (0.50, 0.30, 2.0),
    "USDJPY": (0.45, 0.30, 2.0), "AUDUSD": (0.60, 0.35, 2.0),
    "USDCAD": (0.65, 0.35, 2.0), "USDCHF": (0.70, 0.35, 2.0),
    "NZDUSD": (0.85, 0.45, 2.5),
    "SPX500": (1.00, 0.50, 3.0), "US30": (1.00, 0.50, 3.0),
    "NAS100": (1.00, 0.50, 3.0),
    "WTI": (2.00, 1.00, 6.0),
}
MARKETS = list(COSTS)
TFS = {"5min": 12.0, "15min": 4.0}     # bars per hour
FLOOR = 100                            # minimum trades in the training window
TOPN = 10
PAD_DAYS = 6


def fast_grid(bph: float) -> list[dict]:
    """A pruned version of H-002's grid, cut on what its own studies settled.

    Dropped: the 08:00 London anchor (H-001 found the NY cash open is the only
    session anchor carrying anything, and Asia the worst region), and three of
    the seven filters (the paired-lift study ranked participation first and
    scored `ATRrank<0.5` and `ATRrank>0.7` as noise). What is left is 7,776
    configurations instead of 18,144, which is what makes a 5-minute
    walk-forward across fourteen markets finish.
    """
    hold_bars = [0] + [max(1, int(round(h * bph))) for h in (4, 12)]
    roll = max(20, int(round(24 * 4 * bph)))
    filters = {"none": {}, "rvol>1.5": {"min_rvol": 1.5},
               "rvol>2.5": {"min_rvol": 2.5}, "ATRrank>0.5": {"min_atr_rank": 0.5}}
    cfgs = []
    for ah, am in [a for a in ANCHORS if a != (8, 0)]:
        am2 = roll if ah == -1 else am
        for mode in (0, 1, 2, 3, 4):
            band_ks = [2.0] if mode in (0, 4) else [1.5, 2.0, 2.5]
            targets = [0, 3] if mode in (0, 3, 4) else [0, 1, 2, 3]
            stops = ([(0, 6.0), (1, 6.0)] if mode == 0
                     else [(0, 0.5), (0, 1.0), (1, 1.0), (1, 2.0)])
            for bk in band_ks:
                for sm, sk in stops:
                    for tm in targets:
                        for rr in ([1.0, 2.0, 3.0] if tm == 3 else [0.0]):
                            for hb in hold_bars:
                                for fname, fover in filters.items():
                                    c = dict(DEFAULTS)
                                    c.update(anchor_hour=ah, anchor_minute=am2,
                                             mode=mode, fill_mode=1, band_k=bk,
                                             stop_mode=sm, stop_k=sk,
                                             target_mode=tm, rr=rr,
                                             max_hold_bars=hb,
                                             warmup_bars=max(2, int(bph * 2)))
                                    c.update(fover)
                                    c["filter"] = fname
                                    cfgs.append(c)
    return cfgs


def kappa(r: np.ndarray, span_days: float) -> float:
    """K = R per day / |max drawdown in R|. The quantity the goal is made of.

    Undefined (and returned as nan) when the series never draws down or never
    makes money - both of which are artefacts of a tiny sample, not strategies
    worth selecting.
    """
    if len(r) < 5 or span_days <= 0:
        return np.nan
    eq = np.concatenate(([0.0], np.cumsum(r)))
    dd = float((eq - np.maximum.accumulate(eq)).min())
    if dd >= 0:
        return np.nan
    rpd = float(r.sum()) / span_days
    return rpd / abs(dd) if rpd > 0 else np.nan


def _panel(args):
    sym, tf = args
    try:
        df = fx_data.build_tf(sym, tf)
    except Exception as e:                                  # noqa: BLE001
        return [], [], f"{sym} {tf}: {e}"
    if len(df) < 20_000:
        return [], [], f"{sym} {tf}: only {len(df)} bars"

    bph = TFS[tf]
    fee, slip, minrisk = COSTS[sym]
    cfgs = fast_grid(bph)
    for c in cfgs:
        c["min_risk_bps"] = minrisk
    feats = features(df)
    pad = int(PAD_DAYS * 24 * bph)

    q0 = (df.index[0] + pd.DateOffset(months=TRAIN_MONTHS))
    q0 = (q0 + pd.offsets.QuarterBegin(startingMonth=1)).normalize()
    fold_rows, trade_rows = [], []

    for t0 in pd.date_range(q0, df.index[-1], freq="QS", tz="UTC"):
        tr_lo = t0 - pd.DateOffset(months=TRAIN_MONTHS)
        te_hi = t0 + pd.DateOffset(months=TEST_MONTHS)
        if te_hi > df.index[-1]:
            break
        train, f_tr, pad_tr = _slice_with_pad(df, feats, tr_lo, t0, pad)
        test, f_te, pad_te = _slice_with_pad(df, feats, t0, te_hi, pad)
        if len(train) < 5000 or len(test) - pad_te < 500:
            continue

        # Train at DOUBLE cost: HANDOFF.md fixes this and it is the rule that
        # kept four fragile legs out of H-002's book. Both criteria are ranked
        # on the same 2x series so the comparison is only about the criterion.
        tr_span = (train.index[-1] - train.index[pad_tr]).total_seconds() / 86400.0
        vw_tr = {}
        pfs = np.full(len(cfgs), np.nan)
        kks = np.full(len(cfgs), np.nan)
        cnts = np.zeros(len(cfgs), dtype=int)
        for ci, cfg in enumerate(cfgs):
            r, _, _ = _run(train, f_tr, pad_tr, cfg, fee * 2, slip * 2, vw_tr)
            cnts[ci] = len(r)
            if len(r):
                pfs[ci] = _pf(r)
                kks[ci] = kappa(r, tr_span)

        elig = np.flatnonzero((cnts >= FLOOR) & np.isfinite(pfs))
        if elig.size == 0:
            continue

        te_span = (test.index[-1] - test.index[pad_te]).total_seconds() / 86400.0
        vw_te, vw_te2, cache = {}, {}, {}

        def run_book(pick):
            rs, r2s, ex, en = [], [], [], []
            for ci in pick:
                if ci not in cache:
                    a = _run(test, f_te, pad_te, cfgs[ci], fee, slip, vw_te)
                    b, _, _ = _run(test, f_te, pad_te, cfgs[ci], fee * 2,
                                   slip * 2, vw_te2)
                    cache[ci] = (a[0], a[1], a[2], b)
                r1, e1, n1, r2 = cache[ci]
                if not len(r1):
                    continue
                rs.append(r1 / len(pick)); r2s.append(r2 / len(pick))
                ex.append(e1); en.append(n1)
            if not rs:
                return None
            r1 = np.concatenate(rs); r2 = np.concatenate(r2s)
            e = np.concatenate(ex); n = np.concatenate(en)
            o = np.argsort(e, kind="stable")
            return r1[o], r2[o], e[o], n[o]

        for crit, score in (("pf", pfs), ("K", kks)):
            good = elig[np.isfinite(score[elig])]
            if good.size == 0:
                continue
            order = good[np.argsort(-score[good])][:TOPN]
            got = run_book(order)
            if got is None:
                continue
            r1, r2, e, n = got
            fold_rows.append({
                "symbol": sym, "tf": tf, "quarter": str(t0.date()), "crit": crit,
                "train_score": round(float(score[order[0]]), 5),
                "train_pf": round(float(pfs[order[0]]), 3),
                "train_K": round(float(kks[order[0]]), 5)
                if np.isfinite(kks[order[0]]) else None,
                "n_eligible": int(elig.size),
                "test_trades": int(len(r1)),
                "test_pf_2x": round(_pf(r2), 3),
                "test_tpd": round(len(r1) / max(te_span, 1e-9), 3),
                "test_total_r": round(float(r1.sum()), 3),
            })
            trade_rows.append(pd.DataFrame({
                "symbol": sym, "tf": tf, "crit": crit, "quarter": str(t0.date()),
                "entry_ts": test.index[n], "exit_ts": test.index[e],
                "r": r1, "r_2x": r2}))

    return fold_rows, trade_rows, f"{sym} {tf}: {len(fold_rows)} fold rows"


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    combos = [(s, tf) for s in MARKETS for tf in TFS]
    folds, trades, t0 = [], [], time.time()
    with ProcessPoolExecutor(max_workers=14) as ex:
        futs = {ex.submit(_panel, c): c for c in combos}
        for fu in as_completed(futs):
            f, t, msg = fu.result()
            folds += f
            trades += t
            print(f"  [{time.time()-t0:5.0f}s] {msg}", flush=True)

    fd = pd.DataFrame(folds)
    fd.to_csv(OUT / "stage3_folds.csv", index=False)
    if trades:
        pd.concat(trades, ignore_index=True).to_parquet(OUT / "stage3_trades.parquet")
    print(f"\n{len(fd)} fold rows, {time.time()-t0:.0f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
