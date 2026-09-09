"""Fewer trades, better trades — does it help? Kris's question, 2026-09-09.

He looked at the indicator on gold and asked whether the rule is trading too
often, and to "remove quantity and increase quality and check if it helps".

TWO DIFFERENT THINGS WERE BEHIND THAT QUESTION and only one of them was real.
The chart was drawing every bar the condition held, which made one trade look
like ten - fixed in `indicator.pine`. What is left is the honest version of his
question: at the same cost and the same blind walk-forward, does taking FEWER
and more extreme signals fund an account sooner?

THE FOUR ARMS, all on XAUUSD, identical folds, identical costs:

  baseline      the grid as shipped: threshold 0.5 to 1.5 sigma
  higher bar    threshold 1.5 to 3.0 sigma. Strictly fewer, strictly more
                extreme signals, nothing else changed
  fresh cross   one trade per excursion. The rule may only fire on the bar z
                CROSSES out through its threshold; while price stays beyond the
                band no new trade starts, even after the previous one closes.
                This is the "quality" reading that is not in the grid at all
  both          fresh cross on the higher-bar grid

HOW "FRESH CROSS" IS APPLIED WITHOUT TOUCHING THE KERNEL. The kernel skips any
bar whose `z` is not finite, so blanking `z` on the bars to be refused is exactly
equivalent to declining those entries - same skip, same non-overlap behaviour.
The mask depends on the configuration's own threshold, so it is built inside
`run()` where the config is known, rather than in `features()` where it is not.
The shipped kernel is untouched and the board's fingerprint does not move.

WHAT WOULD COUNT AS AN ANSWER. Not a higher profit factor: `RESEARCH_LOG.md`
2026-09-08 measured correlation(PF@2x, expected days) = +0.231, so raising PF by
cutting trades usually makes the evaluation SLOWER. The question is expected days
to a funded account - and it has to clear the cell's own noise band, printed next
to every number below, or it is not evidence of anything.

Run: .venv/bin/python strategies/vwapbreak/research/quality.py
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from core.run_hypothesis import run_market, window                 # noqa: E402
from strategies.vwapbreak.strategy import STRATEGY, grid_for       # noqa: E402

SYM = "XAUUSD"
TFS = ("1h", "4h")
UNIVERSE = {"FX": ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD"],
            "Metals/Energy": ["XAUUSD", "XAGUSD", "WTI"],
            "Crypto": ["BTCUSDT", "ETHUSDT", "SOLUSDT"]}

#: The higher-bar grid. The shipped thresholds are 0.5-1.5; these start where
#: those stop, so the two arms overlap at exactly one value and the comparison is
#: "further out" rather than "a different search".
HIGH_THRESHOLDS = (1.5, 2.0, 2.5, 3.0)


class Variant:
    """H-027 with a threshold grid and, optionally, one trade per excursion."""

    extra_column = "z"

    def __init__(self, name: str, thresholds=None, cross_only: bool = False):
        self.name = name
        self.thresholds = thresholds
        self.cross_only = cross_only

    def features(self, df):
        return STRATEGY.features(df)

    def new_cache(self):
        f = getattr(STRATEGY, "new_cache", None)
        return f() if callable(f) else {}

    def grid(self, tf: str):
        g = STRATEGY.grid(tf)
        if self.thresholds is None:
            return g
        # Same axes, same everything, only the threshold values replaced. Built
        # from the shipped `grid_for` so the two arms cannot drift apart.
        from core.markets import TF_BPH
        base = grid_for(TF_BPH[tf])
        seen, out = set(), []
        for cfg in base:
            for thr in self.thresholds:
                c = dict(cfg)
                c["thr"] = thr
                key = tuple(sorted(c.items()))
                if key not in seen:
                    seen.add(key)
                    out.append(c)
        return out

    def run(self, df, cfg, fee_bps, slip_bps, feats=None, **kw):
        f = feats if feats is not None else self.features(df)
        if self.cross_only:
            f = dict(f)
            z = np.asarray(f["z"], dtype=float).copy()
            thr = float(cfg["thr"])
            # A bar is refused when the PREVIOUS bar was already beyond the same
            # threshold on the same side: the excursion is not fresh. NaN in z is
            # the kernel's own "nothing to decide here".
            prev = np.roll(z, 1)
            prev[0] = np.nan
            stale = (((z >= thr) & (prev >= thr)) | ((z <= -thr) & (prev <= -thr)))
            z[stale] = np.nan
            f["z"] = z
        return STRATEGY.run(df, cfg, fee_bps, slip_bps, feats=f, **kw)


ARMS = (
    ("baseline", Variant("vwapbreak")),
    ("higher bar", Variant("vwapbreak_hi", thresholds=HIGH_THRESHOLDS)),
    ("fresh cross", Variant("vwapbreak_x", cross_only=True)),
    ("both", Variant("vwapbreak_hix", thresholds=HIGH_THRESHOLDS, cross_only=True)),
)


def band_str(b) -> str:
    if not b or b.get("days_lo") is None:
        return "—"
    return f"{b['days_lo']:.0f}–{b['days_hi']:.0f}"


def best60(res: dict):
    hit = [r for r in res.get("rules", []) if r.get("days60")]
    return min(hit, key=lambda r: r["days60"]) if hit else None


def main() -> int:
    syms = [s for v in UNIVERSE.values() for s in v]
    span = window(syms, ["1h", "4h"])
    print(f"window {span[0].date()} -> {span[1].date()}   XAUUSD, four arms, "
          f"identical folds and costs\n")

    out = {}
    for tf in TFS:
        for tag, strat in ARMS:
            res = run_market(strat, SYM, tf, pipe_kw={}, null_seeds=1, span=span)
            res.pop("_trades", None)
            out[f"{tf}|{tag}"] = res
            b = res.get("band") or {}
            print(f"  {tf:3s} {tag:12s} tpd {res.get('trades_per_day'):5.2f}  "
                  f"PF@2x {res.get('pf_2x')}  days {res.get('days_to_pass')} "
                  f"[{band_str(b)}]  pass {res.get('pass_pct')}%  "
                  f"null {res.get('null_pf')} beats {res.get('beats_null')}",
                  flush=True)

    dest = ROOT / "backtests" / "vwapbreak" / "quality.json"
    dest.write_text(json.dumps(out, indent=1, default=str))

    print("\n=== DOES FEWER MEAN FASTER? ===")
    print(f"{'tf':>4s} {'arm':12s} {'tr/day':>7s} {'PF@2x':>7s} {'exp days':>9s} "
          f"{'band':>12s} {'pass%':>7s} {'60% in':>8s} {'beats null':>11s}")
    for tf in TFS:
        for tag, _ in ARMS:
            r = out[f"{tf}|{tag}"]
            b60 = best60(r)
            print(f"{tf:>4s} {tag:12s} {r.get('trades_per_day'):7.2f} "
                  f"{(r.get('pf_2x') or float('nan')):7.3f} "
                  f"{(r.get('days_to_pass') or float('nan')):9.1f} "
                  f"{band_str(r.get('band')):>12s} "
                  f"{(r.get('pass_pct') or float('nan')):7.1f} "
                  f"{(f'{b60['days60']:.1f}' if b60 else 'never'):>8s} "
                  f"{str(r.get('beats_null')):>11s}")

    print("\nWHAT THE BLIND SELECTOR CHOSE, per arm — the thresholds it actually "
          "picked\nacross the folds. A selector that declines the higher bar when "
          "offered it is\nevidence in its own right.")
    for tf in TFS:
        for tag, _ in ARMS:
            r = out[f"{tf}|{tag}"]
            picks = Counter()
            for rule in r.get("rules", []):
                for f in rule.get("folds", []):
                    if f.get("thr") is not None:
                        picks[float(f["thr"])] += 1
            if picks:
                s = "  ".join(f"{k:g}: {v}" for k, v in sorted(picks.items()))
                print(f"  {tf:3s} {tag:12s} {s}")

    print("\nREAD THE BANDS BEFORE THE NUMBERS. Two arms whose bands overlap have "
          "not been\nshown to differ - the measured noise floor on this hypothesis "
          "is 13.3-26.5\nexpected days, which is wider than most differences this "
          "project has reported.")
    print(f"\nwrote {dest.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
