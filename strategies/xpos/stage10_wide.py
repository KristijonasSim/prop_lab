"""H-017 stage 10 - H-009's exact kernel on every coin the crowd feed covers.

Stage 8 priced the goal: a 14-day median needs roughly annualised Sharpe 10-15
and H-009 has 3.73, so no single strategy here reaches it. What stage 1 DID
measure is that these legs diversify almost perfectly - K scales as N^0.441,
against a theoretical 0.5 - and H-009 runs eight legs on three coins while the
Binance metrics archive covers **eleven**. Nobody has ever run the kernel on
the other eight.

At the measured exponent, going from 8 legs to ~40 is 2.2x on K, which is the
difference between 48.7 days and roughly 22. That is not the goal, but it is
the largest honest improvement available and it is the only one left.

WHY THIS IS NOT H-012 AGAIN. H-012 widened a book to 57 legs and got SLOWER
(130.7 days held out), and its diagnosis was dilution: the median leg had R/day
-0.0013, so equal weighting dragged the book down. The legs added here are not
a grab bag - they are the identical kernel, on the identical asset class, with
the identical crowd gate, on the eight remaining coins whose feed H-006 and
H-015 already validated. If they come out as weak as H-012's did, that is the
answer and the wide book is dead for good.

Every leg is walk-forward: configuration chosen blind on the 12 months before
each test quarter, on 2x-cost profit factor, never re-chosen inside the test.
The crowd gate is H-009's, at its fixed zero threshold, read as-of each entry.

Output: backtests/xpos/stage10_legs.csv, stage10_trades.parquet
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

from strategies.vwap.stage6_walkforward import (TEST_MONTHS,        # noqa: E402
                                                TRAIN_MONTHS, _pf,
                                                _run, _slice_with_pad)
from strategies.vwap.engine import T_DIR, T_ENTRY_I, T_EXIT_I, T_R   # noqa: E402
from strategies.vwap.sweep import features, run_one                 # noqa: E402
from strategies.xpos.stage3_fastbook import fast_grid               # noqa: E402

FEEDS = ROOT / "data" / "feeds"
OUT = ROOT / "backtests" / "xpos"

COINS = ["ADAUSDT", "AVAXUSDT", "BNBUSDT", "BTCUSDT", "DOGEUSDT", "DOTUSDT",
         "ETHUSDT", "LINKUSDT", "LTCUSDT", "SOLUSDT", "XRPUSDT"]
#: 5m and 2h added after stage 12: the wide book's speed comes from leg count
#: and these are the only two clocks left that the 5-minute feed supports.
TFS = {"5min": 12.0, "15min": 4.0, "30min": 2.0, "1h": 1.0, "2h": 0.5,
       "4h": 0.25}
AGG = {"open": "first", "high": "max", "low": "min", "close": "last",
       "volume": "sum"}
#: A Binance USDT-M perp round trip, the same figure H-006 and H-009 use.
FEE, SLIP, MINRISK = 5.0, 2.0, 10.0
FLOOR, TOPN = 100, 10


def _run_dir(df, feats, n_pad, cfg, fee, slip, vw_cache):
    """`stage6._run`, but keeping the trade's SIDE.

    The upstream helper returns only (R, exit, entry). H-009's gate is
    directional - keep a long when the crowd is not already long, and the
    mirror for a short - so without the side there is no gate to apply.
    """
    tr = run_one(df, feats, vw_cache, cfg, fee, slip)
    if len(tr) == 0:
        e = np.empty(0)
        return e, e.astype(int), e.astype(int), e
    tr = tr[tr[:, T_ENTRY_I] >= n_pad]
    if len(tr) == 0:
        e = np.empty(0)
        return e, e.astype(int), e.astype(int), e
    return (tr[:, T_R], tr[:, T_EXIT_I].astype(int),
            tr[:, T_ENTRY_I].astype(int), tr[:, T_DIR])


def bars(sym: str, tf: str) -> pd.DataFrame:
    d = pd.read_parquet(FEEDS / f"{sym}_perp_5m.parquet")
    d = d[~d.index.duplicated(keep="last")].sort_index()
    return d.resample(tf, label="left", closed="left").agg(AGG).dropna(
        subset=["open"])


def crowd_signal(sym: str) -> pd.Series:
    """H-006's crowd reading: rolling z of the log long/short ACCOUNT ratio."""
    m = pd.read_parquet(FEEDS / f"{sym}_metrics_5m.parquet")
    c = np.log(m["count_long_short_ratio"].astype(float).replace(0.0, np.nan))
    mu = c.rolling(288, min_periods=144).mean().shift(1)
    sd = c.rolling(288, min_periods=144).std(ddof=0).shift(1)
    return (c - mu) / sd.replace(0.0, np.nan)


