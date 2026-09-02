"""H-013 stage 1 — does the perp-versus-cash gap rank forward returns at all?

Same diagnostic, same construction and the same three gates as H-006's
`strategies/orderflow/stage1_ic.py`, deliberately: the point of this hypothesis
is that it measures something H-006 could not see, and that claim is only
checkable if the two tables are directly comparable. So the IC, the bucket
response, the block-shuffle null and the cost thresholds are IMPORTED from that
stage rather than reimplemented.

The bar to clear is on record:

    H-006's best feature, crowd_z, averaged 19.6bps of bucket spread,
    beat its null in 53% of cells and cleared 2x cost in 20%.

Anything here that does not beat that is not worth taking further, because
H-006 already exists and already scored 1.3.

Run: .venv/bin/python strategies/basis/stage1_response.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from strategies.basis import basis as bs                      # noqa: E402
from strategies.orderflow import orderflow as of              # noqa: E402
from strategies.orderflow.stage1_ic import ic, response       # noqa: E402

FEEDS = ROOT / "data" / "feeds"
OUT = ROOT / "backtests" / "basis"
OUT.mkdir(parents=True, exist_ok=True)

SYMS = ("BTCUSDT", "ETHUSDT", "SOLUSDT")
HORIZONS = (12, 48, 96, 144, 288)
HNAME = {12: "1h", 48: "4h", 96: "8h", 144: "12h", 288: "24h"}
NSEEDS = 5
COST_1X, COST_2X = bs.ROUND_TRIP_BPS, 2 * bs.ROUND_TRIP_BPS


def main():
    syms = sys.argv[1:] or list(SYMS)
    rows, resp_rows = [], []
    for sym in syms:
        try:
            df = bs.load(sym, FEEDS)
        except FileNotFoundError as e:
            print(f"{sym}: {e} — run core/basis_data.py first")
            continue
        F = bs.features(df)
        R = bs.forward_returns(df, HORIZONS)
        print(f"\n{sym}: {len(df):,} bars  {df.index[0]:%Y-%m-%d} -> "
              f"{df.index[-1]:%Y-%m-%d}  ({len(F.columns)} features)", flush=True)

        for name in F.columns:
            f = F[name]
            for h in HORIZONS:
                r = R[f"fwd_{h}"]
                real = ic(f, r)
                if real != real:
                    continue
                nulls = [x for x in
                         (ic(of.block_shuffle(f, seed=s * 7919 + h), r)
                          for s in range(NSEEDS)) if x == x]
                vals, spread, mono = response(f, r)
                per_year = f.groupby(f.index.year).apply(
                    lambda g: ic(g, r.reindex(g.index))).dropna()
                same = (float((np.sign(per_year) == np.sign(real)).mean())
                        if len(per_year) else np.nan)
                rows.append({
                    "symbol": sym, "feature": name, "horizon": HNAME[h],
                    "ic": round(real, 5),
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
        print("no data")
        return
    res = pd.DataFrame(rows)
    # Tag the output when a symbol set is passed, so a wide-universe run cannot
    # silently overwrite the core three-coin result it is meant to be compared
    # against. It nearly did, once, before this line existed.
    tag = "" if list(syms) == list(SYMS) else "_" + "-".join(x[:3] for x in syms)
    res.to_csv(OUT / f"stage1_ic{tag}.csv", index=False)
    pd.DataFrame(resp_rows).to_csv(OUT / f"stage1_response{tag}.csv", index=False)

    print("\n" + "=" * 96)
    print("STRONGEST FEATURE x HORIZON, by |bucket spread| in basis points")
    print("=" * 96)
    top = res.reindex(res.spread_bps.abs().sort_values(ascending=False).index).head(20)
    print(top[["symbol", "feature", "horizon", "ic", "null_best", "beats_null",
               "spread_bps", "monotone", "same_sign_years", "clears_2x"]]
          .to_string(index=False))

    print("\n" + "=" * 96)
    print(f"THE THREE GATES  ({COST_1X:.0f}bps at 1x, {COST_2X:.0f}bps at 2x)")
    print("=" * 96)
    keep = res[res.beats_null & res.clears_2x & (res.monotone >= 0.75)
               & (res.same_sign_years >= 0.75)]
    print(f"  beats its own null        {res.beats_null.sum():4d} of {len(res)}"
          f"  ({res.beats_null.mean():6.1%})")
    print(f"  spread clears 1x cost     {res.clears_1x.sum():4d} of {len(res)}"
          f"  ({res.clears_1x.mean():6.1%})")
    print(f"  all four conditions       {len(keep):4d} of {len(res)}"
          f"  ({len(keep)/len(res):6.1%})")

    print("\nBY FEATURE, averaged over symbols and horizons "
          "(H-006's best was crowd_z at 19.6bps / 53% / 20%):")
    agg = (res.groupby("feature")
              .agg(mean_abs_ic=("ic", lambda s: float(np.mean(np.abs(s)))),
                   mean_abs_spread=("spread_bps", lambda s: float(np.mean(np.abs(s)))),
                   beats_null=("beats_null", "mean"),
                   clears_2x=("clears_2x", "mean"),
                   stable=("same_sign_years", "mean"))
              .sort_values("mean_abs_spread", ascending=False))
    print(agg.round(3).to_string())

    if len(keep):
        print("\nSURVIVORS — worth a grid:")
        print(keep.sort_values("spread_bps", key=abs, ascending=False)
                 .to_string(index=False))
    else:
        print("\nNothing clears all four. On this evidence H-013 is not a strategy.")
    print(f"\nwrote stage1_ic{tag}.csv and stage1_response{tag}.csv in {OUT}")


if __name__ == "__main__":
    main()
