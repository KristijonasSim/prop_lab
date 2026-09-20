"""H-046c — the two questions H-046b left open.

H-046b found every footprint setup directionally positive and too small: 0.1 to
3 bps gross against a 1.83 bps Dukascopy round trip and the 5.50 bps the live
demo measured on Bybit. Two things could change that and neither was tested.

QUESTION 1 - DOES THE EDGE KEEP GROWING WITH THE HOLD?
Cost is paid once per trade and is FIXED. If the gross effect keeps compounding
with time held, there is a hold at which it clears any given spread. If it flattens
or decays, no venue saves it. Holds extended to a full trading day.

QUESTION 2 - WHAT DOES THE SPREAD ACTUALLY COST, HOUR BY HOUR?
`spread_bps` is on every footprint bar, so the venue question is partly
measurable rather than a matter of opinion. Gold's spread is strongly
session-dependent, so the real question is not "what is the average spread" but
**does the edge survive in the hours when the spread is tight**. If the setups
only fire when gold is expensive, that is the end of it.

Both are reported at 1x, 2x and 3x the MEASURED Dukascopy round trip, and the 3x
column is the live Bybit reading - so the pessimistic column is not a guess.

Run: .venv/bin/python strategies/goldflow/longhold.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from core.gold_flow import load_flow                               # noqa: E402
from strategies.goldflow.scalp import RT_DUKAS, features, signals  # noqa: E402

RT_BYBIT = 5.50
#: 3-minute bars, so 20 = 1h, 160 = 8h, 480 = a full day
LONG_HOLDS = (20, 40, 80, 160, 320, 480)
CHEAP_Q = 0.33           # the tightest third of hours by spread


def run_holds(d: pd.DataFrame, sigs: dict, tf: str) -> None:
    print(f"\n=== Q1: does the edge grow with the hold?   XAUUSD {tf} " + "=" * 18)
    bars_per_h = {"3min": 20, "1h": 1}[tf]
    hdr = (f"{'setup':9}{'hold':>8}{'n':>7}{'gross':>8}{'@1x':>8}"
           f"{'@2x':>8}{'@3x=Bybit':>11}{'win%':>7}")
    print(hdr); print("-" * len(hdr))
    for name, s in sigs.items():
        for h in LONG_HOLDS:
            entry, exit_ = d.open.shift(-1), d.open.shift(-(1 + h))
            ret = ((exit_ / entry - 1.0) * 1e4 * s)[s != 0]
            ret = ret.replace([np.inf, -np.inf], np.nan).dropna()
            if len(ret) < 100:
                continue
            g = float(ret.mean())
            lab = f"{h}b/{h/bars_per_h:.0f}h"
            flag = "  <- clears Bybit" if g - RT_BYBIT > 0 else ""
            print(f"{name:9}{lab:>8}{len(ret):>7}{g:>8.2f}{g-RT_DUKAS:>8.2f}"
                  f"{g-2*RT_DUKAS:>8.2f}{g-RT_BYBIT:>11.2f}"
                  f"{float((ret>0).mean()*100):>7.1f}{flag}", flush=True)


def spread_by_hour(d: pd.DataFrame) -> pd.Series:
    return d.groupby(d.index.hour).spread_bps.median()


def run_cheap_hours(d: pd.DataFrame, sigs: dict, hold: int) -> None:
    sp = spread_by_hour(d)
    cheap = set(sp[sp <= sp.quantile(CHEAP_Q)].index)
    print(f"\n=== Q2: the spread by hour, and whether the edge lives there " + "=" * 8)
    print("median spread bps by UTC hour:")
    print("  " + "  ".join(f"{h:02d}:{sp[h]:.2f}" for h in sorted(sp.index)[:12]))
    print("  " + "  ".join(f"{h:02d}:{sp[h]:.2f}" for h in sorted(sp.index)[12:]))
    print(f"\ncheapest third (used below): "
          f"{sorted(cheap)}  median {sp[sorted(cheap)].median():.2f} bps "
          f"vs {sp.median():.2f} bps overall")
    hdr = (f"\n{'setup':9}{'hours':>10}{'n':>7}{'gross':>8}"
           f"{'net@spread':>12}{'win%':>7}")
    print(hdr); print("-" * len(hdr.strip("\n")))
    for name, s in sigs.items():
        for lab, mask in (("cheapest", d.index.hour.isin(cheap)),
                          ("rest", ~d.index.hour.isin(cheap))):
            sel = s.where(mask, 0.0)
            entry, exit_ = d.open.shift(-1), d.open.shift(-(1 + hold))
            ret = ((exit_ / entry - 1.0) * 1e4 * sel)[sel != 0]
            ret = ret.replace([np.inf, -np.inf], np.nan).dropna()
            if len(ret) < 50:
                continue
            g = float(ret.mean())
            # charge the round trip that actually applied in those hours
            rt = float(d.spread_bps[mask].median()) * 2
            print(f"{name:9}{lab:>10}{len(ret):>7}{g:>8.2f}{g-rt:>12.2f}"
                  f"{float((ret>0).mean()*100):>7.1f}", flush=True)


def main() -> int:
    print("H-046c — do longer holds or cheaper hours rescue the footprint edge?")
    print(f"Costs: Dukascopy round trip {RT_DUKAS} bps measured; "
          f"Bybit {RT_BYBIT} measured live (3.0x).")
    for tf in ("3min", "1h"):
        f = load_flow("XAUUSD", tf)
        f = f[f.vol > 0]
        if len(f) < 2000:
            continue
        d = features(f)
        sigs = signals(d)
        run_holds(d, sigs, tf)
        if tf == "3min":
            run_cheap_hours(d, sigs, 160)      # 8h hold, the best from Q1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
