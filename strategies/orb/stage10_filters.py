"""ORB stage 10 — do any of the usual filters actually help?

The honest way to score a filter is a PAIRED test: run the identical family of
configurations with the filter off and on, and look at how the whole
distribution moves. A filter that only raises the maximum has done nothing but
make the sample smaller and the luck bigger. A filter that is really finding
something moves the MEDIAN and keeps most of the trades.

Reported per filter: median change in profit factor, share of configurations
improved, and the share of trades it throws away to get there.
"""
from __future__ import annotations

import sys, time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from strategies.orb.sweep import sweep, features, DEFAULTS      # noqa: E402
from strategies.orb.deep_test import OUT                        # noqa: E402
from strategies.orb.stage7_assets import ASSETS, load           # noqa: E402
from strategies.orb.stage9_anchors import base_grid             # noqa: E402

# The anchors with a real mechanism behind them, not the data-mined winners.
ANCHORS = [(8, 0), (13, 30), (14, 30), (0, 0)]

FILTERS = {
    "none": {},
    # entry mechanics
    "retest, 4 bars":            {"entry_mode": 3, "retest_bars": 4},
    "retest, 8 bars":            {"entry_mode": 3, "retest_bars": 8},
    "retest, 16 bars":           {"entry_mode": 3, "retest_bars": 16},
    "entry window 4 bars":       {"max_entry_bars": 4},
    "entry window 8 bars":       {"max_entry_bars": 8},
    "entry window 16 bars":      {"max_entry_bars": 16},
    # stop management
    "breakeven at 0.5R":         {"be_at_r": 0.5},
    "breakeven at 1.0R":         {"be_at_r": 1.0},
    "breakeven at 1.5R":         {"be_at_r": 1.5},
    # participation
    "opening-range rvol > 1.2":  {"min_rvol": 1.2},
    "opening-range rvol > 1.5":  {"min_rvol": 1.5},
    "opening-range rvol > 2.0":  {"min_rvol": 2.0},
    "breakout-bar rvol > 1.2":   {"min_break_rvol": 1.2},
    "breakout-bar rvol > 1.5":   {"min_break_rvol": 1.5},
    "breakout-bar rvol > 2.0":   {"min_break_rvol": 2.0},
    # volatility regime
    "ATR rank > 0.5":            {"min_atr_rank": 0.5},
    "ATR rank > 0.7":            {"min_atr_rank": 0.7},
    "ATR rank < 0.5":            {"max_atr_rank": 0.5},
    "ATR rank < 0.3":            {"max_atr_rank": 0.3},
    # range shape
    "range > 0.5x ATR":          {"min_or_atr": 0.5},
    "range > 1.0x ATR":          {"min_or_atr": 1.0},
    "range < 1.5x ATR":          {"max_or_atr": 1.5},
    "range < 1.0x ATR":          {"max_or_atr": 1.0},
    # trend
    "with 200-EMA":              {"trend_mode": 1},
    "against 200-EMA":           {"trend_mode": 2},
    "with 20-EMA":               {"fast_trend_mode": 1},
    "against 20-EMA":            {"fast_trend_mode": 2},
    "with 5-day trend":          {"dtrend_mode": 1},
    "against 5-day trend":       {"dtrend_mode": 2},
}

MIN_TRADES = 60


def main():
    KEEP = ["symbol", "filter", "cfg_id", "pf", "trades", "win_rate",
            "trades_per_day", "avg_hold_h", "avg_r", "max_dd", "days_to_target"]
    frames = []
    for sym, (fee, slip, minrisk) in ASSETS.items():
        df = load(sym)
        feats = features(df)
        cfgs = []
        for h, m in ANCHORS:
            cfgs += base_grid(h, m)
        for c in cfgs:
            c["min_risk_bps"] = minrisk
        print(f"{sym}: {len(cfgs)} base configs x {len(FILTERS)} filters", flush=True)

        for name, over in FILTERS.items():
            variant = []
            for c in cfgs:
                v = dict(c)
                v.update(over)
                variant.append(v)
            t = time.time()
            r = sweep(df, variant, fee_bps=fee, slip_bps=slip, feats=feats)
            r["symbol"], r["filter"] = sym, name
            r["cfg_id"] = range(len(r))
            frames.append(r[KEEP].copy())      # keep the sweep frames out of memory
            del r
        print(f"  {sym} done, {time.time()-t:.0f}s on the last filter", flush=True)

    allr = pd.concat(frames, ignore_index=True)
    allr.to_csv(OUT / "stage10_filters_raw.csv", index=False)

    # ---- paired lift ----
    base = allr[allr["filter"] == "none"][["symbol", "cfg_id", "pf", "trades"]]
    base = base.rename(columns={"pf": "pf_base", "trades": "trades_base"})
    rows = []
    for name in FILTERS:
        if name == "none":
            continue
        v = allr[allr["filter"] == name][["symbol", "cfg_id", "pf", "trades",
                                          "win_rate", "trades_per_day"]]
        m = v.merge(base, on=["symbol", "cfg_id"])
        m = m[(m.trades >= MIN_TRADES) & (m.trades_base >= MIN_TRADES)]
        if len(m) < 20:
            continue
        for sym in list(ASSETS) + ["ALL"]:
            k = m if sym == "ALL" else m[m.symbol == sym]
            if len(k) < 20:
                continue
            d = k.pf - k.pf_base
            rows.append({
                "filter": name, "symbol": sym, "configs": int(len(k)),
                "median_pf_base": round(float(k.pf_base.median()), 3),
                "median_pf_filtered": round(float(k.pf.median()), 3),
                "median_lift": round(float(d.median()), 4),
                "share_improved": round(float((d > 0).mean()), 3),
                "trades_kept": round(float((k.trades / k.trades_base).median()), 3),
                "best_pf": round(float(k.pf.max()), 3),
                "median_tpd": round(float(k.trades_per_day.median()), 3),
            })
    out = pd.DataFrame(rows).sort_values(["symbol", "median_lift"], ascending=[True, False])
    out.to_csv(OUT / "stage10_filter_lift.csv", index=False)
    print("saved stage10_filter_lift.csv", len(out), "rows")
    print(out[out.symbol == "ALL"].head(15).to_string(index=False))


if __name__ == "__main__":
    main()
