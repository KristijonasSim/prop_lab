"""The fold selector ranks on 1x cost. The repo's own rule says 2x. Does it matter?

THE DEFECT. `README.md` 3.3 and `START_HERE.md` both carry the same hard-learned
rule:

    "Select configurations on 2x-cost profit factor inside the fold, not on 1x
     with a 2x check afterwards. Selecting on 1x and checking 2x afterwards let
     four fragile legs into the book."

`core/pipeline.py` did not implement it. `walk_forward` computed the train-slice
profit factor from the 1x trade series and ranked on that, while the 2x series -
which `_trades` already computes on the same slice, for free - was used only to
REPORT the test fold afterwards. Every H-002 and H-027 number on the board was
selected the way the repo says not to select.

This file measures what the rule is worth on gold rather than assuming it. Same
grid, same folds, same costs, same everything: only the ranking key changes.

A configuration whose 2x re-run produced a different trade count falls back to 1x
for ranking - at 2x the stop distances are unchanged but the fills are not, so a
marginal trade can disappear. That is rare and it is reported.

Run: .venv/bin/python strategies/vwapbreak/research/select_cost.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from pathlib import Path as _P

ROOT = _P(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from core.run_hypothesis import run_market, window                 # noqa: E402
from strategies.vwapbreak.strategy import STRATEGY                 # noqa: E402

SYM = "XAUUSD"
TFS = ("1h", "4h")
UNIVERSE = {"FX": ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD"],
            "Metals/Energy": ["XAUUSD", "XAGUSD", "WTI"],
            "Crypto": ["BTCUSDT", "ETHUSDT", "SOLUSDT"]}


def show(tag: str, res: dict) -> None:
    print(f"\n--- {tag}: {res['sym']} {res['tf']}")
    print(f"    headline  PF {res.get('pf')}  PF@2x {res.get('pf_2x')}  "
          f"tpd {res.get('trades_per_day')}  risk {res.get('risk_pct')}%  "
          f"pass {res.get('pass_pct')}%  days {res.get('days_to_pass')}  "
          f"null {res.get('null_pf')}  beats {res.get('beats_null')}")
    print(f"    {'floor':>5s} {'topn':>4s} {'tpd':>6s} {'PF':>6s} "
          f"{'days':>8s} {'pass%':>6s} {'days@60%':>9s}")
    for r in res.get("rules", []):
        d60 = f"{r['days60']:.1f}" if r.get("days60") else "—"
        d = r["days_to_pass"]
        print(f"    {r['floor']:5d} {r['topn']:4d} {r['tpd']:6.2f} {r['pf']:6.3f} "
              f"{(f'{d:.1f}' if d else '—'):>8s} {r['pass_pct']:6.1f} {d60:>9s}")


def main() -> int:
    syms = [s for v in UNIVERSE.values() for s in v]
    span = window(syms, ["1h", "4h"])
    print(f"window {span[0].date()} -> {span[1].date()}   "
          f"only the fold selector's ranking key changes")

    out = {}
    for tf in TFS:
        for tag, kw in (("select on 1x (as shipped)", {"select_on": "1x"}),
                        ("select on 2x (the rule)", {"select_on": "2x"})):
            res = run_market(STRATEGY, SYM, tf, pipe_kw=kw, null_seeds=1,
                             span=span)
            res.pop("_trades", None)
            show(tag, res)
            out[f"{tf}|{tag}"] = res

    dest = ROOT / "backtests" / "vwapbreak" / "select_cost.json"
    dest.write_text(json.dumps(out, indent=1, default=str))
    print(f"\nwrote {dest.relative_to(ROOT)}")

    print("\n=== VERDICT — fastest route to 60% pass ===")
    print(f"{'tf':>4s} {'select':>7s} {'days@60%':>9s} {'pass%':>7s} "
          f"{'headline d':>11s} {'PF@2x':>7s}")
    for tf in TFS:
        for tag in ("select on 1x (as shipped)", "select on 2x (the rule)"):
            r = out[f"{tf}|{tag}"]
            hit = [x for x in r.get("rules", []) if x.get("days60")]
            b = min(hit, key=lambda x: x["days60"]) if hit else None
            d60 = f"{b['days60']:.1f}" if b else "never"
            p60 = f"{b['pass60']:.1f}" if b else "—"
            hd = r.get("days_to_pass")
            hd = f"{hd:.1f}" if hd else "—"
            pf2 = r.get("pf_2x")
            pf2 = f"{pf2:.3f}" if pf2 else "—"
            print(f"{tf:>4s} {('1x' if '1x' in tag else '2x'):>7s} {d60:>9s} "
                  f"{p60:>7s} {hd:>11s} {pf2:>7s}")
    print("\nGoal is 60% pass inside 14 days. 'never' means no selection rule "
          "reaches 60%\nat any risk level on the ladder.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
