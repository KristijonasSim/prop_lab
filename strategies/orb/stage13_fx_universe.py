"""ORB stage 13 — is it an FX effect, or was GBPUSD one lucky pair?

GBPUSD produced the only configuration in the whole study to clear PF 1.20 with
a sane win rate. One pair out of four proves nothing either way: with an
8,160-way search per market, somebody has to come first. The test is whether the
effect shows up across a universe of pairs.

Reported per pair: how many configurations clear the gate, the best and median,
what the best one costs at 2x, and what the top 10 by fit profit factor do on a
year they were not chosen on.
"""
from __future__ import annotations

import sys, time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from core import fx_data                                    # noqa: E402
from strategies.orb.sweep import sweep, features            # noqa: E402
from strategies.orb.deep_test import build_grid, OUT        # noqa: E402

START, END, SPLIT = "2023-09-01", "2026-09-01", "2025-09-01"

# symbol -> (fee bps/side, slippage bps/side, min_risk_bps)
# Spreads are typical ECN/institutional. A prop firm is routinely 4-6x wider,
# which is what the 2x and 3x columns are for.
UNIVERSE = {
    "EURUSD": (0.45, 0.30, 2.0),
    "GBPUSD": (0.50, 0.30, 2.0),
    "USDJPY": (0.45, 0.30, 2.0),
    "AUDUSD": (0.60, 0.35, 2.0),
    "USDCAD": (0.65, 0.35, 2.0),
    "USDCHF": (0.70, 0.35, 2.0),
    "NZDUSD": (0.85, 0.45, 2.5),
    "EURGBP": (0.80, 0.40, 2.0),
    "EURJPY": (0.70, 0.35, 2.0),
    "GBPJPY": (0.95, 0.50, 2.5),
    "AUDJPY": (0.85, 0.45, 2.5),
    "XAUUSD": (1.00, 0.50, 3.0),
    "XAGUSD": (2.50, 1.00, 4.0),
}

KEYS = ["hour", "or_bars", "hold_bars", "entry_mode", "stop_mode",
        "stop_atr_mult", "rr", "fade"]


def main():
    cfgs = build_grid()
    rows, raw = [], []
    for sym, (fee, slip, minrisk) in UNIVERSE.items():
        try:
            df = fx_data.load(sym)
        except FileNotFoundError:
            print(f"SKIP {sym} (no data yet)", flush=True)
            continue
        df = df[(df.index >= START) & (df.index < END)]
        if len(df) < 20000:
            print(f"SKIP {sym} (only {len(df)} bars)", flush=True)
            continue
        for c in cfgs:
            c["min_risk_bps"] = minrisk

        t = time.time()
        feats = features(df)
        full1 = sweep(df, cfgs, fee_bps=fee, slip_bps=slip, feats=feats)
        full2 = sweep(df, cfgs, fee_bps=fee * 2, slip_bps=slip * 2, feats=feats)
        is_df, oos_df = df[df.index < SPLIT], df[df.index >= SPLIT]
        a = sweep(is_df, cfgs, fee_bps=fee, slip_bps=slip, feats=features(is_df))
        b = sweep(oos_df, cfgs, fee_bps=fee, slip_bps=slip, feats=features(oos_df))

        k1 = full1[full1.trades >= 100]
        k2 = full2[full2.trades >= 100]
        if not len(k1):
            continue
        best = k1.loc[k1.pf.idxmax()]
        same2 = k2.copy()
        for kk in KEYS:
            same2 = same2[same2[kk] == best[kk]]
        pf2 = float(same2.pf.iloc[0]) if len(same2) else np.nan

        m = a[KEYS + ["pf", "trades"]].merge(b[KEYS + ["pf", "trades"]], on=KEYS,
                                             suffixes=("_is", "_oos"))
        m = m[(m.trades_is >= 60) & (m.trades_oos >= 25)]
        top10 = m.nlargest(10, "pf_is") if len(m) else None

        rows.append({
            "symbol": sym,
            "configs": int(len(k1)),
            "gate_1x": int((k1.pf >= 1.2).sum()),
            "gate_2x": int((k2.pf >= 1.2).sum()) if len(k2) else 0,
            "be_1x": int((k1.pf >= 1.0).sum()),
            "best_pf": round(float(k1.pf.max()), 3),
            "median_pf": round(float(k1.pf.median()), 3),
            "best_pf_at_2x": round(pf2, 3) if pf2 == pf2 else None,
            "best_tpd": round(float(best.trades_per_day), 2),
            "best_win": round(float(best.win_rate), 3),
            "best_dd": round(float(best.max_dd), 3),
            "best_resolve": (round(float(best.days_to_target), 0)
                             if np.isfinite(best.days_to_target) else None),
            "top10_is": round(float(top10.pf_is.median()), 3) if top10 is not None else None,
            "top10_oos": round(float(top10.pf_oos.median()), 3) if top10 is not None else None,
            "top10_kept": int((top10.pf_oos >= 1.0).sum()) if top10 is not None else None,
        })
        full1["symbol"] = sym
        raw.append(full1[KEYS + ["symbol", "pf", "trades", "win_rate", "avg_r",
                                 "trades_per_day", "max_dd", "days_to_target"]].copy())
        print(f"{sym}: gate1x {rows[-1]['gate_1x']:4d}  best {rows[-1]['best_pf']:.3f} "
              f"(2x {rows[-1]['best_pf_at_2x']})  median {rows[-1]['median_pf']:.3f}  "
              f"[{time.time()-t:.0f}s]", flush=True)

    out = pd.DataFrame(rows)
    out.to_csv(OUT / "stage13_fx_universe.csv", index=False)
    pd.concat(raw, ignore_index=True).to_csv(OUT / "stage13_fx_raw.csv", index=False)
    print("\nsaved stage13_fx_universe.csv")
    print(out.to_string(index=False))


if __name__ == "__main__":
    main()
