"""H-023 stage 14 — price the cost lever at its FLOOR, on the real board book.

Stage 13 measured what maker pricing is worth on a fresh grid. This asks the
question that actually decides whether the whole direction is worth pursuing,
and it asks it of H-009 itself rather than of a new search:

    if execution were free, how fast would the board be?

That is the ceiling on every cost-reduction idea — maker entries, maker exits,
a better fee tier, a cheaper venue. If a 0bps round trip does not reach the
5-15 day phase target, no execution work can, and the direction closes.

METHOD. Cost enters an R multiple linearly, so the board's own two columns
pin the whole line: `r` is the trade at 1x cost and `r_2x` the same trade at
2x, therefore the cost burden is (r - r_2x) per trade and

    r(c) = r - (c - 1) * (r - r_2x)

is exact, not an approximation - it reproduces r at c=1 and r_2x at c=2 by
construction. No re-backtest is needed and no new fit is introduced.

VALIDATION FIRST. The reconstruction is only worth reading if it reproduces the
published board numbers at c=1. H-009 stands at 92.4% pass and 45 median days
on the two-step structure; if this file does not land there, the reconstruction
is wrong and every other row is noise. That check is printed before anything
else.

Run: .venv/bin/python strategies/vwap/stage14_costfloor.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from core import riskladder                                    # noqa: E402

TRADES = ROOT / "backtests" / "gated_vwap" / "stage6_trades.parquet"
OUT = ROOT / "backtests" / "queue"
OUT.mkdir(parents=True, exist_ok=True)

# Cost multipliers, as a fraction of the repo's 1x assumption (crypto: 5bps
# taker + 2bps slippage per side, 14bps the round trip).
LEVELS = {
    "2.0x  (28bps) board stress": 2.0,
    "1.0x  (14bps) BOARD":        1.0,
    "0.64x  (9bps) maker exit":   9.0 / 14.0,
    "0.29x  (4bps) full maker":   4.0 / 14.0,
    "0.00x  (0bps) FREE":         0.0,
}


def book_daily(t: pd.DataFrame, c: float) -> tuple[pd.Series, np.ndarray]:
    """Equal-weight the legs, then sum to a daily R stream at cost multiple c."""
    r = t.r - (c - 1.0) * (t.r - t.r_2x)
    n_legs = t.groupby(["symbol", "tf"]).ngroups
    w = r / n_legs                          # equal weight per leg, as the board does
    daily = pd.Series(w.values, index=pd.DatetimeIndex(t.exit_ts)).resample("1D").sum()
    return daily, w.values


def main():
    t = pd.read_parquet(TRADES)
    # H-009 IS the gated book: keep only the trades the crowd gate lets through.
    g = t[t.gated].copy() if t.gated.any() else t.copy()
    print(f"H-009 book: {len(g):,} gated trades of {len(t):,}, "
          f"{g.groupby(['symbol', 'tf']).ngroups} legs, "
          f"{g.exit_ts.min():%Y-%m} -> {g.exit_ts.max():%Y-%m}")
    print(f"legs: {sorted(set(zip(g.symbol, g.tf)))}")

    rows = []
    for label, c in LEVELS.items():
        daily, rr = book_daily(g, c)
        try:
            _, best = riskladder.from_trades(rr, g.exit_ts)
        except Exception as e:
            print(f"{label}: ladder failed {e}")
            continue
        rows.append({
            "cost": label, "mult": c,
            "total_r": float(rr.sum()),
            "r_per_day": float(daily.mean()),
            "risk": best.get("risk"),
            "pass_rate": best.get("pass_rate"),
            "median_days": best.get("median_days"),
            "expected_days": best.get("expected") or best.get("expected_days"),
            "fail_max": best.get("fail_max"),
            "fail_daily": best.get("fail_daily"),
        })

    res = pd.DataFrame(rows)
    res.to_csv(OUT / "stage14_costfloor.csv", index=False)

    print(f"\n{'=' * 86}\nH-009 RE-PRICED. Board is the 1.0x row — it must "
          f"reproduce 92.4% / 45 days.\n{'=' * 86}")
    print(f"{'cost level':28} {'risk':>6} {'pass%':>7} {'median d':>9} "
          f"{'exp d':>7} {'totalR':>8} {'R/day':>7}")
    for _, r in res.iterrows():
        pr = "" if r.pass_rate is None else f"{100 * r.pass_rate:7.1f}"
        md = "" if r.median_days is None else f"{r.median_days:9.1f}"
        ed = "" if r.expected_days is None else f"{r.expected_days:7.1f}"
        print(f"{r.cost:28} {str(r.risk):>6} {pr} {md} {ed} "
              f"{r.total_r:8.1f} {r.r_per_day:7.4f}")

    print(f"\nwrote {OUT / 'stage14_costfloor.csv'}")


if __name__ == "__main__":
    main()
