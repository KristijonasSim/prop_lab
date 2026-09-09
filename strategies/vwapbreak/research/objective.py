"""TASK 3 — what should the fold selector maximise?

THE PROBLEM. The selector ranks configurations on PROFIT FACTOR at double cost.
Profit factor is maximised by a very tight stop that wins 5% of the time and pays
hugely when it wins - and a prop evaluation does not pay for profit factor, it
pays for reaching a target before a drawdown. Given every stop width from 0.75 to
20 sigma the profit-factor selector picks 0.75, which is why the traded settings
had to be pinned by hand in `core/chosen.py`. The pin is the symptom; this is the
cause.

THE THREE OBJECTIVES, identical folds, identical grid, identical costs:

    2x     profit factor at double cost   (what the pipeline does today)
    rday   R per day on the train slice   (pays for speed, ignores drawdown)
    days   R per day / max drawdown in R  (the identity that sets time-to-funded:
           days = maxDD_R / R_per_day, so this maximises its reciprocal)

Nothing else changes. Whatever wins here should become `Pipeline.SELECT_ON`, and
if it picks the wide stop by itself the hand-pin can be deleted.

Run: .venv/bin/python strategies/vwapbreak/research/objective.py
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from core.prop_rules import PropRules                              # noqa: E402
from core.riskladder import run_accounts                           # noqa: E402
from core.run_hypothesis import run_market, window                 # noqa: E402
from strategies.vwapbreak.research.exits import (UNIVERSE, WIDE_SIGMA,  # noqa: E402
                                                 ExitVariant)

SYM, TFS = "XAUUSD", ("1h", "4h")
OBJECTIVES = ("2x", "rday", "days")
ASH = PropRules(profit_target=0.02, daily_loss=0.03, max_loss=0.06,
                min_trading_days=0)


def main() -> int:
    span = window([s for v in UNIVERSE.values() for s in v], list(TFS))
    out = {}
    print(f"XAUUSD, wide-stop grid, floor 30 / top 5, three selector objectives\n")
    print(f"{'tf':>3} {'objective':>10}{'trades':>8}{'tr/day':>8}{'PF':>8}{'win%':>7}"
          f"{'pass%@2':>9}{'blown%':>8}{'days@2%':>9}   stop picks")
    for tf in TFS:
        for obj in OBJECTIVES:
            res = run_market(ExitVariant("wide", stops=WIDE_SIGMA), SYM, tf,
                             pipe_kw={"floors": (30,), "topn": (5,),
                                      "select_on": obj},
                             null_seeds=0, span=span)
            tr = res.pop("_trades")
            daily = pd.Series(tr.r.values,
                              index=pd.DatetimeIndex(tr.exit_ts)).resample("1D").sum()
            a = run_accounts(daily, 0.02, ASH)
            picks = Counter()
            for rule in res.get("rules", []):
                for f in rule.get("folds", []):
                    if f.get("stop_sig") is not None:
                        picks[float(f["stop_sig"])] += 1
            out[f"{tf}|{obj}"] = {k: v for k, v in res.items() if k != "rules"}
            out[f"{tf}|{obj}"] |= {
                "pass_pct": round(a["pass_rate"] * 100, 1),
                "blown_pct": round((a["fail_max"] + a["fail_daily"]) * 100, 1),
                "days": round(a["median_days"] / a["pass_rate"], 1) if a["pass_rate"] else None,
                "stop_picks": {str(k): v for k, v in sorted(picks.items())}}
            print(f"{tf:>3} {obj:>10}{res['trades']:8d}{res['trades_per_day']:8.2f}"
                  f"{res['pf']:8.3f}{res['win_pct']:7.1f}"
                  f"{a['pass_rate']*100:9.1f}{(a['fail_max']+a['fail_daily'])*100:8.1f}"
                  f"{(a['median_days']/a['pass_rate'] if a['pass_rate'] else float('nan')):9.1f}"
                  f"   " + "  ".join(f"{k:g}:{v}" for k, v in sorted(picks.items())),
                  flush=True)
    dest = ROOT / "backtests" / "vwapbreak" / "objective.json"
    dest.write_text(json.dumps(out, indent=1, default=str))
    print(f"\nwrote {dest.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
