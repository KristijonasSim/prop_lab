"""H-015 stage 2 — replace H-009's per-coin gate with a complex-wide one.

Stage 1 found the advantage is real but NARROW: at the 8-hour horizon the
complex reading beats the coin's own on every measure (mean |IC| 0.0207 vs
0.0159, beats its null in 82% of cells vs 55%, quintile spread 24bps vs 16bps),
and at 1h, 4h and 24h it does not. It also found that `idio` - crowding in this
coin BEYOND the complex - is the weakest feature in the table, which is the
mechanism claim surviving its own test: crowding is systemic, not per-coin.

If that is true then H-009's per-coin gate is reading a noisy proxy for a
market-wide quantity, and reading the quantity directly should keep more of the
edge. This tests exactly that, on H-009's own trades.

THREE THINGS THIS IS CAREFUL ABOUT.

  * The comparison is against H-009's ACTUAL gate, not against ungated H-002.
    Beating no gate at all would prove nothing - H-009 already does that.
  * Everything is measured on the COMMON WINDOW where the systemic signal
    exists (>= 6 coins listed, so 2021-12 on). H-009's record starts 2019, and
    comparing a gate on 2021-2026 against a baseline on 2019-2026 would be
    measuring the market, not the gate.
  * The threshold is fixed at zero, not searched, for the reason H-009 fixed
    its own: a searched threshold on a few thousand trades is a fitted number.

The number that decides it is RETURN OVER DRAWDOWN, not profit factor. H-013
raised PF from 1.806 to 1.946 and was still rejected, because it halved R per
day and `days = maxDD_R / R_per_day` got worse. A gate that improves this book
has to keep the R.

Run: .venv/bin/python strategies/breadth/stage2_gate.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from strategies.breadth import breadth as br                   # noqa: E402

FEEDS = ROOT / "data" / "feeds"
OUT = ROOT / "backtests" / "breadth"
OUT.mkdir(parents=True, exist_ok=True)
TRADES = ROOT / "backtests" / "gated_vwap" / "stage6_trades.parquet"


def pf(r):
    w, l = r[r > 0].sum(), -r[r < 0].sum()
    return float(w / l) if l > 0 else float("nan")


def maxdd(r):
    e = np.cumsum(r)
    return float((e - np.maximum.accumulate(e)).min())


def stats(d):
    if len(d) < 20:
        return None
    r = d.r_2x.values
    span = max((d.exit_ts.max() - d.entry_ts.min()).days, 1)
    dd = maxdd(r)
    return {"trades": len(r), "pf_2x": pf(r), "total_r": float(r.sum()),
            "maxdd_r": dd, "ret_dd": float(r.sum()) / abs(dd) if dd else np.nan,
            "r_per_day": float(r.sum()) / span, "tpd": len(r) / span}


def show(label, s, base=None):
    if s is None:
        print(f"  {label:34s}  (too few trades)")
        return
    mark = ""
    if base is not None and base["ret_dd"] > 0:
        d = (s["ret_dd"] - base["ret_dd"]) / base["ret_dd"] * 100.0
        mark = f"   ret/DD {d:+6.1f}% vs H-009"
    print(f"  {label:34s} n={s['trades']:5d}  PF2x {s['pf_2x']:.3f}  "
          f"maxDD {s['maxdd_r']:7.2f}R  R/day {s['r_per_day']:.4f}  "
          f"ret/DD {s['ret_dd']:6.2f}{mark}")


def asof(sig: pd.Series, when: pd.Series) -> np.ndarray:
    """Last reading that had CLOSED before each entry. The +5min shift matters:
    a 5-minute bar stamped T is only observable at T+5m."""
    sd = sig.dropna()
    obs = pd.DataFrame({"ts": sd.index + pd.Timedelta("5min"),
                        "v": sd.values}).sort_values("ts")
    # `when.values` drops the tz and merge_asof then refuses the join on a
    # dtype mismatch. Keep the Series so both keys stay tz-aware UTC.
    left = pd.DataFrame({"i": np.arange(len(when)),
                         "t": when.reset_index(drop=True)}).sort_values("t")
    j = pd.merge_asof(left, obs, left_on="t", right_on="ts",
                      direction="backward", tolerance=pd.Timedelta(days=1))
    return j.sort_values("i").v.values


def main():
    t = pd.read_parquet(TRADES)
    t["entry_ts"] = pd.to_datetime(t.entry_ts, utc=True)
    t["exit_ts"] = pd.to_datetime(t.exit_ts, utc=True)

    print("building the cross-sectional panel ...", flush=True)
    pan = br.panel(FEEDS)
    sysdf = br.systemic(pan)
    first = sysdf["sys"].dropna().index[0]
    t = t[t.entry_ts >= first].copy()
    print(f"common window: {first:%Y-%m-%d} -> {t.exit_ts.max():%Y-%m-%d}, "
          f"{len(t)} trades of H-002's book\n")

    ungated = stats(t)
    h009 = stats(t[t.gated])
    print("BASELINES on the common window")
    show("H-002, no gate", ungated)
    show("H-009, per-coin crowd gate", h009)
    print()

    rows = []
    print("SYSTEMIC GATES — keep a long only when the complex is not crowded long")
    for name in ("sys", "breadth", "dsys_12", "dsys_48", "dsys_144", "sys_gap"):
        v = asof(sysdf[name], t.entry_ts)
        d = t.direction.values
        # mirror of H-009's rule: long survives a falling / uncrowded reading,
        # short survives a rising / crowded one. NaN leaves the trade alone.
        keep = np.where(d > 0, v < 0, v > 0)
        keep = np.where(np.isnan(v), True, keep)
        on = stats(t[keep])
        off = stats(t[~keep])
        show(f"gate = {name}", on, h009)
        if off:
            print(f"  {'  ^ what it removed':34s} n={off['trades']:5d}  "
                  f"PF2x {off['pf_2x']:.3f}  total {off['total_r']:.1f}R"
                  f"   (must be WORSE than what it keeps)")
        if on:
            rows.append({"gate": name, **on})

    # And the honest stack: does the systemic reading ADD to H-009's own gate,
    # rather than replace it?
    print("\nSTACKED ON TOP OF H-009's EXISTING GATE")
    tg = t[t.gated]
    for name in ("sys", "breadth", "dsys_144"):
        v = asof(sysdf[name], tg.entry_ts)
        d = tg.direction.values
        keep = np.where(d > 0, v < 0, v > 0)
        keep = np.where(np.isnan(v), True, keep)
        show(f"H-009 + {name}", stats(tg[keep]), h009)

    if rows:
        pd.DataFrame(rows).to_csv(OUT / "stage2_gate.csv", index=False)
        print(f"\nwrote stage2_gate.csv in {OUT}")


if __name__ == "__main__":
    main()
