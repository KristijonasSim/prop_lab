"""The exit axis — the only lever on H-027 that has never been tested.

WHY THIS, AND WHY NOW. Kris, 2026-09-09, looking at the indicator on a gold 1h
chart: "we trade 1h but we usually exit 1 or 2 bars after? isn't it too fast?"
It is. Measured on the modal fold configuration over our three years:

    median stop distance   10.8 bps ($3.11 on gold)
    one 1h bar's range     21.4 bps
    stop vs one bar        0.51x  - the stop sits INSIDE half a bar's range

and the consequence is the whole strategy:

    hold <= 2 bars    51.6% of trades   win 0.0%   avg R -1.08
    hold 3-10         27.0%             win 0.0%   avg R -1.06
    hold 11-50        10.7%             win 0.0%   avg R -1.04
    hold > 50         10.7%             win 37.5%  avg R +12.37

Every trade that dies early dies for the full risk. All of the money comes from
the tenth of trades that survive the first fifty bars. That is a stop problem,
not an entry problem, and the entry axis has been swept to exhaustion already
(thresholds, sessions, 25 filters, relative volume, fresh-cross - all measured,
all dead or inside the noise band).

THE THREE ARMS, identical folds, identical costs, identical entries:

    baseline    stop = 0.75-2.0 x the VWAP band sigma, as shipped
    wide sigma  stop = 2.5-8.0 x the same sigma. Same shape, more room
    ATR stop    stop = 0.5-4.0 x ATR(14). A different quantity entirely: sigma
                is the spread of price about the session VWAP and collapses
                early in a session, while ATR is the size of a bar and does not

HOW THE ATR ARM AVOIDS TOUCHING THE KERNEL. The kernel reads `sd` for exactly
one purpose - `risk = stop_sig * sd[i]` - while the entry reads `z`, which is
computed separately in `features()`. Swapping the `sd` array for ATR therefore
changes the STOP and nothing else: same entries, same bars, same everything
downstream. The shipped kernel is untouched and the board's fingerprint does not
move.

WHAT WOULD COUNT AS AN ANSWER. Expected days to a funded account, outside the
baseline's noise band. A wider stop mechanically raises the win rate and lowers
the average R; that is arithmetic, not evidence. It also risks the opposite
failure - a stop so wide the position never dies and the account stalls - so
`stalled %` is reported next to everything else.

Run: .venv/bin/python strategies/vwapbreak/research/exits.py
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from core.run_hypothesis import run_market, window                 # noqa: E402
from strategies.vwapbreak.strategy import STRATEGY, grid_for       # noqa: E402

SYM = "XAUUSD"
TFS = ("1h", "4h")
UNIVERSE = {"FX": ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD"],
            "Metals/Energy": ["XAUUSD", "XAGUSD", "WTI"],
            "Crypto": ["BTCUSDT", "ETHUSDT", "SOLUSDT"]}

WIDE_SIGMA = (2.5, 3.0, 4.0, 6.0, 8.0)
#: THE EDGE OF THE WIDE GRID BOUND on the first run - the selector took 8 sigma,
#: the widest offered, in 24 of 56 1h folds. Per the 2026-09-08 lesson a binding
#: edge is not itself evidence the edge continues (relieving HOLD_HOURS made the
#: out-of-sample result WORSE), so it is relieved and re-measured rather than
#: assumed.
WIDER_SIGMA = (6.0, 8.0, 10.0, 12.0, 16.0, 20.0)
ATR_MULTS = (0.5, 1.0, 1.5, 2.0, 3.0, 4.0)
ATR_LEN = 14


class ExitVariant:
    """H-027 with the stop measured differently. Entries are untouched."""

    extra_column = "z"

    def __init__(self, name: str, stops=None, atr: bool = False):
        self.name = name
        self.stops = stops
        self.atr = atr

    def features(self, df: pd.DataFrame):
        f = dict(STRATEGY.features(df))
        if self.atr:
            h, l, c = df.high.values, df.low.values, df.close.values
            pc = np.roll(c, 1)
            pc[0] = c[0]
            tr = np.maximum(h - l, np.maximum(np.abs(h - pc), np.abs(l - pc)))
            # Wilder's smoothing, the same one core/metrics and the vwap kernel
            # use, so "ATR" means one thing across the repo.
            f["sd"] = pd.Series(tr).ewm(alpha=1.0 / ATR_LEN, adjust=False).mean().values
        return f

    def new_cache(self):
        g = getattr(STRATEGY, "new_cache", None)
        return g() if callable(g) else {}

    def grid(self, tf: str):
        if self.stops is None:
            return STRATEGY.grid(tf)
        from core.markets import TF_BPH
        base = grid_for(TF_BPH[tf])
        seen, out = set(), []
        for cfg in base:
            for s in self.stops:
                c = dict(cfg)
                c["stop_sig"] = s
                key = tuple(sorted(c.items()))
                if key not in seen:
                    seen.add(key)
                    out.append(c)
        return out

    def run(self, df, cfg, fee_bps, slip_bps, feats=None, **kw):
        return STRATEGY.run(df, cfg, fee_bps, slip_bps,
                            feats=feats if feats is not None else self.features(df),
                            **kw)


ARMS = (
    ("baseline", ExitVariant("vwapbreak")),
    ("wide sigma", ExitVariant("vwapbreak_wide", stops=WIDE_SIGMA)),
    ("ATR stop", ExitVariant("vwapbreak_atr", stops=ATR_MULTS, atr=True)),
    ("wider still", ExitVariant("vwapbreak_wider", stops=WIDER_SIGMA)),
)


def band_str(b) -> str:
    if not b or b.get("days_lo") is None:
        return "—"
    return f"{b['days_lo']:.0f}–{b['days_hi']:.0f}"


def stalled(res: dict):
    lad = [x for x in res.get("ladder", []) if x.get("picked")]
    return lad[0].get("still_open_pct") if lad else None


def best60(res: dict):
    hit = [r for r in res.get("rules", []) if r.get("days60")]
    return min(hit, key=lambda r: r["days60"]) if hit else None


def main() -> int:
    syms = [s for v in UNIVERSE.values() for s in v]
    span = window(syms, ["1h", "4h"])
    print(f"window {span[0].date()} -> {span[1].date()}   XAUUSD, three exits, "
          f"identical entries\n")

    out = {}
    for tf in TFS:
        for tag, strat in ARMS:
            res = run_market(strat, SYM, tf, pipe_kw={}, null_seeds=1, span=span)
            res.pop("_trades", None)
            out[f"{tf}|{tag}"] = res
            print(f"  {tf:3s} {tag:11s} tpd {res.get('trades_per_day'):5.2f}  "
                  f"PF@2x {res.get('pf_2x')}  win {res.get('win_pct')}%  "
                  f"avgR {res.get('avg_r')}  days {res.get('days_to_pass')} "
                  f"[{band_str(res.get('band'))}]  pass {res.get('pass_pct')}%  "
                  f"stalled {stalled(res)}%  beats null {res.get('beats_null')}",
                  flush=True)

    dest = ROOT / "backtests" / "vwapbreak" / "exits.json"
    dest.write_text(json.dumps(out, indent=1, default=str))

    print("\n=== DOES A WIDER STOP FUND AN ACCOUNT SOONER? ===")
    print(f"{'tf':>4s} {'exit':11s} {'tr/day':>7s} {'win%':>6s} {'avg R':>7s} "
          f"{'PF@2x':>7s} {'exp days':>9s} {'band':>10s} {'pass%':>7s} "
          f"{'stall%':>7s} {'60% in':>8s}")
    for tf in TFS:
        for tag, _ in ARMS:
            r = out[f"{tf}|{tag}"]
            b60 = best60(r)
            d60 = f"{b60['days60']:.1f}" if b60 else "never"
            print(f"{tf:>4s} {tag:11s} {r.get('trades_per_day'):7.2f} "
                  f"{(r.get('win_pct') or float('nan')):6.1f} "
                  f"{(r.get('avg_r') or float('nan')):7.3f} "
                  f"{(r.get('pf_2x') or float('nan')):7.3f} "
                  f"{(r.get('days_to_pass') or float('nan')):9.1f} "
                  f"{band_str(r.get('band')):>10s} "
                  f"{(r.get('pass_pct') or float('nan')):7.1f} "
                  f"{(stalled(r) or float('nan')):7.1f} {d60:>8s}")

    print("\nWHAT THE BLIND SELECTOR CHOSE — the stop multiples it actually picked "
          "across folds.")
    for tf in TFS:
        for tag, _ in ARMS:
            picks = Counter()
            for rule in out[f"{tf}|{tag}"].get("rules", []):
                for f in rule.get("folds", []):
                    if f.get("stop_sig") is not None:
                        picks[float(f["stop_sig"])] += 1
            if picks:
                print(f"  {tf:3s} {tag:11s} " +
                      "  ".join(f"{k:g}: {v}" for k, v in sorted(picks.items())))

    print("\nBands first. Two arms whose bands overlap have not been shown to "
          "differ - the\nmeasured noise floor here is 13.3-26.5 expected days.")
    print(f"\nwrote {dest.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
