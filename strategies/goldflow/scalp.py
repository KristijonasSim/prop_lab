"""H-046b — the actual footprint playbook on gold, at 1m and 3m.

WHY THIS EXISTS. `gate2.py` deciled one number - bar imbalance - against forward
returns and came back negative. Kris, correctly: *"what strategy are you testing
how you can say it dont work there is million of strategies to trade footprint
charts"*. He is right. Deciling a single feature is not testing footprint
trading; it is testing one weak version of one of its ingredients. This file
tests the setups footprint traders actually take, and names each one before it
is run.

THE FOUR SETUPS, fixed before any number is read:

  BURST       Kris's own: volume > k x its trailing average AND the bar is
              strongly one-sided. Trade WITH the delta. The read is that a
              sudden burst of one-sided size is somebody with size starting,
              not finishing.
  ABSORB      Large one-sided delta and the price does NOT move - a small range
              and a close near the open. Trade AGAINST the delta. The read is
              that a passive seller is soaking up every buy, and when the buying
              stops price falls to find them.
  EXHAUST     Price makes a new N-bar high while the delta behind it is WEAKER
              than at the previous high. Trade against. The read is a push
              running out of fuel.
  STACK       Three consecutive bars with the same-sign strong delta. Trade
              with it. The read is persistent one-way pressure.

Two of these say follow and two say fade, on purpose: if every arm wins the
setup is not doing the work, the market direction is.

COST. Gold's Dukascopy round trip is 1.83 bps, but the live demo measured Bybit
charging **5.50 bps round trip on XAUUSDT, exactly 3.0x**. At a one-minute hold
the spread is the whole game, so every arm is reported at BOTH: the optimistic
1.83 and the measured 5.50. An arm that only clears the optimistic one is not
tradeable at the only venue this project has actually touched.

NO SELECTION HERE. Fixed parameters, entry at the next bar's open, exit after a
fixed number of bars. Gross first, costs charged after - H-043's ordering.

Run: .venv/bin/python strategies/goldflow/scalp.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from core.gold_flow import load_flow                               # noqa: E402

RT_DUKAS = 1.83          # measured round trip, bps
RT_BYBIT = 5.50          # measured on the live demo, 3.0x
HOLDS = (1, 3, 5, 10, 20)
TFS = ("1min", "3min")

BURST_MULT = 3.0         # volume vs its trailing mean
IMB_STRONG = 0.30        # |imb| for "strongly one-sided"
ABSORB_RANGE_Q = 0.30    # bar range in the bottom 30% of recent ranges
EXHAUST_LOOK = 20        # bars for the "new high" test
VOL_WIN = 60             # trailing window for volume and range norms


def features(f: pd.DataFrame) -> pd.DataFrame:
    d = f.copy()
    d["rng"] = (d.high - d.low) / d.close * 1e4                    # bps
    d["vol_ma"] = d.vol.rolling(VOL_WIN, min_periods=20).mean().shift(1)
    d["rng_q"] = d.rng.rolling(VOL_WIN, min_periods=20).quantile(ABSORB_RANGE_Q).shift(1)
    d["burst"] = d.vol / d.vol_ma
    d["body"] = (d.close - d.open).abs() / d.close * 1e4
    d["hi20"] = d.high.rolling(EXHAUST_LOOK, min_periods=EXHAUST_LOOK).max().shift(1)
    d["lo20"] = d.low.rolling(EXHAUST_LOOK, min_periods=EXHAUST_LOOK).min().shift(1)
    d["dmax20"] = d.delta.rolling(EXHAUST_LOOK, min_periods=EXHAUST_LOOK).max().shift(1)
    d["dmin20"] = d.delta.rolling(EXHAUST_LOOK, min_periods=EXHAUST_LOOK).min().shift(1)
    return d


def signals(d: pd.DataFrame) -> dict[str, pd.Series]:
    """+1 long, -1 short, 0 flat. Every condition uses only the closed bar."""
    strong_up = d.imb > IMB_STRONG
    strong_dn = d.imb < -IMB_STRONG
    big_vol = d.burst > BURST_MULT
    quiet = d.rng < d.rng_q

    burst = pd.Series(0, index=d.index, dtype=float)
    burst[big_vol & strong_up] = 1
    burst[big_vol & strong_dn] = -1

    # absorption: the size is there, the price is not
    absorb = pd.Series(0, index=d.index, dtype=float)
    absorb[big_vol & strong_up & quiet] = -1          # fade the buying
    absorb[big_vol & strong_dn & quiet] = 1

    # exhaustion: new extreme on weaker flow than the last extreme
    exhaust = pd.Series(0, index=d.index, dtype=float)
    exhaust[(d.high > d.hi20) & (d.delta < d.dmax20)] = -1
    exhaust[(d.low < d.lo20) & (d.delta > d.dmin20)] = 1

    s_up = (d.imb > IMB_STRONG).astype(int)
    s_dn = (d.imb < -IMB_STRONG).astype(int)
    stack = pd.Series(0, index=d.index, dtype=float)
    stack[s_up.rolling(3).sum() == 3] = 1
    stack[s_dn.rolling(3).sum() == 3] = -1

    return {"BURST": burst, "ABSORB": absorb, "EXHAUST": exhaust, "STACK": stack}


def score(d: pd.DataFrame, sig: pd.Series, hold: int) -> dict | None:
    """Enter at the NEXT bar's open, exit `hold` bars later at the open."""
    entry = d.open.shift(-1)
    exit_ = d.open.shift(-(1 + hold))
    ret = (exit_ / entry - 1.0) * 1e4 * sig
    ret = ret[sig != 0].replace([np.inf, -np.inf], np.nan).dropna()
    if len(ret) < 100:
        return None
    g = float(ret.mean())
    return {"n": int(len(ret)), "gross": round(g, 2),
            "net_dukas": round(g - RT_DUKAS, 2),
            "net_bybit": round(g - RT_BYBIT, 2),
            "win": round(float((ret > 0).mean() * 100), 1),
            "median": round(float(ret.median()), 2)}


def main() -> int:
    print("H-046b — the footprint playbook on gold. Gross bps per trade, then")
    print(f"net of Dukascopy's {RT_DUKAS} and the live-measured Bybit {RT_BYBIT}.\n")
    for tf in TFS:
        f = load_flow("XAUUSD", tf)
        f = f[f.vol > 0]
        if len(f) < 5000:
            print(f"{tf}: only {len(f)} bars, skipped")
            continue
        d = features(f)
        sigs = signals(d)
        print(f"=== XAUUSD {tf}   {len(d):,} bars   "
              f"{d.index[0].date()} -> {d.index[-1].date()} " + "=" * 14)
        hdr = (f"{'setup':9}{'hold':>6}{'n':>8}{'gross':>8}"
               f"{'net@1.83':>10}{'net@5.50':>10}{'win%':>7}{'median':>8}")
        print(hdr); print("-" * len(hdr))
        for name, s in sigs.items():
            for h in HOLDS:
                r = score(d, s, h)
                if not r:
                    continue
                flag = ""
                if r["net_bybit"] > 0:
                    flag = "  <- clears REAL cost"
                elif r["net_dukas"] > 0:
                    flag = "  (only at the optimistic cost)"
                print(f"{name:9}{h:>6}{r['n']:>8}{r['gross']:>8.2f}"
                      f"{r['net_dukas']:>10.2f}{r['net_bybit']:>10.2f}"
                      f"{r['win']:>7.1f}{r['median']:>8.2f}{flag}", flush=True)
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
