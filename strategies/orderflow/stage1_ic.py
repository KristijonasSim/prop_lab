"""H-006 stage 1 — does the order-flow feed predict anything at all?

This is a DIAGNOSTIC, not a strategy, and it comes first on purpose. The
cleanest refutation this project has produced was H-008's z-response: a flat
table showing that the size of a residual said nothing about what followed,
which killed the idea before a single backtest was fitted to it. The same
question is asked here, of each feed feature, before any entry rule exists.

Three things have to be true before an order-flow strategy is worth building,
and each has killed a hypothesis here already:

  1. The feature has to rank forward returns.       (H-008 failed this)
  2. It has to beat its own null.                   (H-003 and H-005 failed this)
  3. The spread between its best and worst buckets  (H-007 failed this)
     has to be worth more than a round trip.

The third is the one that is easy to skip and it is the one that killed the
cross-sectional hypothesis: a real edge of about 10% on profit factor that a
14bps round trip ate whole. So every response below is printed in BASIS POINTS
and compared against 14bps at 1x cost and 28bps at 2x.

The null shuffles day-long blocks of the FEATURE against untouched returns, five
seeds, read as a distribution rather than a single number.

Run: .venv/bin/python strategies/orderflow/stage1_ic.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from strategies.orderflow import orderflow as of        # noqa: E402

FEEDS = ROOT / "data" / "feeds"
OUT = ROOT / "backtests" / "orderflow"
OUT.mkdir(parents=True, exist_ok=True)

SYMS = ("BTCUSDT", "ETHUSDT", "SOLUSDT")
HORIZONS = (12, 48, 96, 144, 288)          # 1h, 4h, 8h, 12h, 24h in 5m bars
HNAME = {12: "1h", 48: "4h", 96: "8h", 144: "12h", 288: "24h"}
NSEEDS = 5
NBUCKET = 5
COST_1X, COST_2X = of.ROUND_TRIP_BPS, 2 * of.ROUND_TRIP_BPS


def ic(f: pd.Series, r: pd.Series) -> float:
    """Spearman rank correlation on the overlapping, finite rows."""
    m = f.notna() & r.notna()
    if m.sum() < 500:
        return float("nan")
    return float(f[m].rank().corr(r[m].rank()))


def response(f: pd.Series, r: pd.Series, n: int = NBUCKET) -> tuple:
    """Mean forward return per feature bucket, in basis points.

    Buckets are cut on the feature's own quantiles over the whole sample, which
    is hindsight about the DISTRIBUTION but not about the returns - it says
    where the boundaries sit, not which side pays. A walk-forward would have to
    cut them on training data only; this stage is asking whether there is
    anything to walk forward at all."""
    m = f.notna() & r.notna()
    if m.sum() < 500:
        return [np.nan] * n, np.nan, np.nan
    try:
        b = pd.qcut(f[m], n, labels=False, duplicates="drop")
    except ValueError:
        return [np.nan] * n, np.nan, np.nan
    g = (r[m] * 1e4).groupby(b).mean()
    vals = [float(g.get(i, np.nan)) for i in range(n)]
    spread = vals[-1] - vals[0]
    # monotone in either direction: a real ranking signal should not zigzag
    d = np.diff([v for v in vals if v == v])
    mono = float(np.mean(d > 0)) if len(d) else np.nan
    mono = max(mono, 1 - mono)
    return vals, spread, mono


def main():
    syms = sys.argv[1:] or list(SYMS)
    rows, resp_rows = [], []
    for sym in syms:
        try:
            df = of.load(sym, FEEDS)
        except FileNotFoundError as e:
            print(f"{sym}: {e}")
            continue
        F = of.features(df)
        R = of.forward_returns(df, HORIZONS)
        print(f"\n{sym}: {len(df):,} bars  {df.index[0]:%Y-%m-%d} -> {df.index[-1]:%Y-%m-%d}"
              f"  ({len(F.columns)} features)")

        for name in F.columns:
            f = F[name]
            for h in HORIZONS:
                r = R[f"fwd_{h}"]
                real = ic(f, r)
                if real != real:
                    continue
                nulls = [ic(of.block_shuffle(f, seed=s * 7919 + h), r)
                         for s in range(NSEEDS)]
                nulls = [x for x in nulls if x == x]
                vals, spread, mono = response(f, r)
                # A full-sample number hides a signal that worked once and
                # stopped. Sign agreement across calendar years is the cheapest
                # stability check there is, and it costs nothing here.
                per_year = f.groupby(f.index.year).apply(
                    lambda g: ic(g, r.reindex(g.index)))
                per_year = per_year.dropna()
                same = (float((np.sign(per_year) == np.sign(real)).mean())
                        if len(per_year) else np.nan)
                rows.append({
                    "symbol": sym, "feature": name, "horizon": HNAME[h],
                    "ic": round(real, 5),
                    "null_med": round(float(np.median(nulls)), 5) if nulls else None,
                    "null_best": round(float(np.max(np.abs(nulls))), 5) if nulls else None,
                    "beats_null": bool(nulls) and abs(real) > np.max(np.abs(nulls)),
                    "spread_bps": round(spread, 2),
                    "monotone": round(mono, 2) if mono == mono else None,
                    "clears_1x": abs(spread) >= COST_1X,
                    "clears_2x": abs(spread) >= COST_2X,
                    "years": int(len(per_year)),
                    "same_sign_years": round(same, 2) if same == same else None,
                    "n": int((f.notna() & r.notna()).sum()),
                })
                resp_rows.append({"symbol": sym, "feature": name, "horizon": HNAME[h],
                                  **{f"q{i+1}_bps": round(v, 2) if v == v else None
                                     for i, v in enumerate(vals)}})

    if not rows:
        print("no data - run core/binance_metrics.py first")
        return
    res = pd.DataFrame(rows)
    tag = "" if len(syms) == len(SYMS) else "_" + "-".join(s[:3] for s in syms)
    res.to_csv(OUT / f"stage1_ic{tag}.csv", index=False)
    pd.DataFrame(resp_rows).to_csv(OUT / f"stage1_response{tag}.csv", index=False)

    print("\n" + "=" * 78)
    print("STRONGEST FEATURE x HORIZON, by |bucket spread| in basis points")
    print("=" * 78)
    top = res.reindex(res.spread_bps.abs().sort_values(ascending=False).index).head(20)
    print(top[["symbol", "feature", "horizon", "ic", "null_best", "beats_null",
               "spread_bps", "monotone", "same_sign_years", "clears_2x"]]
          .to_string(index=False))

    print("\n" + "=" * 78)
    print(f"THE THREE GATES  (spread must beat {COST_1X:.0f}bps at 1x, "
          f"{COST_2X:.0f}bps at 2x)")
    print("=" * 78)
    g1 = res.beats_null.mean()
    g2 = res.clears_1x.mean()
    g3 = (res.beats_null & res.clears_2x & (res.monotone >= 0.75)
          & (res.same_sign_years >= 0.75)).mean()
    print(f"  beats its own null           {res.beats_null.sum():4d} of {len(res)}  ({g1:6.1%})")
    print(f"  spread clears 1x cost        {res.clears_1x.sum():4d} of {len(res)}  ({g2:6.1%})")
    print(f"  clears 2x AND beats null AND monotone AND stable across years  "
          f"{int(g3*len(res)):4d} of {len(res)}  ({g3:6.1%})")

    keep = res[res.beats_null & res.clears_2x & (res.monotone >= 0.75)
               & (res.same_sign_years >= 0.75)]
    if len(keep):
        print("\nSURVIVORS — worth a walk-forward:")
        print(keep.sort_values("spread_bps", key=abs, ascending=False)
                 .to_string(index=False))
    else:
        print("\nNothing clears all three. On this evidence H-006 is not a strategy.")

    # per-feature summary: is any feed carrying signal across coins at all?
    print("\nBY FEATURE, averaged over symbols and horizons:")
    agg = (res.groupby("feature")
              .agg(mean_abs_ic=("ic", lambda s: float(np.mean(np.abs(s)))),
                   mean_abs_spread=("spread_bps", lambda s: float(np.mean(np.abs(s)))),
                   beats_null=("beats_null", "mean"))
              .sort_values("mean_abs_spread", ascending=False))
    print(agg.round(4).to_string())
    print(f"\nwrote stage1_ic{tag}.csv and stage1_response{tag}.csv in {OUT}")


if __name__ == "__main__":
    main()
