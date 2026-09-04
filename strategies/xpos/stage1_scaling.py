"""Does K scale with the number of legs? The cheap test, on H-009's own trades.

Stage 0 fixed the target: K = R_per_day / |maxDD_R|, and the goal needs 2.2x
H-009's K for 14 days, 4.5x for 7.

K is SCALE-INVARIANT - multiplying every trade's R by a constant moves the
numerator and the denominator equally - so "equal weight divides R by the leg
count" cannot by itself explain H-012's dilution result. What actually happens
when legs are added is that the book's R per day becomes the MEAN of the legs'
(so a weak leg drags it down) while its drawdown falls like 1/sqrt(N) only if
the legs are genuinely uncorrelated. For equal-quality uncorrelated legs:

    K(N)  =  sqrt(N) * K(1)

which is the entire case for a wider universe, and the entire reason H-012
failed with 57 legs whose median R/day was negative.

This measures the exponent directly on H-009's eight legs before any new
compute is spent: fit K(N) over every subset of every size. If the exponent is
near 0.5 the wide book is worth building; if it is near 0, nothing about a
wider universe will reach the goal and the search has to go elsewhere.

Output: backtests/xpos/stage1_scaling.csv
"""
from __future__ import annotations

import itertools
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

OUT = ROOT / "backtests" / "xpos"
TRADES = ROOT / "backtests" / "gated_vwap" / "stage6_trades.parquet"


def kstat(s: pd.DataFrame, nlegs: int) -> dict | None:
    """R/day, max drawdown in R and K for one equal-weight book."""
    if len(s) < 50:
        return None
    r = s.r_2x.values / nlegs
    eq = np.concatenate(([0.0], np.cumsum(r)))
    dd = float((eq - np.maximum.accumulate(eq)).min())
    span = max((s.exit_ts.max() - s.entry_ts.min()).days, 1)
    rpd = float(r.sum()) / span
    if dd >= 0 or rpd <= 0:
        return None
    return {"r_per_day": rpd, "max_dd_r": dd, "K": rpd / abs(dd),
            "trades": len(s), "tpd": len(s) / span}


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    t = pd.read_parquet(TRADES)
    t["entry_ts"] = pd.to_datetime(t.entry_ts, utc=True)
    t["exit_ts"] = pd.to_datetime(t.exit_ts, utc=True)
    t = t[t.gated].copy()                      # H-009 is the gated book

    legs = sorted(set(zip(t.symbol, t.tf)))
    # Common window: every subset is measured over identical dates, else a
    # late-starting leg silently shortens the window and the comparison is
    # between two different periods rather than two different books.
    common = max(t[(t.symbol == a) & (t.tf == b)].entry_ts.min() for a, b in legs)
    t = t[t.entry_ts >= common]
    print(f"H-009 gated trades, common window from {common:%Y-%m-%d}: "
          f"{len(t):,} trades across {len(legs)} legs\n")

    print("  per leg, alone:")
    solo = {}
    for a, b in legs:
        k = kstat(t[(t.symbol == a) & (t.tf == b)], 1)
        solo[(a, b)] = k
        if k:
            print(f"    {a:8s} {b:4s}  R/day {k['r_per_day']:+.4f}  "
                  f"maxDD {k['max_dd_r']:7.2f}R  K {k['K']:.4f}  "
                  f"{k['tpd']:.3f} trades/day")
        else:
            print(f"    {a:8s} {b:4s}  (no positive-R book)")

    rows = []
    print("\n  every subset, K by leg count:")
    print(f"    {'N':>2s}  {'subsets':>8s}  {'median K':>9s}  {'best K':>8s}  "
          f"{'median days':>12s}")
    for n in range(1, len(legs) + 1):
        ks = []
        for sub in itertools.combinations(legs, n):
            s = t[[(a, b) in sub for a, b in zip(t.symbol, t.tf)]]
            k = kstat(s.sort_values("exit_ts"), n)
            if k:
                ks.append(k["K"])
                rows.append({"n_legs": n, "legs": " + ".join(f"{a} {b}" for a, b in sub),
                             **{kk: round(vv, 5) for kk, vv in k.items()}})
        if not ks:
            continue
        med, best = float(np.median(ks)), float(np.max(ks))
        print(f"    {n:>2d}  {len(ks):>8d}  {med:>9.4f}  {best:>8.4f}  "
              f"{1.625/med:>12.1f}")

    df = pd.DataFrame(rows)
    df.to_csv(OUT / "stage1_scaling.csv", index=False)

    # Fit the exponent: log K = a + b log N. b ~= 0.5 is the diversification
    # law; b ~= 0 means adding legs buys nothing and the goal needs a different
    # mechanism, not a wider universe.
    g = df.groupby("n_legs").K.median()
    b, a = np.polyfit(np.log(g.index.values), np.log(g.values), 1)
    print(f"\n  FITTED EXPONENT: K ~ N^{b:.3f}   "
          f"(0.5 = clean diversification, 0 = no benefit)")
    kmax = df.K.max()
    print(f"  best single subset K = {kmax:.4f} -> {1.625/kmax:.1f} days")
    print(f"  goal needs K 0.1161 (14 days) / 0.2321 (7 days)")
    if b > 0.05:
        need = (0.1161 / g.iloc[0]) ** (1 / b)
        print(f"\n  At this exponent, 14 days needs about {need:.0f} "
              f"equal-quality uncorrelated legs.")
    print(f"\nwrote {OUT / 'stage1_scaling.csv'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
