"""ORB stage 11 — stack the filters that actually lifted the median.

Stage 10 scored 29 filters as paired lifts. Three moved the median without
gutting the sample: breakout-bar relative volume, a high-volatility regime, and
taking the trade AGAINST the 20-bar EMA. This stage stacks them on the two
anchors that the 20-anchor sweep says carry the most (the NY futures and cash
opens), and then splits the window so the combination has to survive a year it
was not chosen on.
"""
from __future__ import annotations

import itertools, sys, time
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from strategies.orb.sweep import sweep, features                # noqa: E402
from strategies.orb.deep_test import OUT                        # noqa: E402
from strategies.orb.stage7_assets import ASSETS, load           # noqa: E402
from strategies.orb.stage9_anchors import base_grid             # noqa: E402

SPLIT = "2025-09-01"
ANCHORS = [(13, 0), (13, 30)]

AXES = {
    "break_rvol": [{}, {"min_break_rvol": 1.5}, {"min_break_rvol": 2.0}],
    "regime":     [{}, {"min_atr_rank": 0.5}, {"min_atr_rank": 0.7}],
    "counter20":  [{}, {"fast_trend_mode": 2}],
}
KEYS = ["hour", "minute", "or_bars", "hold_bars", "entry_mode", "stop_mode",
        "stop_atr_mult", "rr", "fade", "min_break_rvol", "min_atr_rank",
        "fast_trend_mode"]


def combos():
    out = []
    for pick in itertools.product(*AXES.values()):
        merged = {}
        for p in pick:
            merged.update(p)
        out.append(merged)
    return out


def main():
    frames = []
    for sym, (fee, slip, minrisk) in ASSETS.items():
        df = load(sym)
        cfgs = []
        for h, m in ANCHORS:
            for base in base_grid(h, m):
                for over in combos():
                    c = dict(base)
                    c.update(over)
                    c["min_risk_bps"] = minrisk
                    cfgs.append(c)
        print(f"{sym}: {len(cfgs)} configs", flush=True)
        for name, w in (("IS", df[df.index < SPLIT]), ("OOS", df[df.index >= SPLIT])):
            feats = features(w)
            t = time.time()
            r = sweep(w, cfgs, fee_bps=fee, slip_bps=slip, feats=feats)
            r["symbol"], r["window"] = sym, name
            frames.append(r[KEYS + ["symbol", "window", "pf", "trades", "win_rate",
                                    "avg_r", "trades_per_day", "avg_hold_h", "max_dd",
                                    "sharpe", "days_to_target"]].copy())
            del r
            print(f"  {sym} {name} {time.time()-t:.0f}s", flush=True)

    out = pd.concat(frames, ignore_index=True)
    out.to_csv(OUT / "stage11_combined.csv", index=False)
    print("saved stage11_combined.csv", len(out), "rows", flush=True)

    a = out[out.window == "IS"]
    b = out[out.window == "OOS"]
    m = a.merge(b, on=KEYS + ["symbol"], suffixes=("_is", "_oos"))
    m = m[(m.trades_is >= 60) & (m.trades_oos >= 25)]
    print()
    for sym in ASSETS:
        k = m[m.symbol == sym]
        if not len(k):
            continue
        g = k[k.pf_is >= 1.2]
        print(f"{sym:8s} paired {len(k):5d} | median IS {k.pf_is.median():.3f} "
              f"| best IS {k.pf_is.max():.3f} | clear 1.2 IS {len(g):3d} "
              f"| still clear OOS {int((g.pf_oos >= 1.2).sum()):3d} "
              f"| median OOS of those {g.pf_oos.median() if len(g) else float('nan'):.3f}")


if __name__ == "__main__":
    main()
