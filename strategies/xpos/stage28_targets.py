"""How long to pass, at a 5%, 6% or 8% profit target?

The board reports one structure - the two-step 8% then 5% chosen on 2026-09-01 -
because that is what the firms shortlisted actually sell. Kris asked the other
question: if the target were a single 5%, 6% or 8% step, how many days?

Everything else is held at the project's standing assumptions: 4% daily loss,
8% max loss enforced both static and trailing, 5 minimum trading days. Only the
profit target moves, so the columns are comparable to each other and to the
board.

RISK IS RE-CHOSEN PER STRUCTURE, INSIDE THE FIT WINDOW. A lower target is worth
less risk per trade - the account has less to gain and the same amount to lose -
so holding 0.50% across all four would report the wrong number for three of
them. Each structure picks its own risk on the fit half and is then run blind on
the test half, which is the same discipline stage 18 applied to the leg count.

Two books, both exactly as their stages left them: the H-017 baseline and the
stage 23 volatility-managed overlay.

The number to read is `all-in days`, not `median days`. Median days counts only
the accounts that passed; all-in adds the ones that died on the way, which is
what actually stands between Kris and a funded account.

Output: backtests/xpos/stage28_targets.csv
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from core.prop_rules import PropRules                               # noqa: E402
from strategies.xpos.stage18_nested import (allin, build, gated,    # noqa: E402
                                            rank_legs)
from strategies.xpos.stage23_volmanaged import multiplier           # noqa: E402

OUT = ROOT / "backtests" / "xpos"
LEG_COUNTS = (4, 6, 8, 10, 12, 14, 17, 20, 25)
RISKS = (0.0025, 0.005, 0.0075, 0.01, 0.015, 0.02)
MAX_DAYS = 400

STRUCTURES = {
    "one-step 5%": (PropRules(profit_target=0.05),),
    "one-step 6%": (PropRules(profit_target=0.06),),
    "one-step 8%": (PropRules(profit_target=0.08),),
    "two-step 8%+5% (board)": (PropRules(profit_target=0.08),
                               PropRules(profit_target=0.05)),
}


def first_account(d: np.ndarray, phases) -> tuple[bool, int]:
    """One account opened on day 0. Same rules as `stage17._first_account`,
    but the phase list is an argument instead of being hard-coded."""
    k, total = 0, 0
    n = len(d)
    for rules in phases:
        eq = peak = 0.0
        day = traded = 0
        passed = False
        while k < n and total + day < MAX_DAYS:
            day += 1
            step = d[k]; k += 1
            if step != 0.0:
                traded += 1
            if min(step, 0.0) <= -rules.daily_loss:
                break
            low = eq + min(step, 0.0)
            if low - peak <= -rules.max_loss or low <= -rules.max_loss:
                break
            eq += step
            peak = max(peak, eq)
            if eq >= rules.profit_target and traded >= rules.min_trading_days:
                passed = True
                break
        total += day
        if not passed:
            return False, total
    return True, total


def stats(dv: np.ndarray, risk: float, phases) -> dict:
    starts = list(range(0, max(len(dv) - MAX_DAYS, 1), 7))
    if len(starts) < 10:
        return {}
    res = [first_account(dv[s0:] * risk, phases) for s0 in starts]
    ok = [d for p, d in res if p]
    bad = [d for p, d in res if not p]
    if not ok:
        return {"pass_rate": 0.0, "median_days": None, "allin_days": None}
    pr = len(ok) / len(res)
    wasted = float(np.mean(bad)) if bad else 0.0
    med = float(np.median(ok))
    return {"pass_rate": round(pr, 4), "median_days": med,
            "p25_days": float(np.percentile(ok, 25)),
            "p75_days": float(np.percentile(ok, 75)),
            "allin_days": round(med + (1 / pr - 1) * wasted, 1),
            "accounts": round(1 / pr, 2)}


def main() -> int:
    t = pd.read_parquet(OUT / "stage14_trades.parquet")
    t["entry_ts"] = pd.to_datetime(t.entry_ts, utc=True)
    t["exit_ts"] = pd.to_datetime(t.exit_ts, utc=True)
    t = t[t.topn == 1].sort_values("exit_ts")
    g0 = gated(t)
    mid = g0.exit_ts.quantile(0.5)
    f_lo, f_hi, s_lo, s_hi = g0.exit_ts.min(), mid, mid, g0.exit_ts.max()
    print(f"FIT   {f_lo:%Y-%m-%d} -> {f_hi:%Y-%m-%d}")
    print(f"TEST  {s_lo:%Y-%m-%d} -> {s_hi:%Y-%m-%d}")
    print("rules held fixed: 4% daily loss, 8% max loss "
          "(static AND trailing), 5 min trading days\n")

    order = rank_legs(g0[g0.exit_ts <= mid])
    best = None
    for n in LEG_COUNTS:
        if n > len(order):
            continue
        _, dv = build(g0[g0.exit_ts <= mid], order[:n], f_lo, f_hi)
        if dv is None:
            continue
        for risk in RISKS:
            a = allin(dv, risk)
            if a and a.get("allin_days") and (
                    best is None or a["allin_days"] < best["allin_days"]):
                best = {"n": n, "risk": risk, **a}
    keys = order[:best["n"]]
    print(f"{best['n']} legs, chosen on the fit window\n")

    _, dv_fit = build(g0[g0.exit_ts <= mid], keys, f_lo, f_hi)
    _, dv_test = build(g0[g0.exit_ts > mid], keys, s_lo, s_hi)
    m_fit, target = multiplier(dv_fit, 10, 0.25, 3.0)
    m_test, _ = multiplier(dv_test, 10, 0.25, 3.0, target=target)

    books = {"H-017 baseline": (dv_fit, dv_test),
             "H-018 vol-managed": (dv_fit * m_fit, dv_test * m_test)}

    rows = []
    for label, phases in STRUCTURES.items():
        print(f"{label}")
        print(f"   {'book':22s} {'risk':>6s} {'pass':>7s} {'median d':>9s} "
              f"{'p25-p75':>12s} {'all-in d':>9s} {'accts':>6s}")
        for bk, (fit, test) in books.items():
            # risk chosen on the FIT window for THIS structure
            pick = None
            for risk in RISKS:
                a = stats(fit, risk, phases)
                if a and a.get("allin_days") and (
                        pick is None or a["allin_days"] < pick[1]["allin_days"]):
                    pick = (risk, a)
            if pick is None:
                print(f"   {bk:22s} {'nothing admissible on the fit half':>50s}")
                continue
            risk = pick[0]
            a = stats(test, risk, phases)
            if not a or not a.get("allin_days"):
                print(f"   {bk:22s} {risk*100:>5.2f}% "
                      f"{'never passes on the test half':>44s}")
                continue
            print(f"   {bk:22s} {risk*100:>5.2f}% {a['pass_rate']*100:>6.1f}% "
                  f"{a['median_days']:>9.0f} "
                  f"{a['p25_days']:>5.0f}-{a['p75_days']:<6.0f} "
                  f"{a['allin_days']:>9.1f} {a['accounts']:>6.2f}")
            rows.append({"structure": label, "book": bk, "risk": risk, **a})
        print()

    pd.DataFrame(rows).to_csv(OUT / "stage28_targets.csv", index=False)
    print(f"wrote {OUT / 'stage28_targets.csv'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
