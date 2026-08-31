"""ORB stage 7 — the same grid on Gold and FX, last 3 years.

BTC has no opening auction, which is the main reason the ORB mechanism should
not transfer to it. Gold and the FX majors DO have real session opens, so this
is where the hypothesis deserves its best shot. BTC is re-run on the identical
3-year window so the comparison is like for like.

Costs are per side and are assumptions, so everything is reported at 0x / 1x /
2x / 3x as usual:
  BTCUSDT perp  5.0 bps taker + 2.0 slippage
  XAUUSD        0.5 half-spread + 0.5 commission + 0.5 slippage
  EURUSD        0.1 half-spread + 0.35 commission + 0.3 slippage
  GBPUSD        0.15 half-spread + 0.35 commission + 0.3 slippage
FX and metals are far cheaper than crypto relative to their volatility, which is
exactly the thing that killed ORB on BTC.
"""
from __future__ import annotations

import sys, time
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from core import data as crypto_data                 # noqa: E402
from core import fx_data                             # noqa: E402
from strategies.orb.sweep import sweep, features     # noqa: E402
from strategies.orb.deep_test import build_grid, OUT # noqa: E402

START, END = "2023-09-01", "2026-09-01"

# symbol -> (fee_bps_per_side, slip_bps_per_side, min_risk_bps)
# min_risk_bps rejects a stop sitting inside the noise; it has to scale with the
# instrument or FX setups get silently thrown away.
ASSETS = {
    "BTCUSDT": (5.0, 2.0, 10.0),
    "XAUUSD":  (1.0, 0.5, 3.0),
    "EURUSD":  (0.45, 0.3, 2.0),
    "GBPUSD":  (0.50, 0.3, 2.0),
}


def load(sym: str) -> pd.DataFrame:
    if sym == "BTCUSDT":
        df = crypto_data.load("BTC/USDT", "15m")
    else:
        df = fx_data.load(sym)
    return df[(df.index >= START) & (df.index < END)]


def main():
    cfgs = build_grid()
    frames = []
    for sym, (fee, slip, minrisk) in ASSETS.items():
        try:
            df = load(sym)
        except FileNotFoundError as e:
            print(f"SKIP {sym}: {e}", flush=True)
            continue
        for c in cfgs:
            c["min_risk_bps"] = minrisk
        feats = features(df)
        sessions = len(df.resample("1D").first().dropna())
        print(f"{sym}: {len(df)} bars, ~{sessions} days, "
              f"{df.index[0].date()} -> {df.index[-1].date()}", flush=True)
        for mult in (0.0, 1.0, 2.0, 3.0):
            t = time.time()
            r = sweep(df, cfgs, fee_bps=fee * mult, slip_bps=slip * mult,
                      label=f"{sym}_cost{mult:g}x", feats=feats)
            r["symbol"], r["cost_mult"] = sym, mult
            frames.append(r)
            print(f"  {sym} cost {mult:g}x  {time.time()-t:.0f}s", flush=True)

    out = pd.concat(frames, ignore_index=True)
    out.to_csv(OUT / "stage7_assets.csv", index=False)
    print("saved stage7_assets.csv", len(out), "rows")


if __name__ == "__main__":
    main()
