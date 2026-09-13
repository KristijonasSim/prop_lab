"""H-034 GATE B — does the term structure move forward returns?

Only runs because Gate A passed: all six readings fire 57-243 times a year on
both markets, against a pre-registered floor of 40. `pace.py` has the counts.

WHAT THIS IS. `core/probe.py`, the repo's gate-2 harness: forward return after
the event against the SAME statistic computed on randomly shifted event dates.
No stops, no targets, no sizing, no grid - those cost days and belong to gate 3.

THE READINGS ARE IMPORTED, NOT REDEFINED. `pace.py` owns the six definitions.
Two copies of an event definition drift, and the drift is invisible until a
number moves for no reason anyone can find.

DIRECTIONS ARE PRE-REGISTERED, in `notes.md`, before any of this ran:

    L+ rich        short   leverage is crowded long
    L- cheap       long
    K  shock down  short   the cash-and-carry unwind
    K' shock up    long
    S  steep       long    leverage demand arriving
    S' flat        short

EVERY READING SHIPS WITH ITS OPPOSITE AS A CONTROL. L+/L-, K/K', S/S' are
opposite events traded in opposite directions. If BOTH sides of a pair clear the
gate, the pair is measuring the market and not the mechanism, and both die. That
is H-030's discipline applied here.

Run: .venv/bin/python strategies/termstruct/edge.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from core.probe import by_year, probe                              # noqa: E402
from strategies.termstruct.pace import (FEEDS, MARKETS,            # noqa: E402
                                        crosses, readings)

HORIZONS = [4, 12, 24, 72]
#: reading -> pre-registered trade direction, and the reading that controls it
DIRECTION = {
    "L+ rich": -1, "L- cheap": +1,
    "K  shock down": -1, "K' shock up": +1,
    "S  steep": +1, "S' flat": -1,
}
PAIRS = (("L+ rich", "L- cheap"), ("K  shock down", "K' shock up"),
         ("S  steep", "S' flat"))
#: Gate B, fixed in notes.md before the first number
MIN_PCTILE = 95.0
MIN_YEARS_SAME_SIGN = 4


def main() -> int:
    out: dict[str, list] = {}
    frames = []
    for sym in MARKETS:
        p = FEEDS / f"{sym}_termstruct_1h.parquet"
        if not p.exists():
            print(f"{sym}: no {p.name} - run core/termstruct.py first")
            continue
        df = pd.read_parquet(p).sort_index()
        n = len(df)
        print(f"\n=== {sym} === {n:,} hourly rows, "
              f"{df.index[0]:%Y-%m-%d} -> {df.index[-1]:%Y-%m-%d}")
        print(f"  {'reading':16}{'h':>4}{'events':>8}{'edge_bps':>10}"
              f"{'base':>8}{'null_p95':>10}{'pct':>7}{'hurdle':>8}  gate")

        for name, state in readings(df).items():
            ev = crosses(state).values
            side = np.full(n, DIRECTION[name], dtype=float)
            r = probe(df, ev, HORIZONS, sym, name, side=side, n_null=400)
            r["market"] = sym
            frames.append(r)
            for _, row in r.iterrows():
                ok = (row.beats_hurdle and np.isfinite(row.pctile)
                      and row.pctile >= MIN_PCTILE)
                print(f"  {name:16}{int(row.h_bars):4}{int(row.events):8}"
                      f"{row.edge_bps:10.2f}{row.baseline_bps:8.2f}"
                      f"{row.null_p95:10.2f}{row.pctile:7.1f}"
                      f"{row.hurdle_bps:8.1f}  {'PASS' if ok else '.'}")

    if not frames:
        return 1
    allr = pd.concat(frames, ignore_index=True)

    # ---- Gate B, applied out loud ------------------------------------- #
    print("\n" + "=" * 72)
    print("GATE B: edge > hurdle, pctile >= 95, same sign in >= 4 of 6 years,")
    print("        and the opposite reading must NOT also clear.\n")
    survivors = []
    for sym in allr.market.unique():
        df = pd.read_parquet(FEEDS / f"{sym}_termstruct_1h.parquet").sort_index()
        sub = allr[allr.market == sym]
        for name in DIRECTION:
            rows = sub[sub.mechanism == name]
            hit = rows[(rows.beats_hurdle) & (rows.pctile >= MIN_PCTILE)]
            if not len(hit):
                continue
            best = hit.loc[hit.edge_bps.idxmax()]
            ev = crosses(readings(df)[name]).values
            side = np.full(len(df), DIRECTION[name], dtype=float)
            yr = by_year(df, ev, int(best.h_bars), side=side)
            pos = int((yr > 0).sum())
            same = max(pos, len(yr) - pos)
            print(f"  {sym} {name:16} h={int(best.h_bars):3} "
                  f"edge {best.edge_bps:7.2f}bps  pct {best.pctile:5.1f}  "
                  f"years {same}/{len(yr)}  {dict(yr)}")
            if same >= MIN_YEARS_SAME_SIGN:
                survivors.append((sym, name, float(best.edge_bps),
                                  int(best.h_bars)))

    names = {n for _, n, _, _ in survivors}
    for a, b in PAIRS:
        if a in names and b in names:
            print(f"\n  CONTROL FAILURE: {a} and {b} both clear. "
                  f"Opposite events in opposite directions cannot both be the "
                  f"mechanism. Both die.")
            survivors = [s for s in survivors if s[1] not in (a, b)]

    print()
    if survivors:
        for sym, name, e, h in survivors:
            print(f"  SURVIVES -> {sym} {name} h={h} edge {e:.2f}bps")
        print("\n  Survivors go to gate 3 (kernel + walk-forward). "
              "A survivor is a maybe, not a result.")
    else:
        print("  NOTHING SURVIVES GATE B. H-034 is closed by measurement, "
              "exactly as pre-registered.")

    dst = ROOT / "backtests" / "termstruct"
    dst.mkdir(parents=True, exist_ok=True)
    allr.to_json(dst / "edge.json", orient="records", indent=1)
    print(f"\nwrote backtests/termstruct/edge.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
