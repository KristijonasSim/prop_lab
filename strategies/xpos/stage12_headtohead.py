"""H-017 stage 12 - the wide book against H-009, on one identical window.

Stage 11's best held-out book is 45.9 expected days and H-009's board record
says 48.7, but those are measured over different spans and the comparison is
worthless as it stands. This puts both on the same dates.

The window is the stage 11 HELD-OUT half - the period the wide book's legs were
NOT chosen on. H-009's legs were chosen (by the earlier project) with knowledge
of this period, so if anything the comparison now favours H-009.

Both books are sized the same way: scaled so worst drawdown exactly fills the
8% cap, then run through the project's real two-step evaluation.

Output: backtests/xpos/stage12_headtohead.csv
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from strategies.xpos.stage11_book import (apply_gate, book_stats,   # noqa: E402
                                          simulate)

OUT = ROOT / "backtests" / "xpos"
H009 = ROOT / "backtests" / "gated_vwap" / "stage6_trades.parquet"


def main() -> int:
    wide = pd.read_parquet(OUT / "stage10_trades.parquet")
    wide["entry_ts"] = pd.to_datetime(wide.entry_ts, utc=True)
    wide["exit_ts"] = pd.to_datetime(wide.exit_ts, utc=True)
    picks = pd.read_csv(OUT / "stage11_book.csv")
    best = picks[picks.expected_days.notna()].sort_values("expected_days").iloc[0]
    sub = [tuple(x.rsplit(" ", 1)) for x in best.legs.split(", ")]
    nlegs = int(best.n_legs)

    h9 = pd.read_parquet(H009)
    h9["entry_ts"] = pd.to_datetime(h9.entry_ts, utc=True)
    h9["exit_ts"] = pd.to_datetime(h9.exit_ts, utc=True)
    h9 = h9[h9.gated]
    n9 = h9.groupby(["symbol", "tf"]).ngroups

    mid = wide.exit_ts.quantile(0.5)
    lo = max(mid, h9.exit_ts.min())
    hi = min(wide.exit_ts.max(), h9.exit_ts.max())
    print(f"common window {lo:%Y-%m-%d} -> {hi:%Y-%m-%d}  "
          f"({(hi-lo).days} days)\n")

    def cut(d):
        return d[(d.exit_ts >= lo) & (d.exit_ts <= hi)].sort_values("exit_ts")

    rows = []
    print(f"  {'book':34s} {'legs':>5s} {'trades':>8s} {'t/day':>7s} "
          f"{'PF2x':>6s} {'K':>8s} {'pass':>6s} {'median':>7s} {'EXPECTED':>9s}")

    w = cut(wide[[(a, b) in sub for a, b in zip(wide.symbol, wide.tf)]])
    wg = cut(apply_gate(wide)[[(a, b) in sub for a, b in
                               zip(apply_gate(wide).symbol, apply_gate(wide).tf)]])
    h = cut(h9)

    for label, d, n in (("H-009 (3 coins + gold, gated)", h, n9),
                        ("H-017 wide, ungated", w, nlegs),
                        ("H-017 wide + crowd gate", wg, nlegs)):
        st = book_stats(d, n)
        if not st:
            print(f"  {label:34s}  (too few trades)")
            continue
        sm = simulate(d, n)
        print(f"  {label:34s} {n:>5d} {st['trades']:>8d} {st['tpd']:>7.2f} "
              f"{st['pf_2x']:>6.3f} {st['K']:>8.5f} "
              f"{sm.get('pass_rate', 0)*100:>5.1f}% "
              f"{str(sm.get('median_days')):>7s} "
              f"{str(sm.get('expected_days')):>9s}")
        rows.append({"book": label, **st, **sm})

    # Combining them: the two books share a kernel but not a universe, so the
    # question is whether they diversify or duplicate.
    comb = pd.concat([h.assign(src="h009"), wg.assign(src="wide")],
                     ignore_index=True).sort_values("exit_ts")
    st = book_stats(comb, n9 + nlegs)
    if st:
        sm = simulate(comb, n9 + nlegs)
        print(f"  {'both books together':34s} {n9+nlegs:>5d} {st['trades']:>8d} "
              f"{st['tpd']:>7.2f} {st['pf_2x']:>6.3f} {st['K']:>8.5f} "
              f"{sm.get('pass_rate', 0)*100:>5.1f}% "
              f"{str(sm.get('median_days')):>7s} "
              f"{str(sm.get('expected_days')):>9s}")
        rows.append({"book": "both together", **st, **sm})

    pd.DataFrame(rows).to_csv(OUT / "stage12_headtohead.csv", index=False)
    print(f"\n  goal: 14 days")
    print(f"\nwrote {OUT / 'stage12_headtohead.csv'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
