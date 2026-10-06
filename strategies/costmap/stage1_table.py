"""H-049 stage 1 — re-price the crypto cost table for the size actually traded.

WHAT THIS REPLACES. `core/markets.py` gives every crypto market a `half_spread`
in bps per side, and every one of them is flagged `spread ASSUMED`. BTCUSDT's
comment says it outright: *"the SPREAD is unmeasured - bookTicker stopped in
2024-03 - so half_spread is an assumption and is the weakest number in this
table."*

The archive really does stop (verified: the last free `bookTicker` day is
2024-03-30). It was never needed. **A spread is visible in the trades**, and
stage 0 measured BTCUSDT's at 0.01bps per side against the 2.0 assumed.

SO WHAT IS THE 2.0? It is not a spread, it is an unmeasured SLIPPAGE allowance,
and a slippage allowance is only meaningful attached to an ORDER SIZE. Stage 0
priced which one: with a median $69.7M resting within 0.2% of BTC's mid, 2.0bps
per side is the cost of a **$10,000,000** order. The live book's legs are $877.

THE TWO PIECES, MEASURED SEPARATELY BECAUSE THEY SCALE DIFFERENTLY.

  half_spread(S) = quoted_half_spread + impact(S)

  * QUOTED HALF-SPREAD - what the smallest possible order pays. Measured by the
    bid-ask bounce on adjacent aggTrades: every consecutive pair whose aggressor
    sign flips, buy price minus sell price, halved. Consecutive trades are
    milliseconds apart so there is no drift between them. **Do not measure this
    as vwap(buys) - vwap(sells) over a bar** - that is separated by the bar's
    own trend as much as by the spread, it reads negative on falling bars, and
    dropping those silently deletes 39% of the sample. Stage 0 did exactly that
    and the number had to be retracted.
    **Independent of size.**

  * IMPACT - what walking the book costs on top. From `data/feeds/*_depth_5m
    .parquet`, which holds the resting notional within 0.2% of mid. An order of
    size S consumes the fraction S/depth of that band and, on a book taken as
    uniform across it, fills at the midpoint of what it consumed:

        impact_bps = 20 * (S / depth) / 2

    **Linear in size.** Measured at the 10th percentile of depth, not the
    median, because a cost model should be wrong in the pessimistic direction.

THE SIZE THE TABLE IS SET FOR. `SIZE_USD` below is **$100,000 of notional per
leg**. The live book runs five legs at ~$877 each on $10,000 of equity - about
8.8% of equity per leg - so $100k a leg is roughly a **$1.1M account**, an order
of magnitude beyond anything this project will fund. That is deliberate: the
resulting number is an overstatement of the real cost at every account size
currently in scope, and the ladder printed at the end says where it stops being
one.

KILL CRITERION, WRITTEN BEFORE THE RUN. If the measured cost lands **within 30%
of the assumed on 3 of the 5 coins**, the table is close enough, the direction
closes and nothing gets edited.

SCOPE. Spread is sampled, not exhaustive: a stratified sample of days across the
available range, which is how `core/fx_spread.py` handles the same problem for
FX. Depth is the full 2023-01 -> 2026-09 series.

Run:  .venv/bin/python strategies/costmap/stage1_table.py
      .venv/bin/python strategies/costmap/stage1_table.py --days 8
"""
from __future__ import annotations

import argparse
import io
import os
import sys
import urllib.request
import zipfile

import numpy as np
import pandas as pd

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, REPO)

from core.markets import COSTS                                   # noqa: E402

TICKS = os.path.join(REPO, "data", "ticks")
FEEDS = os.path.join(REPO, "data", "feeds")
OUT = os.path.join(REPO, "backtests", "footprint")
BASE = ("https://data.binance.vision/data/futures/um/daily/aggTrades/"
        "{sym}/{sym}-aggTrades-{day}.zip")

COINS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "BNBUSDT"]

