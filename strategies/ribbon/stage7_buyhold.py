"""H-016 stage 7 - the gold legs against simply owning gold.

Stage 6 found the only walk-forward survivors are gold, and stage 5 found the
winning configurations hold a position 76-83% of all bars in a market that rose
130%. That combination demands one specific question, and it is Kris's:

    does the strategy beat buy-and-hold on the same gold, over the same window?

MAKING THE COMPARISON FAIR. The strategy's P&L is in R multiples against its
initial stop; buy-and-hold's is a percentage. They are not comparable until
both are put on the same risk. This project already fixes how: size each so its
worst drawdown exactly fills the prop cap, then compare what each returns.

    strategy   risk per trade x% = DD_CAP / |maxDD_in_R|
               account return    = total_R * x%
    hold       leverage L        = DD_CAP / maxDD_pct
               account return    = L * hold_return

That is the same arithmetic as `days = maxDD_R / R_per_day x (target / cap)`,
which is how every other hypothesis here is scored. It flatters neither side:
whichever produces more return per unit of worst-case pain wins.

Reported on THREE windows, because the honest one is also the shortest:

  OOS      the stitched walk-forward quarters only - nothing chosen with
           hindsight. This is the number that counts.
  full     the whole gold cache, config chosen over the whole cache. In-sample
           and flattering, shown so the gap between the two is visible.
  drawdown both sides' worst peak-to-trough, since that is what decides
           whether an account survives to collect anything.

Output: backtests/ribbon/stage7_buyhold.csv
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
                                     load_tf, ribbon_inputs, run_one)
from strategies.ribbon.stage6_walkforward import (                 # noqa: E402
    FLOOR, PAD, TEST_MONTHS, TOPN, TRAIN_MONTHS, cost_adjusted, pf, run_window)

DD_CAP = 8.0          # the prop max-loss cap, in percent
TARGET = 8.0          # the prop profit target, in percent


def hold_stats(df: pd.DataFrame, lo=None, hi=None) -> dict:
    """Buy and hold: total return and worst peak-to-trough, on closes.

    Measured on the same bars the strategy saw, so neither side gets a window
    the other did not have.
    """
    d = df
    if lo is not None:
        d = d[(d.index >= lo) & (d.index <= hi)]
    c = d["close"].to_numpy(float)
    eq = c / c[0]
    dd = float((eq / np.maximum.accumulate(eq) - 1.0).min())
    days = max((d.index[-1] - d.index[0]).days, 1)
    ret = float(eq[-1] - 1.0)
    daily = pd.Series(np.diff(np.log(c)), index=d.index[1:]).resample("1D").sum()
    sd = daily.std(ddof=1)
    return {"ret_pct": ret * 100.0, "maxdd_pct": dd * 100.0, "days": days,
            "sharpe": float(daily.mean() / sd * np.sqrt(365)) if sd else 0.0,
            "time_in_market": 1.0}


def scaled(ret_pct: float, maxdd_pct: float, days: int) -> dict:
    """Lever a return stream so its worst drawdown exactly fills the 8% cap."""
    if maxdd_pct >= 0 or not np.isfinite(maxdd_pct):
        return {"lev": np.nan, "capped_ret": np.nan, "days_to_target": np.nan}
    lev = DD_CAP / abs(maxdd_pct)
    r = ret_pct * lev
    per_day = r / days
    return {"lev": lev, "capped_ret": r,
            "days_to_target": TARGET / per_day if per_day > 0 else np.nan}


def walkforward_series(sym: str, tf: str, rule: str):
    """Re-run stage 6 for one leg, keeping the stitched R series and its dates."""
    df = load_tf(sym, tf)
    inp = ribbon_inputs(df)
    fee, slip, mr = COSTS[sym]
    cfgs = build_grid(TFS[tf][1])
    for c in cfgs:
        c["min_risk_bps"] = mr

    start = df.index[0] + pd.DateOffset(months=TRAIN_MONTHS)
    start = (start + pd.offsets.QuarterBegin(startingMonth=1)).normalize()
    ends = pd.date_range(start, df.index[-1], freq="QS", tz="UTC")

    chunks, first, last, in_mkt, nbars = [], None, None, 0, 0
    for q in ends:
        tr_lo = q - pd.DateOffset(months=TRAIN_MONTHS)
        te_hi = q + pd.DateOffset(months=TEST_MONTHS)
        if te_hi > df.index[-1]:
            break
        train = run_window(inp, df, tr_lo, q, cfgs, fee, slip, mr)
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
        if first is None:
            first = q
        last = min(te_hi, df.index[-1])

        if rule == "single":
            r, tr = test.get(scored[0][1], (np.array([]), None))
            chunks.append(r)
            if tr is not None and tr.shape[0]:
                in_mkt += int((tr[:, E.T_EXIT_I] - tr[:, E.T_ENTRY_I]).sum())
        else:
            book = []
            for _, cid in scored[:TOPN]:
                r, tr = test.get(cid, (np.array([]), None))
                if len(r):
                    book.append(r / TOPN)
            chunks.append(np.concatenate(book) if book else np.array([]))
        nbars += ((df.index >= q) & (df.index < te_hi)).sum()

    r = np.concatenate([c for c in chunks if len(c)]) if chunks else np.array([])
    return r, first, last, (in_mkt / nbars if nbars and rule == "single" else np.nan)


def main() -> int:
    rows = []
    legs = [("XAUUSD", "1h", "single"), ("XAUUSD", "15m", "single"),
            ("XAUUSD", "1h", "top10"), ("XAUUSD", "15m", "top10"),
            ("XAUUSD", "30m", "single"), ("XAGUSD", "30m", "single")]

    print("GOLD STRATEGY vs OWNING GOLD, both levered to the same 8% drawdown cap\n")
    print("Out-of-sample only: the stitched walk-forward quarters.\n")
    hdr = (f"  {'leg':22s} {'trades':>7s} {'PF@2x':>6s} {'totalR':>7s} "
           f"{'maxDD_R':>8s} {'risk%':>6s} {'RETURN':>8s} {'days':>7s}")
    print(hdr)
    print("  " + "-" * (len(hdr) - 2))

    for sym, tf, rule in legs:
        r, lo, hi, tim = walkforward_series(sym, tf, rule)
        if len(r) < 30:
            continue
        eq = np.concatenate(([0.0], np.cumsum(r)))
        dd_r = float((eq - np.maximum.accumulate(eq)).min())
        days = max((hi - lo).days, 1)
        risk = DD_CAP / abs(dd_r) if dd_r < 0 else np.nan
        ret = float(r.sum()) * risk
        per_day = ret / days
        d2t = TARGET / per_day if per_day > 0 else np.nan
        print(f"  {sym+' '+tf+' '+rule:22s} {len(r):>7d} {pf(r):>6.3f} "
              f"{r.sum():>7.1f} {dd_r:>8.2f} {risk:>5.2f}% {ret:>7.1f}% "
              f"{d2t:>7.0f}")
        rows.append({"leg": f"{sym} {tf} {rule}", "kind": "strategy",
                     "window": f"{lo:%Y-%m-%d}..{hi:%Y-%m-%d}", "days": days,
                     "trades": len(r), "pf_2x": round(pf(r), 3),
                     "total_r": round(float(r.sum()), 2),
                     "maxdd_r": round(dd_r, 2), "risk_pct": round(risk, 3),
                     "capped_ret_pct": round(ret, 1),
                     "days_to_target": round(d2t, 1) if np.isfinite(d2t) else None,
                     "time_in_market": round(tim, 3) if np.isfinite(tim) else None})

        # the same window, simply owning the metal
        df = load_tf(sym, tf)
        h = hold_stats(df, lo, hi)
        s = scaled(h["ret_pct"], h["maxdd_pct"], h["days"])
        print(f"  {'  ^ BUY AND HOLD':22s} {'-':>7s} {'-':>6s} {'-':>7s} "
              f"{h['maxdd_pct']:>7.1f}% {s['lev']:>5.2f}x {s['capped_ret']:>7.1f}% "
              f"{s['days_to_target']:>7.0f}   (raw {h['ret_pct']:+.1f}%)")
        rows.append({"leg": f"{sym} {tf} {rule}", "kind": "buy_and_hold",
                     "window": f"{lo:%Y-%m-%d}..{hi:%Y-%m-%d}", "days": h["days"],
                     "raw_ret_pct": round(h["ret_pct"], 2),
                     "maxdd_pct": round(h["maxdd_pct"], 2),
                     "leverage": round(s["lev"], 3),
                     "capped_ret_pct": round(s["capped_ret"], 1),
                     "days_to_target": (round(s["days_to_target"], 1)
                                        if np.isfinite(s["days_to_target"]) else None),
                     "sharpe": round(h["sharpe"], 3), "time_in_market": 1.0})
        print()

    # The cap is doing the work above, so the uncapped view has to be shown
    # too - it is the relevant one for Kris's own money, where nothing forces a
    # position down to 0.28x. At a conventional 1% risk per trade the ranking
    # REVERSES, and that is the honest other half of the answer.
    print("\nSAME LEGS, NO CAP: 1% risk per trade against simply owning it\n")
    print(f"  {'leg':22s} {'strat ret':>10s} {'strat DD':>9s} "
          f"{'hold ret':>9s} {'hold DD':>8s}  verdict")
    for row in [r for r in rows if r["kind"] == "strategy"]:
        h = [x for x in rows if x["kind"] == "buy_and_hold"
             and x["leg"] == row["leg"]][0]
        sr, sd = row["total_r"] * 1.0, row["maxdd_r"] * 1.0
        v = "strategy" if sr > h["raw_ret_pct"] else "HOLD WINS"
        print(f"  {row['leg']:22s} {sr:>9.1f}% {sd:>8.1f}% "
              f"{h['raw_ret_pct']:>8.1f}% {h['maxdd_pct']:>7.1f}%  {v}")

    print("\nFULL CACHE, in-sample, for the gap between chosen-blind and chosen-late\n")
    for sym in ("XAUUSD", "XAGUSD"):
        df = load_tf(sym, "1h")
        h = hold_stats(df)
        s = scaled(h["ret_pct"], h["maxdd_pct"], h["days"])
        print(f"  {sym} hold {df.index[0]:%Y-%m}..{df.index[-1]:%Y-%m}: "
              f"raw {h['ret_pct']:+.1f}%, maxDD {h['maxdd_pct']:.1f}%, "
              f"at 8% cap {s['lev']:.2f}x -> {s['capped_ret']:+.1f}%, "
              f"{s['days_to_target']:.0f} days to +8%, Sharpe {h['sharpe']:.2f}")
        rows.append({"leg": f"{sym} full-cache", "kind": "buy_and_hold_full",
                     "window": f"{df.index[0]:%Y-%m-%d}..{df.index[-1]:%Y-%m-%d}",
                     "days": h["days"], "raw_ret_pct": round(h["ret_pct"], 2),
                     "maxdd_pct": round(h["maxdd_pct"], 2),
                     "leverage": round(s["lev"], 3),
                     "capped_ret_pct": round(s["capped_ret"], 1),
                     "days_to_target": round(s["days_to_target"], 1),
                     "sharpe": round(h["sharpe"], 3)})

    pd.DataFrame(rows).to_csv(OUT / "stage7_buyhold.csv", index=False)
    print(f"\nwrote {OUT / 'stage7_buyhold.csv'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
