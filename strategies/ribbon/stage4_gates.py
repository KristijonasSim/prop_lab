"""H-016 stage 4 - variations A and D, the two that combine the ribbon with
something that already works.

A. RIBBON GATES H-009. Take H-009's trades unchanged and keep only the ones
   where the ribbon on that leg's own symbol and timeframe agrees with the
   trade's direction. Nothing is refitted, the threshold is FIXED, and the
   comparison is against H-009's actual gated book - not against ungated
   H-002, because beating no gate at all would prove nothing.

   This is the highest-prior test in H-016 for one reason: the only two things
   that have ever improved this project's book were gates (H-009, H-015), and
   neither invented a new entry.

D. THE CROWD GATES THE RIBBON. The mirror. Take the ribbon's own trades and
   keep only the ones where Binance's long/short ACCOUNT ratio is positioned
   against them - H-006's kernel, the one data feed in this project that has
   ever paid. A price pattern crossed with the feed that works.

The number that decides both is RETURN OVER DRAWDOWN, not profit factor.
H-013 raised PF and was rejected because it halved R per day and
`days = maxDD_R / R_per_day` got worse. A gate that helps has to keep the R.

Output: backtests/ribbon/stage4_gates.csv
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from strategies.orderflow import orderflow as of                    # noqa: E402
from strategies.ribbon import engine as E                           # noqa: E402
from strategies.ribbon.ribbon import RibbonParams, features         # noqa: E402
from strategies.ribbon.sweep import (COSTS, OUT, TFS, load_tf,      # noqa: E402
                                     metrics, ribbon_inputs, run_one)

FEEDS = ROOT / "data" / "feeds"
TRADES = ROOT / "backtests" / "gated_vwap" / "stage6_trades.parquet"


def pf(r):
    w, l = r[r > 0].sum(), -r[r < 0].sum()
    return float(w / l) if l > 0 else float("nan")


def maxdd(r):
    e = np.cumsum(r)
    return float((e - np.maximum.accumulate(e)).min())


def stats(d, rcol="r_2x"):
    if len(d) < 20:
        return None
    r = d[rcol].values
    span = max((d.exit_ts.max() - d.entry_ts.min()).days, 1)
    dd = maxdd(r)
    return {"trades": len(r), "pf_2x": pf(r), "total_r": float(r.sum()),
            "maxdd_r": dd, "ret_dd": float(r.sum()) / abs(dd) if dd else np.nan,
            "r_per_day": float(r.sum()) / span, "tpd": len(r) / span}


def show(label, s, base=None):
    if s is None:
        print(f"  {label:38s}  (too few trades)")
        return
    mark = ""
    if base is not None and base["ret_dd"] > 0:
        d = (s["ret_dd"] - base["ret_dd"]) / base["ret_dd"] * 100.0
        mark = f"   ret/DD {d:+6.1f}% vs base"
    print(f"  {label:38s} n={s['trades']:5d}  PF2x {s['pf_2x']:.3f}  "
          f"maxDD {s['maxdd_r']:7.2f}R  R/day {s['r_per_day']:.4f}  "
          f"ret/DD {s['ret_dd']:6.2f}{mark}")


def asof(sig: pd.Series, when: pd.Series, lag: str) -> np.ndarray:
    """Last reading CLOSED before each timestamp.

    `lag` is the bar's own duration: a bar stamped T only finished at T+lag, so
    reading it at T would be look-ahead. This is the single easiest place in a
    gate study to leak the future and it is why the shift is explicit.
    """
    sd = sig.dropna()
    obs = pd.DataFrame({"ts": sd.index + pd.Timedelta(lag),
                        "v": sd.values}).sort_values("ts")
    left = pd.DataFrame({"i": np.arange(len(when)),
                         "t": when.reset_index(drop=True)}).sort_values("t")
    j = pd.merge_asof(left, obs, left_on="t", right_on="ts",
                      direction="backward", tolerance=pd.Timedelta(days=2))
    return j.sort_values("i").v.values


# --------------------------------------------------------------------------
# A - the ribbon gates H-009
# --------------------------------------------------------------------------

def variation_a(rows: list[dict]) -> None:
    t = pd.read_parquet(TRADES)
    t["entry_ts"] = pd.to_datetime(t.entry_ts, utc=True)
    t["exit_ts"] = pd.to_datetime(t.exit_ts, utc=True)

    print("A. RIBBON GATES H-009 — keep only trades the ribbon agrees with\n")
    base_h002 = stats(t)
    base_h009 = stats(t[t.gated])
    show("H-002, no gate", base_h002)
    show("H-009, crowd gate (the baseline)", base_h009)
    print()

    # The ribbon reading for every (symbol, tf) leg the book actually holds.
    agree = {}
    for sym, tf in sorted(set(zip(t.symbol, t.tf))):
        df = load_tf(sym, tf)
        if len(df) < 1000:
            continue
        agree[(sym, tf)] = features(df, RibbonParams())["agree"]
    print(f"  ribbon built on {len(agree)} legs\n")

    lag = {"5m": "5min", "15m": "15min", "30m": "30min", "1h": "1h", "4h": "4h"}
    v = np.full(len(t), np.nan)
    for (sym, tf), s in agree.items():
        m = (t.symbol.values == sym) & (t.tf.values == tf)
        if m.sum():
            v[m] = asof(s, t.entry_ts[m], lag[tf])
    t["ribbon"] = v
    print(f"  ribbon reading available on {np.isfinite(v).mean():.1%} of trades\n")

    for thr, label in ((0.0, "same sign"), (0.6, "|agree|>=0.6"),
                       (1.0, "fully stacked")):
        d = t.direction.values
        # WITH the ribbon: keep a long only when the ribbon is up.
        keep = np.where(d > 0, v >= thr, v <= -thr)
        keep = np.where(np.isnan(v), True, keep)      # no reading, no opinion
        on = stats(t[t.gated & keep])
        show(f"H-009 + ribbon agrees ({label})", on, base_h009)
        if on:
            rows.append({"variation": "A", "rule": f"agree>={thr}", **on})
        # AGAINST it - the control. If the ribbon is measuring anything, this
        # has to be worse. If both help, the gate is just cutting trades.
        anti = np.where(d > 0, v <= -thr, v >= thr)
        anti = np.where(np.isnan(v), True, anti)
        off = stats(t[t.gated & anti])
        show(f"   CONTROL: ribbon DISagrees ({label})", off, base_h009)
        if off:
            rows.append({"variation": "A-control", "rule": f"agree>={thr}", **off})
    print()


# --------------------------------------------------------------------------
# D - the crowd gates the ribbon
# --------------------------------------------------------------------------

def variation_d(rows: list[dict]) -> None:
    print("D. THE CROWD GATES THE RIBBON — H-006's feed on the ribbon's trades\n")
    # The feed exists at 5m for the coins the archive covers. The ribbon's own
    # best crypto cut is 4h, so the gate is read as-of each entry.
    cfg = dict(mode=E.MODE_AGREE, entry_thr=1.0, require_flip=1, squeeze_n=0,
               min_strength=0.0, trail_mode=E.TRAIL_CHAND, trail_k=6.0,
               stop_k=6.0, trail_start_r=0.0, rr=0.0, max_hold_bars=6 * 7,
               flip_exit=0, dir_mode=E.DIR_BOTH, cfg=0)

    for sym in ("BTCUSDT", "ETHUSDT", "SOLUSDT"):
        try:
            feed = of.load(sym, FEEDS)
            f = of.features(feed)
        except Exception as e:                       # noqa: BLE001
            print(f"  {sym}: no feed ({e})")
            continue
        crowd = f["crowd_z"]

        for tf in ("1h", "4h"):
            df = load_tf(sym, tf)
            if len(df) < 5000:
                continue
            inp = ribbon_inputs(df)
            fee, slip, minrisk = COSTS[sym]
            c = dict(cfg); c["max_hold_bars"] = int(TFS[tf][1] * 7)
            tr = run_one(inp, c, fee, slip, minrisk)
            if tr.shape[0] < 40:
                continue
            ei = tr[:, E.T_ENTRY_I].astype(int)
            ts = pd.Series(df.index[ei])
            cz = asof(crowd, ts, "5min")
            side = tr[:, E.T_DIR]

            base = metrics(tr, df.index, fee, slip)
            # H-006's rule: the crowd is fadeable, so keep a long only when the
            # crowd is NOT already crowded long.
            keep = np.where(side > 0, cz < 0, cz > 0)
            keep = np.where(np.isnan(cz), True, keep)
            gated = metrics(tr[keep], df.index, fee, slip) if keep.sum() > 20 else None
            anti = metrics(tr[~keep], df.index, fee, slip) if (~keep).sum() > 20 else None

            def line(tag, m):
                if not m or not m.get("trades"):
                    return f"  {tag:38s}  (too few trades)"
                dd = m["max_dd_r"]
                rd = m["total_r"] / abs(dd) if dd else np.nan
                return (f"  {tag:38s} n={m['trades']:5d}  PF2x {m['pf_2x']:.3f}  "
                        f"maxDD {dd:7.2f}R  R/day {m['r_per_day']:.4f}  "
                        f"ret/DD {rd:6.2f}")

            print(line(f"{sym} {tf} ribbon, no gate", base))
            print(line(f"{sym} {tf}  + crowd offside (D)", gated))
            print(line(f"{sym} {tf}  CONTROL crowd agrees", anti))
            for tag, m in (("D-base", base), ("D", gated), ("D-control", anti)):
                if m and m.get("trades"):
                    dd = m["max_dd_r"]
                    rows.append({"variation": tag, "rule": f"{sym} {tf}",
                                 "trades": m["trades"], "pf_2x": m["pf_2x"],
                                 "total_r": m["total_r"], "maxdd_r": dd,
                                 "ret_dd": m["total_r"] / abs(dd) if dd else np.nan,
                                 "r_per_day": m["r_per_day"],
                                 "tpd": m["trades_per_day"]})
            print()


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    rows: list[dict] = []
    variation_a(rows)
    variation_d(rows)
    pd.DataFrame(rows).to_csv(OUT / "stage4_gates.csv", index=False)
    print(f"wrote {OUT / 'stage4_gates.csv'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
