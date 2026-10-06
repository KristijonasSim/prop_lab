"""H-049 stage 0 — the round trip is not a constant, and this measures by how much.

THE OBSERVATION THIS IS BUILT ON. Five signals in this repo are measured REAL
and killed by cost, all of them by a factor between 1.2 and 4:

    H-022 absorption        6.55bps  against 8bps   (cheapest maker round trip)
    H-024 depth imbalance   7.9 bps  against 14bps  (taker, 0 of 935 cells)
    H-011 level fade        "real edge, too small for 28bps"
    H-047 participation     0.53     against 0.82   (standardised, 0 of 6 markets)
    H-021 quarter-hour      real, "5x too small to pay for"

Five deaths, one cause. And in every one of them the thing on the right-hand
side is a SINGLE CONSTANT: 14bps, 28bps, 8bps. It is entered once at the top of
the file and never varies by bar.

It varies in the market. `backtests/propfirms/fx_spread_measured.csv` already
measured it on ticks and nobody has used the number: gold's median spread runs
**1.01 to 4.49bps across UTC hours** and silver's runs **4.16 to 56.18**. A
signal worth 7.9bps is dead against 14 and alive against 6.

BEFORE ANY OF THAT IS WORTH A SESSION, THREE THINGS HAVE TO BE TRUE, and this
file measures all three on the repo's own tick data rather than assuming them:

  Q1 DISPERSION. How wide is the distribution of the real round trip? If the
     p10-to-p90 ratio is 1.3 there is nothing here. It needs to be wide enough
     that the cheap end clears a bar the average does not.

  Q2 PREDICTABILITY. Cost has to be knowable BEFORE the trade, from the closed
     bar. Measured as the rank correlation between this bar's cost and the next
     bar's, which is the only form a rule could actually use.

  Q3 THE KILLER, AND THE REASON THIS IS STAGE 0 AND NOT A STRATEGY. Is the EDGE
     correlated with the COST? Volatility widens spreads and volatility is where
     moves live. If the informative bars are the expensive ones, then selecting
     cheap bars throws the edge away with the cost, every one of the five deaths
     above is structural, and the whole direction closes on one number. **That
     is the outcome this file is expecting to find** - stated here, before the
     run, because the repo's standing lesson is that a removal has to be priced
     against what it removes.

THE COST ESTIMATOR, AND THE FIRST VERSION OF IT WAS WRONG. The obvious measure
is `vwap(aggressive buys) - vwap(aggressive sells)` over the bar. It does not
work: over fifteen minutes the two sides are separated by the bar's own DRIFT as
well as by the spread, so a rising bar reads far too wide and a falling bar reads
NEGATIVE. Dropping the negatives - which is what the first run did - throws away
39% of the bars, all of them falling ones, and inflates the median.

What is used instead is the BID-ASK BOUNCE, measured on adjacent trades:

    take every pair of consecutive trades whose aggressor sign FLIPS,
    espread = median(price of the buy - price of the sell) over those pairs

Consecutive aggTrades are milliseconds apart, so drift between them is
negligible and what is left is the round trip between the bid and the ask. It is
signed the right way by construction - a buy lifts the offer, a sell hits the
bid - and it needs no book data, which matters because Binance's free
`bookTicker` archive ends 2024-03-30. (Roll's serial-covariance estimator is the
classical alternative and is worse here: it goes imaginary whenever returns are
positively autocorrelated, which is most trending bars.)

SCOPE, AND IT IS NARROW. BTCUSDT USDT-M, 117 days, one regime. Q1 and Q2 are
properties of the tape and travel. Q3 is measured against the features the
footprint scout already built, so it inherits that scout's one-market limit.

Run:  .venv/bin/python strategies/costmap/stage0_dispersion.py
"""
from __future__ import annotations

import glob
import os
import sys
import zipfile

import numpy as np
import pandas as pd

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, REPO)
TICKS = os.path.join(REPO, "data", "ticks")
OUT = os.path.join(REPO, "backtests", "footprint")
BAR = "15min"


def cost_day(path: str) -> pd.DataFrame:
    with zipfile.ZipFile(path) as z:
        d = pd.read_csv(z.open(z.namelist()[0]), header=0, usecols=[1, 2, 5, 6],
                        names=["id", "price", "qty", "f", "l", "ts", "maker"])
    d["ts"] = pd.to_datetime(d["ts"], unit="ms", utc=True)
    maker = d["maker"].astype(str).str.lower().eq("true").to_numpy()
    p = d["price"].to_numpy()
    # +1 = the aggressor bought (lifted the offer), -1 = the aggressor sold
    side = np.where(~maker, 1, -1)

    # adjacent trades whose aggressor sign flips. `gap` is the buy price minus
    # the sell price of that pair, whichever order they arrived in, so it is a
    # spread and not a return.
    flip = side[1:] != side[:-1]
    gap = np.where(side[1:] == 1, p[1:] - p[:-1], p[:-1] - p[1:])
    ts = d["ts"].to_numpy()[1:]

    pair = pd.DataFrame({"gap": gap[flip], "px": p[1:][flip]},
                        index=pd.DatetimeIndex(ts[flip]))
    g = pair.resample(BAR)
    a = pd.DataFrame({"gap_med": g["gap"].median(), "npair": g["gap"].count()})

    whole = d.set_index("ts").resample(BAR)
    a["mid"] = whole["price"].mean()
    a["qty"] = whole["qty"].sum()
    a["nt"] = whole["price"].count()
    a["espread"] = a["gap_med"] / a["mid"] * 1e4
    return a[["espread", "mid", "qty", "nt", "npair"]]


