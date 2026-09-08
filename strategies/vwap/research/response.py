"""Does the VWAP band signal predict anything at all, before any strategy?

THE KILLER TEST THIS REPO USES FIRST, and the one that should have been run
before H-002 ever had a board entry. H-008 died on it: the z-response was FLAT -
profit factor before costs ran 1.000 / 0.997 / 1.006 / 1.013 as entry went 1.5 to
3.0 sigma, so the size of a deviation said nothing about what followed, and there
was no mechanism left to repair.

Method, deliberately stripped of everything a strategy adds:

  * z = (close - vwap) / vwstd, on a CLOSED bar;
  * bucket z, and measure the forward return over the next N bars;
  * report in BASIS POINTS, gross, so it can be compared with the round trip;
  * non-overlapping samples, so 3,000 bars do not become 3,000 correlated draws.

What a real edge looks like: forward return MONOTONE in z, and the extreme
buckets big enough to pay the round trip. What noise looks like: a flat or
non-monotone table, or a monotone one whose spread is under the cost.

Run: .venv/bin/python strategies/vwap/research/response.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from core.markets import COSTS, EXEC_MODE, TF_BPH, load             # noqa: E402
from core.nulls import null_seed, shuffle_market_paired             # noqa: E402
from core.run_hypothesis import YEARS, window                       # noqa: E402
from strategies.vwap.sweep import vwap_series                       # noqa: E402

#: DECILES, not fixed z edges. The first version of this used fixed edges and
#: the extreme buckets held 7 to 29 samples, so "top bucket minus bottom bucket"
#: was measuring tail noise - and the phase-randomised null produced spreads just
#: as large, which is how it was caught. Equal-count buckets give every point on
#: the response the same standard error.
N_BUCKETS = 10
#: forward horizons in BARS
HORIZONS = (1, 2, 4, 8, 24)
ANCHOR = (0, 0)          # UTC-day anchored VWAP, the plainest form


def response(df: pd.DataFrame, horizon: int, anchor=ANCHOR) -> tuple:
    """(decile table, information coefficient) for z against forward return.

    The IC is Spearman: does a HIGHER z systematically precede a higher forward
    return? It is the whole question, it uses every observation rather than two
    tails, and it is the statistic H-006 and H-013 were judged on.
    """
    vwap, vwstd, _ = vwap_series(df, *anchor)
    c = df.close.values
    live = df.volume.values > 0
    with np.errstate(invalid="ignore", divide="ignore"):
        z = (c - vwap) / np.where(vwstd > vwap * 1e-6, vwstd, np.nan)

    n = len(c)
    idx = np.arange(0, n - horizon, horizon)          # non-overlapping
    idx = idx[live[idx] & live[idx + horizon]]
    zz = z[idx]
    fwd = (c[idx + horizon] / c[idx] - 1.0) * 1e4     # bps
    ok = np.isfinite(zz) & np.isfinite(fwd)
    zz, fwd = zz[ok], fwd[ok]
    if len(zz) < N_BUCKETS * 20:
        return pd.DataFrame(), float("nan")

    d = pd.DataFrame({"z": zz, "fwd": fwd})
    d["b"] = pd.qcut(d.z, N_BUCKETS, labels=False, duplicates="drop")
    tab = d.groupby("b").agg(n=("fwd", "size"), z_mid=("z", "mean"),
                             mean_bps=("fwd", "mean")).round(2)
    ic = float(d.z.corr(d.fwd, method="spearman"))
    return tab, ic


def spread(tab) -> float:
    """Top decile minus bottom decile, in bps."""
    if not len(tab):
        return float("nan")
    return float(tab.mean_bps.iloc[-1] - tab.mean_bps.iloc[0])


def main() -> int:
    markets = [("XAUUSD", "1h"), ("XAUUSD", "4h"),
               ("ETHUSDT", "4h"), ("BTCUSDT", "4h"),
               ("USDJPY", "1h"), ("EURUSD", "1h")]
    lo, hi = window([m for m, _ in markets], ["1h", "4h"], YEARS)
    print(f"window {lo.date()} -> {hi.date()}   z = (close - vwap) / vwstd, "
          f"UTC-day anchor, deciles, non-overlapping\n")

    N_SEEDS = 3
    rows = []
    for sym, tf in markets:
        df = load(sym, tf)
        df = df[(df.index >= lo) & (df.index <= hi)]
        rt = COSTS[sym].round_trip(EXEC_MODE)
        print(f"{'=' * 96}\n{sym} {tf}   round trip {rt:.2f}bps   {len(df):,} bars\n{'=' * 96}")
        best = None
        for h in HORIZONS:
            tab, ic = response(df, h)
            if not len(tab):
                continue
            nul = []
            for s_ in range(N_SEEDS):
                _, nic = response(shuffle_market_paired(
                    df, null_seed(sym, tf, f"resp{s_}")), h)
                nul.append(abs(nic))
            beat = abs(ic) > max(nul)
            print(f"  horizon {h:>2} bars  n={int(tab.n.sum()):>6}  "
                  f"IC {ic:+.4f}   |null| best {max(nul):.4f}   "
                  f"decile spread {spread(tab):>8.2f}bps   "
                  f"{'BEATS null' if beat else 'lost to null'}")
            if best is None or abs(ic) > abs(best[1]):
                best = (h, ic, tab, max(nul), beat)
        if best is None:
            print("  not enough data\n")
            continue
        h, ic, tab, nb, beat = best
        print(f"\n  decile response at {h} bars (strongest IC):")
        print("   " + tab.to_string().replace("\n", "\n   "))
        mono = tab.mean_bps.is_monotonic_increasing or tab.mean_bps.is_monotonic_decreasing
        print(f"\n  monotone across deciles: {mono}   "
              f"IC {ic:+.4f} vs best null {nb:.4f}\n")
        rows.append(dict(sym=sym, tf=tf, horizon=h, ic=round(ic, 4),
                         null_ic=round(nb, 4), beats_null=beat,
                         decile_spread_bps=round(spread(tab), 2),
                         cost_bps=round(rt, 2), monotone=mono))

    d = pd.DataFrame(rows)
    print(f"{'=' * 96}\nSUMMARY\n{'=' * 96}")
    print(d.to_string(index=False))
    print("\nIC is Spearman rank correlation between z and the forward return.")
    print("A real signal is monotone across deciles AND beats its own null.")
    out = ROOT / "backtests" / "vwap" / "research_response.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    d.to_csv(out, index=False)
    print(f"\nwrote {out.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
