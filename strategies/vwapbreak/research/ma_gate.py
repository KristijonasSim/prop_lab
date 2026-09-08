"""Does the MA200 slope gate actually make H-027 gold FASTER? Blind, in-kernel.

`filters.py` screened 25 candidate filters as a post-hoc mask and only one came
out negative on days-to-funded on BOTH timeframes: take a long only while the
200-bar moving average is rising, a short only while it is falling. On 1h it sped
up 80% of configurations and improved the profit factor of 96% of them.

That was a screen with a known approximation - masking a trade out afterwards is
not the same as refusing it inside the kernel, because refusing it frees the bars
it occupied and a different trade can happen. This file removes the approximation.

HOW THE GATE IS APPLIED, and why it needs no kernel change. The kernel already
skips any bar whose `z` is not finite. So the gate is expressed by setting `z` to
NaN on the bars it refuses, which is EXACTLY equivalent to declining the entry -
same skip, same non-overlap behaviour, same everything downstream. The shipped
kernel is untouched, so the board's fingerprint does not move and there is no
chance of a second implementation disagreeing with the first.

WHAT IS COMPARED. The identical grid, the identical folds, the identical costs,
gate off versus gate on. Nothing is added to the grid - widening the grid is what
cost gold its headline earlier today, and a gate that has to be SELECTED is a
different and much weaker claim than one that is simply better.

Run: .venv/bin/python strategies/vwapbreak/research/ma_gate.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from core.run_hypothesis import run_market, window                 # noqa: E402
from strategies.vwapbreak.strategy import STRATEGY                 # noqa: E402

SYM = "XAUUSD"
TFS = ("1h", "4h")
MA = 200
UNIVERSE = {"FX": ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD"],
            "Metals/Energy": ["XAUUSD", "XAGUSD", "WTI"],
            "Crypto": ["BTCUSDT", "ETHUSDT", "SOLUSDT"]}


class MaSlopeGated:
    """H-027 with entries gated on the sign of the 200-bar MA slope."""

    name = "vwapbreak_magate"
    extra_column = "z"

    def __init__(self, period: int = MA):
        self.period = period

    def features(self, df: pd.DataFrame):
        f = dict(STRATEGY.features(df))
        m = pd.Series(df.close.values).rolling(self.period,
                                               min_periods=self.period).mean().values
        rising = np.r_[np.nan, np.diff(m)]
        z = np.array(f["z"], dtype=float)
        # Refuse the wrong side of the trend. A NaN z is a bar the kernel skips.
        # Both comparisons are False when `rising` is NaN, which is the warm-up,
        # so the warm-up is blocked rather than silently traded - the kernel's
        # own pad is what keeps that from costing fold coverage.
        block = ((rising > 0) & (z < 0)) | ((rising < 0) & (z > 0)) | ~np.isfinite(rising)
        z[block] = np.nan
        f["z"] = z
        return f

    def grid(self, tf: str):
        return STRATEGY.grid(tf)

    def run(self, df, cfg, fee_bps, slip_bps, feats=None, **kw):
        return STRATEGY.run(df, cfg, fee_bps, slip_bps,
                            feats=feats if feats is not None else self.features(df),
                            **kw)


def show(tag: str, res: dict) -> None:
    print(f"\n--- {tag}: {res['sym']} {res['tf']}")
    print(f"    headline  PF {res.get('pf')}  PF@2x {res.get('pf_2x')}  "
          f"tpd {res.get('trades_per_day')}  risk {res.get('risk_pct')}%  "
          f"pass {res.get('pass_pct')}%  days {res.get('days_to_pass')}  "
          f"null {res.get('null_pf')}  beats {res.get('beats_null')}")
    print(f"    {'floor':>5s} {'topn':>4s} {'tpd':>6s} {'PF':>6s} "
          f"{'days':>7s} {'pass%':>6s} {'days@60%':>9s}")
    for r in res.get("rules", []):
        d60 = f"{r['days60']:.1f}" if r.get("days60") else "—"
        print(f"    {r['floor']:5d} {r['topn']:4d} {r['tpd']:6.2f} {r['pf']:6.3f} "
              f"{r['days_to_pass'] or float('nan'):7.1f} {r['pass_pct']:6.1f} "
              f"{d60:>9s}")


def main() -> int:
    syms = [s for v in UNIVERSE.values() for s in v]
    span = window(syms, ["1h", "4h"])
    print(f"window {span[0].date()} -> {span[1].date()}   "
          f"gate: {MA}-bar MA slope, entries aligned with it")

    out = {}
    for tf in TFS:
        for tag, strat in (("gate OFF (H-027 as shipped)", STRATEGY),
                           (f"gate ON  (MA{MA} slope)", MaSlopeGated())):
            res = run_market(strat, SYM, tf, pipe_kw={}, null_seeds=1, span=span)
            res.pop("_trades", None)
            show(tag, res)
            out[f"{tf}|{tag}"] = res

    dest = ROOT / "backtests" / "vwapbreak" / "ma_gate.json"
    dest.write_text(json.dumps(out, indent=1, default=str))
    print(f"\nwrote {dest.relative_to(ROOT)}")

    print("\n=== VERDICT TABLE — fastest route to 60% pass, gate off vs on ===")
    print(f"{'tf':>4s} {'gate':>5s} {'days@60%':>9s} {'pass%':>7s} "
          f"{'headline d':>11s} {'PF@2x':>7s}")
    for tf in TFS:
        for tag in ("gate OFF (H-027 as shipped)", f"gate ON  (MA{MA} slope)"):
            r = out[f"{tf}|{tag}"]
            hit = [x for x in r.get("rules", []) if x.get("days60")]
            b = min(hit, key=lambda x: x["days60"]) if hit else None
            d60 = f"{b['days60']:.1f}" if b else "never"
            p60 = f"{b['pass60']:.1f}" if b else "—"
            hd = r.get("days_to_pass")
            hd = f"{hd:.1f}" if hd else "—"
            pf2 = r.get("pf_2x")
            pf2 = f"{pf2:.3f}" if pf2 else "—"
            gate = "ON" if "ON" in tag else "OFF"
            print(f"{tf:>4s} {gate:>5s} {d60:>9s} {p60:>7s} {hd:>11s} {pf2:>7s}")
    print("\nGoal is 60% pass inside 14 days. days@60% is the fastest selection "
          "rule that\nreaches 60% at any risk level; 'never' means no rule does.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
