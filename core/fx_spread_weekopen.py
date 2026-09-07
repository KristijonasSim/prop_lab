"""Measure the FX spread IN THE WEEKLY-OPEN WINDOW, which has never been sampled.

WHY. `mechanisms/run_batch1.py` promoted M-007 "FX weekly open" — a +0.76 to
+2.37bps gross drift in EURUSD and GBPUSD over 21:00-03:00 UTC Sunday into
Monday, at the 96-99th percentile of its own null and positive in all four years.

It was scored against a hurdle of 0.274bps for EURUSD. That number comes from
`core/fx_spread.py`, and that module does:

    days = days[days.dayofweek < 5]          # skip weekends

**So Sunday has never been sampled, and the hurdle M-007 was scored against
explicitly excludes the hours M-007 trades.** The weekly reopen is the single
thinnest liquidity window of the FX week — the hour when a spread is widest, by
a wide margin, in every practitioner account of this market.

A 2bps gross edge measured against an average-hour hurdle is not a 2bps edge.
This module settles it by measuring the same tick files in the actual window.

Run: .venv/bin/python core/fx_spread_weekopen.py
"""
from __future__ import annotations

import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.fx_spread import _hour, START, END, WORKERS       # noqa: E402

SYMS = ("EURUSD", "GBPUSD")
#: the hours M-007 actually trades, established by the probe's live-bar filter
OPEN_HOURS = {6: (21, 22, 23), 0: (0, 1, 2, 3)}   # Sunday, then Monday
#: mid-week London/NY hours, as the control the 0.274bps figure represents
CTRL_HOURS = {2: (9, 13, 17)}                     # Wednesday
N_WEEKS = 70


def jobs_for(sym: str, spec: dict, n: int):
    days = pd.date_range(START, END, freq="D", tz="UTC")
    out = []
    for dow, hours in spec.items():
        d = days[days.dayofweek == dow]
        d = d[np.linspace(0, len(d) - 1, min(n, len(d))).astype(int)]
        out += [x.to_pydatetime().replace(hour=h, tzinfo=timezone.utc)
                for x in d for h in hours]
    return out


def run(sym: str, spec: dict, label: str) -> pd.DataFrame:
    js = jobs_for(sym, spec, N_WEEKS)
    print(f"  {sym} {label}: {len(js)} hour-files ...", flush=True)
    frames = []
    with ThreadPoolExecutor(WORKERS) as ex:
        for got in ex.map(lambda t: _hour(sym, t), js):
            if got is not None:
                frames.append(got)
    if not frames:
        return pd.DataFrame()
    df = pd.concat(frames, ignore_index=True)
    df["sym"], df["window"] = sym, label
    return df


def main():
    print("Measuring the FX spread in the WEEKLY-OPEN window.\n"
          "core/fx_spread.py skips weekends, so these hours have never been "
          "sampled.\n")
    out = []
    for sym in SYMS:
        out.append(run(sym, OPEN_HOURS, "weekly open 21-03 UTC"))
        out.append(run(sym, CTRL_HOURS, "mid-week 09/13/17 UTC"))
    df = pd.concat([x for x in out if not x.empty], ignore_index=True)
    df.to_csv(ROOT / "backtests" / "fx_spread_weekopen.csv", index=False)

    print("\n" + "=" * 92)
    print("SPREAD BY WINDOW — bps of mid, ONE SIDE")
    print("=" * 92)
    g = (df.groupby(["sym", "window"])
           .agg(hours=("median_bps", "size"), ticks=("ticks", "sum"),
                median=("median_bps", "median"), mean=("mean_bps", "mean"),
                p90=("p90_bps", "median"))
           .round(3))
    print(g.to_string())

    print("\n" + "=" * 92)
    print("WHAT M-007 ACTUALLY HAS TO PAY")
    print("=" * 92)
    # M-007's measured gross edge, from mechanisms/run_batch1.py
    EDGE = {("EURUSD", 1): 0.762, ("EURUSD", 4): 1.926, ("GBPUSD", 4): 2.370}
    COMMISSION = 0.15          # cTrader round trip, same figure used for gold
    # REPORT BOTH, AND JUDGE ON THE MEAN. The spread distribution in this window
    # is skewed 2.3-2.7x: EURUSD's median is 0.362bps and its mean is 0.961,
    # because a handful of reopen minutes are far worse than typical. Expected
    # P&L is E[edge - cost] = mean edge - MEAN cost, so the median is the wrong
    # estimator here and it flatters every leg. Reporting only the median is how
    # this measurement would have produced a second false positive.
    print(f"  {'leg':14} {'gross':>7} | {'RT@median':>10} {'net':>8} | "
          f"{'RT@mean':>8} {'net':>8} | verdict")
    for (sym, h), edge in EDGE.items():
        try:
            med = float(g.loc[(sym, "weekly open 21-03 UTC"), "median"])
            mean = float(g.loc[(sym, "weekly open 21-03 UTC"), "mean"])
        except KeyError:
            continue
        rt_med = med * 2 + COMMISSION
        rt_mean = mean * 2 + COMMISSION
        verdict = ("SURVIVES" if edge > rt_mean else
                   "median-only" if edge > rt_med else "DEAD")
        print(f"  {sym} h={h}h{'':4} {edge:+7.3f} | {rt_med:10.3f} "
              f"{edge - rt_med:+8.3f} | {rt_mean:8.3f} {edge - rt_mean:+8.3f} "
              f"| {verdict}")

    print("\n  Skew in the open window (mean / median):")
    for sym in SYMS:
        try:
            med = float(g.loc[(sym, "weekly open 21-03 UTC"), "median"])
            mean = float(g.loc[(sym, "weekly open 21-03 UTC"), "mean"])
            print(f"    {sym}: median {med:.3f}  mean {mean:.3f}  = {mean/med:.1f}x")
        except KeyError:
            pass

    print("\nThe hurdle M-007 was originally scored against was 0.274bps for "
          "EURUSD,\nwhich is the MID-WEEK number and excludes every hour this "
          "mechanism trades.\nJudge on the RT@mean column.")
    return df


if __name__ == "__main__":
    main()
