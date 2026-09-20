"""What a FUNDED account is worth — the half of the business never simulated.

THE GAP THIS CLOSES. `docs/FIRMS.md` scores 44 products on one number: expected
days to a funded account. `economics.py` prices the euros to get there. Neither
asks what happens next, and `FIRMS.md` says so itself about the trailing rows:
*"the trailing cap would bite on a funded account held for months, which this
table does not simulate."*

The business goal in `README.md` is income from 10-20 funded seats. Getting
funded is a cost, not a revenue. **Revenue is payouts**, and no number in this
repo is a payout.

WHAT IS AND IS NOT A SEARCH. This is arithmetic on a fixed series, exactly like
`firms.py` — the blind walk-forward daily R of H-027 gold 1h, run through a rule
set. No parameter is chosen to make a number look good, so nothing here is
charged to the trial ledger. The firm rules and the payout policy are INPUTS and
each is swept, because none of them is signed.

THE TWO READINGS OF A PAYOUT, and they are not close. Withdrawing profit drops
the balance back toward its start. Whether the drawdown floor follows it is the
single most important unsigned rule in the model:

    reset    max loss is measured from the STARTING balance. A withdrawal
             restores the full 6% buffer. The friendly reading.
    ratchet  max loss trails the equity high-water mark and a withdrawal does
             not lower it. The buffer never comes back. The punitive reading.

Both are run. If a firm's answer is `ratchet`, the seat is a different product.

Run: .venv/bin/python strategies/vwapbreak/research/funded.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from core.prop_rules import PropRules                              # noqa: E402

CACHE = ROOT / "backtests" / "vwapbreak" / "daily_traded.json"
OUT = ROOT / "backtests" / "vwapbreak" / "funded.json"
LEG = "XAUUSD|1h"

#: FundingPips 1-Step Flex — the row docs/FIRMS.md picked. EUR 61, cTrader,
#: no consistency rule, no minimum trading days. Third-party as of 2026-09-15.
EVAL = PropRules(profit_target=0.10, daily_loss=0.03, max_loss=0.06,
                 trailing=False, static=True, min_trading_days=0)
#: The funded seat: same caps, no target. A funded account is never "passed".
FUNDED = PropRules(profit_target=9.99, daily_loss=0.03, max_loss=0.06,
                   trailing=False, static=True, min_trading_days=0)

FEE_EUR = 61.0
ACCOUNT_EUR = 10_000.0
SPLIT = 0.80           #: trader's share of profit
HORIZON = 365          #: calendar days a seat is held before the count stops
MAX_EVAL_DAYS = 120

RISKS = (0.01, 0.015, 0.02, 0.025, 0.03, 0.04)
PAYOUT_EVERY = (14, 30, 60)


def series() -> pd.Series:
    v = json.loads(CACHE.read_text())[LEG]
    return pd.Series(v["r"], index=pd.date_range(v["t0"], periods=len(v["r"]),
                                                 freq="D"))


def _run_eval(d: np.ndarray, s: int, risk: float, rules: PropRules):
    """Returns (passed, index_of_day_after_pass)."""
    eq = peak = 0.0
    n = len(d)
    for k in range(s, min(s + MAX_EVAL_DAYS, n)):
        step = d[k] * risk
        if min(step, 0.0) <= -rules.daily_loss:
            return False, k
        low = eq + min(step, 0.0)
        if (rules.trailing and low - peak <= -rules.max_loss) or \
           (rules.static and low <= -rules.max_loss):
            return False, k
        eq += step
        peak = max(peak, eq)
        if eq >= rules.profit_target:
            return True, k + 1
    return False, min(s + MAX_EVAL_DAYS, n)


def _run_funded(d: np.ndarray, s: int, risk: float, rules: PropRules,
                every: int, floor_mode: str):
    """One funded seat from day s. Returns (payout_pct, days_alive, died)."""
    eq = peak = 0.0          # profit above the CURRENT balance, in account %
    banked = 0.0             # cumulative gross profit withdrawn, account %
    floor = -rules.max_loss  # the equity level that kills the account
    n = len(d)
    end = min(s + HORIZON, n)
    for k in range(s, end):
        step = d[k] * risk
        if min(step, 0.0) <= -rules.daily_loss:
            return banked, k - s, True
        low = eq + min(step, 0.0)
        if low <= floor or (rules.trailing and low - peak <= -rules.max_loss):
            return banked, k - s, True
        eq += step
        peak = max(peak, eq)
        if (k - s + 1) % every == 0 and eq > 0.0:
            banked += eq
            if floor_mode == "reset":
                eq = peak = 0.0
                floor = -rules.max_loss
            else:                       # ratchet: the floor does not come back
                floor = max(floor, peak - rules.max_loss) - eq
                eq = 0.0
                peak = 0.0
    return banked, end - s, False


def seat(daily: pd.Series, risk: float, every: int, floor_mode: str) -> dict:
    d = daily.values
    n = len(d)
    rows = []
    for s in range(n):
        ok, k = _run_eval(d, s, risk, EVAL)
        if not ok:
            rows.append((False, 0.0, 0, False))
            continue
        pay, alive, died = _run_funded(d, k, risk, FUNDED, every, floor_mode)
        rows.append((True, pay, alive, died))
    df = pd.DataFrame(rows, columns=["funded", "gross_pct", "days", "died"])
    f = df[df.funded]
    pass_rate = len(f) / len(df) if len(df) else 0.0
    if not len(f):
        return {"risk_pct": risk * 100, "every": every, "floor": floor_mode,
                "pass_pct": 0.0, "eur_per_seat": None, "payout_eur": 0.0,
                "paid_pct": 0.0, "died_pct": 0.0, "roi": None}
    net = f.gross_pct * SPLIT * ACCOUNT_EUR
    fee_per_seat = FEE_EUR / pass_rate
    return {
        "risk_pct": risk * 100,
        "every": every,
        "floor": floor_mode,
        "pass_pct": round(pass_rate * 100, 1),
        "eur_per_seat": round(fee_per_seat, 0),
        "payout_eur": round(float(net.mean()), 0),
        "payout_med_eur": round(float(net.median()), 0),
        "paid_pct": round(float((f.gross_pct > 0).mean()) * 100, 1),
        "died_pct": round(float(f.died.mean()) * 100, 1),
        "days_alive": round(float(f.days.median()), 0),
        "roi": round(float(net.mean()) / fee_per_seat, 2),
    }


def tradeoff(daily: pd.Series, risks=(0.0025, 0.003, 0.0035, 0.004, 0.005,
                                     0.0075, 0.01, 0.02, 0.04)) -> list[dict]:
    """The table that answers the pace target. Speed and survival, same rungs.

    `MAX_EVAL_DAYS` is raised here so the slow rungs resolve instead of being
    scored as failures - a 120-day cap makes a 78-day median look like a
    rejection.
    """
    global MAX_EVAL_DAYS
    keep, MAX_EVAL_DAYS = MAX_EVAL_DAYS, 400
    d = daily.values
    out = []
    print("\n=== SPEED vs SURVIVAL — the same account, both halves ===")
    print(f"{'risk':>6} {'DD budget':>10} {'eval pass%':>11} {'med days':>9} "
          f"{'seat died%':>11} {'med alive':>10}")
    for x in risks:
        days = [k - s for s in range(len(d))
                for ok, k in [_run_eval(d, s, x, EVAL)] if ok]
        st = seat(daily, x, 30, "reset")
        med = float(np.median(days)) if days else None
        out.append({"risk_pct": x * 100, "dd_budget_r": round(0.06 / x, 1),
                    "pass_pct": st["pass_pct"], "median_days": med,
                    "died_pct": st["died_pct"],
                    "days_alive": st.get("days_alive")})
        print(f"{x*100:>5.2f}% {0.06/x:>9.1f}R {st['pass_pct']:>11} "
              f"{str(med):>9} {st['died_pct']:>11} "
              f"{str(st.get('days_alive')):>10}")
    MAX_EVAL_DAYS = keep
    return out


def ablate(daily: pd.Series, drops=(0, 1, 2, 3, 5, 10)) -> list[dict]:
    """Zero the N largest days and re-run. The concentration test."""
    r = daily.values.copy()
    order = np.argsort(r)[::-1]
    out = []
    print("\n=== LEAVE-THE-BEST-DAYS-OUT, risk 2% ===")
    print(f"{'dropped':>8} {'total R':>9} {'eval pass%':>11} "
          f"{'net EUR/slot-yr':>16}")
    for n in drops:
        rr = r.copy()
        if n:
            rr[order[:n]] = 0.0
        s = pd.Series(rr, index=daily.index)
        st = seat(s, 0.02, 30, "reset")
        sl = slot(s, 0.02, 30, "reset")
        out.append({"dropped": n, "total_r": round(float(rr.sum()), 1),
                    "pass_pct": st["pass_pct"],
                    "net_med_eur": sl["net_med_eur"]})
        print(f"{n:>8} {rr.sum():>9.1f} {st['pass_pct']:>11} "
              f"{sl['net_med_eur']:>16.0f}")
    return out


def main() -> int:
    daily = series()
    r = daily.values
    eq = np.cumsum(r)
    dd = float((eq - np.maximum.accumulate(eq)).min())
    rpd = float(r.mean())
    print(f"{LEG}  {len(daily)} days  {daily.index[0].date()} -> "
          f"{daily.index[-1].date()}  total {r.sum():.1f} R")
    print(f"max DD {abs(dd):.1f} R   R/day {rpd:.4f}")
    print(f"README formula: {abs(dd):.1f} / {rpd:.4f} x (10/6) = "
          f"{abs(dd)/rpd*10/6:.0f} days for a SURVIVABLE seat")
    print(f"one seat = EUR {ACCOUNT_EUR:,.0f}, {SPLIT:.0%} split, "
          f"EUR {FEE_EUR:.0f}/evaluation, {HORIZON}d horizon\n")

    seats = []
    for floor_mode in ("reset", "ratchet"):
        print(f"--- one evaluation, payout floor: {floor_mode} ---")
        print(f"{'risk':>5} {'payout':>7} {'pass%':>6} {'EUR/seat':>9} "
              f"{'payout EUR':>11} {'median':>8} {'everpaid%':>10} "
              f"{'died%':>6} {'alive':>6} {'ROI':>6}")
        for risk in RISKS:
            for every in PAYOUT_EVERY:
                x = seat(daily, risk, every, floor_mode)
                seats.append(x)
                print(f"{x['risk_pct']:>4.1f}% {x['every']:>6}d "
                      f"{x['pass_pct']:>6} {str(x['eur_per_seat']):>9} "
                      f"{str(x['payout_eur']):>11} "
                      f"{str(x.get('payout_med_eur')):>8} "
                      f"{x['paid_pct']:>10} {x['died_pct']:>6} "
                      f"{str(x.get('days_alive')):>6} {str(x['roi']):>6}")
        print()

    tr = tradeoff(daily)
    sl = slots(daily)
    ab = ablate(daily)
    OUT.write_text(json.dumps(
        {"leg": LEG, "account_eur": ACCOUNT_EUR, "split": SPLIT,
         "fee_eur": FEE_EUR, "horizon_days": HORIZON,
         "max_dd_r": round(abs(dd), 2), "r_per_day": round(rpd, 4),
         "seats": seats, "tradeoff": tr, "slots": sl, "ablation": ab},
        indent=1))
    print(f"\nwrote {OUT.relative_to(ROOT)}")
    return 0




# ---------------------------------------------------------------------------
# THE BUSINESS NUMBER: one SEAT SLOT held for a year.
#
# The table above prices one evaluation. It is not what the business does. The
# business keeps a seat slot occupied: buy an evaluation, fail it, buy another,
# pass, get funded, trade until the seat dies, buy another. What matters is the
# net euros that slot produces in a year and nothing above measures it, because
# every row stops at the first outcome.
#
# So: run the calendar. Spend a fee on every attempt, bank every payout, and
# report net. This is the number that decides whether 10-20 seats is a business.
# ---------------------------------------------------------------------------

def slot(daily: pd.Series, risk: float, every: int, floor_mode: str,
         year: int = 365) -> dict:
    """One seat slot run for `year` days from every start day, re-buying."""
    d = daily.values
    n = len(d)
    rows = []
    for s0 in range(n - year):
        k, spent, gross, attempts, funded_days = s0, 0.0, 0.0, 0, 0
        stop = s0 + year
        while k < stop:
            spent += FEE_EUR
            attempts += 1
            ok, k2 = _run_eval(d, k, risk, EVAL)
            if k2 >= stop:
                k = stop
                break
            if not ok:
                k = k2 + 1
                continue
            pay, alive, died = _run_funded(d, k2, risk, FUNDED, every,
                                           floor_mode)
            gross += pay
            funded_days += min(alive, stop - k2)
            k = k2 + alive + 1
        net = gross * SPLIT * ACCOUNT_EUR - spent
        rows.append((net, spent, gross * SPLIT * ACCOUNT_EUR, attempts,
                     funded_days))
    df = pd.DataFrame(rows, columns=["net", "spent", "paid", "attempts",
                                     "funded_days"])
    return {
        "risk_pct": risk * 100,
        "every": every,
        "floor": floor_mode,
        "net_mean_eur": round(float(df.net.mean()), 0),
        "net_med_eur": round(float(df.net.median()), 0),
        "p25_eur": round(float(df.net.quantile(0.25)), 0),
        "p75_eur": round(float(df.net.quantile(0.75)), 0),
        "loss_prob_pct": round(float((df.net < 0).mean()) * 100, 1),
        "fees_eur": round(float(df.spent.mean()), 0),
        "attempts": round(float(df.attempts.mean()), 1),
        "funded_days": round(float(df.funded_days.mean()), 0),
    }


def slots(daily: pd.Series, risks=(0.002, 0.003, 0.004, 0.005, 0.0075,
                                   0.01, 0.015, 0.02, 0.03, 0.04),
          every: int = 30, floor_mode: str = "reset") -> list[dict]:
    print(f"\n=== ONE SEAT SLOT, {365}d, payout every {every}d, "
          f"floor={floor_mode} ===")
    print(f"{'risk':>6} {'net mean':>9} {'net med':>9} {'p25':>8} {'p75':>9} "
          f"{'P(loss)':>8} {'fees':>7} {'tries':>6} {'funded d':>9}")
    out = []
    for r in risks:
        x = slot(daily, r, every, floor_mode)
        out.append(x)
        print(f"{x['risk_pct']:>5.2f}% {x['net_mean_eur']:>9.0f} "
              f"{x['net_med_eur']:>9.0f} {x['p25_eur']:>8.0f} "
              f"{x['p75_eur']:>9.0f} {x['loss_prob_pct']:>8} "
              f"{x['fees_eur']:>7.0f} {x['attempts']:>6} "
              f"{x['funded_days']:>9.0f}")
    return out


if __name__ == "__main__":
    raise SystemExit(main())
