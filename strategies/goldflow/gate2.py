"""H-046 gate 2 — does gold's order-flow imbalance pay for the spread?

PRE-REGISTRATION: `PREREG.md`. The bar was fixed before any number: the
top-versus-bottom decile spread must clear **3.66 bps gross**, twice gold's
measured 1.83 bps round trip. No stops, no walk-forward, no selection at this
gate - H-043 introduced this ordering and it has killed three ideas in twenty
minutes each instead of a day.

THE SIGNAL. `imb = (askvol - bidvol) / (askvol + bidvol)` per bar, from the
Dukascopy tick files. Positive means more size on the ask side.

WHAT IT IS. Two-sided quoted size published with each tick, so this is a
LIQUIDITY IMBALANCE, not confirmed aggressor flow - the H-024 family, which was
real, monotone, beat its null and cleared its cost in 0 of 935 cells. That is the
prior. It is also Dukascopy's own liquidity-provider size, not a consolidated
tape; spot gold has no central exchange to check it against.

THE DATA HAS A GAP and it is not hidden: the download was re-pointed mid-run to
fetch the most recent twelve months first, so coverage is 2023-08/09 plus
2025-08 onward, not a continuous window. Both sub-periods are reported
separately - a signal that only works in one of them is not a signal.

Run: .venv/bin/python strategies/goldflow/gate2.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from core.gold_flow import load_flow                               # noqa: E402

BAR_BPS = 3.66                    # 2x gold's measured 1.83 bps round trip
TFS = ("15min", "1h", "4h")
HORIZONS = (1, 2, 4, 8)           # in bars
DECILES = 10


def forward(c: pd.Series, h: int) -> pd.Series:
    """Return over the next h bars, in bps. Shifted so bar i uses only its own close."""
    return (c.shift(-h) / c - 1.0) * 1e4


def decile_response(f: pd.DataFrame, sig: str, h: int) -> dict | None:
    """Mean forward return per signal decile, and the top-minus-bottom spread."""
    d = f[[sig]].copy()
    d["fwd"] = forward(f.close, h)
    d = d.replace([np.inf, -np.inf], np.nan).dropna()
    if len(d) < 200 or d[sig].nunique() < DECILES:
        return None
    try:
        d["bucket"] = pd.qcut(d[sig], DECILES, labels=False, duplicates="drop")
    except ValueError:
        return None
    m = d.groupby("bucket").fwd.mean()
    if len(m) < 3:
        return None
    lo, hi = float(m.iloc[0]), float(m.iloc[-1])
    # monotonicity: Spearman of decile index against its mean return. A real
    # effect orders the deciles; a flat response is H-008's death and is
    # decisive on its own.
    rho = float(pd.Series(m.values).corr(pd.Series(range(len(m))), method="spearman"))
    return {"n": int(len(d)), "lo": round(lo, 2), "hi": round(hi, 2),
            "spread": round(hi - lo, 2), "rho": round(rho, 3),
            "deciles": [round(x, 2) for x in m.values]}


def run(f: pd.DataFrame, tag: str) -> None:
    print(f"\n=== {tag}   {len(f):,} bars   "
          f"{f.index[0].date()} -> {f.index[-1].date()} " + "=" * 20, flush=True)
    hdr = (f"{'signal':10}{'h':>4}{'n':>8}{'botDec':>9}{'topDec':>9}"
           f"{'SPREAD':>9}{'rho':>7}   vs {BAR_BPS} bps")
    print(hdr); print("-" * len(hdr))
    for sig in ("imb", "delta_z"):
        if sig not in f:
            continue
        for h in HORIZONS:
            r = decile_response(f, sig, h)
            if not r:
                continue
            v = "PASS" if abs(r["spread"]) > BAR_BPS else "fail"
            print(f"{sig:10}{h:>4}{r['n']:>8}{r['lo']:>9.2f}{r['hi']:>9.2f}"
                  f"{r['spread']:>9.2f}{r['rho']:>7.3f}   {v}", flush=True)


def prep(tf: str) -> pd.DataFrame:
    f = load_flow("XAUUSD", tf)
    if not len(f):
        return f
    f = f[f.vol > 0].copy()
    # delta normalised by its own trailing scale, so a busy session does not
    # dominate purely by being busy
    s = f.delta.rolling(100, min_periods=30).std()
    f["delta_z"] = (f.delta / s).replace([np.inf, -np.inf], np.nan)
    return f


def main() -> int:
    print(f"H-046 GATE 2 — the fee test. Bar: |spread| > {BAR_BPS} bps gross.")
    print("Signal is a LIQUIDITY imbalance (quoted size), not aggressor flow.")
    for tf in TFS:
        f = prep(tf)
        if not len(f):
            print(f"\n{tf}: no data")
            continue
        run(f, f"XAUUSD {tf}  ALL")
        # the two disjoint download chunks, reported separately
        early = f[f.index < "2024-01-01"]
        late = f[f.index >= "2025-08-01"]
        if len(early) > 400:
            run(early, f"XAUUSD {tf}  2023 chunk")
        if len(late) > 400:
            run(late, f"XAUUSD {tf}  2025-26 chunk")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
