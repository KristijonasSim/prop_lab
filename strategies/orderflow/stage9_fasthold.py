"""H-006 stage 9 — the 4-hour hold. TASK T1 from `NEXT.md`.

WHY THIS EXISTS. H-006 never died of signal. Stage 3's walk-forward holds PF
1.227 at double cost on BTC alone and beats every null seed; it needs ~548 days
because the equity curve draws down **63.5R** against H-002's 3.8R. The notes
say it plainly: "the reason it loses is drawdown, not profit factor". The
governing identity is

    days = maxDD_in_R / R_per_day x (target / cap)

so the only thing worth attacking is the numerator.

WHAT IS NEW HERE, AND IT IS ONE THING. Every hold H-006 has ever traded is in
`stage2_grid.HOLDS = (96, 144, 288, 576, 864)` — **8h to 72h**. The stacking
study then measured the same feed family at 4h and found it strong: BTC
`dcrowd_4h` −17.3bps monotone in 7 of 7 calendar years, BTC `crowd_z` −16.2bps
7 of 7, ETH and LINK the same at 6 of 6 (`strategies/stack/stage2_size.py`).
Nobody has ever traded this family at a hold that short. A 4h hold is 2-18x
shorter than what drew down 63.5R.

WHAT THIS IS NOT. It is not "add a stop and re-search". That was tested and
reverted on 2026-09-02: with `stop_k` in the fold selector the book went PF@2x
1.050 -> 1.007 on a profit-factor selector and 1.050 -> 0.990 on a
drawdown-aware one, because quadrupling the configuration count mostly bought
four times as many chances to fit the training quarter. So the hold here is
**FIXED at 48 bars** and not selectable, which keeps the configuration count at
560 against stage 3's 700 rather than above it.

THE TWO ARMS

  ARM A — the kill criterion, and it is measured before the backtest.
    Median max drawdown in R against hold length, in sample, over the same
    configuration family at 12/24/48/96/144/288/576/864 bars. If drawdown does
    NOT fall roughly in proportion to the hold, then the drawdown is not coming
    from hold length, the one new ingredient is spent, and this family is
    finished. That verdict is printed whatever arm B says.

  ARM B — the walk-forward, identical to stage 3 except for the hold.
    Config re-chosen blind every quarter on 2x-cost training profit factor,
    >= 40 closed training trades to be eligible, 4 quarters of history before
    the first test quarter, five block-shuffled null seeds through the same
    procedure. Scored on **days to a funded account**, not on profit factor —
    stage 5 of H-017 already showed a gate can raise PF and make a book slower.

THE STOP, AND THE ASSUMPTION UNDER IT. `of.run_one` fills AT the stop level on
the first bar that touches it. That is optimistic; a gap through fills worse.
Which is why every headline here is quoted at 2x cost and why the number is
provisional until an engine cross-check. Stops offered: none, 1.5, 2.0, 3.0
sigma — stage 4 found wider monotonically better and 1.0 sigma actively harmful,
so the harmful end is not re-tested.

Run: .venv/bin/python strategies/orderflow/stage9_fasthold.py
"""
from __future__ import annotations

import itertools
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from core import riskladder                                     # noqa: E402
from strategies.orderflow import orderflow as of                # noqa: E402
from strategies.orderflow.stage2_grid import vol_unit, FEE_BPS  # noqa: E402
from strategies.vwap.stage3_timeframes import null_seed         # noqa: E402

FEEDS = ROOT / "data" / "feeds"
OUT = ROOT / "backtests" / "orderflow"
OUT.mkdir(parents=True, exist_ok=True)

SYMS = ("BTCUSDT", "ETHUSDT", "SOLUSDT")

# --- the grid. Identical to stage 2 except HOLD and STOPS. -------------------
LOOKS = (12, 48, 144)                 # 1h, 4h, 12h  (dcrowd only)
WINS = (288, 864)                     # z baseline: 1 day, 3 days
QS = (0.02, 0.05, 0.10, 0.20, 0.30)   # how far into the tail an entry needs
BANDS = (2016, 8640)                  # trailing quantile window: 7d, 30d
HOLD = 48                             # 4 HOURS. The one new thing. Not selectable.
STOPS = (0.0, 1.5, 2.0, 3.0)          # sigmas; 1.0 was harmful in stage 4

# Arm A sweeps the hold instead, with the stop held at three values so the
# curve is not an artefact of one stop choice.
DD_HOLDS = (24, 48, 96, 144, 288, 576, 864)      # 2h .. 72h
DD_STOPS = (0.0, 2.0, 3.0)

TRAIN_Q = 4          # quarters of history before the first test quarter
MIN_TRAIN = 40       # closed trades a config needs to be eligible
NSEEDS = 5
WORKERS = 8
GATE = 1.20
CFGKEY = ["signal", "look", "win", "q", "band", "hold", "contrarian", "stop_k"]


