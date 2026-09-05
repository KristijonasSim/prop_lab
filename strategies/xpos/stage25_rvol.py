"""H-020 - relative volume, the "stocks in play" selector, ported to perps.

MECHANISM, before any result. Zarattini, Barbon and Aziz get Sharpe 2.81 out of
an opening-range breakout not because the breakout rule is good - this project
already killed that rule on single symbols as H-001 - but because they rebuild
the universe every morning, keeping only the top 20 of 7,000 stocks by opening
RELATIVE volume. The claim being borrowed is only the selector: an instrument
trading far above its own normal volume has news or flow in it, and a
directional rule works on it and does not work on the same instrument on a
quiet day. Who is on the other side: liquidity providers who widen on abnormal
volume, and slower participants repricing after the fact.

Why it should move the number that matters. Stage 18's weakest finding was that
K-ranked leg selection is only weakly better than drawing legs at random - the
random-leg null's best seed reached 29.0 against the real 30.3. Leg selection is
therefore the loosest screw in H-017. Relative volume is a selector that changes
every day rather than once per window, so if "in play" means anything the book
should stop paying for the legs that are asleep.

HONEST SCOPE. The wide-universe download was interrupted, so this runs on the
ELEVEN coins already on disk, not the 69 the archive covers. That is a test of
whether the selector carries information, not of the width it was meant to buy.
Six more coins have metrics but no perp klines and cannot be legs yet.

Two forms, both chosen on the fit window:

  absolute   keep a trade when its coin's relative volume exceeds a threshold.
             "Is this coin busy right now."
  crossX     keep a trade only when its coin is in the top-k of the cross-
             section by relative volume that day. This is the paper's actual
             mechanic - a rank, not a level - and it is the one that holds the
             number of live legs constant as the whole market gets busy.

Relative volume is volume in the last 24h over the median of the same
time-of-day window across the prior 14 days, so the intraday shape of crypto
volume is divided out rather than mistaken for news. It is shifted one bar.

Null: the same selector driven by a block-shuffled relative-volume series, which
keeps how often the gate fires and destroys which day it fires on.

Output: backtests/xpos/stage25_rvol.csv
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from strategies.orderflow import orderflow as of                    # noqa: E402
from strategies.xpos.stage16_kris_shape import maxdd, pf            # noqa: E402
from strategies.xpos.stage18_nested import (allin, build, gated,    # noqa: E402
                                            rank_legs)
from strategies.xpos.stage24_commonflow import attach               # noqa: E402

FEEDS = ROOT / "data" / "feeds"
OUT = ROOT / "backtests" / "xpos"
LEG_COUNTS = (4, 6, 8, 10, 12, 14, 17, 20, 25)
RISKS = (0.0025, 0.005, 0.0075, 0.01, 0.015)
DAY = 288                        # 5m bars in a day
BASE_DAYS = 14                   # the paper's own lookback
RV_THR = (1.0, 1.2, 1.5, 2.0)    # "absolute" form
TOP_K = (2, 3, 4, 6, 8)          # "crossX" form


def rvol_panel() -> pd.DataFrame:
    """Per-coin relative volume on the 5m grid, causal.

    Numerator is trailing 24h volume. Denominator is the median of that same
    trailing-24h series sampled at the SAME point of the previous 14 days, so
    the daily volume shape cancels. Both are shifted one bar: a bar's own
    volume is not knowable when its signal is read.
    """
    cols = {}
    for p in sorted(FEEDS.glob("*_perp_5m.parquet")):
        sym = p.name.replace("_perp_5m.parquet", "")
        df = pd.read_parquet(p)
        if "volume" not in df:
            continue
        v = df.volume[~df.index.duplicated(keep="last")].sort_index()
        cur = v.rolling(DAY, min_periods=DAY // 2).sum().shift(1)
        base = pd.concat([cur.shift(DAY * k) for k in range(1, BASE_DAYS + 1)],
                         axis=1).median(axis=1)
        cols[sym] = cur / base.replace(0.0, np.nan)
    panel = pd.DataFrame(cols).sort_index()
    print(f"relative volume for {panel.shape[1]} coins, "
          f"{panel.index.min():%Y-%m} -> {panel.index.max():%Y-%m}")
    return panel


def attach_rvol(t: pd.DataFrame, panel: pd.DataFrame) -> pd.DataFrame:
    """Each trade gets its own coin's relative volume and its cross-sectional
    rank among the coins quoted at that moment."""
    rank = panel.rank(axis=1, ascending=False, method="min")
    out = t.copy()
    out["rvol"] = np.nan
    out["rvrank"] = np.nan
    for sym, g in t.groupby("symbol"):
        if sym not in panel.columns:
            continue
        for col, name in ((panel[sym], "rvol"), (rank[sym], "rvrank")):
            v = attach(g[["entry_ts"]], col, "v")["v"].values
            out.loc[g.index, name] = v
    return out


def keep_abs(t, thr):
    v = t.rvol.values
    return t[np.where(np.isnan(v), True, v >= thr)]


def keep_rank(t, k):
    v = t.rvrank.values
    return t[np.where(np.isnan(v), True, v <= k)]


def main() -> int:
    t = pd.read_parquet(OUT / "stage14_trades.parquet")
    t["entry_ts"] = pd.to_datetime(t.entry_ts, utc=True)
    t["exit_ts"] = pd.to_datetime(t.exit_ts, utc=True)
    t = t[t.topn == 1].sort_values("exit_ts")

    t = attach_rvol(t, rvol_panel())
    print(f"relative volume present on {t.rvol.notna().mean()*100:.1f}% "
          f"of trades, median {np.nanmedian(t.rvol):.2f}\n")

    g0 = gated(t)
    mid = g0.exit_ts.quantile(0.5)
    f_lo, f_hi, s_lo, s_hi = g0.exit_ts.min(), mid, mid, g0.exit_ts.max()
    print(f"FIT   {f_lo:%Y-%m-%d} -> {f_hi:%Y-%m-%d}")
    print(f"TEST  {s_lo:%Y-%m-%d} -> {s_hi:%Y-%m-%d}\n")

    order = rank_legs(g0[g0.exit_ts <= mid])
    best = None
    for n in LEG_COUNTS:
        if n > len(order):
            continue
        _, dv = build(g0[g0.exit_ts <= mid], order[:n], f_lo, f_hi)
        if dv is None:
            continue
        for risk in RISKS:
            a = allin(dv, risk)
            if a and a.get("allin_days") and (
                    best is None or a["allin_days"] < best["allin_days"]):
                best = {"n": n, "risk": risk, **a}
    keys, risk = order[:best["n"]], best["risk"]
    print(f"baseline config chosen on FIT: {best['n']} legs at "
          f"{risk*100:.2f}% risk\n")

    print("choosing the selector on the FIT window only")
    pick, rows = None, []
    for form, grid, fn in (("absolute", RV_THR, keep_abs),
                           ("crossX", TOP_K, keep_rank)):
        for p in grid:
            gg = fn(g0, p)
            _, dv = build(gg[gg.exit_ts <= mid], keys, f_lo, f_hi)
            if dv is None:
                continue
            a = allin(dv, risk)
            if a and a.get("allin_days") and (
                    pick is None or a["allin_days"] < pick["allin_days"]):
                pick = {"form": form, "param": p, "fn": fn, **a}
    if pick is None:
        print("no admissible selector in the fit window")
        return 1
    print(f"  -> {pick['form']} at {pick['param']} "
          f"(fit all-in {pick['allin_days']}d)\n")

    print("APPLIED BLIND TO THE TEST WINDOW")
    print(f"  {'book':30s} {'trades':>7s} {'t/day':>6s} {'PF2x':>6s} "
          f"{'pass':>7s} {'median d':>9s} {'all-in d':>9s}")
    span = max((s_hi - s_lo).days, 1)

    def row(gg, label):
        s, dv = build(gg[gg.exit_ts > mid], keys, s_lo, s_hi)
        if dv is None:
            print(f"  {label:30s} {'too few trades':>40s}")
            return None
        a = allin(dv, risk)
        if not a or not a.get("allin_days"):
            print(f"  {label:30s} {'no admissible account':>40s}")
            return None
        print(f"  {label:30s} {len(s):>7d} {len(s)/span:>6.2f} "
              f"{pf(s.r_2x.values):>6.3f} {a['pass_rate']*100:>6.1f}% "
              f"{str(a['median_days']):>9s} {a['allin_days']:>9.1f}")
        rows.append({"window": "test", "book": label, "trades": len(s),
                     "tpd": round(len(s)/span, 2),
                     "pf_2x": round(pf(s.r_2x.values), 3), **a})
        return a

    base = row(g0, "H-017 baseline")
    real = row(pick["fn"](g0, pick["param"]), "H-020 + relative volume")

    col = "rvol" if pick["form"] == "absolute" else "rvrank"
    nd = []
    for seed in range(8):
        sh = of.block_shuffle(pd.Series(g0[col].values).set_axis(g0.entry_ts),
                              seed=seed + 51, block=DAY).values
        s2 = g0.copy()
        s2[col] = sh
        gg = pick["fn"](s2, pick["param"])
        _, dv2 = build(gg[gg.exit_ts > mid], keys, s_lo, s_hi)
        if dv2 is None:
            continue
        a2 = allin(dv2, risk)
        if a2 and a2.get("allin_days"):
            nd.append(a2["allin_days"])
    if nd:
        print(f"  {'NULL shuffled rel volume':30s} {'-':>7s} {'-':>6s} "
              f"{'-':>6s} {'-':>7s} {'-':>9s} {np.mean(nd):>9.1f}   "
              f"(best seed {min(nd):.1f})")
        rows.append({"window": "test", "book": "null shuffled rel volume",
                     "allin_days": round(float(np.mean(nd)), 1),
                     "best_seed": round(float(min(nd)), 1)})

    if base and real:
        d = (base["allin_days"] - real["allin_days"]) / base["allin_days"]
        print(f"\n  VERDICT: {base['allin_days']:.1f} -> "
              f"{real['allin_days']:.1f} all-in days ({d*100:+.1f}%)")

    pd.DataFrame(rows).to_csv(OUT / "stage25_rvol.csv", index=False)
    print(f"\nwrote {OUT / 'stage25_rvol.csv'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
