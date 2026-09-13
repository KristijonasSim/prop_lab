"""H-034 GATE A — pace, and nothing else.

Pre-registered in `notes.md`: a reading must fire **at least 40 times a year on
BTCUSDT** or the hypothesis dies WITHOUT an edge test. The basis is smooth
(stdev 1.76% annualised), so the named most-likely death is that a sensible
threshold fires a handful of times a year and cannot resolve a 5-14 day
evaluation however good the edge is.

THIS FILE MEASURES NO EDGE. It counts events. That separation is the point: the
count is knowable in seconds and kills the idea before a kernel exists, which is
the pattern `core/probe.py` was built around and the twelve price hypotheses
skipped.

WHAT COUNTS AS AN EVENT, decided before any count was seen. A decile condition is
true on ~10% of bars, which is ~876 bars a year, and counting those would clear a
40/year gate trivially and dishonestly. **An event is the FRESH CROSS into the
state** - the first bar of a run - not every bar inside it. That is the
conservative reading and it is the one the bot already applies to its own signals.

THRESHOLDS ARE SHIFTED. A trailing quantile that includes the current bar judges
a bar partly on itself. `strategy.py` records the same lesson for rvol, where not
shifting inflated a profit factor from 0.627 to 2.765. Every threshold here is
`.shift(1)`.

Run: .venv/bin/python strategies/termstruct/pace.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

FEEDS = ROOT / "data" / "feeds"
MARKETS = ("BTCUSDT", "ETHUSDT")

WIN = 24 * 90            # trailing 90 days of hourly bars
MINP = 24 * 30           # 30 days before any threshold is emitted
MIN_EVENTS_PER_YEAR = 40  # THE GATE. Fixed 2026-09-13, before any count.


def readings(df: pd.DataFrame) -> dict[str, pd.Series]:
    """The six pre-registered readings, as boolean STATE series."""
    b = df.basis_ann
    hi = b.rolling(WIN, min_periods=MINP).quantile(0.90).shift(1)
    lo = b.rolling(WIN, min_periods=MINP).quantile(0.10).shift(1)

    d24 = b.diff(24)
    d_lo = d24.rolling(WIN, min_periods=MINP).quantile(0.05).shift(1)
    d_hi = d24.rolling(WIN, min_periods=MINP).quantile(0.95).shift(1)

    s = df.slope_bps
    s_hi = s.rolling(WIN, min_periods=MINP).quantile(0.90).shift(1)
    s_lo = s.rolling(WIN, min_periods=MINP).quantile(0.10).shift(1)

    return {
        "L+ rich": b >= hi,
        "L- cheap": b <= lo,
        "K  shock down": d24 <= d_lo,
        "K' shock up": d24 >= d_hi,
        "S  steep": s >= s_hi,
        "S' flat": s <= s_lo,
    }


def crosses(state: pd.Series) -> pd.Series:
    """Fresh entries into the state. NaN is not a state."""
    st = state.fillna(False).astype(bool)
    return st & ~st.shift(1, fill_value=False)


def main() -> int:
    print(f"H-034 GATE A - pace only. Gate: >= {MIN_EVENTS_PER_YEAR} "
          f"events/year on BTCUSDT.\n")
    verdict = {}
    for sym in MARKETS:
        p = FEEDS / f"{sym}_termstruct_1h.parquet"
        if not p.exists():
            print(f"{sym}: no {p.name} - run core/termstruct.py first")
            continue
        df = pd.read_parquet(p).sort_index()
        yrs = (df.index[-1] - df.index[0]).total_seconds() / (365.25 * 86400)
        print(f"=== {sym} === {len(df):,} hourly rows, "
              f"{df.index[0]:%Y-%m-%d} -> {df.index[-1]:%Y-%m-%d} ({yrs:.1f}y)")
        print(f"  basis_ann: median {df.basis_ann.median():.2f}%  "
              f"stdev {df.basis_ann.std():.2f}  "
              f"min {df.basis_ann.min():.2f}  max {df.basis_ann.max():.2f}")
        print(f"  slope available on {df.slope_bps.notna().sum():,} rows "
              f"({df.slope_bps.notna().mean() * 100:.0f}%)\n")

        print(f"  {'reading':16}{'events':>8}{'per year':>10}{'in state %':>12}"
              f"{'median run h':>14}  gate")
        for name, st in readings(df).items():
            ev = crosses(st)
            n = int(ev.sum())
            per_year = n / yrs if yrs else 0.0
            share = float(st.fillna(False).mean() * 100)
            # median length of a run, in hours
            runs = (st.fillna(False).astype(int).groupby(
                (~st.fillna(False)).cumsum()).sum())
            runs = runs[runs > 0]
            med = float(runs.median()) if len(runs) else 0.0
            ok = per_year >= MIN_EVENTS_PER_YEAR
            if sym == "BTCUSDT":
                verdict[name] = ok
            print(f"  {name:16}{n:8}{per_year:10.1f}{share:12.1f}{med:14.0f}"
                  f"  {'PASS' if ok else 'fail'}")
        print()

    if verdict:
        alive = [k for k, v in verdict.items() if v]
        print("GATE A on BTCUSDT: " +
              (f"{len(alive)} reading(s) pass -> {', '.join(alive)}" if alive
               else "NO reading fires often enough. H-034 DIES HERE, "
                    "with no edge test, exactly as pre-registered."))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
