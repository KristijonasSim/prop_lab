"""Reward:risk 1 to 12, on gold, measured properly.

Kris, 2026-09-10, looking at an 11.6:1 average win over average loss: *"its little
bit crazy :D i think usually its 1:1 or 1:2 maybe sometimes 1:3 or 1:4... can you
test all these scenarios with gold with R:R being from 1 to 12".*

WHY THE 11.6 IS NOT WHAT IT LOOKS LIKE. It is `avg win / avg loss` on the traded
book, and the denominator is the surprise, not the numerator: the average loser is
**-0.205R**, and not one trade in 591 loses a full 1R. The blind selector keeps
choosing 8-20 sigma stops, so the stop almost never fires and a loser is a horizon
exit that drifted a fifth of the way to it. The ratio is high because the losses
are small, not because the wins are enormous.

WHAT THIS FILE DOES. Adds a real TARGET at k x risk, k = 1..12, and walk-forwards
each one blind on identical folds, entries untouched. That is the textbook
reward:risk Kris means: a trade either makes k x what it risks or it is stopped.

WHAT IS ALREADY KNOWN, and why this is still worth running. `research/shape.py`
swept reward:risk 1 to 8 on the OLD grid and average R rose monotonically to the
edge of the grid every time, which is what removed the target axis from the
shipped kernel. That sweep ran before the stop grid was widened to 2.5-20 sigma on
2026-09-09, and a target interacts with the stop width: with a 20-sigma stop, a 1R
target is a very different trade from a 1R target on a 2-sigma stop. The result
may well repeat. Repeating a measurement whose conditions have changed is not
waste, and if it does repeat that is the answer to the question.

REPORTED PER ARM: the realised win rate, average win, average loss, the RESULTING
reward:risk (which is not the target - a target of 3 does not give a 3:1 realised
ratio once losers are small and some trades still exit at the horizon), profit
factor at 1x and 2x cost, expected days with its band, and the pass rate.

Run: .venv/bin/python strategies/vwapbreak/research/rr.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from core.noiseband import band                                    # noqa: E402
from core.prop_rules import PropRules                              # noqa: E402
from core.riskladder import run_accounts                           # noqa: E402
from core.run_hypothesis import run_market, window                 # noqa: E402
from strategies.vwapbreak.research.exits import UNIVERSE           # noqa: E402
from strategies.vwapbreak.research.exitshape import (ShapedExit,   # noqa: E402
                                                     payout_stats)

ASH = PropRules(profit_target=0.02, daily_loss=0.03, max_loss=0.06,
                min_trading_days=0)
RISKS = (0.01, 0.015, 0.02, 0.03)
SYM, TF = "XAUUSD", "1h"
TARGETS = (1.0, 2.0, 3.0, 4.0, 6.0, 8.0, 10.0, 12.0)


def score(res: dict, tag: str, target) -> dict:
    tr = res["_trades"]
    r = tr.r.values
    w, l = r[r > 0], r[r <= 0]
    daily = pd.Series(r, index=pd.DatetimeIndex(tr.exit_ts)).resample("1D").sum()
    best = None
    for risk in RISKS:
        a = run_accounts(daily, risk, ASH)
        if not a["pass_rate"]:
            continue
        exp = a["median_days"] / a["pass_rate"]
        line = {"risk_pct": risk * 100, "pass_pct": round(a["pass_rate"] * 100, 1),
                "blown_pct": round((a["fail_max"] + a["fail_daily"]) * 100, 1),
                "days": round(exp, 1), "band": band(daily, risk, rules=ASH)}
        if best is None or exp < best["days"]:
            best = line
    return {
        "tag": tag, "target_r": target,
        "trades": int(len(r)),
        "win_pct": round(float(len(w) / len(r)) * 100, 1),
        "avg_win_r": round(float(w.mean()), 3) if len(w) else None,
        "avg_loss_r": round(float(l.mean()), 3) if len(l) else None,
        "realised_rr": (round(float(w.mean() / abs(l.mean())), 2)
                        if len(w) and len(l) and l.mean() != 0 else None),
        "median_win_r": round(float(np.median(w)), 3) if len(w) else None,
        "max_r": round(float(r.max()), 2),
        "avg_r": round(float(r.mean()), 4),
        "pf": res.get("pf"), "pf_2x": res.get("pf_2x"),
        "trades_per_day": res.get("trades_per_day"),
        "beats_null": res.get("beats_null"), "null_pf": res.get("null_pf"),
        **(best or {"days": None}),
        **payout_stats(daily.values * 0.02),
    }


def main() -> int:
    span = window([s for v in UNIVERSE.values() for s in v], ["1h", "4h"])
    arms = [("no target (as traded)", None, ShapedExit("vwapbreak"))]
    arms += [(f"target {int(t)}R", t, ShapedExit(f"vwapbreak_t{int(t)}", target_r=t))
             for t in TARGETS]

    print(f"{SYM} {TF}, blind quarterly walk-forward, identical folds\n")
    print(f"{'arm':22}{'trades':>7}{'win%':>7}{'avgWin':>8}{'avgLoss':>8}"
          f"{'R:R':>7}{'avgR':>8}{'PF':>7}{'PF2x':>7}{'days':>7}{'band':>12}{'pass%':>7}")
    rows = []
    for tag, t, arm in arms:
        res = run_market(arm, SYM, TF, pipe_kw={"floors": (30,), "topn": (5,)},
                         null_seeds=1, span=span)
        s = score(res, tag, t)
        rows.append(s)
        b = s.get("band") or {}
        print(f"{tag:22}{s['trades']:7}{s['win_pct']:7.1f}{s['avg_win_r']:8.3f}"
              f"{s['avg_loss_r']:8.3f}{(s['realised_rr'] or 0):7.2f}{s['avg_r']:8.4f}"
              f"{(s['pf'] or 0):7.3f}{(s['pf_2x'] or 0):7.3f}{(s['days'] or 0):7.1f}"
              f"{('%.0f-%.0f' % (b.get('days_lo', 0), b.get('days_hi', 0))):>12}"
              f"{(s['pass_pct'] or 0):7.1f}", flush=True)

    dest = ROOT / "backtests" / "vwapbreak" / "rr.json"
    dest.write_text(json.dumps({"sym": SYM, "tf": TF, "targets": list(TARGETS),
                                "rows": rows}, indent=1, default=str))
    print(f"\nwrote {dest.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
