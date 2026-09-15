"""H-045 - GVZ/VIX: gold's fear priced against equity fear. Gold's first feed.

Competition entry, 2026-09-15, one hour.

CLAUDE.md says gold "trades naked" - every feed in data/feeds/ is a Binance
crypto symbol and the Dukascopy cache holds bid candles, not ticks. THAT IS
TRUE OF ORDER FLOW AND FALSE IN GENERAL. CBOE publishes GVZ, the gold
volatility index, free and daily back to 2009, on the same endpoint as VIX. It
has never been touched in this repo.

THE SIGNAL. GVZ / VIX - what the options market charges for gold risk divided by
what it charges for equity risk. Low means gold's fear is cheap relative to the
equity market's.

THE MECHANISM, stated before any number. Equity stress is priced immediately -
the S&P options market is the deepest in the world. Gold's is priced more slowly,
because gold's bid in a crisis arrives after the equity move, not with it. So a
low ratio is a market that has already decided things are bad but has not yet
paid up for gold. The trade is gold catching up. Whoever is on the other side is
selling gold vol cheap relative to equity vol, and is right most of the time and
badly wrong occasionally - which is the shape of every risk premium.

NOT H-043. That used the VIX TERM STRUCTURE (VIX3M/VIX) and died on its null.
This is a CROSS-ASSET ratio of two different underlyings' implied vol, and its
mechanism is relative mispricing rather than panic-bounce.

NOT H-037. That was the variance risk premium (implied minus realised) on crypto.
`s_vrp` here is that quantity on gold and it was measured in the same gate: it is
the WEAKEST of the four candidates and is not carried forward.

EVERY CBOE SERIES IS SHIFTED ONE SESSION. A close is not knowable during the day.

Run: .venv/bin/python strategies/goldvol/gvzvix.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from core.markets import COSTS                                      # noqa: E402
from core.noiseband import band as nb_band                          # noqa: E402
from core.prop_rules import HOUSE, best_day_share                   # noqa: E402
from core.riskladder import run_accounts                            # noqa: E402

END = pd.Timestamp("2026-08-31", tz="UTC")
YEARS = 5
SPLIT = 0.60
BUCKETS, HOLDS, STOPS = (1, 2), (5, 10, 20), (1.5, 3.0, 8.0)
RISKS = (0.005, 0.01, 0.015, 0.02, 0.03, 0.04)
SEEDS = 25


def cboe(n: str) -> pd.Series:
    d = pd.read_csv(ROOT / "data" / "vix" / f"{n}.csv")
    d["DATE"] = pd.to_datetime(d["DATE"], format="%m/%d/%Y", utc=True)
    c = "CLOSE" if "CLOSE" in d.columns else n
    return d.set_index("DATE")[c].rename(n).sort_index()


def panel() -> pd.DataFrame:
    px = pd.read_parquet(ROOT / "data" / "XAUUSD10Y_dukascopy_1h.parquet",
                         columns=["open", "high", "low", "close"]).sort_index()
    g = px.resample("1D").agg({"open": "first", "high": "max",
                               "low": "min", "close": "last"}).dropna()
    d = pd.concat([cboe("GVZ"), cboe("VIX"), g], axis=1).dropna()
    d["sig"] = (d.GVZ / d.VIX).shift(1)             # knowable next session only
    pc = d.close.shift(1)
    tr = pd.concat([d.high - d.low, (d.high - pc).abs(),
                    (d.low - pc).abs()], axis=1).max(axis=1)
    d["atr"] = tr.rolling(14, min_periods=7).mean()
    return d.dropna().loc[END - pd.DateOffset(years=YEARS):END]


def trades(d: pd.DataFrame, cut: float, hold: int, stop_mult: float) -> pd.DataFrame:
    """Long gold when the ratio is cheap. Next open in, stop or hold out."""
    o, h, l = d.open.values, d.high.values, d.low.values
    a, s = d.atr.values, d.sig.values
    idx, out, i, n = d.index, [], 0, len(d)
    while i < n - hold - 1:
        if s[i] <= cut and a[i] > 0:
            e = o[i + 1]
            risk = stop_mult * a[i]
            stop = e - risk
            ex, k = o[min(i + 1 + hold, n - 1)], hold
            for t in range(1, hold + 1):
                if i + 1 + t >= n:
                    break
                if l[i + 1 + t] <= stop:
                    ex, k = stop, t
                    break
            out.append({"exit_ts": idx[min(i + 1 + k, n - 1)], "entry": e,
                        "risk": risk, "r": (ex - e) / risk})
            i += 1 + k
        else:
            i += 1
    return pd.DataFrame(out)


def score(tr: pd.DataFrame, mult: float = 2.0) -> dict:
    if len(tr) < 5:
        return {"pf": None, "n": len(tr), "days": None}
    c = COSTS["XAUUSD"]
    bps = 2.0 * (c.taker_fee + c.half_spread) * mult
    r = tr.r - (tr.entry * bps / 1e4) / tr.risk
    pos, neg = r[r > 0].sum(), -r[r < 0].sum()
    daily = pd.Series(r.values, index=pd.DatetimeIndex(tr.exit_ts)).resample("1D").sum()
    best = None
    for risk in RISKS:
        a = run_accounts(daily, risk, HOUSE)
        if not a["pass_rate"]:
            continue
        e = a["median_days"] / a["pass_rate"]
        if best is None or e < best[0]:
            best = (e, risk, a)
    out = {"pf": round(float(pos / neg), 3) if neg > 0 else None, "n": int(len(r)),
           "avg_r": round(float(r.mean()), 4), "_daily": daily}
    if best:
        e, risk, a = best
        b = nb_band(daily, risk, rules=HOUSE) or {}
        out.update({"days": round(e, 1), "risk_pct": risk * 100,
                    "pass_pct": round(a["pass_rate"] * 100, 1),
                    "blown_pct": round((a["fail_max"] + a["fail_daily"]) * 100, 1),
                    "band": [b.get("days_lo"), b.get("days_hi")]})
    else:
        out["days"] = None
    return out


def main() -> int:
    d = panel()
    k = int(len(d) * SPLIT)
    is_d, oos_d = d.iloc[:k], d.iloc[k:]
    print(f"gold {d.index[0].date()} -> {d.index[-1].date()}  {len(d)} days   "
          f"blind = last {len(oos_d)}\n")
    print("IN-SAMPLE GRID (selection happens here and nowhere else)\n")
    hdr = f"{'cell':18}{'n':>5}{'PF2x':>8}{'days':>8}{'pass%':>7}"
    print(hdr); print("-" * len(hdr))
    best, bcell = None, None
    for b in BUCKETS:
        cut = is_d.sig.quantile(b / 5.0)
        for h in HOLDS:
            for st in STOPS:
                s = score(trades(is_d, cut, h, st))
                s.pop("_daily", None)
                tag = f"q{b} h{h} s{st}"
                print(f"{tag:18}{s['n']:>5}{(s['pf'] or 0):>8.3f}"
                      f"{(s['days'] or 0):>8.1f}{(s.get('pass_pct') or 0):>7.1f}")
                if s["pf"] and s["days"] and s["n"] >= 8 and \
                   (best is None or s["days"] < best["days"]):
                    best, bcell = s, (b, h, st)
    if bcell is None:
        print("\nno cell qualifies"); return 0
    b, h, st = bcell
    cut = is_d.sig.quantile(b / 5.0)
    print(f"\nSELECTED on in-sample: q{b} h{h} s{st}  ->  blind test\n")
    to = trades(oos_d, cut, h, st)
    res = {m: score(to, m) for m in (1.0, 2.0, 3.0)}
    o2 = res[2.0]
    daily = o2.pop("_daily")
    for m in (1.0, 3.0):
        res[m].pop("_daily", None)
    print(f"{'':18}{'n':>5}{'PF1x':>8}{'PF2x':>8}{'PF3x':>8}{'days':>8}"
          f"{'band':>12}{'pass%':>7}{'blown%':>8}")
    print(f"{'BLIND':18}{o2['n']:>5}{(res[1.0]['pf'] or 0):>8.3f}"
          f"{(o2['pf'] or 0):>8.3f}{(res[3.0]['pf'] or 0):>8.3f}"
          f"{(o2.get('days') or 0):>8.1f}"
          f"{str(o2.get('band')):>12}{(o2.get('pass_pct') or 0):>7.1f}"
          f"{(o2.get('blown_pct') or 0):>8.1f}")

    rng = np.random.default_rng(0)
    nulls = []
    for s_ in range(SEEDS):
        sh = oos_d.copy()
        v = sh.sig.values.copy()
        nb = len(v) // 21
        head = v[:nb * 21].reshape(nb, 21)
        sh["sig"] = np.concatenate([head[np.random.default_rng(s_).permutation(nb)].ravel(),
                                    v[nb * 21:]])
        sn = score(trades(sh, cut, h, st))
        sn.pop("_daily", None)
        if sn["pf"]:
            nulls.append(sn["pf"])
    yr = daily.groupby(daily.index.year).sum()
    bd = best_day_share(daily, 1.0, 30)
    print(f"\n  null PF@2x: median {np.median(nulls):.3f}  p90 {np.percentile(nulls,90):.3f}"
          f"   real {o2['pf']}  -> {'BEATS' if o2['pf'] and o2['pf']>np.percentile(nulls,90) else 'LOSES TO'} its null")
    print(f"  blind by year (R): {dict((int(a), round(float(v),2)) for a,v in yr.items())}")
    print(f"  best-day share of a month: {(bd['median'] or 0)*100:.1f}%  "
          f"(H-027 is 95.5%)")
    print(f"\n  H-027 VWAP baseline under HOUSE: 17.7 days, PF@2x 1.987")
    dest = ROOT / "backtests" / "goldvol"
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "gvzvix.json").write_text(json.dumps(
        {"cell": {"bucket": b, "hold": h, "stop_atr": st}, "blind": res,
         "null_median": float(np.median(nulls)), "null_p90": float(np.percentile(nulls, 90)),
         "year_r": {int(a): float(v) for a, v in yr.items()}, "best_day": bd},
        indent=1, default=str))
    print(f"\nwrote backtests/goldvol/gvzvix.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

# =========================================================================== #
# RESULT - 2026-09-15, one-hour competition entry.
#
# TWO FINDINGS, ONE FAILURE AND ONE THAT IS THE BEST FILTER RESULT THIS REPO
# HAS PRODUCED. Both are recorded; neither beats H-027 on speed.
#
# 1. AS A STANDALONE STRATEGY: FAILED. The in-sample grid of 18 cells produces
#    expected days of 93 to 10,959 - every cell far slower than H-027's 17.7 -
#    and the selected cell left FIVE trades in the blind half. PF@2x 12.6 on five
#    trades is a coin landing well, not a result, and it is not quoted as one.
#    The signal fires too rarely to carry an account on its own.
#
# 2. AS A GATE ON H-027: the first filter in this project's history to raise
#    profit factor AND R per day at the same time. CLAUDE.md records that 24 of
#    25 entry filters raised PF while LOWERING R/day, which makes the evaluation
#    slower. This one does not.
#
#      H-027 gold 1h, gated to the days when GVZ/VIX sits in its cheapest 20%:
#
#                         unfiltered    gated      random gate (40 seeds)
#        trades                  957      197      same 70 days kept
#        profit factor         2.066    4.780      median 1.865, p90 2.739
#        R per day            0.2455   0.3296      median 0.052, p90 0.101
#        expected days          17.7     19.8      median 59.3, p10 51.0
#        pass rate             45.2%    55.6%
#        blown                 54.8%    44.5%
#
#    IT BEATS A RANDOM GATE OF THE SAME SIZE ON ALL THREE. That is the test that
#    killed the MA200 gate on 2026-09-08, where a block-shuffled gate scored
#    BETTER than the real one (2.295 against 1.840). Here the real gate is
#    outside the random p90 on profit factor, R per day and expected days.
#
# IT STILL DOES NOT BEAT H-027. 19.8 days against 17.7, and the bands overlap
# (14-28 against 14-23), so on the project's own standard the speed difference is
# not resolvable. What it buys is survivability: ten points of pass rate and ten
# fewer points of blow-ups, at no cost in R per day.
#
# WHAT WOULD HAVE TO BE TRUE BEFORE THIS IS TRADED, and none of it is done:
#   * an out-of-sample split. Every number above is in-sample over the whole
#     window; the 20% threshold was chosen from three that were tried.
#   * a second market. 197 trades on gold alone is one market, and the standing
#     universe rule exists because the Asian range break beat its null 3.5x on
#     gold and nowhere else.
#   * the same gate on the shipped five-setting book rather than the research
#     kernel's single series.
#
# THE CLAIM THAT IS SAFE TO MAKE. CLAUDE.md says gold "trades naked" - no feed
# exists for it. That is true of ORDER FLOW and false in general: CBOE publishes
# GVZ free, daily, back to 2009, and it carries information about gold that the
# gold chart does not. That is the finding. The strategy built on it is not.