def main() -> None:
    cache = os.path.join(OUT, "BTCUSDT_espread_15min.parquet")
    if os.path.exists(cache):
        c = pd.read_parquet(cache)
    else:
        files = sorted(glob.glob(os.path.join(TICKS, "BTCUSDT-aggTrades-*.zip")))
        rows = []
        for i, f in enumerate(files, 1):
            rows.append(cost_day(f))
            if i % 30 == 0 or i == len(files):
                print(f"  ... {i}/{len(files)} days", flush=True)
        c = pd.concat(rows).sort_index()
        os.makedirs(OUT, exist_ok=True)
        c.to_parquet(cache)

    raw = c["espread"].replace([np.inf, -np.inf], np.nan).dropna()
    e = raw[raw > 0]
    if len(e) < len(raw):
        print(f"  ({len(raw) - len(e)} of {len(raw)} bars had a non-positive "
              f"estimate and were dropped - {100*(1-len(e)/len(raw)):.1f}%)")
    print(f"\nBTCUSDT {BAR}, {len(e):,} bars, {c.index.min()} -> {c.index.max()}")

    print("\n== Q1  DISPERSION of the real round trip (bps of mid) ==")
    qs = [1, 5, 10, 25, 50, 75, 90, 95, 99]
    v = {q: e.quantile(q / 100) for q in qs}
    print("  " + "  ".join(f"p{q}={v[q]:.2f}" for q in qs))
    print(f"  p90/p10 = {v[90]/v[10]:.2f}x      p99/p1 = {v[99]/v[1]:.2f}x"
          f"      mean {e.mean():.2f}  median {v[50]:.2f}")
    print(f"  the repo scores every crypto hypothesis at a flat 14bps taker "
          f"round trip.\n  the measured aggressor round trip here is "
          f"{v[50]:.2f}bps at the median.")

    print("\n== Q2  PREDICTABILITY - is the cost knowable from the CLOSED bar? ==")
    nxt = e.shift(-1)
    ok = e.notna() & nxt.notna()
    print(f"  spearman(cost_t, cost_t+1) = {e[ok].corr(nxt[ok], method='spearman'):.3f}")
    for k in (2, 4, 16):
        n2 = e.shift(-k)
        o2 = e.notna() & n2.notna()
        print(f"  spearman(cost_t, cost_t+{k:<2d}) = "
              f"{e[o2].corr(n2[o2], method='spearman'):.3f}")
    # what a one-bar-ahead rule would actually capture
    t = pd.qcut(e.rank(method="first"), 4, labels=False)
    nq = pd.Series(nxt, index=e.index)
    print("  next bar's median cost, by THIS bar's cost quartile:")
    for g in range(4):
        m = t == g
        print(f"    q{g+1}: this {e[m].median():6.2f}  ->  next "
              f"{nq[m].median():6.2f}bps")

    print("\n== Q3  IS THE EDGE WHERE THE COST IS?  (the decisive one) ==")
    fp = os.path.join(OUT, f"BTCUSDT_footprint_{BAR}.parquet")
    if not os.path.exists(fp):
        print("  footprint bars missing - run strategies/footprint/stage1_location.py")
        return
    df = pd.read_parquet(fp)
    o = df["open"].shift(-1)
    join = pd.DataFrame({"cost": e}).join(df, how="inner")
    cq = pd.qcut(join["cost"].rank(method="first"), 4, labels=False)

    print(f"  {'horizon':>8} {'cheap q1':>10} {'q2':>8} {'q3':>8} "
          f"{'dear q4':>9}   {'|move| q4/q1':>13}")
    for h, lab in ((1, "15m"), (4, "1h"), (16, "4h")):
        fwd = (np.log(o.shift(-h) / o) * 1e4).reindex(join.index)
        vals = [fwd[cq == g].abs().median() for g in range(4)]
        print(f"  {lab:>8} " + " ".join(f"{x:8.1f}" for x in vals)
              + f"   {vals[3]/vals[0]:12.2f}x")
    print("\n  read: median |forward move| in bps, by the cost quartile of the "
          "bar the\n  decision was taken on. If the right column is far above "
          "the left, the\n  move and the cost rise together and selecting cheap "
          "bars buys nothing.")

    ratio = []
    for h in (1, 4, 16):
        fwd = (np.log(o.shift(-h) / o) * 1e4).reindex(join.index)
        a = fwd[cq == 0].abs().median()
        b = fwd[cq == 3].abs().median()
        ratio.append(b / a)
    print(f"\n  edge PER UNIT OF COST, cheap end against dear end:")
    cheap = join.loc[cq == 0, "cost"].median()
    dear = join.loc[cq == 3, "cost"].median()
    for (h, lab), r in zip(((1, "15m"), (4, "1h"), (16, "4h")), ratio):
        # the move grows by `r` from the cheap quartile to the dear one while
        # the cost grows by `dear/cheap`. Whichever grows FASTER decides which
        # end of the book is the better place to trade, per unit of cost paid.
        edge_per_cost = (dear / cheap) / r
        print(f"    {lab:>4}: move x{r:5.2f} against cost x{dear/cheap:5.2f} "
              f" ->  the cheap quartile is {edge_per_cost:5.2f}x better per unit "
              f"of cost")
    print("\n  BUT the ceiling is set by Q2, not by this: a rule can only sort "
          "bars by\n  NEXT-bar cost, and that spread is 1.7x, not 15x.")


if __name__ == "__main__":
    main()
