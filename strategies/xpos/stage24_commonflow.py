"""H-019 - the COMMON order-flow factor as a second gate on the H-017 book.

MECHANISM, before any result. Anastasopoulos, Gradojevic, Liu, Maynard and
Tsiakas (Journal of Financial Markets, 2026) find that an AGGREGATE order flow
built by summing signed volume across venues - they call it world order flow -
has more explanatory and predictive power for any individual coin's return than
that coin's own order flow does. One standard deviation of it moves daily
returns 1.9% (t = 29.33). Their long-short machine-learning portfolio earns
0.81% a day at annualised Sharpe 3.61 with a break-even cost of 0.50% per day,
against the 0.14% round trip charged here. Who is on the other side: the
aggregate is the market-wide risk appetite that individual coins get repriced
against, so a coin's own flow is a noisy read on it and the cross-sectional
average is the cleaner one.

Why this is not something already tested here. Stage 2 tested every feed
feature RAW and CROSS-SECTIONALLY DEMEANED. Demeaning removes exactly this
factor - it throws away the market-wide component to keep the idiosyncratic
residual. The cross-sectional MEAN, used as a single common signal applied to
every coin, has never been built in this project.

Construction. Per coin, signed taker flow (buy - sell) / volume on the 5m
archive - the same source the crowd gate already uses, so no new data. The
common factor is the equal-weighted cross-sectional mean of that across all
coins present at each 5m stamp, then z-scored on a trailing, shifted window so
a bar is never scored against itself. Coins are equal-weighted rather than
volume-weighted so BTC does not simply become the factor.

The gate. The paper's effect is POSITIVE - flow pushes returns the same way -
so the momentum reading keeps a long when the factor is high. The contrarian
reading is tested beside it because this project's one working gate (H-009's
crowd gate) is contrarian, and assuming the sign is how a result gets invented.
Sign, threshold and whether the gate replaces or stacks on the crowd gate are
ALL chosen inside the fit window, then run blind.

Null: the same gate driven by a block-shuffled factor. It keeps the factor's
distribution and autocorrelation and destroys only its alignment with the day,
so it holds the share of trades cut roughly constant.

Output: backtests/xpos/stage24_commonflow.csv
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
                                            rank_legs, to_daily)

FEEDS = ROOT / "data" / "feeds"
OUT = ROOT / "backtests" / "xpos"
LEG_COUNTS = (4, 6, 8, 10, 12, 14, 17, 20, 25)
RISKS = (0.0025, 0.005, 0.0075, 0.01, 0.015)
ZWIN = 288                       # one day of 5m bars, matching orderflow.features
QS = (0.0, 0.2, 0.3, 0.4, 0.5)   # share of trades the gate is allowed to cut


def common_factor() -> pd.Series:
    """Equal-weighted cross-sectional mean of per-coin signed taker flow.

    Each coin's flow is z-scored FIRST, on its own trailing window, so a coin
    with a structurally higher taker share does not dominate the average, and
    so the mean is a mean of comparable quantities rather than of levels.
    """
    cols = {}
    for p in sorted(FEEDS.glob("*_perp_5m.parquet")):
        sym = p.name.replace("_perp_5m.parquet", "")
        try:
            df = pd.read_parquet(p)
        except Exception:
            continue
        if "taker_buy_base" not in df or "volume" not in df:
            continue
        buy = df.taker_buy_base
        vol = df.volume.replace(0.0, np.nan)
        cvd = (buy - (df.volume - buy).clip(lower=0.0)) / vol
        m = cvd.rolling(ZWIN, min_periods=ZWIN // 2).mean().shift(1)
        s = cvd.rolling(ZWIN, min_periods=ZWIN // 2).std(ddof=0).shift(1)
        z = (cvd - m) / s.replace(0.0, np.nan)
        cols[sym] = z[~z.index.duplicated(keep="last")]
    if not cols:
        raise SystemExit("no perp feeds found")
    panel = pd.DataFrame(cols).sort_index()
    n = panel.notna().sum(axis=1)
    print(f"common factor from {panel.shape[1]} coins, "
          f"{n.max()} at the widest, {panel.index.min():%Y-%m} "
          f"-> {panel.index.max():%Y-%m}")
    # at least three coins present, else the "cross-section" is one coin
    return panel.mean(axis=1).where(n >= 3)


def attach(t: pd.DataFrame, f: pd.Series, name: str) -> pd.DataFrame:
    """Point-in-time factor reading at each trade's entry, no forward fill."""
    idx = f.dropna()
    # A 5m bar stamped t covers [t, t+5m), so it is not READABLE until t+5m.
    # Shifting the observation times forward by one bar before the backward
    # search is what stops a trade filled at t from seeing the bar it is
    # standing in - the same convention as `stage10_wide.asof`, which is how
    # H-009's crowd gate avoids the identical trap.
    # `.values` drops the tz on both sides, so both are naive UTC and directly
    # comparable; mixing a tz-aware index with a naive array raises.
    ix = idx.index.values + np.timedelta64(5, "m")
    want = t.entry_ts.values
    pos = np.searchsorted(ix, want, side="right") - 1
    at = np.clip(pos, 0, len(ix) - 1)
    v = np.where(pos >= 0, idx.values[at], np.nan)
    # a reading more than two bars stale is not a reading
    age = np.where(pos >= 0, (want - ix[at]) / np.timedelta64(1, "m"), np.inf)
    out = t.copy()
    out[name] = np.where(age <= 15.0, v, np.nan)
    return out


