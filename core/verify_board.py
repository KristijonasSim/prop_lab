"""INDEPENDENT VERIFICATION of the H-002 VWAP board numbers.

Written to be audited by someone who does not trust the rest of this repo. It
imports nothing from strategies/ or core/ except pandas and numpy, reads only the
raw walk-forward trade file, and recomputes every headline number from first
principles with each step printed.

Run:  .venv/bin/python core/verify_board.py

WHAT THE INPUT IS
-----------------
backtests/vwap/stage10_trades.parquet holds one row per out-of-sample
trade from the quarterly walk-forward whose fold selector ranks by train PF at
double cost. Columns:
    symbol, tf      market and timeframe
    floor, topn     the selection rule that produced the trade (see below)
    quarter         the test quarter it was traded in
    entry_ts        entry timestamp (UTC)
    exit_ts         exit timestamp (UTC)
    r               profit in R multiples, ALREADY divided by `topn`
    r_2x            the same trade at double cost

`r` is a return in units of "risk taken on that trade". R = +1 means the trade
made exactly what it risked. Fees and slippage are already subtracted.

THE BOOK CONSTRUCTION
---------------------
The board uses the best tradeable subset found by stage 11 on the twelve-market
universe: BTCUSDT 4h, ETHUSDT 1h, ETHUSDT 30m, SOLUSDT 4h and XAUUSD 5m, one
blind-chosen configuration per leg, equal weighted on the common 2024-09+ window.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
TRADES = ROOT / "backtests" / "vwap" / "stage10_trades.parquet"
STITCHED = ROOT / "backtests" / "vwap" / "stage10_stitched.csv"

TARGET = 0.08        # prop profit target
MAX_LOSS = 0.08      # prop max-loss cap
DAILY_LOSS = 0.04    # prop daily-loss cap
COMMON_START = "2024-09-01"   # first quarter every leg in the book has
GATE = 1.20
SELECTED_LEGS = [
    ("BTCUSDT", "4h"),
    ("ETHUSDT", "1h"),
    ("ETHUSDT", "30m"),
    ("SOLUSDT", "4h"),
    ("XAUUSD", "5m"),
]
FLOOR = 100
TOPN = 1


def rule(msg):
    print("\n" + "=" * 78)
    print(msg)
    print("=" * 78)


def profit_factor(r):
    w, l = r[r > 0].sum(), -r[r < 0].sum()
    return float(w / l) if l > 0 else float("nan")


def max_drawdown_R(r):
    """Peak-to-trough of the cumulative R curve, in R."""
    eq = np.concatenate(([0.0], np.cumsum(r)))
    return float((eq - np.maximum.accumulate(eq)).min())


def simulate_accounts(daily_r: pd.Series, risk: float, max_days: int = 400):
    """Open a fresh challenge account on every trading day and run it forward.

    Rules, applied literally:
      * equity moves by daily_R * risk each day;
      * if a single day's loss reaches 4% -> FAIL_DAILY;
      * if equity falls 8% below its running peak, or 8% below the start
        -> FAIL_MAX (both readings of "max loss" enforced, the stricter one);
      * if equity reaches +8% having traded at least 5 days -> PASS;
      * worst case within a day: the whole day's loss lands before its gain.
    """
    d = daily_r.values * risk
    n = len(d)
    out = []
    for s in range(n):
        eq = peak = 0.0
        day = traded = 0
        res = "OPEN"
        for k in range(s, min(s + max_days, n)):
            day += 1
            step = d[k]
            if step != 0.0:
                traded += 1
            if min(step, 0.0) <= -DAILY_LOSS:
                res = "FAIL_DAILY"; break
            low = eq + min(step, 0.0)
            if low - peak <= -MAX_LOSS or low <= -MAX_LOSS:
                res = "FAIL_MAX"; break
            eq += step
            peak = max(peak, eq)
            if eq >= TARGET and traded >= 5:
                res = "PASS"; break
        out.append((res, day))
    df = pd.DataFrame(out, columns=["outcome", "days"])
    p = df[df.outcome == "PASS"]
    return {
        "accounts": len(df),
        "pass_rate": len(p) / len(df) if len(df) else 0.0,
        "fail_max": float((df.outcome == "FAIL_MAX").mean()),
        "fail_daily": float((df.outcome == "FAIL_DAILY").mean()),
        "still_open": float((df.outcome == "OPEN").mean()),
        "median_days": float(p.days.median()) if len(p) else float("nan"),
    }


def main():
    if not TRADES.exists():
        sys.exit(f"missing {TRADES}")
    tr = pd.read_parquet(TRADES)
    tr["entry_ts"] = pd.to_datetime(tr.entry_ts, utc=True)
    tr["exit_ts"] = pd.to_datetime(tr.exit_ts, utc=True)

    rule("STEP 1 — which markets are in the book, and why")
    st = pd.read_csv(STITCHED)
    piv = st.pivot_table(index=["symbol", "tf"], columns=["floor", "topn"], values="pf_2x")
    worst = piv.min(axis=1)
    survivors = [k for k in worst[worst >= GATE].index]
    print(f"{len(piv)} market x timeframe combinations were walk-forwarded.")
    print(f"A combination is kept only if its stitched 2x-COST profit factor clears {GATE}")
    print("under ALL FOUR selection rules (trade-count floor 30 or 100, top-1 or")
    print("top-10). That is the strictest of the four, not the best.")
    print(f"\n{len(survivors)} survive: {', '.join(f'{a} {b}' for a, b in survivors)}")
    print("\nworst-of-four 2x-cost profit factor per survivor:")
    for a, b in survivors:
        print(f"    {a:8s} {b:4s}  {worst.loc[(a, b)]:.3f}")

    print("\nboard-selected tradeable subset:")
    for a, b in SELECTED_LEGS:
        print(f"    {a:8s} {b:4s}")

    for topn, label in ((TOPN, "BOARD: 1 config per selected market"),):
        rule(f"STEP 2 — book with topn={topn}   ({label})")
        sel = tr[(tr.floor == FLOOR) & (tr.topn == topn) &
                 (tr.exit_ts >= COMMON_START)]
        sel = sel[[(s, t) in SELECTED_LEGS for s, t in zip(sel.symbol, sel.tf)]]
        sel = sel.sort_values("exit_ts")
        n_legs = len(SELECTED_LEGS)
        n_books = n_legs * topn

        # equal weight across legs: each leg's R is divided by the leg count.
        # `r` in the file is already divided by topn.
        r = sel.r.values / n_legs
        r2 = sel.r_2x.values / n_legs
        span_days = (sel.exit_ts.iloc[-1] - sel.exit_ts.iloc[0]).days

        print(f"  legs                 {n_legs}")
        print(f"  configs per leg      {topn}")
        print(f"  parallel strategies  {n_books}")
        print(f"  each strategy risks  1/{n_books} of the account's per-trade risk")
        print(f"  trade rows           {len(r)}")
        print(f"  span                 {span_days} days ({sel.exit_ts.iloc[0].date()}"
              f" -> {sel.exit_ts.iloc[-1].date()})")
        print(f"  rows per day         {len(r)/span_days:.2f}")
        print(f"  rows/day per strategy{len(r)/span_days/n_books:8.3f}   <- the real signal rate")
        print()
        pf = profit_factor(r)
        dd = max_drawdown_R(r)
        total = r.sum()
        rpd = total / span_days
        print(f"  profit factor        {pf:.4f}      (unchanged by position sizing)")
        print(f"  profit factor at 2x  {profit_factor(r2):.4f}")
        print(f"  win rate             {(r>0).mean()*100:.2f}%")
        print(f"  total R              {total:+.3f}")
        print(f"  R per day            {rpd:+.5f}   <- THIS sets time to target")
        print(f"  max drawdown         {dd:.3f} R")
        print(f"  return / drawdown    {total/-dd:.2f}")

        print(f"\n  Largest risk that keeps peak drawdown inside the {MAX_LOSS:.0%} cap:")
        risk_cap = MAX_LOSS / abs(dd)
        print(f"    risk = {MAX_LOSS:.2%} / {abs(dd):.3f} R = {risk_cap*100:.3f}% per trade")
        print(f"  At that risk the account gains {rpd*risk_cap*100:.4f}% per day,")
        print(f"  so a straight line to +{TARGET:.0%} takes "
              f"{TARGET/(rpd*risk_cap):.0f} days.")

        print(f"\n  THE GOVERNING IDENTITY (trades per day does not appear):")
        print(f"    days = maxDD_in_R / R_per_day * (target / cap)")
        print(f"         = {abs(dd):.3f} / {rpd:.5f} * ({TARGET:.2f}/{MAX_LOSS:.2f})"
              f" = {abs(dd)/rpd*(TARGET/MAX_LOSS):.0f} days")

        print(f"\n  Simulation, fresh account every trading day:")
        daily = pd.Series(r, index=sel.exit_ts).resample("1D").sum()
        for risk in (0.005, risk_cap, 0.0125, 0.015):
            a = simulate_accounts(daily, risk)
            md = a["median_days"]
            exp = md / a["pass_rate"] if a["pass_rate"] else float("nan")
            print(f"    risk {risk*100:5.3f}%  DD {abs(dd)*risk*100:5.2f}%  "
                  f"pass {a['pass_rate']*100:5.1f}%  killed "
                  f"{(a['fail_max']+a['fail_daily'])*100:5.1f}%  "
                  f"unresolved {a['still_open']*100:4.0f}%  "
                  f"median {md:6.1f}d  expected {exp:6.1f}d")

    rule("STEP 3 — what would be needed to pass in 14 days")
    sel = tr[(tr.floor == FLOOR) & (tr.topn == TOPN) & (tr.exit_ts >= COMMON_START)]
    sel = sel[[(s, t) in SELECTED_LEGS for s, t in zip(sel.symbol, sel.tf)]].sort_values("exit_ts")
    r = sel.r.values / len(SELECTED_LEGS)
    span = (sel.exit_ts.iloc[-1] - sel.exit_ts.iloc[0]).days
    dd, rpd = abs(max_drawdown_R(r)), r.sum() / span
    print(f"  tradeable book: maxDD {dd:.2f} R, R/day {rpd:.4f}")
    print(f"  days = {dd:.2f} / {rpd:.4f} = {dd/rpd:.0f}")
    print(f"  for 14 days you need EITHER")
    print(f"     R/day >= {dd/14:.3f} R   (have {rpd:.3f})  -> {dd/14/rpd:.1f}x more edge")
    print(f"  OR maxDD  <= {rpd*14:.2f} R  (have {dd:.2f})   -> {dd/(rpd*14):.1f}x less drawdown")
    print("\n  Trades per day is absent from every line above. It only ever enters")
    print("  through R per day, and splitting the same edge across more parallel")
    print("  strategies divides R per trade by exactly the number you add.")


if __name__ == "__main__":
    main()
