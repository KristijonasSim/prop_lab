"""H-017 stage 11 - the wide book, with the leg choice held out.

Stage 10 ran H-002's kernel, walk-forward, on all eleven coins the Binance
metrics archive covers: 33 legs, **29 of them clearing PF 1.20 at double cost**,
per-leg K up to 0.021 against the 0.0002-0.0116 stage 1 measured on H-009's own
eight. That is the opposite of H-012's dilution and it is why this is worth
building.

But 33 legs is a search. Picking the best of them on the window they are then
reported on is exactly the mistake H-012's held-out test was designed to catch,
and the one HANDOFF warns about. So:

  * legs are ranked on the FIRST HALF only,
  * the book is built from that ranking,
  * and every number that matters is measured on the SECOND HALF, which had no
    part in choosing anything.

The full-window figure is shown beside it purely so the size of the hindsight
premium is visible.

The crowd gate is H-009's, unchanged, at its fixed zero threshold: keep a long
only when the crowd reading is below zero, a short only when it is above.
Nothing is refitted and no threshold is searched.

Output: backtests/xpos/stage11_book.csv
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from core import riskladder as RL                                   # noqa: E402
from core.prop_rules import TWO_STEP                                # noqa: E402

OUT = ROOT / "backtests" / "xpos"
TARGET_DD_R = 4.0
GATE_PF = 1.20


def pf(r):
    w, l = r[r > 0].sum(), -r[r < 0].sum()
    return float(w / l) if l > 0 else np.nan


def maxdd(r):
    e = np.cumsum(r)
    return float((e - np.maximum.accumulate(e)).min())


def book_stats(s: pd.DataFrame, nlegs: int) -> dict | None:
    if len(s) < 200 or nlegs == 0:
        return None
    r = s.r_2x.values / nlegs
    dd = maxdd(r)
    span = max((s.exit_ts.max() - s.entry_ts.min()).days, 1)
    if dd >= 0 or r.sum() <= 0:
        return None
    return {"n_legs": nlegs, "trades": len(r), "pf_2x": round(pf(r), 3),
            "total_r": round(float(r.sum()), 2), "max_dd_r": round(dd, 2),
            "tpd": round(len(r) / span, 2),
            "K": round((r.sum() / span) / abs(dd), 5)}


def simulate(s: pd.DataFrame, nlegs: int) -> dict:
    """Sized to fill the 8% cap, then the project's real two-step evaluation."""
    r = s.r_2x.values / nlegs
    dd = maxdd(r)
    if dd >= 0:
        return {}
    r = r * (TARGET_DD_R / abs(dd))
    _rows, pick = RL.from_trades(r, s.exit_ts.values)
    return {"risk": pick["risk"], "pass_rate": pick["pass_rate"],
            "killed": round(pick["fail_max"] + pick["fail_daily"], 4),
            "median_days": pick["median_days"],
            "expected_days": pick["expected_days"]}


def apply_gate(t: pd.DataFrame) -> pd.DataFrame:
    """H-009's crowd gate, threshold fixed at zero, direction-aware."""
    v, d = t.crowd_z.values, t.direction.values
    keep = np.where(d > 0, v < 0, v > 0)
    keep = np.where(np.isnan(v), True, keep)
    return t[keep]


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    t = pd.read_parquet(OUT / "stage10_trades.parquet")
    t["entry_ts"] = pd.to_datetime(t.entry_ts, utc=True)
    t["exit_ts"] = pd.to_datetime(t.exit_ts, utc=True)
    t = t.sort_values("exit_ts")

    mid = t.exit_ts.quantile(0.5)
    print(f"{len(t):,} walk-forward trades, "
          f"{t.exit_ts.min():%Y-%m} -> {t.exit_ts.max():%Y-%m}")
    print(f"leg selection on the FIRST half (to {mid:%Y-%m-%d}), "
          f"every reported number on the SECOND\n")

    rows = []
    for label, tr in (("ungated", t), ("crowd-gated (H-009 rule)", apply_gate(t))):
        first, second = tr[tr.exit_ts <= mid], tr[tr.exit_ts > mid]
        legs = sorted(set(zip(tr.symbol, tr.tf)))

        # Rank on the first half only.
        rank = []
        for a, b in legs:
            g = first[(first.symbol == a) & (first.tf == b)]
            st = book_stats(g, 1)
            if st and st["pf_2x"] >= GATE_PF:
                rank.append((st["K"], a, b))
        rank.sort(reverse=True)
        print(f"{label}: {len(rank)} legs clear PF {GATE_PF} on the first half")

        for n in (1, 3, 5, 8, 12, 20, len(rank)):
            if n < 1 or n > len(rank):
                continue
            sub = [(a, b) for _, a, b in rank[:n]]
            sel = second[[(a, b) in sub for a, b in zip(second.symbol, second.tf)]]
            sel = sel.sort_values("exit_ts")
            st = book_stats(sel, n)
            if not st:
                continue
            sm = simulate(sel, n)
            full = tr[[(a, b) in sub for a, b in zip(tr.symbol, tr.tf)]].sort_values("exit_ts")
            sf = simulate(full, n)
            print(f"  {n:>3d} legs  held-out: PF2x {st['pf_2x']:>5.3f}  "
                  f"{st['tpd']:>6.2f} t/day  K {st['K']:.5f}  "
                  f"pass {sm.get('pass_rate', 0)*100:>5.1f}%  "
                  f"median {str(sm.get('median_days')):>6s}  "
                  f"EXPECTED {str(sm.get('expected_days')):>7s}"
                  f"   (full window {str(sf.get('expected_days')):>7s})")
            rows.append({"variant": label, **st, **sm,
                         "full_window_expected_days": sf.get("expected_days"),
                         "legs": ", ".join(f"{a} {b}" for a, b in sub)})
        print()

    df = pd.DataFrame(rows)
    df.to_csv(OUT / "stage11_book.csv", index=False)
    ok = df[df.expected_days.notna()]
    if len(ok):
        b = ok.loc[ok.expected_days.idxmin()]
        print(f"BEST held-out: {b.expected_days} expected days  "
              f"({b.n_legs} legs, {b.variant}, PF@2x {b.pf_2x}, {b.tpd} t/day)")
        print(f"  H-009 on the board: 48.7 expected days. Goal: 14.")
    print(f"\nwrote {OUT / 'stage11_book.csv'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
