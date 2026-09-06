"""H-024 stage 2 — what a clip ACTUALLY costs, measured instead of assumed.

Every number in this repo rests on one assumption: a 14bps round trip, from
5bps taker plus 2bps slippage a side. It has never been measured. It is the
single most load-bearing unmeasured quantity in the project — H-023 spent a whole
session on the fee half of it and the slippage half was still a guess.

`bookDepth` makes the impact half measurable, per coin, every five minutes, for
three and a half years.

WHAT THIS CAN AND CANNOT SAY. The archive gives CUMULATIVE resting notional at
+/-0.2, 1, 2, 3, 4 and 5 percent from the mid. That is enough to answer "how far
out does a clip of size S have to walk", and not enough to resolve anything
finer than the 0.2% band. So:

  * MEASURED here: market-impact cost, i.e. the average price concession paid
    walking the book for a clip of S dollars.
  * NOT measured here: the bid-ask spread itself. `bookTicker` would give it and
    the archive stopped publishing it in March 2024. The fee is a published
    number. So the repo's 14bps splits into a known fee, an unmeasured spread,
    and the impact this file measures.

THE MODEL, and why it is deliberately pessimistic at the first band. Inside a
band the archive says only the total resting there, not how it is distributed.
Two readings are computed and both reported:

  UNIFORM   liquidity spread evenly across the band. Filling a fraction f of
            the band's notional pays an average concession of f/2 of the band
            width. This is the honest central case.
  EDGE      all of the band's liquidity sits at its far edge, so any fill pays
            the full band width. This is the pessimistic bound.

A clip that walks past a band pays that band in full and continues into the
next. Anything that cannot be filled inside 5% is reported as unfillable rather
than extrapolated — beyond the archive there is nothing to stand on.

WHY IT MATTERS RIGHT NOW. The microstructure literature says identical order-book
features are worth Sharpe 0.25 on BTC and 5-9 on rank-20-to-100 coins, which
argues this whole project should move down the cap curve. The obvious objection
is that small coins cost more to trade. This measures exactly how much more, so
the argument can be settled with a number instead of an intuition.

Run: .venv/bin/python strategies/depth/stage2_cost.py
     .venv/bin/python strategies/depth/stage2_cost.py BTCUSDT LINKUSDT
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

FEEDS = ROOT / "data" / "feeds"
OUT = ROOT / "backtests" / "depth"
OUT.mkdir(parents=True, exist_ok=True)

COINS = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT", "ADAUSDT",
         "AVAXUSDT", "LINKUSDT", "DOTUSDT", "LTCUSDT", "BNBUSDT")
BANDS = (0.2, 1.0, 2.0, 3.0, 4.0, 5.0)          # percent from mid
#: clip sizes in USD. A 100k account risking 0.5% with a 1% stop trades ~50k
#: notional; the ladder brackets that by two orders of magnitude either way.
CLIPS = (1_000, 10_000, 50_000, 250_000, 1_000_000, 5_000_000)
MIN_SNAP = 5


def impact_bps(cum: np.ndarray, clip: float, mode: str) -> float:
    """One-way impact in bps for `clip` dollars walking a cumulative book.

    `cum` is cumulative notional at each band edge, same order as BANDS. Returns
    NaN when the clip cannot be filled inside the deepest band, because the
    archive says nothing about what is out there.
    """
    prev_cum, prev_edge, paid, filled = 0.0, 0.0, 0.0, 0.0
    for c, edge in zip(cum, BANDS):
        if not np.isfinite(c) or c <= prev_cum:
            # A missing band must NOT advance the inner edge. The archive only
            # began publishing the 0.2% level on 2026-01-15; before that the
            # finest band is 1%, and the honest reading is that the first
            # AVAILABLE band spans [0, its edge]. Advancing prev_edge to 0.2
            # here would floor every fill at 20bps and manufacture a cost that
            # is an artifact of a missing column.
            continue
        avail = c - prev_cum
        need = clip - filled
        take = min(avail, need)
        if mode == "uniform":
            # average concession across the slice actually consumed
            frac = take / avail
            lo, hi = prev_edge, edge
            px = lo + (hi - lo) * frac / 2.0
        else:                                    # "edge": pay the full band
            px = edge
        paid += take * px
        filled += take
        prev_cum, prev_edge = c, edge
        if filled >= clip - 1e-9:
            return paid / clip * 100.0           # percent -> bps
    return np.nan


def main():
    coins = sys.argv[1:] or list(COINS)
    rows = []
    for sym in coins:
        p = FEEDS / f"{sym}_depth_5m.parquet"
        if not p.exists():
            print(f"  {sym}: no depth feed, skipped")
            continue
        d = pd.read_parquet(p)
        d = d[d.n_snap >= MIN_SNAP]
        cols = [f"dep_{b:g}" for b in BANDS]
        if any(c not in d.columns for c in cols):
            print(f"  {sym}: missing depth columns, skipped")
            continue
        # dep_* is bid + ask within the band; one side is about half of it, and
        # a market order only eats one side.
        cum = d[cols].to_numpy(float) / 2.0
        # Sample rather than walk 380k bars x 6 clips x 2 modes: the quantity
        # wanted is a distribution, and 20k bars pins it to well under a bps.
        n = len(cum)
        step = max(1, n // 20000)
        cum = cum[::step]
        print(f"  {sym}: {n:,} bars, {len(cum):,} sampled  "
              f"{d.index[0]:%Y-%m}..{d.index[-1]:%Y-%m}", flush=True)

        # The 0.2% band exists only from 2026-01-15. Reported separately rather
        # than pooled: resolution changes the answer, and mixing the two eras
        # would let a finer recent book flatter three coarser years.
        fine = d["dep_0.2"].notna().to_numpy()[::step]

        for clip in CLIPS:
            for mode in ("uniform", "edge"):
                v = np.array([impact_bps(row, clip, mode) for row in cum])
                ok = np.isfinite(v)
                okf = ok & fine
                rows.append({
                    "sym": sym, "clip_usd": clip, "mode": mode,
                    "median_bps_fine": (float(np.median(v[okf])) if okf.any()
                                        else np.nan),
                    "n_fine": int(okf.sum()),
                    "fillable": float(ok.mean()),
                    "median_bps": float(np.median(v[ok])) if ok.any() else np.nan,
                    "p90_bps": float(np.percentile(v[ok], 90)) if ok.any() else np.nan,
                    "p99_bps": float(np.percentile(v[ok], 99)) if ok.any() else np.nan,
                    "round_trip_median": (float(np.median(v[ok])) * 2
                                          if ok.any() else np.nan),
                })

    if not rows:
        print("no depth feeds found")
        return
    out = pd.DataFrame(rows)
    out.to_csv(OUT / "stage2_cost.csv", index=False)

    u = out[out["mode"] == "uniform"]
    print(f"\n{'=' * 96}\nONE-WAY MARKET IMPACT, median bps, uniform-in-band "
          f"(the repo assumes 2bps slippage a side)\n{'=' * 96}")
    piv = u.pivot_table(index="sym", columns="clip_usd", values="median_bps")
    print(piv.round(3).to_string())

    print(f"\n-- pessimistic bound (all liquidity at the far edge of its band) --")
    e = out[out["mode"] == "edge"]
    print(e.pivot_table(index="sym", columns="clip_usd",
                        values="median_bps").round(3).to_string())

    print(f"\n-- share of bars where the clip is fillable inside 5% --")
    print(u.pivot_table(index="sym", columns="clip_usd",
                        values="fillable").round(4).to_string())

    print(f"\n-- ROUND TRIP impact at the p99 bar (the bad minute), uniform --")
    piv99 = u.pivot_table(index="sym", columns="clip_usd", values="p99_bps") * 2
    print(piv99.round(2).to_string())

    print(f"\n-- the same, restricted to bars that carry the 0.2% band "
          f"(2026-01-15 onward, where the book is resolved 5x finer) --")
    print(u.pivot_table(index="sym", columns="clip_usd",
                        values="median_bps_fine").round(3).to_string())

    print(f"\nwrote {OUT / 'stage2_cost.csv'}")
    print("\nRead this against the repo's standing assumption: 5bps taker fee +\n"
          "2bps slippage per side = 14bps round trip. The fee is published and\n"
          "real. This file measures only the impact component of the slippage;\n"
          "the bid-ask spread is NOT measured here because bookTicker stopped in\n"
          "2024-03.")


if __name__ == "__main__":
    main()
