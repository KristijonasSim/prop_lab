"""Where does the edge go between the signal and the trade?

The response study found ~49bps of gross mean reversion in BTC's extreme VWAP-z
deciles against a 9bps round trip - and the strategy that trades those bands
earns +0.012R per trade. Something between the two is destroying it. This
isolates each candidate, one at a time, on the same bars.

The trade is stripped to nothing: enter when |z| crosses a threshold, hold a
fixed number of bars, exit. NO STOP, no target, no session logic. Then each
piece the real kernel adds is put back and the cost of it measured.

That order matters. Adding machinery to a signal and reading the result tells you
nothing about which piece did what; removing machinery from a working trade tells
you exactly.

Run: .venv/bin/python strategies/vwap/research/tails.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from core.markets import COSTS, EXEC_MODE, load                     # noqa: E402
from core.nulls import null_seed, shuffle_market_paired             # noqa: E402
from core.run_hypothesis import YEARS, window                       # noqa: E402
from strategies.vwap.sweep import vwap_series                       # noqa: E402

ANCHOR = (0, 0)
THRESHOLDS = (1.0, 1.5, 2.0, 2.5, 3.0)
HOLDS = (1, 2, 4, 8, 12)


def zscore(df: pd.DataFrame, anchor=ANCHOR) -> np.ndarray:
    vwap, vwstd, _ = vwap_series(df, *anchor)
    c = df.close.values
    with np.errstate(invalid="ignore", divide="ignore"):
        return (c - vwap) / np.where(vwstd > vwap * 1e-6, vwstd, np.nan)


def fade(df: pd.DataFrame, thr: float, hold: int, cost_bps: float,
         stop_sigma: float | None = None, follow: bool = False) -> dict:
    """Trade the stretch. `follow=False` fades it, `follow=True` goes with it.

    BOTH DIRECTIONS MATTER AND THE NAME OF THE HYPOTHESIS IS MISLEADING. The
    decile response says mean reversion - a negative IC, high z preceding lower
    forward returns - but the blind walk-forward chooses MODE_BREAK in 100 of 140
    folds and MODE_FADE in 4. What is on the board is a BREAKOUT, and testing
    only the fade would have measured the wrong strategy.

    Entry on the NEXT bar's open after the signal bar closes, exactly as the
    kernel does. One position at a time - `i` jumps past the exit - so the same
    stretch is not entered on every bar of it.
    """
    o, h, l, c = (df.open.values, df.high.values,
                  df.low.values, df.close.values)
    live = df.volume.values > 0
    z = zscore(df)
    vwap, vwstd, _ = vwap_series(df, *ANCHOR)
    n = len(c)

    rs, i = [], 1
    while i < n - 1:
        if not (np.isfinite(z[i]) and live[i] and live[i + 1]):
            i += 1
            continue
        side = -1 if z[i] >= thr else (1 if z[i] <= -thr else 0)
        if follow:
            side = -side
        if side == 0:
            i += 1
            continue
        e = i + 1
        entry = o[e]
        j = min(e + hold, n - 1)
        # risk is the sigma the band is measured in, so R means the same thing
        # at every threshold and across markets
        risk = max(vwstd[i], entry * 1e-4)
        exit_px, exit_i = c[j], j
        if stop_sigma is not None:
            stop = entry + side * -1 * stop_sigma * risk
            k = e
            while k <= j:
                if live[k]:
                    if side == 1 and l[k] <= stop:
                        exit_px, exit_i = min(stop, o[k]), k
                        break
                    if side == -1 and h[k] >= stop:
                        exit_px, exit_i = max(stop, o[k]), k
                        break
                k += 1
        gross = (exit_px - entry) * side
        fees = (entry + exit_px) * cost_bps / 2 / 1e4
        rs.append((gross - fees) / risk)
        i = exit_i if exit_i > i else i + 1

    r = np.array(rs)
    if len(r) < 30:
        return {"n": len(r)}
    w, lo = r[r > 0].sum(), -r[r < 0].sum()
    return {"n": len(r), "avg_r": round(float(r.mean()), 4),
            "pf": round(float(w / lo), 3) if lo > 0 else np.inf,
            "win": round(float((r > 0).mean()) * 100, 1),
            "total_r": round(float(r.sum()), 1)}


def main() -> int:
    markets = [("BTCUSDT", "4h"), ("ETHUSDT", "4h"), ("XAUUSD", "4h"),
               ("XAUUSD", "1h")]
    lo, hi = window([m for m, _ in markets], ["1h", "4h"], YEARS)
    print(f"window {lo.date()} -> {hi.date()}   fade |z| >= threshold, fixed "
          f"hold, NO STOP, entry at next open\n")

    rows = []
    for sym, tf in markets:
        df = load(sym, tf)
        df = df[(df.index >= lo) & (df.index <= hi)]
        rt = COSTS[sym].round_trip(EXEC_MODE)
        nulldf = shuffle_market_paired(df, null_seed(sym, tf, "tails"))
        print(f"{'=' * 92}\n{sym} {tf}   round trip {rt:.2f}bps\n{'=' * 92}")
        print(f"{'dir':>6} {'thr':>5} {'hold':>5} {'n':>6} {'avg R':>8} "
              f"{'PF':>7} {'win%':>6} {'total R':>9}   {'null PF':>8}")
        for thr in THRESHOLDS:
            for hold in HOLDS:
                for follow in (False, True):
                    a = fade(df, thr, hold, rt, follow=follow)
                    if a.get("n", 0) < 30:
                        continue
                    b = fade(nulldf, thr, hold, rt, follow=follow)
                    tag = "follow" if follow else "fade  "
                    print(f"{tag} {thr:>5.1f} {hold:>5} {a['n']:>6} "
                          f"{a['avg_r']:>+8.4f} {a['pf']:>7.3f} {a['win']:>6.1f} "
                          f"{a['total_r']:>+9.1f}   {b.get('pf', float('nan')):>8}")
                    rows.append(dict(sym=sym, tf=tf, dirn=tag.strip(), thr=thr,
                                     hold=hold, **a, null_pf=b.get("pf")))
        print()

    d = pd.DataFrame(rows)
    out = ROOT / "backtests" / "vwap" / "research_tails.csv"
    d.to_csv(out, index=False)
    good = d[(d.pf > 1.2) & (d.null_pf.notna()) & (d.pf > d.null_pf) & (d.n >= 100)]
    print(f"{'=' * 92}\ncells with PF > 1.20 that also beat their own null: "
          f"{len(good)} of {len(d)}\n{'=' * 92}")
    if len(good):
        print(good.sort_values("pf", ascending=False).head(12).to_string(index=False))
    print(f"\nwrote {out.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