def grid(holds=(HOLD,), stops=STOPS):
    for kind in of.SIGNALS:
        looks = LOOKS if kind == "dcrowd" else (0,)
        wins = (288,) if kind == "dcrowd" else WINS
        for look, win, q, band, hold, contra, stop in itertools.product(
                looks, wins, QS, BANDS, holds, (True, False), stops):
            yield {"signal": kind, "look": look, "win": win, "q": q,
                   "band": band, "hold": hold, "contrarian": contra,
                   "stop_k": stop}


def families(holds=(HOLD,), stops=STOPS):
    """Configurations grouped by what they share — same signal, same trailing
    quantiles. The rolling quantile over a 30-day window of 5m bars is where the
    time goes, and every config in a family reuses one."""
    fam = {}
    for cfg in grid(holds, stops):
        key = (cfg["signal"], cfg["look"], cfg["win"], cfg["q"], cfg["band"])
        fam.setdefault(key, []).append(cfg)
    return fam


def trades(df: pd.DataFrame, sig: pd.Series, cfg: dict, thr=None,
           vols=None) -> pd.DataFrame:
    """One configuration on one market, as R multiples at each cost level.

    R is the trade's return over a trailing volatility estimate that uses only
    closed bars, floored at 10bps so a dead stretch cannot manufacture a
    twenty-R winner. Same convention as stage 3, so the numbers compare."""
    vol = None if vols is None else vols[cfg["hold"]]
    t = of.run_one(df, sig, hold=cfg["hold"], q=cfg["q"], band=cfg["band"],
                   fee_bps=FEE_BPS, cost_mult=0.0, contrarian=cfg["contrarian"],
                   thr=thr, stop_k=cfg.get("stop_k", 0.0), vol=vol)
    if len(t) < 10:
        return pd.DataFrame()
    ei = t[:, 0].astype(int)
    xi = t[:, 1].astype(int)
    v = (vol if vol is not None else vol_unit(df, cfg["hold"]).values)[
        np.maximum(ei - 1, 0)]
    ok = np.isfinite(v) & (v > 0)
    if ok.sum() < 10:
        return pd.DataFrame()
    t, ei, xi, v = t[ok], ei[ok], xi[ok], v[ok]
    gross = t[:, 5]
    cost = FEE_BPS / 1e4
    idx = df.index
    return pd.DataFrame({
        "entry_ts": idx[ei], "exit_ts": idx[np.minimum(xi, len(idx) - 1)],
        "direction": t[:, 2],
        "r_0x": gross / v,
        "r": (gross - cost) / v,
        "r_2x": (gross - 2 * cost) / v,
        "r_3x": (gross - 3 * cost) / v,
    })


_CACHE = {}


def _init(sym):
    _CACHE[sym] = of.load(sym, FEEDS)


def _agg(t: pd.DataFrame, cfg: dict) -> dict:
    """Per-configuration summary at 2x cost. Arm A aggregates inside the worker
    because its grid at a 2h hold produces tens of thousands of trades per
    configuration and materialising them all is tens of millions of rows."""
    r2 = t.r_2x.values
    return {**cfg, "n": len(t), "dd": _maxdd(r2), "tot": float(r2.sum()),
            "pf": of.pf_of(r2)}


def _job(args):
    sym, key, cfgs, seed, agg = args
    df = _CACHE[sym]
    kind, look, win, q, band = key
    sig = of.signal_series(df, kind, look, win)
    if seed is not None:
        sig = of.block_shuffle(sig, null_seed(sym, kind, look, win, seed, "s9"))
    thr = of.thresholds(sig, q, band)
    vols = {h: vol_unit(df, h).values for h in {c["hold"] for c in cfgs}}
    out = []
    for cfg in cfgs:
        t = trades(df, sig, cfg, thr, vols)
        if t.empty:
            continue
        if agg:
            if len(t) >= 30:
                out.append({"symbol": sym, **_agg(t, cfg)})
            continue
        t["symbol"] = sym
        for k, v in cfg.items():
            t[k] = v
        out.append(t)
    if not out:
        return None
    return pd.DataFrame(out) if agg else pd.concat(out, ignore_index=True)


def run_all(sym: str, seed=None, holds=(HOLD,), stops=STOPS,
            agg: bool = False) -> pd.DataFrame:
    tasks = [(sym, k, v, seed, agg) for k, v in families(holds, stops).items()]
    with ProcessPoolExecutor(WORKERS, initializer=_init, initargs=(sym,)) as ex:
        got = [g for g in ex.map(_job, tasks, chunksize=1) if g is not None]
    return pd.concat(got, ignore_index=True) if got else pd.DataFrame()


def _maxdd(r: np.ndarray) -> float:
    eq = np.concatenate(([0.0], np.cumsum(r)))
    return abs(float((eq - np.maximum.accumulate(eq)).min()))


