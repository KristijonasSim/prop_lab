"""H-006 x H-002 — does the crowd feed improve the one strategy that works?

The obvious test nobody had run. This project's standing pattern is that feeds
work and price patterns do not; H-002 is the one price pattern that survived;
H-006 showed the crowd-positioning feed carries real directional information but
cannot be traded on its own because its drawdown is the wrong shape. Putting the
feed on top of H-002 asks whether the two combine, and it is the most direct
route to "better than H-002" there is, because it starts from H-002.

WHAT IS DONE HERE, exactly:

  * the board's own walk-forward decisions are reused, not redone. For every
    quarter and every crypto leg, stage 10 already chose a configuration blind
    on training data; this re-runs that same configuration on the same test
    quarter and keeps the trades WITH their direction, which the stored trade
    file discards.
  * the crowd signal is read at the bar BEFORE entry, so it is information the
    trade could have had.
  * the filter is directional and follows the stage-1 finding: a long is kept
    when the crowd has been getting shorter, a short when the crowd has been
    getting longer. Fading the crowd, applied to somebody else's entries.
  * the control is the same filter INVERTED. If keeping the trades the crowd
    agrees with pays just as well, then the filter is selecting on something
    other than the crowd and the mechanism story is wrong.

This is a post-filter on realised trades, so it cannot change what H-002 would
have done next after skipping one. That makes the lift an estimate rather than a
backtest, and a positive result here has to be re-run inside the kernel before
it means anything.

Run: .venv/bin/python strategies/orderflow/stage5_vwap_lift.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from strategies.orderflow import orderflow as of                     # noqa: E402
from strategies.vwap.engine import T_ENTRY_I, T_EXIT_I, T_DIR, T_R   # noqa: E402
from strategies.vwap.sweep import features, run_one                  # noqa: E402
from strategies.vwap.stage10_universe import COSTS, load_tf          # noqa: E402
from strategies.vwap.stage6_walkforward import CFGKEY                # noqa: E402

FEEDS = ROOT / "data" / "feeds"
VWAP = ROOT / "backtests" / "vwap"
OUT = ROOT / "backtests" / "orderflow"
OUT.mkdir(parents=True, exist_ok=True)

# the crypto legs of the board's five-leg book, plus the other crypto
# combinations stage 10 walk-forwarded, so the lift is not measured on one leg
LEGS = [("BTCUSDT", "4h"), ("ETHUSDT", "1h"), ("ETHUSDT", "30m"),
        ("SOLUSDT", "4h"), ("BTCUSDT", "1h"), ("BTCUSDT", "30m"),
        ("ETHUSDT", "15m"), ("SOLUSDT", "1h"), ("SOLUSDT", "30m")]
FLOOR, TOPN = 100, 1
SIGNALS = (("dcrowd", 48, 288), ("dcrowd", 144, 288),
           ("crowd_z", 0, 288), ("crowd_z", 0, 864))


def leg_trades(sym: str, tf: str, folds: pd.DataFrame) -> pd.DataFrame:
    """Re-run each fold's chosen configuration and keep the direction."""
    g = folds[(folds.symbol == sym) & (folds.tf == tf)
              & (folds.floor == FLOOR) & (folds.topn == TOPN)]
    if g.empty:
        return pd.DataFrame()
    df = load_tf(sym, tf)
    if len(df) < 3000:
        return pd.DataFrame()
    fee, slip, minrisk = COSTS[sym]
    feats = features(df)
    rows = []
    for row in g.itertuples():
        q = pd.Timestamp(row.quarter, tz="UTC")
        hi = q + pd.DateOffset(months=3)
        cfg = {k: getattr(row, k) for k in CFGKEY if hasattr(row, k)}
        cfg.setdefault("min_risk_bps", minrisk)
        cfg.setdefault("one_trade", 0)
        cfg.setdefault("dir_mode", 0)
        tr = run_one(df, feats, {}, cfg, fee, slip)
        if not len(tr):
            continue
        ei = tr[:, T_ENTRY_I].astype(int)
        ts = df.index[ei]
        keep = (ts >= q) & (ts < hi)
        if not keep.any():
            continue
        tr = tr[keep]
        rows.append(pd.DataFrame({
            "symbol": sym, "tf": tf, "quarter": str(row.quarter),
            "entry_ts": df.index[tr[:, T_ENTRY_I].astype(int)],
            "exit_ts": df.index[tr[:, T_EXIT_I].astype(int)],
            "direction": tr[:, T_DIR], "r": tr[:, T_R],
        }))
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()


def pf(r):
    w, l = r[r > 0].sum(), -r[r < 0].sum()
    return float(w / l) if l > 0 else float("nan")


