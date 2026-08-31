"""ORB stage 9 — a much wider set of session anchors, including Asia and the
half-hour opens the first grid missed.

The New York cash auction is 13:30 or 14:30 UTC depending on daylight saving,
never 13:00. That auction is the one event in this whole study with a documented
mechanism behind it, and the original grid never tested it. Tokyo, Sydney and the
London half-hours are added for the same reason.

Judged on the MEDIAN profit factor of each anchor's family, not the maximum. A
maximum tells you which cell got lucky; a median tells you whether the anchor
carries anything.
"""
from __future__ import annotations

import sys, time
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from strategies.orb.sweep import sweep, features, DEFAULTS      # noqa: E402
from strategies.orb.deep_test import OUT                        # noqa: E402
from strategies.orb.stage7_assets import ASSETS, load           # noqa: E402

ANCHORS = [
    (21, 0, "Sydney open"), (22, 0, "Sydney +1"),
    (0, 0, "Tokyo open / UTC day"), (1, 0, "Tokyo +1"), (2, 0, "Asia mid"),
    (4, 0, "Asia late"), (6, 0, "Frankfurt pre"), (7, 0, "Frankfurt open"),
    (7, 30, "London pre"), (8, 0, "London open"), (8, 30, "London +30"),
    (9, 0, "London +1"), (12, 0, "NY pre"), (13, 0, "NY futures"),
    (13, 30, "NY cash open (EDT)"), (14, 0, "NY +30"),
    (14, 30, "NY cash open (EST)"), (15, 0, "NY morning"),
    (16, 0, "NY afternoon"), (20, 0, "NY close"),
]

OR_BARS = [1, 2, 4, 8]
HOLD = [16, 32, 96]
ENTRY = [0, 1]
STOPS = [(0, 0.0), (2, 1.0), (2, 2.0)]
RR = [0.0, 1.0, 2.0]
FADE = [0, 1]


def base_grid(hour, minute):
    out = []
    for ob in OR_BARS:
        for hb in HOLD:
            for em in ENTRY:
                for sm, sa in STOPS:
                    for rr in RR:
                        for fd in FADE:
                            if fd == 1 and sm == 0:
                                continue     # OR-edge stop is meaningless on a fade
                            c = dict(DEFAULTS)
                            c.update(hour=hour, minute=minute, or_bars=ob, hold_bars=hb,
                                     entry_mode=em, stop_mode=sm, stop_atr_mult=sa,
                                     rr=rr, fade=fd)
                            out.append(c)
    return out


def main():
    rows = []
    for sym, (fee, slip, minrisk) in ASSETS.items():
        df = load(sym)
        feats = features(df)
        for hour, minute, name in ANCHORS:
            cfgs = base_grid(hour, minute)
            for c in cfgs:
                c["min_risk_bps"] = minrisk
            t = time.time()
            r = sweep(df, cfgs, fee_bps=fee, slip_bps=slip, feats=feats)
            r["symbol"], r["anchor"] = sym, name
            r["anchor_utc"] = f"{hour:02d}:{minute:02d}"
            rows.append(r)
        print(f"{sym} done ({len(ANCHORS)} anchors)", flush=True)

    out = pd.concat(rows, ignore_index=True)
    out.to_csv(OUT / "stage9_anchors.csv", index=False)
    print("saved stage9_anchors.csv", len(out), "rows")


if __name__ == "__main__":
    main()