def asof(sig: pd.Series, when) -> np.ndarray:
    sd = sig.dropna()
    obs = pd.DataFrame({"ts": sd.index + pd.Timedelta("5min"),
                        "v": sd.values}).sort_values("ts")
    left = pd.DataFrame({"i": np.arange(len(when)),
                         "t": pd.Series(when)}).sort_values("t")
    j = pd.merge_asof(left, obs, left_on="t", right_on="ts",
                      direction="backward", tolerance=pd.Timedelta(days=1))
    return j.sort_values("i").v.values


def _panel(args):
    sym, tf = args
    try:
        df = bars(sym, tf)
    except Exception as e:                                      # noqa: BLE001
        return None, f"{sym} {tf}: {e}"
    if len(df) < 8000:
        return None, f"{sym} {tf}: {len(df)} bars"

    bph = TFS[tf]
    cfgs = fast_grid(bph)
    for c in cfgs:
        c["min_risk_bps"] = MINRISK
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
            r, _, _ = _run(train, f_tr, p_tr, cfg, FEE * 2, SLIP * 2, vw)
            cnt[ci] = len(r)
            if len(r):
                pfs[ci] = _pf(r)
        el = np.flatnonzero((cnt >= FLOOR) & np.isfinite(pfs))
        if not el.size:
            continue
        pick = el[np.argsort(-pfs[el])][:TOPN]

        v1, v2, ex, en, ds = {}, {}, [], [], []
        rs, r2s = [], []
        for ci in pick:
            r1c, e1, n1, d1 = _run_dir(test, f_te, p_te, cfgs[ci], FEE, SLIP, v1)
            r2c, _, _, _ = _run_dir(test, f_te, p_te, cfgs[ci], FEE * 2,
                                    SLIP * 2, v2)
            if not len(r1c) or len(r2c) != len(r1c):
                continue
            rs.append(r1c / len(pick)); r2s.append(r2c / len(pick))
            ex.append(e1); en.append(n1); ds.append(d1)
        if not rs:
            continue
        r1 = np.concatenate(rs); r2 = np.concatenate(r2s)
        e = np.concatenate(ex); n = np.concatenate(en); dv = np.concatenate(ds)
        o = np.argsort(e, kind="stable")
        out.append(pd.DataFrame({
            "symbol": sym, "tf": tf, "quarter": str(t0.date()),
            "entry_ts": test.index[n[o]], "exit_ts": test.index[e[o]],
            "direction": dv[o], "r": r1[o], "r_2x": r2[o]}))

    if not out:
        return None, f"{sym} {tf}: no folds"
    tr = pd.concat(out, ignore_index=True)

    # H-009's gate, fixed threshold at zero: keep a long only when the crowd
    # reading is falling / not already long, and the mirror for a short.
    try:
        cz = asof(crowd_signal(sym), tr.entry_ts)
    except Exception:
        cz = np.full(len(tr), np.nan)
    # Stored per trade beside the side, so stage 11 can apply H-009's gate at
    # its fixed zero threshold without re-running any of this.
    tr["crowd_z"] = cz
    return tr, (f"{sym} {tf}: {len(tr)} trades, "
                f"PF2x {_pf(tr.r_2x.values):.3f}")


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    combos = [(s, tf) for s in COINS for tf in TFS]
    frames, t0 = [], time.time()
    with ProcessPoolExecutor(max_workers=12) as ex:
        futs = {ex.submit(_panel, c): c for c in combos}
        for fu in as_completed(futs):
            tr, msg = fu.result()
            if tr is not None:
                frames.append(tr)
            print(f"  [{time.time()-t0:5.0f}s] {msg}", flush=True)

    tr = pd.concat(frames, ignore_index=True)
    tr.to_parquet(OUT / "stage10_trades.parquet")

    rows = []
    for (s, tf), g in tr.groupby(["symbol", "tf"]):
        r = g.r_2x.values
        eq = np.concatenate(([0.0], np.cumsum(r)))
        dd = float((eq - np.maximum.accumulate(eq)).min())
        span = max((g.exit_ts.max() - g.entry_ts.min()).days, 1)
        rows.append({"symbol": s, "tf": tf, "trades": len(g),
                     "pf_2x": round(_pf(r), 3), "total_r": round(r.sum(), 2),
                     "max_dd_r": round(dd, 2),
                     "tpd": round(len(g) / span, 3),
                     "K": round((r.sum() / span) / abs(dd), 5)
                     if dd < 0 and r.sum() > 0 else np.nan})
    legs = pd.DataFrame(rows).sort_values("K", ascending=False)
    legs.to_csv(OUT / "stage10_legs.csv", index=False)
    print(f"\n{len(legs)} legs, {time.time()-t0:.0f}s")
    print(legs.head(20).to_string(index=False))
    print(f"\nlegs with PF@2x >= 1.20: {(legs.pf_2x >= 1.2).sum()} of {len(legs)}")
    print(f"median leg K: {legs.K.median():.5f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
