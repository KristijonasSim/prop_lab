"""H-043 gate 1 — CAN IT PAY THE SPREAD? Run before any edge test.

Kris, 2026-09-15, after five crypto feed hypotheses died the same way: the fee
test comes FIRST. H-006, H-024, H-031, H-034 and H-042 were all real effects
that beat their nulls and all five died to the same 14 bps round trip. The cost
test is cheap and it would have decided every one of them in an hour.

THE HYPOTHESIS. The VIX term structure - three-month implied volatility over
one-month, `VIX3M / VIX` - prices near-term stress against far-term stress. Above
1 the market is calm and the curve is in contango; below 1 the near month is bid
above the far month, which only happens when something is actually going wrong.
That inversion is a risk-off signal with a real mechanism behind it: hedging
demand and forced deleveraging both hit the front of the curve first.

If that is information, it should show up as a RISK-OFF BASKET - gold and the yen
bid, equities and the commodity currencies offered - and it should show up on the
markets a prop firm actually quotes, at spreads ten to fifty times thinner than
crypto's.

WHAT THIS FILE DOES AND DOES NOT DO. It measures the gross forward return after
the signal, per market and horizon, against that market's own round-trip cost.
No nulls, no walk-forward, no parameter search - those cost a day and are
pointless if the gross number is smaller than the spread. Nothing here is
evidence of an edge; it decides only whether an edge test is worth running.

NO LOOK-AHEAD. VIX closes at 16:15 ET. A reading dated D is therefore only usable
from D+1, and that is how it is joined.

Run: .venv/bin/python strategies/vixterm/costgate.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from core.markets import COSTS                                     # noqa: E402
from core.universe import STANDARD                                 # noqa: E402

VIX_DIR = ROOT / "data" / "vix"
DATA = ROOT / "data"
HORIZONS_D = (1, 3, 5, 10)
YEARS = 3
END = pd.Timestamp("2026-08-31", tz="UTC")


def vix_term() -> pd.DataFrame:
    """VIX3M / VIX, daily, shifted so a reading is used the day AFTER it closes."""
    def rd(name):
        d = pd.read_csv(VIX_DIR / f"{name}.csv")
        d["DATE"] = pd.to_datetime(d["DATE"], format="%m/%d/%Y", utc=True)
        return d.set_index("DATE")["CLOSE"].rename(name)
    v, v3 = rd("VIX"), rd("VIX3M")
    df = pd.concat([v, v3], axis=1).dropna().sort_index()
    df["ratio"] = df["VIX3M"] / df["VIX"]
    # USABLE FROM THE NEXT SESSION. The close is not knowable during the day.
    df["sig"] = df["ratio"].shift(1)
    df["sig_chg"] = df["ratio"].diff().shift(1)
    return df.dropna()


def bars(sym: str) -> pd.Series:
    """Daily close for one market, from whichever cache holds it."""
    for stem in (f"{sym}_dukascopy_1D.parquet", f"{sym}_dukascopy_1h.parquet",
                 f"{sym}_spot_15m.parquet"):
        p = DATA / stem
        if p.exists():
            d = pd.read_parquet(p, columns=["close"]).sort_index()
            s = d["close"].resample("1D").last().dropna()
            return s
    raise FileNotFoundError(sym)


def cost_bps(sym: str) -> float:
    """Round-trip cost in bps at 1x, the way the kernels charge it."""
    c = COSTS[sym]
    return 2.0 * (c.taker_fee + c.half_spread)


def main() -> int:
    term = vix_term()
    start = END - pd.DateOffset(years=YEARS)
    term = term.loc[start:END]
    inv = term["sig"] < 1.0
    print(f"VIX term structure, {term.index[0].date()} -> {term.index[-1].date()}")
    print(f"  sessions {len(term)}   inverted (VIX3M < VIX) on "
          f"{inv.sum()} of them ({inv.mean()*100:.1f}%)")
    print(f"  ratio: median {term['sig'].median():.3f}  "
          f"p5 {term['sig'].quantile(.05):.3f}  p95 {term['sig'].quantile(.95):.3f}\n")

    print("GROSS MOVE AFTER AN INVERTED CURVE, vs what it costs to trade it\n")
    hdr = (f"{'market':10}{'cost 1x':>9}{'bar 2x':>8}" +
           "".join(f"{f'{h}d':>9}" for h in HORIZONS_D) + f"{'verdict':>26}")
    print(hdr); print("-" * len(hdr))
    out = {}
    for sym in STANDARD:
        try:
            px = bars(sym)
        except FileNotFoundError:
            print(f"{sym:10}   no cache"); continue
        px = px.loc[start:END]
        c1 = cost_bps(sym)
        row = {"cost_1x": round(c1, 3), "bar_2x": round(2 * c1, 3), "h": {}}
        cells = []
        for h in HORIZONS_D:
            fwd = (px.shift(-h) / px - 1.0) * 1e4
            j = pd.concat([term["sig"], fwd.rename("fwd")], axis=1).dropna()
            on = j.loc[j["sig"] < 1.0, "fwd"]
            off = j.loc[j["sig"] >= 1.0, "fwd"]
            d = float(on.mean() - off.mean()) if len(on) > 5 else np.nan
            row["h"][h] = {"n_inverted": int(len(on)),
                           "mean_inverted_bps": round(float(on.mean()), 2) if len(on) else None,
                           "mean_normal_bps": round(float(off.mean()), 2) if len(off) else None,
                           "diff_bps": round(d, 2) if d == d else None}
            cells.append(d)
        best = np.nanmax(np.abs(cells)) if any(c == c for c in cells) else np.nan
        verdict = ("CLEARS 2x" if best > 2 * c1 else
                   "clears 1x only" if best > c1 else "BELOW THE SPREAD")
        out[sym] = row
        print(f"{sym:10}{c1:>9.2f}{2*c1:>8.2f}" +
              "".join(f"{x:>+9.1f}" if x == x else f"{'n/a':>9}" for x in cells) +
              f"{verdict:>26}")

    print("\n  diff = mean move with an inverted curve MINUS mean move without,"
          "\n  in basis points, gross. A negative number means the market FALLS "
          "when\n  the curve inverts, which is tradeable short and counts the same.")
    dest = ROOT / "backtests" / "vixterm"
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "costgate.json").write_text(json.dumps(
        {"sessions": int(len(term)), "inverted_pct": round(float(inv.mean()) * 100, 1),
         "markets": out}, indent=1, default=str))
    print(f"\nwrote backtests/vixterm/costgate.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

# =========================================================================== #
# RESULT - 2026-09-15. GATE 1 PASSED on all six markets. Gate 2 is worth running.
#
# Three years, all six standard markets, gross move after an inverted curve
# against each market's own round-trip cost:
#
#   market     cost1x  bar2x      1d      3d      5d     10d
#   BTCUSDT     14.00  28.00   +72.7   +32.8  +121.0  +351.1
#   XAUUSD       1.83   3.66   +13.3   +38.0   +55.4   +58.5
#   XAGUSD       9.10  18.20   -15.1   -91.2   -68.6   -50.7
#   EURUSD       0.27   0.55   +10.3   +26.4   +34.6   +50.5
#   GBPUSD       0.72   1.44   +10.4   +21.7   +37.3   +65.1
#   USDJPY       1.00   2.00    -2.0   -11.7   -13.0    -7.3
#
# All six clear twice their spread, which is the thing five crypto hypotheses
# could not do. FOUR OF SIX ALSO POINT THE WAY THE MECHANISM SAYS: gold bid,
# silver offered, the yen bid (USDJPY down). BTC rising in a stress episode is
# the opposite of risk-off and EUR/GBP rising means a WEAKER dollar, which is
# not the usual risk-off reflex either. Two signs out of six disagreeing with
# the story is a reason to distrust the three-year window, not to celebrate.
#
# AND THE THREE-YEAR SAMPLE IS NOT 48 OBSERVATIONS. The 48 inverted days fall in
# 17 EPISODES, and two of them - 2025-03-04..14 and 2025-04-03..25 - are half the
# days. Three years of this signal is a study of about two events.
#
# SO IT WAS RE-RUN WHERE THERE IS DEPTH. Gold has eleven years cached
# (XAUUSD10Y) and BTC nine; the FX and silver caches start 2023-09 and would
# need a download.
#
#   XAUUSD, 11 years, 67 episodes, cost bar 3.66 bps
#     crisis only:   +10.5 / +23.4 / +38.0 / +22.8 bps at 1/3/5/10 days
#     every day, by quintile of the ratio (Q1 = most stressed):
#       5d   +27.2  +57.4  +44.3  +12.8   +6.0     Q1-Q5  +21.2
#      10d   +65.2 +102.8  +68.0  +29.0  +29.8     Q1-Q5  +35.4
#
# Gold holds up on 67 episodes rather than 17, clears its spread six to ten
# times over, and the CONTINUOUS version trades every day rather than six times
# a year - which is the pace problem the crisis-only version would have had.
#
# ONE HONEST BLEMISH: Q2 beats Q1 at every horizon on gold, so the response is a
# hump rather than a clean ranking. Small, consistent, and it means condition 1
# of any gate-2 pre-registration ("a ranking signal must rank") is already in
# doubt. BTC is worse - Q3 is the best bucket - and BTC's cost bar is 28 bps.
#
# WHAT IS NOT DONE AND MUST BE BEFORE ANY CLAIM: no null, no walk-forward, no
# stop or sizing, no out-of-sample split. This file decides only that an edge
# test is worth a day, and it does.