#: the six H-024 panel coins that core/markets.py has no entry for at all. They
#: are carried at the small-coin assumption the table uses for SOL/XRP/BNB, so
#: the "assumed" column below is what a cost gate on them would have charged.
EXTRA = ["ADAUSDT", "AVAXUSDT", "DOGEUSDT", "DOTUSDT", "LINKUSDT", "LTCUSDT"]
ASSUMED_DEFAULT = 3.0

#: notional per leg the table is set for - see the module docstring
SIZE_USD = 100_000.0

#: depth percentile the impact term is measured at. 10 = a thin book.
DEPTH_PCTILE = 10

#: the kill criterion, written before the run
TOLERANCE = 0.30


def sample_days(n: int) -> list[str]:
    """A stratified sample across the window the depth feed covers."""
    idx = pd.date_range("2024-06-01", "2026-08-25", freq="D")
    take = np.linspace(0, len(idx) - 1, n).round().astype(int)
    return [idx[i].strftime("%Y-%m-%d") for i in sorted(set(take))]


def _bounce_half_spread(d: pd.DataFrame) -> tuple[float, int]:
    """Median quoted HALF-spread in bps of mid, from the bid-ask bounce."""
    maker = d["maker"].astype(str).str.lower().eq("true").to_numpy()
    p = d["price"].to_numpy()
    side = np.where(~maker, 1, -1)                 # +1 aggressive buy
    flip = side[1:] != side[:-1]
    if flip.sum() < 1000:
        return float("nan"), 0
    gap = np.where(side[1:] == 1, p[1:] - p[:-1], p[:-1] - p[1:])[flip]
    mid = float(np.median(p))
    return float(np.median(gap) / mid * 1e4) / 2.0, int(flip.sum())


def day_spread(sym: str, day: str, keep: bool = False) -> tuple[float, int]:
    local = os.path.join(TICKS, f"{sym}-aggTrades-{day}.zip")
    blob = None
    if os.path.exists(local):
        blob = open(local, "rb").read()
    else:
        try:
            with urllib.request.urlopen(BASE.format(sym=sym, day=day),
                                        timeout=120) as r:
                blob = r.read()
        except Exception as e:
            print(f"    {sym} {day}: {type(e).__name__}", flush=True)
            return float("nan"), 0
        if keep:
            os.makedirs(TICKS, exist_ok=True)
            open(local, "wb").write(blob)
    try:
        with zipfile.ZipFile(io.BytesIO(blob)) as z:
            d = pd.read_csv(z.open(z.namelist()[0]), header=0, usecols=[1, 6],
                            names=["id", "price", "qty", "f", "l", "ts",
                                   "maker"])
    except Exception as e:
        print(f"    {sym} {day}: unreadable ({type(e).__name__})", flush=True)
        return float("nan"), 0
    finally:
        del blob
    return _bounce_half_spread(d)


