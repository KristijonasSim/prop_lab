"""GATE 1 + GATE 2 — the first eight mechanisms, all testable with data we hold.

Every mechanism below names a FORCED TRADER before it names a pattern. That is
the point of the inversion: the twelve dead price hypotheses in this repo could
not name who was on the other side, and none of them survived.

Selection rule for this batch: **derivable from timestamps alone.** No download,
no new feed, so gate 2 runs in minutes rather than a session.

Run: .venv/bin/python mechanisms/run_batch1.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.probe import probe, by_year                      # noqa: E402
from strategies.vwap.stage3_timeframes import load_tf      # noqa: E402

# ---------------------------------------------------------------------------
# THE MECHANISMS. who is forced -> when -> why they cannot wait.
# ---------------------------------------------------------------------------

MECHANISMS = {
    "M-001 London 4pm fix": dict(
        who="index funds and corporates hedging FX exposure",
        when="16:00 London, every business day",
        why="mandates benchmark them to the 4pm WMR fix; missing it is tracking error",
        events_per_year=250,
        syms=["EURUSD", "GBPUSD", "XAUUSD"], tf="1h",
        # 15:00 UTC bar closes at the fix in winter, 16:00 does not exist as a
        # separate London hour under BST. Both are tested; the fix window is
        # what we are aiming at, not a specific clock hour.
        mask=lambda d: d.index.hour == 15,
    ),
    "M-002 Month-end rebalance": dict(
        who="global funds rebalancing currency hedges after a month of asset moves",
        when="last business day of the month, into the fix",
        why="the hedge ratio is set by mandate at month end, not when convenient",
        events_per_year=12,
        syms=["EURUSD", "GBPUSD", "XAUUSD"], tf="1h",
        mask=lambda d: (d.index.day >= 28) & (d.index.hour == 15),
    ),
    "M-003 Quarter-end": dict(
        who="the same hedgers, plus pension and index funds with quarterly mandates",
        when="last business days of Mar/Jun/Sep/Dec",
        why="quarterly reporting and mandate dates are hard deadlines",
        events_per_year=4,
        syms=["EURUSD", "XAUUSD"], tf="1h",
        mask=lambda d: (d.index.month.isin([3, 6, 9, 12]) & (d.index.day >= 28)),
    ),
    "M-004 Turn of month": dict(
        who="pension inflows and index funds putting new contributions to work",
        when="last 1 and first 3 business days of a month",
        why="contributions arrive on a payroll calendar, not a market one",
        events_per_year=48,
        syms=["EURUSD", "XAUUSD"], tf="1h",
        mask=lambda d: (d.index.day >= 30) | (d.index.day <= 3),
    ),
    "M-005 Monthly options expiry": dict(
        who="dealers hedging expiring gamma, and holders rolling positions",
        when="third Friday of the month",
        why="the option ceases to exist; the hedge must be unwound or rolled",
        events_per_year=12,
        syms=["XAUUSD", "EURUSD"], tf="1h",
        mask=lambda d: (d.index.dayofweek == 4) & (d.index.day >= 15) & (d.index.day <= 21),
    ),
    "M-006 Crypto funding settlement": dict(
        who="perp holders paying or receiving funding, and the basis traders around them",
        when="00:00, 08:00, 16:00 UTC every day",
        why="the payment happens at a fixed clock; positions are adjusted around it",
        events_per_year=1095,
        syms=["BTCUSDT", "ETHUSDT"], tf="1h",
        mask=lambda d: d.index.hour.isin([0, 8, 16]),
    ),
    "M-007 FX weekly open": dict(
        who="anyone carrying risk over a closed market, plus gap-fillers",
        when="Sunday 22:00 UTC, the first hours of the week",
        why="the market was shut; two days of news clear at once and cannot be traded earlier",
        events_per_year=52,
        syms=["EURUSD", "XAUUSD", "GBPUSD"], tf="1h",
        mask=lambda d: (d.index.dayofweek == 6) | ((d.index.dayofweek == 0) & (d.index.hour < 4)),
    ),
    "M-008 NY cash open": dict(
        who="US institutional order flow arriving in one burst at the equity open",
        when="13:30 UTC (14:30 EST winter)",
        why="US mandates and desks start at the cash open; flow is not spread evenly",
        events_per_year=250,
        syms=["XAUUSD", "EURUSD"], tf="1h",
        mask=lambda d: d.index.hour == 13,
    ),
}

HORIZONS = [1, 4, 24]          # 1h, 4h, 1 day, on a 1h bar


def main():
    print("=" * 100)
    print("MECHANISM BATCH 1 — gate 2 (does the event move forward returns?)")
    print("=" * 100)
    print("edge_bps is a GROSS forward return with no execution in it.")
    print("Compare it to hurdle_bps, the round-trip cost. pctile is the edge's")
    print("rank in its own shuffled-date null — under ~95 means indistinguishable.\n")

    out = []
    for name, m in MECHANISMS.items():
        print(f"\n{'-' * 100}\n{name}")
        print(f"  forced: {m['who']}")
        print(f"  when:   {m['when']}  (~{m['events_per_year']}/yr)")
        print(f"  why:    {m['why']}")
        for sym in m["syms"]:
            try:
                d = load_tf(sym, m["tf"])
            except Exception as e:
                print(f"    {sym}: no data ({e})"); continue
            ev = np.asarray(m["mask"](d))
            if ev.sum() < 30:
                print(f"    {sym}: only {ev.sum()} events, skipped"); continue
            r = probe(d, ev, HORIZONS, sym, name)
            out.append(r)
            for _, x in r.iterrows():
                flag = ""
                if np.isfinite(x.pctile) and (x.pctile >= 95 or x.pctile <= 5):
                    flag = "  <- beats its null"
                if x.beats_hurdle and flag:
                    flag = "  <- BEATS NULL AND HURDLE"
                print(f"    {sym:8s} h={x.h_bars:3d}  n={x.events:5d}  "
                      f"edge {x.edge_bps:+8.3f}  base {x.baseline_bps:+7.3f}  "
                      f"null {x.null_mean:+6.3f}  pct {x.pctile:5.1f}  "
                      f"hurdle {x.hurdle_bps:5.2f}{flag}")

    res = pd.concat(out, ignore_index=True)
    res.to_csv(ROOT / "backtests" / "mechanisms_batch1.csv", index=False)

    print("\n" + "=" * 100)
    print("PROMOTE LIST — beats its null AND clears the instrument's round trip")
    print("=" * 100)
    good = res[(res.pctile >= 95) & (res.beats_hurdle)]
    if good.empty:
        print("  NOTHING. Every mechanism in batch 1 is either indistinguishable")
        print("  from shuffled dates or too small to pay the spread.")
        print("  That is a result: eight ideas killed in minutes, none built.")
    else:
        print(good[["mechanism", "sym", "h_bars", "events", "edge_bps",
                    "hurdle_bps", "pctile"]].to_string(index=False))
    print(f"\nwrote backtests/mechanisms_batch1.csv  ({len(res)} rows)")
    return res


if __name__ == "__main__":
    main()
