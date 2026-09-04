"""H-016 stage 9 - silver and the three US index CFDs.

Kris asked for silver, S&P 500, US30 and the Nasdaq. Silver was already in the
sweep; the three indices were not in the repo at all and were pulled from the
same Dukascopy feed everything else here uses (`core/fx_data.DUKAS_SYM`),
2023-09-01 to 2026-08-31, the identical window gold and silver run on.

Everything is the same procedure as stages 2, 3, 6 and 8 - the same 660-config
grid, the same paired null, the same blind walk-forward, the same
levered-to-the-8%-cap comparison against simply owning the thing. Nothing is
re-tuned for indices.

Indices are charged GOLD's cost model, which overstates their real spread.

Output: backtests/ribbon/stage9_indices.csv
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from strategies.ribbon.sweep import (OUT, TFS, build_grid, load_tf,  # noqa: E402
                                     shuffled, sweep)
from strategies.ribbon.stage6_walkforward import pf                  # noqa: E402
from strategies.ribbon.stage8_last2y import (DD_CAP, TARGET,         # noqa: E402
                                             YEARS, hold, legs_series)

NEW = ["XAGUSD", "SPX500", "US30", "NAS100"]
TF_SET = ["15m", "30m", "1h", "4h"]
NSEEDS = 3


def gate(d):
    return ((d.pf_2x >= 1.20) & np.isfinite(d.pf_2x)
            & (d.trades >= 100) & (d.trades_per_day >= 0.10))


def main() -> int:
    rows = []

    print("1. GRID vs PAIRED NULL — same 660 configs, 3 shuffle seeds\n")
    print(f"  {'market':8s} {'tf':>4s}  {'best PF@2x':>10s}  "
          f"{'clears: real':>12s}  {'null/seed':>9s}  {'median real/null':>18s}")
    for sym in NEW:
        for tf in TF_SET:
            df = load_tf(sym, tf)
            if len(df) < 5000:
                continue
            g = build_grid(TFS[tf][1])
            real = sweep(df, g, sym, tf)
            nulls = [sweep(shuffled(df, sym, tf, "s9", s), g, sym, tf)
                     for s in range(NSEEDS)]
            n = pd.concat(nulls)
            rc, nc = gate(real).sum(), gate(n).sum() / NSEEDS
            print(f"  {sym:8s} {tf:>4s}  {real.pf_2x.max():>10.3f}  "
                  f"{rc:>12,}  {nc:>9,.0f}  "
                  f"{real.pf_2x.median():>8.3f} / {n.pf_2x.median():.3f}"
                  f"{'   <-- beats null' if rc > nc else ''}")
            rows.append({"stage": "grid_vs_null", "symbol": sym, "tf": tf,
                         "best_pf_2x": round(real.pf_2x.max(), 3),
                         "real_clears": int(rc),
                         "null_clears_per_seed": round(nc, 1),
                         "real_median": round(real.pf_2x.median(), 3),
                         "null_median": round(n.pf_2x.median(), 3)})

    print("\n\n2. WALK-FORWARD, LAST 2 YEARS, vs BUY AND HOLD")
    print("   Config chosen blind on the 12 months before each test quarter.")
    print("   Both sides levered so worst drawdown exactly fills the 8% cap.\n")
    end = load_tf("XAUUSD", "1h").index[-1]
    lo = (end - pd.DateOffset(years=YEARS)).normalize()
    print(f"   window {lo:%Y-%m-%d} -> {end:%Y-%m-%d}\n")
    print(f"  {'':24s} {'trades':>7s} {'PF@2x':>6s} {'maxDD':>8s} "
          f"{'size@cap':>9s} {'RETURN':>8s} {'days':>6s}   {'vs hold':>9s}")
    print("  " + "-" * 92)

    for sym in ["XAUUSD"] + NEW:
        df = load_tf(sym, "1h")
        if len(df) < 5000:
            continue
        hr, hdd = hold(df, lo, end)
        hlev = DD_CAP / abs(hdd) if hdd < 0 else np.nan
        hret = hr * hlev
        days = (end - lo).days
        hd2t = TARGET / (hret / days) if hret > 0 else np.nan

        for tf, rule in (("15m", "top10"), ("1h", "top10"), ("15m", "single")):
            r, tim = legs_series(sym, tf, rule, lo, end)
            if len(r) < 20:
                continue
            eq = np.concatenate(([0.0], np.cumsum(r)))
            dd = float((eq - np.maximum.accumulate(eq)).min())
            if dd >= 0:
                continue
            risk = DD_CAP / abs(dd)
            ret = float(r.sum()) * risk
            d2t = TARGET / (ret / days) if ret > 0 else np.nan
            verdict = "WIN" if ret > hret else "lose"
            print(f"  {sym+' '+tf+' '+rule:24s} {len(r):>7d} {pf(r):>6.3f} "
                  f"{dd:>7.2f}R {risk:>8.2f}% {ret:>7.1f}% {d2t:>6.0f}   "
                  f"{verdict:>9s}")
            rows.append({"stage": "last2y", "symbol": sym, "tf": tf, "rule": rule,
                         "trades": len(r), "pf_2x": round(pf(r), 3),
                         "total_r": round(float(r.sum()), 2),
                         "maxdd_r": round(dd, 2), "risk_pct_at_cap": round(risk, 2),
                         "capped_return_pct": round(ret, 1),
                         "days_to_target": round(d2t, 0) if np.isfinite(d2t) else None,
                         "ret_at_1pct_risk": round(float(r.sum()), 1),
                         "time_in_market": round(tim, 3) if np.isfinite(tim) else None,
                         "beats_hold": bool(ret > hret)})
        print(f"  {'  BUY AND HOLD ' + sym:24s} {'-':>7s} {'-':>6s} "
              f"{hdd:>7.1f}% {hlev:>8.2f}x {hret:>7.1f}% {hd2t:>6.0f}"
              f"      (raw {hr:+.1f}%)")
        rows.append({"stage": "last2y", "symbol": sym, "rule": "buy_and_hold",
                     "maxdd_pct": round(hdd, 2), "leverage_at_cap": round(hlev, 2),
                     "capped_return_pct": round(hret, 1),
                     "days_to_target": round(hd2t, 0) if np.isfinite(hd2t) else None,
                     "ret_at_1pct_risk": round(hr, 1), "time_in_market": 1.0})
        print()

    pd.DataFrame(rows).to_csv(OUT / "stage9_indices.csv", index=False)
    print(f"wrote {OUT / 'stage9_indices.csv'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
