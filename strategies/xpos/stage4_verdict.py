"""H-017 stage 4 - did selecting on K work, and how fast is the resulting book?

Two questions, in order, and the first one has to be answered before the second
is worth reading.

1. THE PAIRED METHOD TEST. Same folds, same grid, same kernel; the only
   difference is whether each fold ranked its candidates by profit factor at
   2x cost or by K at 2x cost. If choosing on K does not beat choosing on PF
   on days-to-funded, the idea is wrong and no book built on it counts.

   Reported as a paired comparison per panel, not as two averages, because the
   panels differ enormously and an average would hide which won.

2. THE BOOK. Subsets of surviving legs, equal weight, chosen on K, then run
   through the project's real two-step prop simulation - the same
   `riskladder.from_trades` every other hypothesis on the board is scored by.
   No shortcut estimate: the number that matters is expected days from the
   account simulation, against H-009's 48.7.

Output: backtests/xpos/stage4_legs.csv, stage4_books.csv
"""
from __future__ import annotations

import itertools
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from core import riskladder as RL                                    # noqa: E402
from strategies.xpos.stage3_fastbook import kappa                    # noqa: E402

OUT = ROOT / "backtests" / "xpos"
GATE = 1.20
MIN_TRADES = 100


def pf(r):
    w, l = r[r > 0].sum(), -r[r < 0].sum()
    return float(w / l) if l > 0 else np.nan


def stats(s: pd.DataFrame, nlegs: int = 1) -> dict | None:
    if len(s) < MIN_TRADES:
        return None
    r, r2 = s.r.values / nlegs, s.r_2x.values / nlegs
    eq = np.concatenate(([0.0], np.cumsum(r2)))
    dd = float((eq - np.maximum.accumulate(eq)).min())
    span = max((s.exit_ts.max() - s.entry_ts.min()).days, 1)
    rpd = float(r2.sum()) / span
    return {"trades": len(r), "pf": round(pf(r), 3), "pf_2x": round(pf(r2), 3),
            "tpd": round(len(r) / span, 3), "total_r_2x": round(float(r2.sum()), 2),
            "max_dd_r": round(dd, 2),
            "K": round(rpd / abs(dd), 5) if dd < 0 and rpd > 0 else np.nan,
            "r_per_day": round(rpd, 4),
            "days_est": round(1.625 * abs(dd) / rpd, 1) if dd < 0 and rpd > 0 else np.nan}


def main() -> int:
    tr = pd.read_parquet(OUT / "stage3_trades.parquet")
    tr["entry_ts"] = pd.to_datetime(tr.entry_ts, utc=True)
    tr["exit_ts"] = pd.to_datetime(tr.exit_ts, utc=True)

    rows = []
    for (sym, tf, crit), g in tr.groupby(["symbol", "tf", "crit"]):
        st = stats(g.sort_values("exit_ts"))
        if st:
            rows.append({"symbol": sym, "tf": tf, "crit": crit, **st})
    legs = pd.DataFrame(rows)
    legs.to_csv(OUT / "stage4_legs.csv", index=False)

    print("1. PAIRED: choosing each fold on K vs on profit factor\n")
    piv = legs.pivot_table(index=["symbol", "tf"], columns="crit",
                           values=["K", "pf_2x", "tpd", "days_est"])
    print(f"  {'panel':18s} {'PF-sel K':>9s} {'K-sel K':>9s} {'  winner':>9s}   "
          f"{'PF-sel days':>12s} {'K-sel days':>11s}")
    wins = {"K": 0, "pf": 0}
    for (sym, tf), r in piv.iterrows():
        kp, kk = r[("K", "pf")], r[("K", "K")]
        dp, dk = r[("days_est", "pf")], r[("days_est", "K")]
        if not (np.isfinite(kp) or np.isfinite(kk)):
            continue
        w = "K" if (np.nan_to_num(kk) > np.nan_to_num(kp)) else "pf"
        wins[w] += 1
        print(f"  {sym+' '+tf:18s} {kp:>9.5f} {kk:>9.5f} {w:>9s}   "
              f"{dp:>12.0f} {dk:>11.0f}")
    print(f"\n  K-selection wins {wins['K']} panels, PF-selection wins {wins['pf']}")
    for crit in ("pf", "K"):
        d = legs[legs.crit == crit]
        print(f"  {crit:>3s}-selected: median K {d.K.median():.5f}  "
              f"median trades/day {d.tpd.median():.2f}  "
              f"median PF@2x {d.pf_2x.median():.3f}  "
              f"legs clearing 1.20: {(d.pf_2x >= GATE).sum()}/{len(d)}")

    print("\n\n2. THE BOOK — real two-step prop simulation\n")
    books = []
    for crit in ("K", "pf"):
        d = tr[tr.crit == crit]
        keys = sorted({(a, b) for a, b in zip(d.symbol, d.tf)})
        good = [k for k in keys
                if (s := stats(d[(d.symbol == k[0]) & (d.tf == k[1])])) is not None
                and s["pf_2x"] >= GATE and np.isfinite(s["K"])]
        if not good:
            print(f"  {crit}: no leg clears the gate")
            continue
        # Common window so every subset is measured over identical dates.
        common = max(d[(d.symbol == a) & (d.tf == b)].entry_ts.min() for a, b in good)
        w = d[d.entry_ts >= common]
        idx = {k: np.flatnonzero((w.symbol.values == k[0]) & (w.tf.values == k[1]))
               for k in good}
        best = None
        # Capped at 5 legs: H-012 showed a wider book dilutes here, and stage 1
        # measured the diversification exponent at 0.441, so the marginal leg
        # buys little once the good ones are in.
        for n in range(1, min(len(good), 5) + 1):
            for sub in itertools.combinations(good, n):
                sel = np.sort(np.concatenate([idx[k] for k in sub]))
                s = w.iloc[sel].sort_values("exit_ts")
                st = stats(s, nlegs=n)
                if not st or st["pf_2x"] < GATE or not np.isfinite(st["K"]):
                    continue
                if best is None or st["K"] > best["st"]["K"]:
                    best = {"sub": sub, "s": s, "st": st, "n": n}
        if best is None:
            continue
        s, n = best["s"], best["n"]
        r2 = s.r_2x.values / n
        ladder = RL.from_trades(r2, s.exit_ts.values)
        rowsL, pick = ladder
        print(f"  selection = {crit}:  {n} legs  "
              f"{', '.join(a+' '+b for a, b in best['sub'])}")
        st = best["st"]
        print(f"    PF@2x {st['pf_2x']}  {st['trades']} trades  "
              f"{st['tpd']}/day  maxDD {st['max_dd_r']}R  K {st['K']}")
        print(f"    prop sim: {pick['risk']*100:.2f}% risk  "
              f"pass {pick['pass_rate']*100:.1f}%  "
              f"killed {(pick['fail_max']+pick['fail_daily'])*100:.1f}%  "
              f"median {pick['median_days']}d  "
              f"EXPECTED {pick['expected_days']}d")
        books.append({"crit": crit, "legs": ", ".join(a+" "+b for a, b in best["sub"]),
                      "n_legs": n, **st,
                      "risk": pick["risk"], "pass_rate": pick["pass_rate"],
                      "median_days": pick["median_days"],
                      "expected_days": pick["expected_days"]})

    pd.DataFrame(books).to_csv(OUT / "stage4_books.csv", index=False)
    print("\n  H-009 for comparison: expected 48.7 days. Goal: 14, ideally 7.")
    print(f"\nwrote {OUT / 'stage4_books.csv'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
