"""H-002 stage 19 — the dead-bar trades the cross-check turned up.

WHERE THIS CAME FROM. `stage17_goldnautilus.py` ran twenty-five configurations
through an independent event-driven engine. Twenty-four agreed with the kernel
on every entry bar. The twenty-fifth — XAUUSD 1h, MODE_TREND, midnight anchor —
matched 87.5% of them, and the first divergence explains the rest:

    2023-09-01 21:00   O=H=L=C 1939.238   volume 0.00000   vwstd 3.692849
    ...
    2023-09-03 00:00   O=H=L=C 1939.238   volume 0.00000   vwstd 0.000000   <- anchor
    2023-09-03 01:00   O=H=L=C 1939.238   volume 0.00000   vwstd 0.000000
    2023-09-03 02:00   O=H=L=C 1939.238   volume 0.00000   vwstd 0.000031   <- trades
    2023-09-03 03:00   O=H=L=C 1939.238   volume 0.00000   vwstd 0.000000

That is the FX weekend. Dukascopy pads the closed market with synthetic bars
carrying zero volume and the last traded price repeated, so a session made
entirely of them has a volume-weighted sigma of exactly zero. `vwstd` is built
as `sqrt(p2v/v - vwap^2)`, a difference of two nearly-equal accumulated sums, so
on those bars it is not zero but **3.1e-5 of floating-point noise** — and the
kernel's only defence is `if sd <= 0.0: skip`, which 3.1e-5 passes.

The streaming port accumulates the same sums in a different order and gets
exactly 0.0 on that bar, so it skips. **Neither is wrong. The kernel is
resolving a trade decision on rounding noise in a market that was closed.**

WHAT THIS ASKS. Not "is the port faithful" — that is settled at 24 of 25. It
asks how much of gold's published edge is booked on bars where nothing traded.
Three cuts, all on the walk-forward output the board is built from:

  1. entries on a bar with **zero volume**;
  2. entries on a bar whose session `vwstd` is below a tolerance, i.e. the
     degenerate-sigma case the divergence found;
  3. what the board's book looks like with those trades removed.

If the share is small the finding is a footnote. If it is not, the gold number
is partly an artefact of a data vendor's weekend padding.

Run: .venv/bin/python strategies/vwap/stage19_deadbars.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from strategies.vwap.stage3_timeframes import load_tf                # noqa: E402

BT = ROOT / "backtests" / "vwap"
SYM = "XAUUSD"
TFS = ("5m", "15m", "30m", "1h", "4h")
SD_EPS = 1e-3          # a volume-weighted sigma below this is degenerate


def pf(r) -> float:
    r = np.asarray(r)
    w, l = r[r > 0].sum(), -r[r < 0].sum()
    return float(w / l) if l > 0 else (float("inf") if w > 0 else float("nan"))


def bar_flags() -> dict:
    """Per timeframe: a frame indexed by bar timestamp saying whether that bar
    had any volume and whether the bar was a flat repeat of the last price."""
    out = {}
    for tf in TFS:
        df = load_tf(SYM, tf)
        flat = (df.high == df.low) & (df.open == df.close)
        out[tf] = pd.DataFrame({"zero_vol": df.volume.values <= 0,
                                "flat": flat.values}, index=df.index)
    return out


def main():
    flags = bar_flags()
    t = pd.read_parquet(BT / "stage6_trades.parquet")
    t = t[t.symbol == SYM].copy()
    t["entry_ts"] = pd.to_datetime(t.entry_ts, utc=True)
    t["exit_ts"] = pd.to_datetime(t.exit_ts, utc=True)

    t["zero_vol"] = False
    t["flat"] = False
    for tf, f in flags.items():
        m = t.tf == tf
        if not m.any():
            continue
        idx = f.index
        pos = idx.get_indexer(t.loc[m, "entry_ts"])
        ok = pos >= 0
        z = np.zeros(int(m.sum()), dtype=bool)
        fl = np.zeros(int(m.sum()), dtype=bool)
        z[ok] = f.zero_vol.values[pos[ok]]
        fl[ok] = f.flat.values[pos[ok]]
        t.loc[m, "zero_vol"] = z
        t.loc[m, "flat"] = fl
        print(f"  {tf}: {int(m.sum()):5d} trades, "
              f"{int((~ok).sum())} entry timestamps not found on the bar index")

    print(f"\n{'=' * 104}")
    print("GOLD WALK-FORWARD TRADES ENTERED ON A BAR WHERE NOTHING TRADED")
    print(f"{'=' * 104}")
    print(f"{'cell':22} {'trades':>7} {'zeroVol':>8} {'share':>7} "
          f"{'R all':>9} {'R zeroVol':>10} {'R share':>8} {'PF all':>8} {'PF clean':>9}")
    rows = []
    for (tf, fl, tn), g in t.groupby(["tf", "floor", "topn"]):
        z = g[g.zero_vol]
        clean = g[~g.zero_vol]
        row = {"tf": tf, "floor": fl, "topn": tn, "trades": len(g),
               "zero_vol_trades": len(z),
               "zero_vol_share": round(len(z) / len(g), 4),
               "r_all": round(float(g.r.sum()), 2),
               "r_zero_vol": round(float(z.r.sum()), 2),
               "r_share": round(float(z.r.sum()) / float(g.r.sum()), 4)
               if abs(float(g.r.sum())) > 1e-9 else np.nan,
               "pf_all": round(pf(g.r.values), 3),
               "pf_clean": round(pf(clean.r.values), 3) if len(clean) else np.nan,
               "flat_bar_trades": int(g.flat.sum())}
        rows.append(row)
        print(f"{tf+' floor'+str(fl)+' top'+str(tn):22} {len(g):7d} {len(z):8d} "
              f"{row['zero_vol_share']:7.3f} {row['r_all']:9.2f} "
              f"{row['r_zero_vol']:10.2f} {str(row['r_share']):>8} "
              f"{row['pf_all']:8.3f} {str(row['pf_clean']):>9}")
    out = pd.DataFrame(rows)
    out.to_csv(BT / "stage19_deadbars.csv", index=False)

    print(f"\nWHOLE GOLD SAMPLE: {len(t):,} trades, "
          f"{int(t.zero_vol.sum()):,} entered on a zero-volume bar "
          f"({t.zero_vol.mean():.3%}), carrying "
          f"{t[t.zero_vol].r.sum():.2f}R of {t.r.sum():.2f}R "
          f"({t[t.zero_vol].r.sum()/t.r.sum():.3%})")
    print(f"                   {int(t.flat.sum()):,} entered on a bar with "
          f"high==low and open==close ({t.flat.mean():.3%})")

    # what the board actually publishes
    board_cells = [("5m", 100, 10), ("4h", 100, 1)]
    sel = t[[(a, b, c) in board_cells
             for a, b, c in zip(t.tf, t.floor, t.topn)]]
    if len(sel):
        cl = sel[~sel.zero_vol]
        print(f"\nTHE BOARD'S BOOK (5m floor100 top10 + 4h floor100 top1):")
        print(f"  as published : {len(sel):5d} trades  PF {pf(sel.r.values):.3f}  "
              f"total {sel.r.sum():.2f}R")
        print(f"  dead bars out: {len(cl):5d} trades  PF {pf(cl.r.values):.3f}  "
              f"total {cl.r.sum():.2f}R")
        print(f"  removed      : {len(sel)-len(cl)} trades, "
              f"{sel.r.sum()-cl.r.sum():+.2f}R")
    print(f"\nwrote {BT / 'stage19_deadbars.csv'}")


if __name__ == "__main__":
    main()
