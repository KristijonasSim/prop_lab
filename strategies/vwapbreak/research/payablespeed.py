"""Can a TARGET break the bind: consistency rule OR too many days?

Kris, 2026-09-15: *"58 days is to much or we need to find another hypothesis you
can see problems now either consistency rule or to much days.... please
investigate our options"*.

HE HAS STATED THE BIND EXACTLY, AND IT IS ONE PROBLEM, NOT TWO.

Both symptoms come from the same property. The rule takes 0.93 trades a day,
wins roughly one in four, and carries that winner a long way with no target. So:

  * the profit arrives in single days - one day is 95.5% of a median month -
    which is what every consistency rule is written to reject; and
  * the profit arrives rarely, which is what makes the evaluation long.

A firm with no consistency rule costs days (FundingPips 2-Step Standard, 58.9).
A fast firm has a rule that costs hundreds (Blue Guardian, 23.3 -> 339.4). The
bind is real and no firm choice escapes it.

THE ONE LEVER THAT ATTACKS THE SHAPE ITSELF IS A TARGET, and it has never been
measured against the thing that matters here. What is on record:

  * `rr.py` (2026-09-10) swept targets 1-12R on speed. Slower.
  * `rr_policy.json` (same day) swept them against a **20% payout** cap and found
    "the first arms that are ever payable - and only just".

Neither asked the question Kris is asking: **does a target make a realistic 50%
CHALLENGE gate survivable, and what does it cost in days?** 50% is twice as
generous as the 20% those arms only just cleared, and an in-challenge gate is a
different object from a payout gate - it blocks passing, not withdrawing
(`consistency.py`).

PRE-REGISTERED BEFORE THE RUN:

  Scored on FundingPips 1-Step Flex rules (10% target, 4% daily, 12% static) -
  the best structure found in the 44-product sweep - twice: with no consistency
  gate, and with a 50% in-challenge gate.

  AN ARM WINS only if, under the 50% gate, its expected days fall inside the
  NO-GATE baseline's noise band. That is the definition of "the consistency rule
  stopped mattering". Being merely better than the baseline-under-gate is not
  enough: the gate costs 316 days on the shipped rule, so almost anything will
  look like an improvement against that.

  A target mechanically raises win rate and lowers average R. Expect it to be
  slower with no gate. The question is whether it is slower by less than the gate
  costs.

  KILL: if no arm clears that, the bind is structural, the shape cannot be
  repaired from inside H-027, and the honest options are (a) accept ~22-59 days
  at a no-consistency firm, or (b) a new hypothesis whose profit is not
  one-day-in-a-month.

Run: .venv/bin/python strategies/vwapbreak/research/payablespeed.py
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from core.noiseband import band as nb_band                          # noqa: E402
from core.prop_rules import PropRules                               # noqa: E402
from core.run_hypothesis import run_market, window                  # noqa: E402
from strategies.vwapbreak.research.exits import UNIVERSE            # noqa: E402
from strategies.vwapbreak.research.exitshape import ShapedExit      # noqa: E402

_s = importlib.util.spec_from_file_location(
    "consistency", Path(__file__).with_name("consistency.py"))
_c = importlib.util.module_from_spec(_s)
_s.loader.exec_module(_c)
run_phase_consistency = _c.run_phase_consistency

_s3 = importlib.util.spec_from_file_location(
    "firms3", Path(__file__).with_name("firms3.py"))
_f3 = importlib.util.module_from_spec(_s3)
_s3.loader.exec_module(_f3)
best_day_shares = _f3.best_day_shares

#: FundingPips 1-Step Flex - the best structure in the 44-product sweep and the
#: one firm verified to carry no consistency rule.
FLEX = PropRules(profit_target=0.10, daily_loss=0.04, max_loss=0.12,
                 trailing=False, static=True, min_trading_days=0)
RISKS = (0.01, 0.015, 0.02, 0.03, 0.04)
GATE = 0.50
SYM, TF = "XAUUSD", "1h"
TARGETS = (1.0, 2.0, 3.0, 4.0, 6.0, 8.0, 12.0)


def best(daily, cap):
    out = None
    for r in RISKS:
        x = run_phase_consistency(daily, r, FLEX, cap)
        if x["days"] and (out is None or x["days"] < out["days"]):
            out = x
    return out or {"days": None, "pass_pct": 0.0, "blown_pct": 0.0,
                   "stuck_pct": 100.0, "risk_pct": None}


def main() -> int:
    span = window([s for v in UNIVERSE.values() for s in v], ["1h", "4h"])
    arms = [("no target (shipped)", None, ShapedExit("vwapbreak"))]
    arms += [(f"target {int(t)}R", t, ShapedExit(f"vwapbreak_t{int(t)}", target_r=t))
             for t in TARGETS]

    print(f"{SYM} {TF}, FundingPips 1-Step Flex rules, blind walk-forward.\n"
          f"Gate = {GATE*100:.0f}% best day, applied INSIDE the challenge.\n")
    hdr = (f"{'arm':22}{'trades':>7}{'win%':>7}{'bestday':>9}{'mo<50%':>8}"
           f"{'| no gate':>11}{'band':>12}{'pass%':>7}{'| 50% gate':>12}{'pass%':>7}"
           f"{'cost':>8}")
    print(hdr); print("-" * len(hdr))
    rows = []
    for tag, t, arm in arms:
        res = run_market(arm, SYM, TF, pipe_kw={"floors": (30,), "topn": (5,)},
                         null_seeds=0, span=span)
        tr = res["_trades"]
        r = tr.r.values
        daily = pd.Series(r, index=pd.DatetimeIndex(tr.exit_ts)).resample("1D").sum()
        s30 = best_day_shares(daily, 30)
        a, g = best(daily, None), best(daily, GATE)
        bd = nb_band(daily, (a["risk_pct"] or 2) / 100, rules=FLEX) or {}
        row = {"arm": tag, "target_r": t, "trades": int(len(r)),
               "win_pct": round(float((r > 0).mean()) * 100, 1),
               "best_day_median": round(float(np.median(s30)) * 100, 1),
               "months_under_gate": round(float((s30 < GATE).mean()) * 100, 1),
               "no_gate": a, "gated": g, "band": bd,
               "inside_band": bool(g["days"] and bd and
                                   g["days"] <= bd.get("days_hi", 0))}
        rows.append(row)
        cost = (g["days"] - a["days"]) if (g["days"] and a["days"]) else None
        print(f"{tag:22}{row['trades']:>7}{row['win_pct']:>7.1f}"
              f"{row['best_day_median']:>8.1f}%{row['months_under_gate']:>7.1f}%"
              f"{(a['days'] or 0):>11.1f}"
              f"{('%.0f-%.0f' % (bd.get('days_lo', 0), bd.get('days_hi', 0))):>12}"
              f"{a['pass_pct']:>7.1f}{(g['days'] or 0):>12.1f}{g['pass_pct']:>7.1f}"
              f"{(f'+{cost:.0f}d' if cost is not None else 'never'):>8}", flush=True)

    win = [r for r in rows if r["target_r"] is not None and r["inside_band"]]
    print("\nAgainst the pre-registered condition - gated days inside the "
          "no-gate band:")
    if win:
        for r in win:
            print(f"  {r['arm']}: gated {r['gated']['days']:.1f}d vs band "
                  f"{r['band']['days_lo']:.0f}-{r['band']['days_hi']:.0f}  <-- CLEARS")
    else:
        print("  NO ARM CLEARS. The bind is structural.")

    dest = ROOT / "backtests" / "vwapbreak" / "payablespeed.json"
    dest.write_text(json.dumps({"gate": GATE, "rows": rows}, indent=1, default=str))
    print(f"\nwrote {dest.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

# =========================================================================== #
# RESULT - 2026-09-15. The bind IS breakable, and breaking it is not worth it.
#
# Two arms clear the pre-registered condition. A target does repair the profit
# shape, exactly as the mechanism predicted:
#
#   arm        best-day    months payable    gate costs
#   no target     95.5%              0.9%        +334 days
#   target 1R     76.6%             34.4%          +4 days
#   target 2R     58.1%             39.8%         +20 days
#
# A 2R target takes the share of payable months from 0.9% to 39.8% and reduces
# the cost of a 50% consistency gate from 334 days to 20. That is a real,
# mechanistic effect and it is the first thing on this hypothesis that moves the
# SHAPE rather than the speed.
#
# IT IS ALSO USELESS, AND THE REASON IS ARITHMETIC. The target costs so much
# speed that the repaired arm at a rule-bound firm is far worse than the shipped
# arm at a firm with no rule:
#
#   shipped rule, no-consistency firm (FundingPips 1-Step Flex)    22.0 days
#   target 2R,    50%-consistency firm                             80.3 days
#
# So the target is the right answer to the wrong question. The consistency rule
# is not something to engineer around - it is something to avoid by choosing the
# firm, and two firms are verified to have no rule at all.
#
# NO ARM IS FASTER THAN THE SHIPPED RULE, either. Ungated, the best target arm is
# 12R at 26.4 days against 22.0. Every other arm is slower, most of them far
# slower, and the ordering is not monotone in the target (1R 123.6, 2R 60.6,
# 3R 78.1, 4R 56.1, 6R 37.2, 8R 40.1, 12R 26.4), which is this repo's signature
# for a lever that is mostly noise around a downward trend toward "no target".
#
# 8R is worth one line as a warning: its best-day share is 125.6% - one day is
# larger than the whole month, because the rest of the month is a net loss - and
# its gated cost is +280 days. An arm can look mid-table on speed and be the
# worst thing in the study on shape.
#
# WHAT THIS SETTLES FOR KRIS'S QUESTION. He asked whether 58 days is too much or
# whether the hypothesis has to change. Neither, exactly:
#
#   * 58.9 days was FundingPips 2-Step Standard. The same firm's 1-STEP Flex is
#     22.0 days at 63.7% pass, 24.3% blown, no consistency rule, no minimum
#     trading days, on cTrader. That is the floor for H-027 and it costs EUR 61.
#   * 22 days is still not the 5-14 day pace target, and nothing in seven closed
#     axes, a tripled drawdown budget, or this target sweep has moved it.
#   * The pace target is therefore out of reach FOR THIS EDGE. A hypothesis whose
#     profit is not one-day-in-a-month is the only thing that would reach it.