def _ret_over_dd(r: np.ndarray) -> float:
    dd = _maxdd(r)
    return float(r.sum()) / dd if dd > 0 else float("nan")


def walkforward(tr: pd.DataFrame) -> tuple:
    """Quarterly, config chosen only on trades that CLOSED before the quarter,
    ranked on 2x-cost profit factor. Deliberately the same selector stage 3
    used, so this run differs from the board record in the HOLD and nothing
    else."""
    if tr.empty:
        return pd.DataFrame(), pd.DataFrame()
    tr = tr.sort_values("exit_ts")
    tr["quarter"] = tr.exit_ts.dt.to_period("Q")
    quarters = sorted(tr.quarter.unique())
    picked, out = [], []
    for qi in range(TRAIN_Q, len(quarters)):
        q = quarters[qi]
        train = tr[tr.quarter < q]
        test = tr[tr.quarter == q]
        if train.empty or test.empty:
            continue
        g = train.groupby(CFGKEY, dropna=False)
        stats = g.r_2x.agg(["size", of.pf_of, _ret_over_dd])
        stats.columns = ["n", "pf2x", "ret_dd"]
        stats = stats[stats.n >= MIN_TRAIN]
        if stats.empty or not np.isfinite(stats.pf2x).any():
            continue
        best = stats.pf2x.idxmax()
        sel = test
        for k, v in zip(CFGKEY, best):
            sel = sel[sel[k] == v]
        if sel.empty:
            continue
        out.append(sel)
        picked.append({"quarter": str(q), **dict(zip(CFGKEY, best)),
                       "train_pf_2x": round(float(stats.loc[best, "pf2x"]), 4),
                       "train_n": int(stats.loc[best, "n"]),
                       "test_trades": len(sel),
                       "test_pf": round(of.pf_of(sel.r.values), 4),
                       "test_pf_2x": round(of.pf_of(sel.r_2x.values), 4)})
    stitched = pd.concat(out, ignore_index=True) if out else pd.DataFrame()
    return stitched, pd.DataFrame(picked)


# ---------------------------------------------------------------------------
# ARM A — does drawdown scale with hold length?
# ---------------------------------------------------------------------------

def arm_a(syms) -> pd.DataFrame:
    rows = []
    for sym in syms:
        t0 = time.time()
        per_all = run_all(sym, holds=DD_HOLDS, stops=DD_STOPS, agg=True)
        if per_all.empty:
            continue
        print(f"  {sym}: {len(per_all):,} configs priced "
              f"[{time.time()-t0:.0f}s]", flush=True)
        for (hold, stop), per in per_all.groupby(["hold", "stop_k"]):
            if per.empty:
                continue
            rows.append({"sym": sym, "hold": int(hold), "stop_k": float(stop),
                         "configs": int(len(per)),
                         "median_dd_r": round(float(per.dd.median()), 2),
                         "median_tot_r": round(float(per.tot.median()), 2),
                         "median_pf2x": round(float(per.pf.median()), 4),
                         "median_n": int(per.n.median())})
    return pd.DataFrame(rows)


def report_arm_a(a: pd.DataFrame):
    print(f"\n{'=' * 96}\nARM A — median max drawdown (R, at 2x cost) by HOLD "
          f"length. The kill criterion.\n{'=' * 96}")
    if a.empty:
        print("nothing measured"); return None
    piv = a.pivot_table(index="hold", columns="stop_k", values="median_dd_r",
                        aggfunc="mean")
    piv.index = [f"{h * 5 / 60:.0f}h ({h})" for h in piv.index]
    print(piv.round(1).to_string())
    m = a.groupby("hold").median_dd_r.mean()
    if HOLD not in m.index:
        return None
    base = m.reindex([96, 144, 288, 576, 864]).dropna()
    if base.empty:
        return None
    ratio_dd = float(m[HOLD]) / float(base.mean())
    ratio_hold = HOLD / float(np.mean(base.index.values))
    print(f"\n4h drawdown / mean 8-72h drawdown : {ratio_dd:.3f}")
    print(f"4h hold      / mean 8-72h hold      : {ratio_hold:.3f}")
    print("KILL CRITERION: drawdown must fall roughly in proportion to the "
          "hold.")
    print(f"VERDICT: {'PROPORTIONAL — hold length IS the drawdown' if ratio_dd <= ratio_hold * 2.5 else 'NOT PROPORTIONAL — drawdown is not coming from hold length'}")
    return ratio_dd, ratio_hold


# ---------------------------------------------------------------------------


