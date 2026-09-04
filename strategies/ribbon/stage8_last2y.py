"""H-016 stage 8 - the gold legs against buy-and-hold over the LAST TWO YEARS.

Stage 7 ran on the stitched walk-forward window that happened to fall out of
the quarterly folds (2024-10-01 to 2026-07-01). Kris asked for the last two
years to today, so the window is pinned instead: **two years back from the end
of the data**, with the final partial quarter included rather than dropped.

Still walk-forward. The configuration is chosen blind on the 12 months before
each test quarter and never re-chosen inside it, exactly as stage 6 does. The
only change is the window and the fact the last, incomplete quarter is scored
instead of discarded.

Both sides are then put on the same risk twice:
  at the 8% prop cap - each levered so its worst drawdown exactly fills 8%
  at 1% risk        - the plain, uncapped comparison

Output: backtests/ribbon/stage8_last2y.csv
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from strategies.ribbon import engine as E                          # noqa: E402
from strategies.ribbon.sweep import (COSTS, OUT, TFS, build_grid,  # noqa: E402
                                     load_tf, ribbon_inputs)
from strategies.ribbon.stage6_walkforward import (                 # noqa: E402
    FLOOR, TOPN, TRAIN_MONTHS, pf, run_window)

DD_CAP, TARGET, YEARS = 8.0, 8.0, 2


def legs_series(sym: str, tf: str, rule: str, lo, hi):
    """Walk-forward R over [lo, hi], config chosen blind before each quarter."""
    df = load_tf(sym, tf)
    inp = ribbon_inputs(df)
    fee, slip, mr = COSTS[sym]
    cfgs = build_grid(TFS[tf][1])
    for c in cfgs:
        c["min_risk_bps"] = mr

    qs = pd.date_range(lo, hi, freq="QS", tz="UTC")
    qs = pd.DatetimeIndex([lo]).append(qs[qs > lo])
    chunks, in_mkt, nbars = [], 0, 0
    for i, q in enumerate(qs):
        te_hi = qs[i + 1] if i + 1 < len(qs) else hi        # last one is partial
        if te_hi <= q:
            continue
        train = run_window(inp, df, q - pd.DateOffset(months=TRAIN_MONTHS), q,
                           cfgs, fee, slip, mr)
        if not train:
            continue
        scored = [(pf(r), cid) for cid, (r, _) in train.items()
                  if len(r) >= FLOOR and np.isfinite(pf(r))]
        if not scored:
            continue
        scored.sort(reverse=True)
        test = run_window(inp, df, q, te_hi, cfgs, fee, slip, mr)
        if not test:
            continue
        if rule == "single":
            r, tr = test.get(scored[0][1], (np.array([]), None))
            chunks.append(r)
            if tr is not None and tr.shape[0]:
                in_mkt += int((tr[:, E.T_EXIT_I] - tr[:, E.T_ENTRY_I]).sum())
            nbars += int(((df.index >= q) & (df.index < te_hi)).sum())
        else:
            book = [test.get(cid, (np.array([]), None))[0]
                    for _, cid in scored[:TOPN]]
            book = [b / TOPN for b in book if len(b)]
            chunks.append(np.concatenate(book) if book else np.array([]))
    r = np.concatenate([c for c in chunks if len(c)]) if chunks else np.array([])
    return r, (in_mkt / nbars if nbars else np.nan)


def hold(df, lo, hi):
    d = df[(df.index >= lo) & (df.index <= hi)]
    c = d["close"].to_numpy(float)
    eq = c / c[0]
    return (float(eq[-1] - 1.0) * 100.0,
            float((eq / np.maximum.accumulate(eq) - 1.0).min()) * 100.0)


def main() -> int:
    end = load_tf("XAUUSD", "1h").index[-1]
    lo = (end - pd.DateOffset(years=YEARS)).normalize()
    print(f"WINDOW: {lo:%Y-%m-%d} -> {end:%Y-%m-%d}  "
          f"({(end - lo).days} days, walk-forward, config chosen blind)\n")

    rows = []
    print(f"  {'':26s} {'trades':>7s} {'PF@2x':>6s} {'maxDD':>8s} "
          f"{'size at 8% cap':>15s} {'RETURN':>8s} {'days to +8%':>12s}")
    print("  " + "-" * 88)
    for sym, tf, rule in (("XAUUSD", "15m", "top10"), ("XAUUSD", "1h", "top10"),
                          ("XAUUSD", "15m", "single"), ("XAUUSD", "1h", "single"),
                          ("XAUUSD", "30m", "single")):
        r, tim = legs_series(sym, tf, rule, lo, end)
        if len(r) < 20:
            continue
        eq = np.concatenate(([0.0], np.cumsum(r)))
        dd = float((eq - np.maximum.accumulate(eq)).min())
        risk = DD_CAP / abs(dd)
        ret = float(r.sum()) * risk
        days = (end - lo).days
        d2t = TARGET / (ret / days) if ret > 0 else np.nan
        print(f"  {sym+' '+tf+' '+rule:26s} {len(r):>7d} {pf(r):>6.3f} "
              f"{dd:>7.2f}R {risk:>13.2f}% {ret:>7.1f}% {d2t:>12.0f}")
        rows.append({"leg": f"{sym} {tf} {rule}", "kind": "strategy",
                     "trades": len(r), "pf_2x": round(pf(r), 3),
                     "total_r": round(float(r.sum()), 2), "maxdd_r": round(dd, 2),
                     "risk_pct_at_cap": round(risk, 2),
                     "capped_return_pct": round(ret, 1),
                     "days_to_target": round(d2t, 0) if np.isfinite(d2t) else None,
                     "ret_at_1pct_risk": round(float(r.sum()), 1),
                     "dd_at_1pct_risk": round(dd, 1),
                     "time_in_market": round(tim, 3) if np.isfinite(tim) else None})

    hr, hdd = hold(load_tf("XAUUSD", "1h"), lo, end)
    lev = DD_CAP / abs(hdd)
    hret = hr * lev
    days = (end - lo).days
    hd2t = TARGET / (hret / days) if hret > 0 else np.nan
    print(f"  {'BUY AND HOLD gold':26s} {'-':>7s} {'-':>6s} {hdd:>7.1f}% "
          f"{lev:>13.2f}x {hret:>7.1f}% {hd2t:>12.0f}")
    rows.append({"leg": "buy and hold gold", "kind": "hold",
                 "maxdd_pct": round(hdd, 2), "leverage_at_cap": round(lev, 2),
                 "capped_return_pct": round(hret, 1),
                 "days_to_target": round(hd2t, 0) if np.isfinite(hd2t) else None,
                 "ret_at_1pct_risk": round(hr, 1), "dd_at_1pct_risk": round(hdd, 1),
                 "time_in_market": 1.0})

    print(f"\n  Uncapped, at 1% risk per trade / 1x on the metal:")
    for x in rows:
        print(f"    {x['leg']:26s} {x['ret_at_1pct_risk']:>7.1f}%   "
              f"drawdown {x['dd_at_1pct_risk']:>6.1f}%")

    pd.DataFrame(rows).to_csv(OUT / "stage8_last2y.csv", index=False)
    print(f"\nwrote {OUT / 'stage8_last2y.csv'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
