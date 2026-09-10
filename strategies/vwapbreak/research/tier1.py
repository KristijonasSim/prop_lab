"""TIER 1, items 3-5: cost sensitivity, and sizing that knows about the evaluation.

Kris: *"lets do tier 1 please, all of them"*. Item 1 (sub-hour) is `subhour.py` and
item 2 (volume bars) is `volbars.py`. This file is the other three, and one of them
turned out not to need doing at all.

--------------------------------------------------------------------------------
ITEM 3 - HOW MUCH SPREAD CAN GOLD PAY? (the researchable half)

Kris has to measure his firm's real gold spread himself; nobody can do that from
here. What CAN be done from here is the sensitivity: at what cost does gold stop
working? Everything in this repo is priced at Dukascopy's **1.06bps round trip**,
measured from ticks, and a prop CFD feed is plausibly 2-4x that.

NO RE-RUN IS NEEDED, and this is exact rather than approximate. The pipeline
already stores every trade at 1x and at 2x cost, so the cost charged to a trade in
R terms is `r - r_2x`, and the same trade at k times cost is

    r_k = r - (k - 1) * (r - r_2x)

which is arithmetic on a fixed trade list, not a new search.

--------------------------------------------------------------------------------
ITEM 4 - SIZING THAT KNOWS WHERE THE ACCOUNT STANDS

The binding constraint is not the profit target, it is the **3% daily cap**: the
worst day is -3.93% of balance at 2% risk and three days in 221 broke 3%. Every one
of those is a dead account, and no entry-side work has ever touched it.

Four schedules, all declared in advance, all scored on the same PASS/FAIL
simulation with real breaches:

    flat            the shipped rule, every trade the same size
    cut on drawdown half size once the account is more than half way to the cap
    cut near target half size once the account is within 0.5% of passing
    budget-linear   size proportional to the remaining drawdown budget

CLAUDE.md forbids a risk manager that sizes down until it can never breach,
because that manufactures a fake 0% fail rate on a book that never resolves. The
guard is structural: **`still_open` is reported next to every arm**, and an arm
that survives by not trading shows up there rather than looking good.

--------------------------------------------------------------------------------
ITEM 5 - RISK SCALED BY BAND WIDTH: ALREADY DONE, BY CONSTRUCTION

Written into the backlog this morning and it does not need a run. Position size is
set so that a stop-out costs `risk_pct` of the account, and the stop is
`stop_sig x sigma` - so a wide-sigma session automatically takes a smaller
position, and R is sigma-free by definition. **The strategy is already volatility
targeted.** What is worth checking instead is the opposite end: how often the
`min_risk_bps` floor binds, because a trade whose sigma is below the floor gets a
WIDER stop than the rule asks for and its R is no longer comparable. That check is
here.

Run: .venv/bin/python strategies/vwapbreak/research/tier1.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from core.markets import COSTS, EXEC_MODE, load                    # noqa: E402
from core.noiseband import band                                    # noqa: E402
from core.prop_rules import PropRules                              # noqa: E402
from core.riskladder import run_accounts                           # noqa: E402
from core.run_hypothesis import run_market, window                 # noqa: E402
from strategies.vwap.sweep import vwap_series                      # noqa: E402
from strategies.vwapbreak.research.exits import (UNIVERSE, WIDE_SIGMA,  # noqa: E402
                                                 ExitVariant)

ASH = PropRules(profit_target=0.02, daily_loss=0.03, max_loss=0.06,
                min_trading_days=0)
RISKS = (0.01, 0.015, 0.02, 0.03)
SYM, TF = "XAUUSD", "1h"
COST_MULTS = (1.0, 2.0, 3.0, 4.0, 5.0, 7.0, 10.0)
MAX_DAYS = 120


def daily_of(r: np.ndarray, ts) -> pd.Series:
    return pd.Series(r, index=pd.DatetimeIndex(ts)).resample("1D").sum()


def ladder(daily: pd.Series) -> dict:
    best = None
    for risk in RISKS:
        a = run_accounts(daily, risk, ASH)
        if not a["pass_rate"]:
            continue
        exp = a["median_days"] / a["pass_rate"]
        line = {"risk_pct": risk * 100, "pass_pct": round(a["pass_rate"] * 100, 1),
                "blown_pct": round((a["fail_max"] + a["fail_daily"]) * 100, 1),
                "still_open_pct": round(a["still_open"] * 100, 1),
                "days": round(exp, 1)}
        if best is None or exp < best["days"]:
            best = line
    return best or {"days": None}


# --------------------------------------------------------------------------- #
# item 4: the same PASS/FAIL simulation, with a size schedule
# --------------------------------------------------------------------------- #
def run_scaled(daily_r: pd.Series, risk: float, schedule: str,
               rules: PropRules = ASH, max_days: int = MAX_DAYS) -> dict:
    """`riskladder.run_accounts` with the day's size set by the account's state.

    Deliberately a copy rather than a flag on the shipped function: the board's
    numbers must not be able to move because of a research arm.
    """
    d = daily_r.values
    n = len(d)
    out = []
    for s in range(n):
        eq, peak, day, traded, res = 0.0, 0.0, 0, 0, "OPEN"
        for k in range(s, min(s + max_days, n)):
            day += 1
            # --- the schedule, evaluated on yesterday's close ------------- #
            dd = min(eq - peak, eq)          # drawdown, static or trailing
            if schedule == "flat":
                mult = 1.0
            elif schedule == "cut_dd":
                mult = 0.5 if dd <= -rules.max_loss / 2 else 1.0
            elif schedule == "cut_near_target":
                mult = 0.5 if eq >= rules.profit_target - 0.005 else 1.0
            elif schedule == "budget":
                left = max(0.0, rules.max_loss + dd) / rules.max_loss
                mult = float(np.clip(left, 0.25, 1.0))
            else:                                        # pragma: no cover
                raise KeyError(schedule)
            step = d[k] * risk * mult
            if step != 0.0:
                traded += 1
            if min(step, 0.0) <= -rules.daily_loss:
                res = "FAIL_DAILY"
                break
            low = eq + min(step, 0.0)
            if (rules.trailing and low - peak <= -rules.max_loss) or \
               (rules.static and low <= -rules.max_loss):
                res = "FAIL_MAX"
                break
            eq += step
            peak = max(peak, eq)
            if eq >= rules.profit_target and traded >= rules.min_trading_days:
                res = "PASS"
                break
        out.append((res, day))
    df = pd.DataFrame(out, columns=["outcome", "days"])
    p = df[df.outcome == "PASS"]
    return {"pass_pct": round(len(p) / len(df) * 100, 1) if len(df) else 0.0,
            "blown_pct": round(float(df.outcome.isin(["FAIL_MAX", "FAIL_DAILY"]).mean()) * 100, 1),
            "still_open_pct": round(float((df.outcome == "OPEN").mean()) * 100, 1),
            "median_days": float(p.days.median()) if len(p) else None,
            "days": (round(float(p.days.median()) / (len(p) / len(df)), 1)
                     if len(p) else None)}


def main() -> int:
    span = window([s for v in UNIVERSE.values() for s in v], ["1h", "4h"])
    res = run_market(ExitVariant("wide", stops=WIDE_SIGMA), SYM, TF,
                     pipe_kw={"floors": (30,), "topn": (5,)},
                     null_seeds=0, span=span)
    tr = res["_trades"]
    r, r2 = tr.r.values, tr.r_2x.values
    cost_r = r - r2                       # what one cost multiple costs, in R
    print(f"{SYM} {TF}: {len(r)} trades, PF {res['pf']}, PF@2x {res['pf_2x']}")
    print(f"median cost per trade: {np.median(cost_r):.4f}R "
          f"({COSTS[SYM].round_trip(EXEC_MODE):.2f}bps round trip)\n")

    # ---- item 3: cost sensitivity ------------------------------------- #
    print("ITEM 3 - what spread can gold pay?")
    print(f"{'x cost':>7}{'bps rt':>9}{'PF':>8}{'avgR':>9}{'days':>8}{'pass%':>8}{'blown%':>8}")
    costs = []
    for m in COST_MULTS:
        rm = r - (m - 1.0) * cost_r
        pf = float(rm[rm > 0].sum() / -rm[rm <= 0].sum()) if (rm <= 0).any() else np.nan
        lad = ladder(daily_of(rm, tr.exit_ts))
        row = {"mult": m, "bps": round(COSTS[SYM].round_trip(EXEC_MODE) * m, 2),
               "pf": round(pf, 3), "avg_r": round(float(rm.mean()), 4), **lad}
        costs.append(row)
        print(f"{m:7.1f}{row['bps']:9.2f}{row['pf']:8.3f}{row['avg_r']:9.4f}"
              f"{(row.get('days') or 0):8.1f}{(row.get('pass_pct') or 0):8.1f}"
              f"{(row.get('blown_pct') or 0):8.1f}", flush=True)

    # ---- item 4: evaluation-aware sizing -------------------------------- #
    print("\nITEM 4 - sizing that knows where the account stands (2% base risk)")
    print(f"{'schedule':18}{'pass%':>8}{'blown%':>8}{'open%':>8}{'medDays':>9}{'days':>8}")
    daily = daily_of(r, tr.exit_ts)
    sizing = []
    for sch in ("flat", "cut_dd", "cut_near_target", "budget"):
        s = run_scaled(daily, 0.02, sch)
        s["schedule"] = sch
        sizing.append(s)
        print(f"{sch:18}{s['pass_pct']:8.1f}{s['blown_pct']:8.1f}"
              f"{s['still_open_pct']:8.1f}{(s['median_days'] or 0):9.0f}"
              f"{(s['days'] or 0):8.1f}", flush=True)

    # ---- item 5: does the min-risk floor bind? --------------------------- #
    df = load(SYM, TF)
    df = df[(df.index >= span[0]) & (df.index <= span[1])]
    _, vwstd, _ = vwap_series(df, 0, 0)
    c = df.close.values
    live = df.volume.values > 0
    floor_bps = COSTS[SYM].min_risk_bps
    sd_bps = vwstd / np.where(c > 0, c, np.nan) * 1e4
    ok = np.isfinite(sd_bps) & live
    print(f"\nITEM 5 - the min-risk floor ({floor_bps}bps)")
    for k in WIDE_SIGMA:
        binds = float(np.nanmean((sd_bps[ok] * k) < floor_bps)) * 100
        print(f"  stop {k:4.1f} sigma -> floor binds on {binds:5.1f}% of bars "
              f"(median stop {np.nanmedian(sd_bps[ok]) * k:6.1f}bps)")

    dest = ROOT / "backtests" / "vwapbreak" / "tier1.json"
    dest.write_text(json.dumps({"cost_sensitivity": costs, "sizing": sizing},
                               indent=1, default=str))
    print(f"\nwrote {dest.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
