"""H-016 stage 1 - the response test, run before anything is built.

The rule this repo learned from H-008: bucket forward return by the signal at
ZERO cost first. If a strong reading does not beat a weak one, there is no
mechanism and no exit, stop or filter can create one. It would have killed
H-008 in ten minutes.

The ribbon's claim is agreement across timescales, so the bucketing variable is
`agree` - the mean sign of the twenty trend scores, +1 when every length is up.
The question is monotonicity, not profitability:

    does agree = +1.0 lead to a better forward return than agree = +0.4?

Reported at zero cost, deliberately. A flat response kills the idea; a real one
still has to survive 14bps a round trip, which is stage 2's problem.

Also reported, because it is the honest counterweight: the CONTINUATION vs
REVERSAL split. A trend-following reading of the ribbon says the response
slopes UP with agreement. Everything this project has found so far says the
crowd is fadeable. Both readings are in the same table and the sign decides.

Output: backtests/ribbon/stage1_response.csv
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from strategies.ribbon.ribbon import RibbonParams, features   # noqa: E402

OUT = ROOT / "backtests" / "ribbon"
SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "BNBUSDT"]
TFS = {"15m": 1, "1h": 4, "4h": 16}
#: Forward horizons in BARS of the timeframe being tested.
HORIZONS = [1, 4, 16]
AGG = {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}

#: `agree` is (n_up - n_dn)/20, so it lands on multiples of 0.1. These edges cut
#: it into readable bands rather than quantiles, because the question is about
#: the VALUE of agreement, not about its rank inside this sample.
EDGES = [-1.001, -0.8, -0.4, -0.1, 0.1, 0.4, 0.8, 1.001]
LABELS = ["<=-0.8", "-0.8..-0.4", "-0.4..-0.1", "flat", "0.1..0.4",
          "0.4..0.8", ">=0.8"]


def bars(sym: str, tf: str) -> pd.DataFrame:
    df = pd.read_parquet(ROOT / "data" / f"{sym}_spot_15m.parquet")
    if tf == "15m":
        return df
    return df.resample({"1h": "1h", "4h": "4h"}[tf]).agg(AGG).dropna()


def rows_for(sym: str, tf: str, p: RibbonParams) -> list[dict]:
    df = bars(sym, tf)
    f = features(df, p)
    c = df["close"].to_numpy(float)

    # Signal read on the CLOSE of bar t, so the earliest tradeable entry is the
    # open of t+1. Forward return is measured from that open, never from the
    # close that produced the signal.
    op = df["open"].to_numpy(float)
    agree = f["agree"].shift(1).to_numpy(float)     # what was known at the open
    band = pd.cut(pd.Series(agree, index=df.index), bins=EDGES, labels=LABELS)

    out = []
    for h in HORIZONS:
        fwd = np.full(c.size, np.nan)
        # entry at this bar's open, exit at the close h bars later
        fwd[:c.size - h + 1] = c[h - 1:] / op[:c.size - h + 1] - 1.0
        d = pd.DataFrame({"band": band, "agree": agree, "fwd": fwd * 1e4})
        d = d.dropna()
        # Crypto drifts up over this window, so a raw band mean measures the
        # drift plus the signal. Everything is also reported as an EXCESS over
        # the unconditional mean of the same bars, which is what a long-only
        # trend read has to beat: buy-and-hold is free.
        base = float(d["fwd"].mean())
        for lab in LABELS:
            g = d[d["band"] == lab]
            if len(g) < 200:
                continue
            out.append({
                "symbol": sym, "tf": tf, "horizon_bars": h, "band": lab,
                "n": len(g),
                "mean_bps": round(float(g["fwd"].mean()), 3),
                "excess_bps": round(float(g["fwd"].mean()) - base, 3),
                "base_bps": round(base, 3),
                "median_bps": round(float(g["fwd"].median()), 3),
                # A directional read: what you would earn going LONG on this
                # band. The fade reading is the same number with the sign
                # flipped, so both are in one column.
                "hit_up": round(float((g["fwd"] > 0).mean()), 4),
                "share": round(len(g) / len(d), 4),
            })
    return out


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    p = RibbonParams()
    rows: list[dict] = []
    for sym in SYMBOLS:
        for tf in TFS:
            rows += rows_for(sym, tf, p)
            print(f"  done {sym} {tf}")
    df = pd.DataFrame(rows)
    df.to_csv(OUT / "stage1_response.csv", index=False)

    print(f"\nwrote {OUT / 'stage1_response.csv'}  ({len(df)} rows)\n")
    print("Mean forward return in bps by ribbon agreement, ZERO cost.")
    print("Trend-following reading needs this to slope UP left to right.\n")
    for val, title in (("mean_bps", "raw"), ("excess_bps", "EXCESS over hold")):
        print(f"########## {title} ##########")
        for h in HORIZONS:
            piv = (df[df["horizon_bars"] == h]
                   .pivot_table(index="tf", columns="band", values=val,
                                aggfunc="mean")
                   .reindex(columns=[c for c in LABELS if c in df["band"].unique()])
                   .reindex(index=list(TFS)))
            print(f"--- forward {h} bar(s), averaged over {len(SYMBOLS)} coins ---")
            print(piv.round(2).to_string(), "\n")

    # The one number that decides whether stage 2 happens.
    ext_up = df[df["band"] == ">=0.8"]["excess_bps"]
    ext_dn = df[df["band"] == "<=-0.8"]["excess_bps"]
    mild_up = df[df["band"] == "0.1..0.4"]["excess_bps"]
    mild_dn = df[df["band"] == "-0.4..-0.1"]["excess_bps"]
    print("All figures below are EXCESS over buy-and-hold on the same bars.")
    print(f"strong up {ext_up.mean():+.2f} bps vs mild up {mild_up.mean():+.2f} bps")
    print(f"strong dn {ext_dn.mean():+.2f} bps vs mild dn {mild_dn.mean():+.2f} bps")
    print(f"long-short spread, strong bands: "
          f"{ext_up.mean() - ext_dn.mean():+.2f} bps")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