def main():
    syms = [s for s in (sys.argv[1:] or list(SYMS))]
    have = []
    for s in syms:
        try:
            of.load(s, FEEDS); have.append(s)
        except FileNotFoundError:
            print(f"{s}: no feed on disk")
    if not have:
        print("no feeds"); return

    print(f"ARM A — drawdown vs hold, {len(list(grid(DD_HOLDS, DD_STOPS)))} "
          f"configs x {len(have)} coins", flush=True)
    a = arm_a(have)
    a.to_csv(OUT / "stage9_ddcurve.csv", index=False)
    report_arm_a(a)

    print(f"\n{'=' * 96}\nARM B — walk-forward at a FIXED {HOLD * 5 / 60:.0f}h "
          f"hold, {len(list(grid()))} configs\n{'=' * 96}", flush=True)
    per_sym, folds_all = {}, []
    for sym in have:
        t0 = time.time()
        tr = run_all(sym)
        st, fd = walkforward(tr)
        print(f"  {sym}: {len(tr):,} config-trades -> {len(st):,} out-of-sample"
              f" [{time.time()-t0:.0f}s]", flush=True)
        if st.empty:
            continue
        per_sym[sym] = st
        fd["symbol"] = sym
        folds_all.append(fd)
    if not per_sym:
        print("no folds resolved"); return

    stitched = pd.concat(per_sym.values(), ignore_index=True).sort_values("exit_ts")
    folds = pd.concat(folds_all, ignore_index=True)
    stitched.to_parquet(OUT / "stage9_trades.parquet", index=False)
    folds.to_csv(OUT / "stage9_folds.csv", index=False)

    n = len(per_sym)
    books = {"book": (stitched, n)}
    for sym, st in per_sym.items():
        books[sym] = (st, 1)

    print(f"\n{'book':10} {'trades':>7} {'PF':>7} {'PF@2x':>7} {'maxDD':>8} "
          f"{'R/day':>8} {'ret/DD':>7} {'tpd':>6} {'days':>7} {'risk':>6} "
          f"{'pass':>6}")
    summary = []
    for name, (st, k) in books.items():
        r = st.r.values / k
        r2 = st.r_2x.values / k
        span = max((st.exit_ts.max() - st.exit_ts.min()).days, 1)
        rows, best = riskladder.from_trades(r2, st.exit_ts)
        rec = {"book": name, "trades": len(st), "pf": round(of.pf_of(r), 3),
               "pf_2x": round(of.pf_of(r2), 3), "max_dd_r": round(_maxdd(r2), 1),
               "r_per_day": round(float(r2.sum()) / span, 4),
               "ret_dd": round(_ret_over_dd(r2), 2),
               "tpd": round(len(st) / span / max(k, 1), 2),
               "win_rate": round(float((r2 > 0).mean()), 4),
               "avg_r": round(float(r2.mean()), 4),
               "hold_h": HOLD * 5 / 60,
               "expected_days": best.get("expected_days"),
               "risk": best.get("risk"), "pass_rate": best.get("pass_rate"),
               "one_step_days": best.get("one_step", {}).get("expected_days")}
        summary.append(rec)
        print(f"{name:10} {rec['trades']:7d} {rec['pf']:7.3f} {rec['pf_2x']:7.3f} "
              f"{rec['max_dd_r']:8.1f} {rec['r_per_day']:8.4f} {rec['ret_dd']:7.2f} "
              f"{rec['tpd']:6.2f} {str(rec['expected_days']):>7} "
              f"{str(rec['risk']):>6} {str(rec['pass_rate']):>6}")
    pd.DataFrame(summary).to_csv(OUT / "stage9_summary.csv", index=False)

    print(f"\nSTAGE 3 RECORD FOR COMPARISON (8-72h holds, no stop):")
    print("  BTC+ETH+SOL  PF 1.143  PF@2x 1.050  maxDD 49.8R  R/day 0.045  "
          "1,119 days")
    print("  BTC only     PF 1.363  PF@2x 1.227  maxDD 63.5R  R/day 0.116  "
          "548 days")

    print(f"\nNULL — the same fold procedure on block-shuffled signals, "
          f"{NSEEDS} seeds", flush=True)
    null_pf2 = []
    for seed in range(NSEEDS):
        parts = []
        for sym in per_sym:
            st, _f = walkforward(run_all(sym, seed=seed))
            if not st.empty:
                parts.append(st)
        if not parts:
            continue
        s = pd.concat(parts, ignore_index=True)
        p = of.pf_of(s.r_2x.values / len(parts))
        null_pf2.append(p)
        print(f"  seed {seed}: PF@2x {p:.3f}  ({len(s)} trades)", flush=True)

    real2 = of.pf_of(stitched.r_2x.values / n)
    if null_pf2:
        print(f"\nreal PF@2x {real2:.3f}  vs null median "
              f"{np.median(null_pf2):.3f} / best {max(null_pf2):.3f}")
        print(f"beats every null seed: {real2 > max(null_pf2)}")
    print(folds.to_string(index=False))


if __name__ == "__main__":
    main()
