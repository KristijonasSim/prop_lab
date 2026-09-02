"""H-015 stage 1 — systemic crowding against the coin's own, head to head.

The claim is an ESTIMATOR claim: that the crowd's position across eleven coins
estimates "the crowd is offside" better than the position in one, which is what
H-009 currently reads. So the test is not "does `sys` predict returns" - it is
"does `sys` predict them BETTER than `own`, on the same coin, over the same bars,
with the same construction". `own` is built identically to H-006's `crowd_z` so
the difference is the aggregation and nothing else.

Series are thinned to hourly before any statistic is computed. 5-minute rows with
multi-hour forward windows overlap heavily; the first version of this analysis on
H-013 reported t-statistics inflated by roughly sqrt(288) for exactly that
reason, and thinning is the cheap half of the fix.

Run: .venv/bin/python strategies/breadth/stage1_headtohead.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from strategies.breadth import breadth as br                   # noqa: E402
from strategies.orderflow import orderflow as of               # noqa: E402
from strategies.orderflow.stage1_ic import ic, response        # noqa: E402

FEEDS = ROOT / "data" / "feeds"
OUT = ROOT / "backtests" / "breadth"
OUT.mkdir(parents=True, exist_ok=True)

HORIZONS = (12, 48, 96, 288)
HNAME = {12: "1h", 48: "4h", 96: "8h", 288: "24h"}
THIN = 12                      # one observation per hour
NSEEDS = 3
COST_2X = 2 * br.ROUND_TRIP_BPS


def main():
    print("building the cross-sectional panel ...", flush=True)
    pan = br.panel(FEEDS)
    sysdf = br.systemic(pan)
    rows = []
    for sym in br.COMPLEX:
        px = br.bars(sym, FEEDS)
        F = br.features(sym, FEEDS, pan, sysdf)
        R = br.forward_returns(px, HORIZONS)
        idx = F.index.intersection(R.index)[::THIN]
        F, R = F.loc[idx], R.loc[idx]
        print(f"  {sym}: {len(idx):,} hourly rows", flush=True)
        for name in F.columns:
            f = F[name]
            for h in HORIZONS:
                r = R[f"fwd_{h}"]
                real = ic(f, r)
                if real != real:
                    continue
                nulls = [x for x in
                         (ic(of.block_shuffle(f, seed=s * 7919 + h, block=24), r)
                          for s in range(NSEEDS)) if x == x]
                vals, spread, mono = response(f, r)
                py = f.groupby(f.index.year).apply(
                    lambda g: ic(g, r.reindex(g.index))).dropna()
                same = float((np.sign(py) == np.sign(real)).mean()) if len(py) else np.nan
                rows.append({"symbol": sym, "feature": name, "horizon": HNAME[h],
                             "ic": round(real, 5),
                             "null_best": round(float(np.max(np.abs(nulls))), 5) if nulls else None,
                             "beats_null": bool(nulls) and abs(real) > np.max(np.abs(nulls)),
                             "spread_bps": round(spread, 2),
                             "monotone": round(mono, 2) if mono == mono else None,
                             "clears_2x": abs(spread) >= COST_2X,
                             "same_sign_years": round(same, 2) if same == same else None,
                             "n": int((f.notna() & r.notna()).sum())})
    res = pd.DataFrame(rows)
    res.to_csv(OUT / "stage1_headtohead.csv", index=False)

    print("\n" + "=" * 88)
    print("THE ONE COMPARISON THAT DECIDES IT: own-coin crowding vs the complex")
    print("=" * 88)
    hh = res[res.feature.isin(["own", "sys", "idio", "breadth"])]
    piv = hh.pivot_table(index="horizon", columns="feature",
                         values="ic", aggfunc=lambda s: float(np.mean(np.abs(s))))
    print("\nmean |IC| across all 11 coins:")
    print(piv.reindex(["1h", "4h", "8h", "24h"]).round(4).to_string())
    piv2 = hh.pivot_table(index="horizon", columns="feature",
                          values="beats_null", aggfunc="mean")
    print("\nshare of cells beating their block-shuffle null:")
    print(piv2.reindex(["1h", "4h", "8h", "24h"]).round(3).to_string())
    piv3 = hh.pivot_table(index="horizon", columns="feature",
                          values="spread_bps", aggfunc=lambda s: float(np.mean(np.abs(s))))
    print("\nmean |quintile spread|, bps (cost is 14 at 1x, 28 at 2x):")
    print(piv3.reindex(["1h", "4h", "8h", "24h"]).round(2).to_string())

    print("\n" + "=" * 88)
    print("ALL FEATURES, averaged over 11 coins and 4 horizons")
    print("=" * 88)
    agg = (res.groupby("feature")
              .agg(mean_abs_ic=("ic", lambda s: float(np.mean(np.abs(s)))),
                   mean_abs_spread=("spread_bps", lambda s: float(np.mean(np.abs(s)))),
                   beats_null=("beats_null", "mean"),
                   clears_2x=("clears_2x", "mean"),
                   stable=("same_sign_years", "mean"))
              .sort_values("mean_abs_ic", ascending=False))
    print(agg.round(4).to_string())
    print(f"\nwrote stage1_headtohead.csv in {OUT}")


if __name__ == "__main__":
    main()