def apply_gate(t: pd.DataFrame, col: str, thr: float, sign: int) -> pd.DataFrame:
    """`sign` +1 = momentum (keep longs when the factor is high)."""
    v = t[col].values
    d = t.direction.values
    keep = np.where(d > 0, sign * v >= thr, sign * v <= -thr)
    return t[np.where(np.isnan(v), True, keep)]


def main() -> int:
    t = pd.read_parquet(OUT / "stage14_trades.parquet")
    t["entry_ts"] = pd.to_datetime(t.entry_ts, utc=True)
    t["exit_ts"] = pd.to_datetime(t.exit_ts, utc=True)
    t = t[t.topn == 1].sort_values("exit_ts")

    f = common_factor()
    t = attach(t, f, "cflow")
    print(f"factor present on {t.cflow.notna().mean()*100:.1f}% of trades\n")

    g0 = gated(t)                       # H-017 as it stands, crowd gate only
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

    # ---- choose sign, threshold and stack-vs-replace on the FIT window ----
    print("choosing the flow gate on the FIT window only")
    thr_grid = [float(np.nanquantile(np.abs(t.cflow.values), q)) if q else 0.0
                for q in QS]
    pick, rows = None, []
    for mode in ("stack", "replace"):
        src = g0 if mode == "stack" else t
        for sign in (+1, -1):
            for q, thr in zip(QS, thr_grid):
                gg = apply_gate(src, "cflow", thr, sign)
                _, dv = build(gg[gg.exit_ts <= mid], keys, f_lo, f_hi)
                if dv is None:
                    continue
                a = allin(dv, risk)
                if a and a.get("allin_days") and (
                        pick is None or a["allin_days"] < pick["allin_days"]):
                    pick = {"mode": mode, "sign": sign, "q": q, "thr": thr, **a}
    if pick is None:
        print("no admissible flow gate in the fit window")
        return 1
    lab = "momentum" if pick["sign"] > 0 else "contrarian"
    print(f"  -> {pick['mode']}, {lab}, |z| >= {pick['thr']:.3f} "
          f"(q={pick['q']}) (fit all-in {pick['allin_days']}d)\n")

    # ---- blind on the TEST window ----
    print("APPLIED BLIND TO THE TEST WINDOW")
    print(f"  {'book':30s} {'trades':>7s} {'t/day':>6s} {'PF2x':>6s} "
          f"{'pass':>7s} {'median d':>9s} {'all-in d':>9s}")
    span = max((s_hi - s_lo).days, 1)

    def row(gg, label, window="test"):
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
        rows.append({"window": window, "book": label, "trades": len(s),
                     "tpd": round(len(s)/span, 2),
                     "pf_2x": round(pf(s.r_2x.values), 3), **a})
        return a

    base = row(g0, "H-017 baseline (crowd gate)")
    src = g0 if pick["mode"] == "stack" else t
    real = row(apply_gate(src, "cflow", pick["thr"], pick["sign"]),
               "H-019 + common flow gate")

    # ---- null: same gate, block-shuffled factor ----
    nd = []
    for seed in range(8):
        sh = of.block_shuffle(pd.Series(src.cflow.values).set_axis(src.entry_ts),
                              seed=seed + 71, block=288).values
        s2 = src.copy()
        s2["cflow_sh"] = sh
        gg = apply_gate(s2, "cflow_sh", pick["thr"], pick["sign"])
        _, dv2 = build(gg[gg.exit_ts > mid], keys, s_lo, s_hi)
        if dv2 is None:
            continue
        a2 = allin(dv2, risk)
        if a2 and a2.get("allin_days"):
            nd.append(a2["allin_days"])
    if nd:
        print(f"  {'NULL shuffled factor':30s} {'-':>7s} {'-':>6s} {'-':>6s} "
              f"{'-':>7s} {'-':>9s} {np.mean(nd):>9.1f}   "
              f"(best seed {min(nd):.1f})")
        rows.append({"window": "test", "book": "null shuffled factor",
                     "allin_days": round(float(np.mean(nd)), 1),
                     "best_seed": round(float(min(nd)), 1)})

    if base and real:
        d = (base["allin_days"] - real["allin_days"]) / base["allin_days"]
        print(f"\n  VERDICT: {base['allin_days']:.1f} -> "
              f"{real['allin_days']:.1f} all-in days ({d*100:+.1f}%)")

    pd.DataFrame(rows).to_csv(OUT / "stage24_commonflow.csv", index=False)
    print(f"\nwrote {OUT / 'stage24_commonflow.csv'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