def dd(r):
    eq = np.concatenate(([0.0], np.cumsum(r)))
    return float((eq - np.maximum.accumulate(eq)).min())


def report(name, r, span):
    d = abs(dd(r))
    return {"book": name, "trades": len(r), "pf": round(pf(r), 3),
            "total_r": round(float(r.sum()), 1), "maxdd_r": round(-d, 2),
            "ret_over_dd": round(float(r.sum()) / d, 2) if d > 0 else np.nan,
            "r_per_day": round(float(r.sum()) / span, 4),
            "win_rate": round(float((r > 0).mean()), 3)}


def main():
    folds = pd.read_parquet(VWAP / "stage10_folds.parquet")
    frames = []
    for sym, tf in LEGS:
        t = leg_trades(sym, tf, folds)
        if not t.empty:
            frames.append(t)
            print(f"  {sym} {tf}: {len(t)} trades", flush=True)
    if not frames:
        print("no trades rebuilt"); return
    tr = pd.concat(frames, ignore_index=True)
    tr["entry_ts"] = pd.to_datetime(tr.entry_ts, utc=True)

    # the 2x-cost R: the stored file's r_2x is r minus one more round trip in R
    # units, and that conversion needs the per-trade risk, which is not stored.
    # So the lift is measured on r at 1x and the RATIO is what carries over.
    out = []
    for kind, look, win in SIGNALS:
        per = {}
        for sym in tr.symbol.unique():
            df = of.load(sym, FEEDS)
            s = of.signal_series(df, kind, look, win).shift(1)   # bar before entry
            per[sym] = s
        # merge_asof, not reindex: the feed is 5-minute and the entries are on
        # 15m-4h bars, so each entry takes the most recent reading at or before
        # it, and never a later one. `tolerance` stops a stale reading from a
        # feed outage being carried hours forward into a trade.
        vals = []
        for sym, g in tr.groupby("symbol"):
            g = g.sort_values("entry_ts")
            feed = per[sym].dropna().rename("sig").reset_index()
            feed.columns = ["ts", "sig"]
            m = pd.merge_asof(g[["entry_ts"]].reset_index(), feed,
                              left_on="entry_ts", right_on="ts",
                              direction="backward",
                              tolerance=pd.Timedelta("1h"))
            vals.append(pd.Series(m.sig.values, index=m["index"].values))
        tr["sig"] = pd.concat(vals).sort_index()
        d = tr.dropna(subset=["sig"]).copy()
        if len(d) < 500:
            continue
        span = max((d.entry_ts.max() - d.entry_ts.min()).days, 1)
        # The signal is ALREADY point in time: `crowd_z` is a rolling z-score
        # against a shifted baseline, and `dcrowd` is a change. Re-normalising
        # either against the whole sample would put hindsight about the
        # distribution into the cut, which is the mistake stage 1 was allowed to
        # make and a backtest is not. So the raw signal is used, and `dcrowd` is
        # divided by its own trailing standard deviation to put the two on a
        # comparable scale without looking forward.
        if kind == "dcrowd":
            sd = (d.groupby("symbol").sig
                   .transform(lambda x: x.expanding(500).std().shift(1)))
            d["sz"] = d.sig / sd
        else:
            d["sz"] = d.sig
        d = d.dropna(subset=["sz"])
        base = report(f"{kind}/{look}/{win} — all trades", d.r.values, span)
        for thr in (0.0, 0.5, 1.0):
            # fade: keep longs when the crowd got shorter, shorts when it got longer
            agree = ((d.direction > 0) & (d.sz <= -thr)) | \
                    ((d.direction < 0) & (d.sz >= thr))
            against = ((d.direction > 0) & (d.sz >= thr)) | \
                      ((d.direction < 0) & (d.sz <= -thr))
            out.append({**base, "signal": kind, "thr": thr, "cut": "baseline"})
            out.append({**report(f"{kind}/{look}/{win} — crowd agrees (fade)",
                                 d.r.values[agree.values], span),
                        "signal": kind, "thr": thr, "cut": "fade"})
            out.append({**report(f"{kind}/{look}/{win} — inverted (control)",
                                 d.r.values[against.values], span),
                        "signal": kind, "thr": thr, "cut": "control"})
    res = pd.DataFrame(out).drop_duplicates()
    res.to_csv(OUT / "stage5_vwap_lift.csv", index=False)
    cols = ["signal", "thr", "cut", "trades", "pf", "total_r", "maxdd_r",
            "ret_over_dd", "r_per_day", "win_rate"]
    print("\n" + "=" * 92)
    print("H-002 TRADES, FILTERED BY THE CROWD FEED")
    print("H-002's own book: return/drawdown 26.4 is the number to beat")
    print("=" * 92)
    print(res[cols].to_string(index=False))


if __name__ == "__main__":
    main()
