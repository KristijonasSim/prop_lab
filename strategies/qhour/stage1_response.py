"""H-021 stage 1 - the quarter-hour effect. Does the CLOCK carry information?

MECHANISM, before any result. Kim and Hansen (arXiv 2607.09426, 2026) show that
Binance perpetual markets burst in volume and volatility on round clock marks -
one minute, five minutes, and most strongly the quarter hour - and that trade
size roundness collapses inside those bursts, which is the signature of
algorithms rather than people. Scheduled bots wake on the clock. Their claim
that matters here is not the burst but what follows it: the ORDER IMBALANCE
measured in the quarter-hour opening interval predicts returns four to twelve
hours out, and the same imbalance measured at finer marks does not. Who is on
the other side: whoever the scheduled programs are trading against, repricing
over the rest of the session.

Why the horizon is the whole point for this project. Stage 2 of H-017 killed
every flow feature below the 8-24h horizon on cost - 0 of 130 cells cleared a
14bps round trip, best spread 5.99bps. A signal at 4-12h sits exactly at that
boundary, which is the only band where a crypto flow signal has ever been
affordable here. And the clock has never been looked at in this project: "time
of day" and "hour of day" appear nowhere in STRATEGY_LOG.md.

The honest caveat that has to travel with this: the paper's own TRADING test was
at a ten-second horizon and earned about 0.5bps gross, a twentieth of a round
trip. They never converted the 4-12h claim into a net-of-fee number. That is
what this stage does.

THE TEST. This is the H-008 killer test, the same shape H-016 stage 1 used.
No strategy, no fitting, no parameters: bucket forward returns by the sign and
size of opening order imbalance, split by CLOCK PHASE, and print the long-short
spread in basis points against the 14bps round trip. If the quarter-hour phase
is not visibly different from the phases around it, the hypothesis is dead here
and no amount of strategy construction will revive it.

Phases, all on the 5-minute archive:

  qhour    bars opening at :00, :15, :30, :45   - the paper's claim
  hour     bars opening at :00 only             - is it really the quarter, or
                                                  just the hour?
  other    the eight 5m bars that are neither   - the control. If these score
                                                  the same, the clock is noise.

Imbalance is (taker buy - taker sell) / volume on the bar itself, z-scored on a
trailing shifted window so a bar is never scored against itself. Returns run
from the NEXT bar's open, so a signal read off a closed bar is fillable.

Null: the paired block shuffle, which moves the feature in day-long blocks and
leaves returns untouched, so the phase structure of returns survives and only
the alignment of the feature to it is destroyed.

Output: backtests/qhour/stage1_response.csv
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from strategies.orderflow import orderflow as of                    # noqa: E402

FEEDS = ROOT / "data" / "feeds"
OUT = ROOT / "backtests" / "qhour"
OUT.mkdir(parents=True, exist_ok=True)

ROUND_TRIP_BPS = of.ROUND_TRIP_BPS          # 14.0
ZWIN = 288                                  # one day of 5m bars
HORIZONS = (48, 96, 144)                    # 4h, 8h, 12h - the paper's band
COINS = ("BTCUSDT", "ETHUSDT", "XRPUSDT", "SOLUSDT", "DOGEUSDT", "ADAUSDT")
PHASES = {"qhour": (0, 15, 30, 45), "hour": (0,)}


def imbalance(df: pd.DataFrame) -> pd.Series:
    buy = df.taker_buy_base
    sell = (df.volume - buy).clip(lower=0.0)
    x = (buy - sell) / df.volume.replace(0.0, np.nan)
    m = x.rolling(ZWIN, min_periods=ZWIN // 2).mean().shift(1)
    s = x.rolling(ZWIN, min_periods=ZWIN // 2).std(ddof=0).shift(1)
    return (x - m) / s.replace(0.0, np.nan)


def spread_bps(z: np.ndarray, fwd: np.ndarray, q: float = 0.2) -> tuple:
    """Long-short spread between the top and bottom `q` of imbalance, in bps.

    Also returns the count, because a spread computed on forty observations is
    a number and not a result.
    """
    ok = np.isfinite(z) & np.isfinite(fwd)
    z, fwd = z[ok], fwd[ok]
    if len(z) < 500:
        return np.nan, np.nan, np.nan, len(z)
    lo, hi = np.quantile(z, q), np.quantile(z, 1 - q)
    top, bot = fwd[z >= hi], fwd[z <= lo]
    if len(top) < 100 or len(bot) < 100:
        return np.nan, np.nan, np.nan, len(z)
    t, b = top.mean() * 1e4, bot.mean() * 1e4
    return t - b, t, b, len(z)


def main() -> int:
    rows = []
    print(f"round trip to beat: {ROUND_TRIP_BPS:.1f} bps "
          f"(1x); 2x cost is {2*ROUND_TRIP_BPS:.1f}\n")

    for sym in COINS:
        p = FEEDS / f"{sym}_perp_5m.parquet"
        if not p.exists():
            print(f"  {sym}: no perp feed, skipped")
            continue
        df = pd.read_parquet(p)
        df = df[~df.index.duplicated(keep="last")].sort_index()
        z = imbalance(df)
        fwd = of.forward_returns(df, horizons=HORIZONS)
        minute = df.index.minute
        masks = {"qhour": np.isin(minute, PHASES["qhour"]),
                 "hour": np.isin(minute, PHASES["hour"])}
        masks["other"] = ~masks["qhour"]

        # the null: same feature, day-blocks reordered, returns untouched
        zn = {s: of.block_shuffle(z, seed=s, block=288).values
              for s in range(3)}

        print(f"{sym}  {df.index.min():%Y-%m} -> {df.index.max():%Y-%m}  "
              f"{len(df):,} bars")
        for h in HORIZONS:
            f = fwd[f"fwd_{h}"].values
            line = f"   {h*5//60:>2d}h  "
            for phase in ("qhour", "hour", "other"):
                m = masks[phase]
                sp, t, b, n = spread_bps(z.values[m], f[m])
                nulls = [spread_bps(zn[s][m], f[m])[0] for s in range(3)]
                nl = float(np.nanmean(nulls)) if np.isfinite(nulls).any() else np.nan
                line += (f"{phase} {sp:>7.2f} (null {nl:>6.2f}, n={n//1000}k)  ")
                rows.append({"symbol": sym, "horizon_h": h * 5 // 60,
                             "phase": phase, "spread_bps": round(float(sp), 2),
                             "top_bps": round(float(t), 2),
                             "bottom_bps": round(float(b), 2),
                             "null_bps": round(nl, 2) if np.isfinite(nl) else None,
                             "n": int(n)})
            print(line)
        print()

    d = pd.DataFrame(rows)
    d.to_csv(OUT / "stage1_response.csv", index=False)

    print("=" * 78)
    print("MEDIAN LONG-SHORT SPREAD IN BPS, ACROSS COINS "
          f"(round trip {ROUND_TRIP_BPS:.0f} bps)")
    piv = d.pivot_table(index="horizon_h", columns="phase",
                        values="spread_bps", aggfunc="median")
    nul = d.pivot_table(index="horizon_h", columns="phase",
                        values="null_bps", aggfunc="median")
    print("\n  real:"); print(piv.round(2).to_string())
    print("\n  null:"); print(nul.round(2).to_string())
    print("\n  real minus null:")
    print((piv - nul).round(2).to_string())

    q = piv.get("qhour"); o = piv.get("other")
    if q is not None and o is not None:
        gap = (q - o).median()
        print(f"\n  quarter-hour advantage over the control phase: "
              f"{gap:+.2f} bps (median across horizons)")
        best = piv.max().max()
        print(f"  best cell anywhere: {best:.2f} bps against a "
              f"{ROUND_TRIP_BPS:.0f} bps round trip -> "
              f"{'TRADEABLE' if best > ROUND_TRIP_BPS else 'DEAD ON COST'}")
    print(f"\nwrote {OUT / 'stage1_response.csv'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
