"""TASK 3 stage 2 — verifying `size_z`, the one thing that cleared 14bps.

WHERE THIS CAME FROM. The stacking study (stage 1) was built to ask whether the
weak feeds add up. They do not — the median combination scored 3.1bps WORSE than
its own best ingredient. But the benchmark it had to beat turned out to be the
finding: on the held-out half, **`size_z` at 4h scored 14.6bps**, the first thing
measured in this project to clear a 14bps taker round trip.

`size_z` is the z-score of `sum_toptrader_long_short_ratio` — Binance's
long/short ratio for the largest accounts, weighted by POSITION SIZE. Money, not
headcount. It is the size-weighted sibling of the crowd ratio that became H-009.

WHY IT MIGHT BE NOTHING. Three reasons to distrust it, all handled here:

  1. **It was selected as the best of 22 features on the test half.** The maximum
     of 22 noisy estimates is biased upward. The fix is to measure it on the full
     sample, per year, against a proper null — the treatment H-025 got, which
     killed ETH's headline number.
  2. **H-006 already swept 20 feed features** including this one, over 8-24h
     horizons, and reported `dcrowd_4h` at 24h as the winner. Its stage-1 output
     was never written to disk, so the only way to know whether `size_z` at 4h is
     new is to measure both here, side by side. `dcrowd_4h` is included as the
     benchmark for exactly that reason.
  3. **H-006 did not die of signal, it died of DRAWDOWN** — 8-72h holds with no
     stop drew down 63.5R against H-002's 3.8R, and needed 548 days. That matters
     for what a 4h result would MEAN: a hold six to eighteen times shorter is a
     different risk object, so a signal that survives at 4h is worth more than
     the same number at 24h, not less.

WHAT IS MEASURED. Quintile response in bps, full sample and per calendar year,
across 1h to 24h, for eleven coins. Block-shuffled nulls at one day, one week and
one month, twenty seeds each — because the day-block null was already caught
being too easy once this session.

Run: .venv/bin/python strategies/stack/stage2_size.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from strategies.orderflow import orderflow as of                # noqa: E402
from strategies.depth.stage1_response import response, year_signs  # noqa: E402

FEEDS = ROOT / "data" / "feeds"
OUT = ROOT / "backtests" / "stack"
OUT.mkdir(parents=True, exist_ok=True)

COINS = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT", "ADAUSDT",
         "AVAXUSDT", "LINKUSDT", "DOTUSDT", "LTCUSDT", "BNBUSDT")
CELLS = ("size_z", "crowd_z", "disagree", "dcrowd_4h")
HORIZONS = (12, 24, 48, 96, 288)
HNAME = {12: "1h", 24: "2h", 48: "4h", 96: "8h", 288: "24h"}
BLOCKS = {"1d": 288, "1w": 288 * 7, "1mo": 288 * 30}
NSEEDS = 20
COSTS = {"taker1x": 14.0, "taker2x": 28.0, "mixed": 9.0, "maker2x": 8.0}


def main():
    coins = sys.argv[1:] or list(COINS)
    rows = []
    for sym in coins:
        try:
            df = of.load(sym, FEEDS)
        except FileNotFoundError:
            print(f"  {sym}: no feed, skipped")
            continue
        F = of.features(df)
        R = of.forward_returns(df, HORIZONS)
        print(f"\n{sym}: {len(df):,} bars  {df.index[0]:%Y-%m-%d} -> "
              f"{df.index[-1]:%Y-%m-%d}", flush=True)

        for name in CELLS:
            if name not in F.columns:
                continue
            f = F[name]
            for h in HORIZONS:
                r = R[f"fwd_{h}"]
                vals, spread, mono, n = response(f, r)
                if not n or spread != spread:
                    continue
                ok, tot = year_signs(f, r)
                row = {"sym": sym, "feature": name, "horizon": HNAME[h],
                       "n": n, "q1": vals[0], "q5": vals[-1], "spread": spread,
                       "abs_spread": abs(spread), "monotone": mono,
                       "years_same_sign": ok, "years": tot}
                for bname, blk in BLOCKS.items():
                    nulls = []
                    for s in range(NSEEDS):
                        _, ns, _, _ = response(
                            of.block_shuffle(f, seed=s * 7919 + h, block=blk), r)
                        if ns == ns:
                            nulls.append(abs(ns))
                    if nulls:
                        a = np.asarray(nulls)
                        row[f"null_{bname}"] = float(a.max())
                        row[f"beats_{bname}"] = bool(abs(spread) > a.max())
                row["beats_all_nulls"] = all(row.get(f"beats_{b}", False)
                                             for b in BLOCKS)
                row.update({f"clears_{k}": bool(abs(spread) > v)
                            for k, v in COSTS.items()})
                rows.append(row)

    if not rows:
        print("nothing measured")
        return
    out = pd.DataFrame(rows)
    out.to_csv(OUT / "stage2_size.csv", index=False)

    print(f"\n{'=' * 112}\nEVERY CELL THAT CLEARS 14bps AND BEATS ALL THREE "
          f"BLOCK NULLS\n{'=' * 112}")
    good = out[out.clears_taker1x & out.beats_all_nulls]
    if len(good):
        print(f"{'sym':9} {'feature':10} {'hz':4} {'q1':>8} {'q5':>8} "
              f"{'spread':>8} {'mono':>5} {'yrs':>6} {'n1d':>7} {'n1w':>7} {'n1mo':>7}")
        for _, r in good.sort_values("abs_spread", ascending=False).iterrows():
            print(f"{r['sym']:9} {r.feature:10} {r.horizon:4} {r.q1:8.1f} "
                  f"{r.q5:8.1f} {r.spread:8.1f} {r.monotone:5.2f} "
                  f"{r.years_same_sign:2d}/{r.years:<3d} "
                  f"{r.null_1d:7.1f} {r.null_1w:7.1f} {r.null_1mo:7.1f}")
    else:
        print("  none")

    print(f"\n-- `size_z` across every coin and horizon --")
    s = out[out.feature == "size_z"]
    print(s.pivot_table(index="sym", columns="horizon",
                        values="spread").round(1).to_string())
    print("\n  ... and whether it beats all three nulls:")
    print(s.pivot_table(index="sym", columns="horizon",
                        values="beats_all_nulls").to_string())

    print(f"\n-- how many cells clear each gate (of {len(out)}), "
          f"and how many of those beat ALL THREE nulls --")
    for k, v in COSTS.items():
        sub = out[out[f"clears_{k}"]]
        print(f"  {k:9} > {v:5.1f}bps : {len(sub):4d} cells, "
              f"{int(sub.beats_all_nulls.sum()):4d} survive")

    print(f"\n-- by feature: median |spread| and share surviving all nulls --")
    print(out.groupby("feature").agg(
        cells=("spread", "size"), med_abs=("abs_spread", "median"),
        max_abs=("abs_spread", "max"),
        survive=("beats_all_nulls", "mean")).round(3).to_string())

    print(f"\nwrote {OUT / 'stage2_size.csv'}")


if __name__ == "__main__":
    main()