def impact_bps(sym: str, size_usd: float) -> tuple[float, float]:
    """(impact in bps at SIZE_USD, the depth it was measured against)."""
    f = os.path.join(FEEDS, f"{sym}_depth_5m.parquet")
    if not os.path.exists(f):
        return float("nan"), float("nan")
    d = pd.read_parquet(f, columns=["dep_0.2"])["dep_0.2"].dropna()
    if d.empty:
        return float("nan"), float("nan")
    dep = float(d.quantile(DEPTH_PCTILE / 100))
    return 20.0 * (size_usd / dep) / 2.0, dep


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=12)
    ap.add_argument("--size", type=float, default=SIZE_USD)
    ap.add_argument("--keep", action="store_true",
                    help="cache downloaded aggTrades under data/ticks/")
    ap.add_argument("--all", action="store_true",
                    help="include the six coins core/markets.py has no entry for")
    args = ap.parse_args()

    coins = COINS + EXTRA if args.all else COINS

    days = sample_days(args.days)
    print(f"stratified sample: {len(days)} days, {days[0]} -> {days[-1]}\n")

    rows = []
    for sym in coins:
        vals, pairs = [], 0
        for day in days:
            hs, n = day_spread(sym, day, keep=args.keep)
            if hs == hs:
                vals.append(hs)
                pairs += n
        if not vals:
            print(f"{sym}: no usable days")
            continue
        quoted = float(np.median(vals))
        imp, dep = impact_bps(sym, args.size)
        c = COSTS.get(sym)
        assumed = c.half_spread if c else ASSUMED_DEFAULT
        maker_fee = c.maker_fee if c else 2.0
        taker_fee = c.taker_fee if c else 5.0
        measured = quoted + imp
        rows.append({
            "sym": sym, "days": len(vals), "flip_pairs": pairs,
            "quoted_half_spread": quoted, "impact_at_size": imp,
            "depth_p10_usd": dep, "measured_half_spread": measured,
            "assumed_half_spread": assumed,
            "in_table": c is not None,
            "ratio": assumed / measured if measured else np.nan,
            "rt_taker_assumed": 2 * (taker_fee + assumed),
            "rt_taker_measured": 2 * (taker_fee + measured),
            "rt_mixed_assumed": maker_fee + taker_fee + assumed,
            "rt_mixed_measured": maker_fee + taker_fee + measured,
        })
        print(f"{sym:9} {len(vals):2d} days  quoted {quoted:7.4f}  "
              f"impact {imp:6.3f}  = {measured:6.3f} bps/side   "
              f"assumed {assumed:.2f}"
              f"{'' if c else '  (no table entry)'}", flush=True)

    r = pd.DataFrame(rows)
    os.makedirs(OUT, exist_ok=True)
    r.to_csv(os.path.join(OUT, "stage1_cost_table.csv"), index=False)

    print(f"\n{'=' * 92}\nhalf-spread, bps per side, at ${args.size:,.0f} of "
          f"notional per leg (depth p{DEPTH_PCTILE})\n{'=' * 92}")
    print(f"{'sym':9} {'quoted':>8} {'impact':>8} {'MEASURED':>9} "
          f"{'assumed':>8} {'over by':>8}   {'taker RT':>14} {'mixed RT':>14}")
    for _, x in r.iterrows():
        print(f"{x.sym:9} {x.quoted_half_spread:8.4f} {x.impact_at_size:8.3f} "
              f"{x.measured_half_spread:9.3f} {x.assumed_half_spread:8.2f} "
              f"{x.ratio:7.1f}x   {x.rt_taker_assumed:6.2f} ->"
              f"{x.rt_taker_measured:6.2f}  {x.rt_mixed_assumed:6.2f} ->"
              f"{x.rt_mixed_measured:6.2f}")

    within = int((((r.assumed_half_spread - r.measured_half_spread).abs()
                   / r.assumed_half_spread) <= TOLERANCE).sum())
    print(f"\n-- the kill criterion, written before the run --")
    print(f"coins whose assumption is within {TOLERANCE:.0%} of measured: "
          f"{within} of {len(r)}")
    if within >= 3:
        print("**3 or more. The table is close enough. Do not edit it.**")
    else:
        print("**Fewer than 3. The table is wrong and stage 2 is warranted.**")

    print(f"\n-- the ladder: at what leg size does the ASSUMED number become "
          f"right? --")
    print(f"{'sym':9} " + " ".join(f"{'$'+s:>10}" for s in
                                   ("10k", "100k", "1M", "10M")) +
          "   break-even")
    for _, x in r.iterrows():
        cells = []
        for S in (1e4, 1e5, 1e6, 1e7):
            cells.append(f"{x.quoted_half_spread + 20*(S/x.depth_p10_usd)/2:10.3f}")
        be = (x.assumed_half_spread - x.quoted_half_spread) * 2 / 20 * x.depth_p10_usd
        print(f"{x.sym:9} " + " ".join(cells) + f"   ${be/1e6:8.1f}M")
    print("\nread: the assumed half-spread is correct at the break-even size "
          "in the right\ncolumn, and too big at every size below it.")
    print(f"\nwritten: {os.path.join(OUT, 'stage1_cost_table.csv')}")


if __name__ == "__main__":
    main()
