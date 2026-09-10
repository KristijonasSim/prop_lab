"""The crypto spread, estimated from bars, and CALIBRATED where it is known.

The cost investigation (`why.py`, section 2 of RESEARCH_2026-09-10_WHY.md) ended
on one unmeasured number: crypto's half-spread in `core/markets.py` is ASSUMED at
2bps, the file says so itself, and it is what makes BTC's sigma/cost the worst in
the universe. Binance's `bookTicker` archive stopped in 2024-03, so the direct
measurement is not available from disk.

IT DOES NOT HAVE TO BE. Corwin & Schultz (2012) estimate the effective spread
from HIGH and LOW prices alone: over two consecutive bars, the high-low range
reflects both volatility and the spread, and volatility scales with time while
the spread does not. The difference identifies the spread.

    beta  = E[ ln(H/L)^2 over bar t  +  ln(H/L)^2 over bar t+1 ]
    gamma = ln(H2/L2)^2 over the two bars combined
    alpha = (sqrt(2 beta) - sqrt(beta)) / (3 - 2 sqrt 2)
            - sqrt(gamma / (3 - 2 sqrt 2))
    S     = 2 (e^alpha - 1) / (1 + e^alpha)

WHY THIS IS NOT JUST ANOTHER ASSUMPTION: it is CALIBRATED. Four markets in this
repo have a MEASURED spread from Dukascopy ticks - XAUUSD 1.671bps, EURUSD 0.190,
GBPUSD 0.515, XAGUSD 9.108. The estimator is run on those four first. Whatever
bias it shows there is what its crypto number should be read with; if it cannot
reproduce a spread that IS known, its estimate of an unknown one is worth nothing
and this file says so rather than quoting it.

Negative alphas are set to zero before averaging, which is the standard treatment
and biases the estimate UP on quiet markets. Only consecutive live bars are used -
no weekend pads, no session gaps - because the estimator assumes continuous
trading between the two bars.

Run: .venv/bin/python strategies/vwapbreak/research/spread.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from core.markets import COSTS, load                               # noqa: E402

K = 3.0 - 2.0 * np.sqrt(2.0)

#: spread MEASURED from Dukascopy ticks, bps round trip (core/fx_spread.py),
#: quoted in core/markets.py. The calibration set.
MEASURED = {"XAUUSD": 1.671, "EURUSD": 0.190, "GBPUSD": 0.515, "XAGUSD": 9.108}
TF = "5m"
CRYPTO = ("BTCUSDT", "ETHUSDT", "SOLUSDT")


def corwin_schultz(df: pd.DataFrame) -> tuple[float, int]:
    """Effective spread in bps, from consecutive live bars only."""
    h, l = df.high.values, df.low.values
    live = df.volume.values > 0
    ok = live[:-1] & live[1:] & (l[:-1] > 0) & (l[1:] > 0)
    h1, l1, h2, l2 = h[:-1][ok], l[:-1][ok], h[1:][ok], l[1:][ok]
    if len(h1) < 500:
        return float("nan"), 0
    beta = np.log(h1 / l1) ** 2 + np.log(h2 / l2) ** 2
    hi2 = np.maximum(h1, h2)
    lo2 = np.minimum(l1, l2)
    gamma = np.log(hi2 / lo2) ** 2
    alpha = (np.sqrt(2 * beta) - np.sqrt(beta)) / K - np.sqrt(gamma / K)
    alpha = np.where(np.isfinite(alpha), alpha, 0.0)
    alpha = np.maximum(alpha, 0.0)          # standard treatment
    s = 2 * (np.exp(alpha) - 1) / (1 + np.exp(alpha))
    return float(np.mean(s) * 1e4), int(len(s))


def main() -> int:
    print("CALIBRATION - markets whose spread is measured from ticks\n")
    print(f"{'market':9}{'bars':>9}{'estimated':>11}{'measured':>10}{'ratio':>8}")
    ratios, rows = [], []
    for sym, meas in MEASURED.items():
        df = load(sym, TF)
        est, n = corwin_schultz(df)
        ratios.append(est / meas)
        rows.append({"sym": sym, "est_bps": round(est, 3), "measured_bps": meas,
                     "ratio": round(est / meas, 2), "bars": n, "set": "calibration"})
        print(f"{sym:9}{n:9}{est:11.3f}{meas:10.3f}{est / meas:8.2f}")
    bias = float(np.median(ratios))
    print(f"\nmedian estimator/measured ratio: {bias:.2f}"
          f"   (1.00 would be unbiased)")

    print("\nCRYPTO - the number that has never been measured\n")
    print(f"{'market':9}{'bars':>9}{'estimated':>11}{'debiased':>10}"
          f"{'assumed in repo':>17}")
    for sym in CRYPTO:
        df = load(sym, TF)
        if df.empty:                      # the crypto cache is 15m-based
            df = load(sym, "15m")
        est, n = corwin_schultz(df)
        deb = est / bias
        assumed = COSTS[sym].half_spread * 2
        rows.append({"sym": sym, "est_bps": round(est, 3),
                     "debiased_bps": round(deb, 3), "assumed_bps": assumed,
                     "bars": n, "set": "crypto"})
        print(f"{sym:9}{n:9}{est:11.3f}{deb:10.3f}{assumed:17.3f}")

    dest = ROOT / "backtests" / "vwapbreak" / "spread.json"
    dest.write_text(json.dumps({"bias": round(bias, 3), "tf": TF, "rows": rows},
                               indent=1, default=str))
    print(f"\nwrote {dest.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
