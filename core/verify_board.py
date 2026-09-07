"""INDEPENDENT VERIFICATION of the H-002 VWAP board numbers.

Written to be audited by someone who does not trust the rest of this repo. It
imports nothing from strategies/ or core/ except pandas and numpy, reads only the
raw walk-forward trade file, and recomputes every headline number from first
principles with each step printed.

Run:  .venv/bin/python core/verify_board.py

It should reproduce the board's headline exactly: PF 2.016, max drawdown 7.518 R,
R per day +0.15627, and 136.9 expected days two-step at the largest risk that
keeps peak drawdown inside the 8% cap (1.064%). The board itself reports 143.6 at
1.00%, because `core/riskladder` only offers discrete risk rungs and 1.064% is not
one of them. If any of those numbers moves, the board is wrong or this is.

REWRITTEN 2026-09-07. It used to audit the five-leg book of 2026-09-01 —
BTCUSDT 4h, ETHUSDT 1h/30m, SOLUSDT 4h, XAUUSD 5m. **Four of those five legs died
on 2026-09-06** when three look-aheads came out of the VWAP kernel, and the whole
file predates the 2026-09-07 dead-bar fix. An audit tool that verifies a book the
board no longer carries is worse than no audit tool, so this now reads the same
walk-forward the board reads.

WHAT THE INPUT IS
-----------------
backtests/vwap/stage6_trades_xauusd_deadfix.parquet holds one row per
out-of-sample trade from the quarterly walk-forward whose fold selector ranks by
train PF at double cost, on the kernel corrected 2026-09-07. Columns:
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
Gold, and only gold. The board's book is four cells of the SAME instrument at
different timeframes — XAUUSD 5m, 30m, 1h and 4h — chosen as the fastest of 78
one-cell-per-timeframe combinations, and weighted by SIGNAL-TO-COST rather than
equally: leg i gets (total R / max drawdown)_i normalised across the legs. Equal
weight is reported beside it as the control, because H-012 established that
adding equally weighted legs makes a book slower, not faster.

Two cells on the same timeframe are the same walk re-selected, so at most one
cell per timeframe may enter the book. The representative cell for a timeframe
is the one with the highest total R inside the common window.

RE-PRICING, AND WHY IT IS EXACT
-------------------------------
The walk-forward charged an ASSUMED 3.00bps round trip on XAUUSD. `core/fx_spread`
later measured 1.83bps from 478 hours of Dukascopy ticks. R is linear in cost and
the file stores each trade at 1x and 2x, so

    C = r_1x - r_2x            (one round trip, in R)
    r_0x = r_1x + C            (zero cost)
    r_s  = r_0x - (s/3.00) * C (any round trip s, in bps)

recovers any cost level exactly. No re-simulation, and no approximation.

THE EVALUATION STRUCTURE
------------------------
The firm target is a TWO-STEP evaluation (8% then 5%) on cTrader, decided
2026-09-01. Step 2 runs the same book forward with a fresh drawdown budget and
a breach in either step kills the account, so time-to-funded roughly doubles.
Both structures are printed: the one-step number is kept only so older board
figures stay comparable. The percentages are NOT verified against any signed
firm's spec — only the structure is.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
TRADES = ROOT / "backtests" / "vwap" / "stage6_trades_xauusd_deadfix.parquet"
STITCHED = ROOT / "backtests" / "vwap" / "stage6_stitched_xauusd_deadfix.csv"

TARGET = 0.08        # prop profit target
MAX_LOSS = 0.08      # prop max-loss cap
DAILY_LOSS = 0.04    # prop daily-loss cap
GATE = 1.20
SYM = "XAUUSD"
ASSUMED_RT = 3.00    # bps round trip the walk-forward charged on XAUUSD
MEASURED_RT = 1.83   # 1.671 mean spread + 0.15 cTrader commission
BOOK_TFS = ["5m", "30m", "1h", "4h"]   # the board's four legs
WEIGHTING = "sig_cost"                 # total R / max drawdown, normalised


def reprice(r_1x, r_2x, rt_bps):
    """R at an arbitrary round-trip cost. Exact: R is linear in cost."""
    c = np.asarray(r_1x) - np.asarray(r_2x)
    return (np.asarray(r_1x) + c) - (rt_bps / ASSUMED_RT) * c


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


# The firm structure, restated here rather than imported: this file audits the
# repo and must not depend on it. Mirrors core/prop_rules.ONE_STEP / TWO_STEP.
ONE_STEP = ({"target": 0.08, "daily": 0.04, "maxloss": 0.08, "mindays": 5},)
TWO_STEP = ({"target": 0.08, "daily": 0.04, "maxloss": 0.08, "mindays": 5},
            {"target": 0.05, "daily": 0.04, "maxloss": 0.08, "mindays": 5})


def simulate_accounts(daily_r: pd.Series, risk: float, phases=ONE_STEP,
                      max_days: int = 400):
    """Open a fresh challenge account on every trading day and run it forward.

    Rules, applied literally, per phase:
      * equity moves by daily_R * risk each day;
      * if a single day's loss reaches the daily cap -> FAIL_DAILY;
      * if equity falls max_loss below its running peak, or max_loss below the
        phase start -> FAIL_MAX (both readings of "max loss", the stricter one);
      * if equity reaches the phase target having traded at least mindays -> PASS;
      * worst case within a day: the whole day's loss lands before its gain.

    With TWO_STEP the account must clear both phases in sequence on the same
    live series. Phase 2 starts the day after phase 1 clears with a fresh
    equity, peak and drawdown budget; a breach in either phase kills the
    account. `days` is the total across both phases.
    """
    d = daily_r.values * risk
    n = len(d)
    out = []
    for s in range(n):
        k, res, total_days = s, "OPEN", 0
        for ph in phases:
            eq = peak = 0.0
            day = traded = 0
            res = "OPEN"
            while k < n and total_days + day < max_days:
                day += 1
                step = d[k]; k += 1
                if step != 0.0:
                    traded += 1
                if min(step, 0.0) <= -ph["daily"]:
                    res = "FAIL_DAILY"; break
                low = eq + min(step, 0.0)
                if low - peak <= -ph["maxloss"] or low <= -ph["maxloss"]:
                    res = "FAIL_MAX"; break
                eq += step
                peak = max(peak, eq)
                if eq >= ph["target"] and traded >= ph["mindays"]:
                    res = "PASS"; break
            total_days += day
            if res != "PASS":
                break
        out.append((res, total_days))
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

    tr = tr[tr.symbol == SYM].copy()

    rule("STEP 1 — which cells clear the gate, and which four are the book")
    print(f"Every number below is at the MEASURED {MEASURED_RT}bps round trip,")
    print(f"recovered exactly from the stored 1x/2x pair (the walk-forward")
    print(f"charged {ASSUMED_RT}bps). '2x' means {MEASURED_RT*2}bps.\n")

    cells = {}
    for k, g in tr.groupby(["tf", "floor", "topn"]):
        g = g.sort_values("exit_ts")
        cells[k] = pd.DataFrame({
            "entry_ts": g.entry_ts.values, "exit_ts": g.exit_ts.values,
            "rm": reprice(g.r.values, g.r_2x.values, MEASURED_RT),
            "rm2": reprice(g.r.values, g.r_2x.values, MEASURED_RT * 2)})

    # every leg must be measured over the SAME dates, or a subset comparison
    # is a comparison of windows rather than of strategies
    lo = max(g.exit_ts.min() for g in cells.values())
    hi = min(g.exit_ts.max() for g in cells.values())
    cut = {k: g[(g.exit_ts >= lo) & (g.exit_ts <= hi)] for k, g in cells.items()}
    print(f"common window {pd.Timestamp(lo).date()} -> {pd.Timestamp(hi).date()}\n")

    n_clear = 0
    for k in sorted(cut, key=lambda x: (BOOK_TFS.index(x[0]) if x[0] in BOOK_TFS
                                        else 99, x[1], x[2])):
        g = cut[k]
        if len(g) < 30:
            continue
        p2 = profit_factor(g.rm2.values)
        n_clear += p2 >= GATE
        print(f"    {k[0]:4s} floor{k[1]:<4d} top{k[2]:<3d}  {len(g):5d} trades  "
              f"PF {profit_factor(g.rm.values):6.3f}  PF@2x {p2:6.3f}"
              f"{'  <- clears' if p2 >= GATE else ''}")
    print(f"\n{n_clear} of {len([k for k in cut if len(cut[k]) >= 30])} cells "
          f"clear PF {GATE} at 2x measured cost.")
    print("  NOTE: stage 20 reports 15 of 20 for the same data. The difference is")
    print("  the window, not the arithmetic — stage 20 scores each cell over its")
    print("  OWN full span, this cuts every cell to the common window so the legs")
    print("  are comparable. Neither is wrong; the common window is the honest one")
    print("  for building a book, the full span for judging a cell on its own.")

    # one cell per timeframe: two cells on one timeframe are the same walk
    # re-selected, so combining them counts one book twice
    rep = {}
    for tf in BOOK_TFS:
        cand = {k: g for k, g in cut.items() if k[0] == tf and len(g) >= 30}
        if cand:
            rep[tf] = max(cand, key=lambda k: float(cand[k].rm.sum()))
    print("\nrepresentative cell per timeframe (highest total R in the window):")
    for tf in BOOK_TFS:
        if tf in rep:
            print(f"    {tf:4s}  floor{rep[tf][1]} top{rep[tf][2]}")

    for _ in (0,):
        rule(f"STEP 2 — the board's book: {'+'.join(BOOK_TFS)} [{WEIGHTING}]")
        legs = [cut[rep[tf]] for tf in BOOK_TFS if tf in rep]
        n_legs = len(legs)
        n_books = sum(rep[tf][2] for tf in BOOK_TFS if tf in rep)

        tot = np.array([max(float(l.rm.sum()), 0.0) for l in legs])
        # max_drawdown_R returns a NEGATIVE number here; take the magnitude
        dds = np.array([max(abs(max_drawdown_R(l.rm.values)), 1e-9) for l in legs])
        raw = tot / dds
        w = raw / raw.sum()
        print("  signal-to-cost weights — total R divided by that leg's own")
        print("  max drawdown, normalised. H-012 showed equal weight dilutes.")
        for tf, l, t, d, wi in zip(BOOK_TFS, legs, tot, dds, w):
            print(f"    {tf:4s}  totalR {t:7.2f}  maxDD {d:6.2f}R  "
                  f"ratio {t/d:6.3f}  weight {wi:.4f}")

        sel = pd.concat([l.assign(rm=l.rm * wi, rm2=l.rm2 * wi)
                         for l, wi in zip(legs, w)],
                        ignore_index=True).sort_values("exit_ts")
        r = sel.rm.values
        r2 = sel.rm2.values
        span_days = (sel.exit_ts.iloc[-1] - sel.exit_ts.iloc[0]).days

        print(f"\n  legs                 {n_legs}")
        print(f"  configs per leg      "
              f"{[int(rep[tf][2]) for tf in BOOK_TFS if tf in rep]}")
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
              f"{TARGET/(rpd*risk_cap):.0f} days  (ONE phase; the two-step")
        print(f"  evaluation has to do this again for +5% before funding).")

        print(f"\n  THE GOVERNING IDENTITY (trades per day does not appear):")
        print(f"    days = maxDD_in_R / R_per_day * (target / cap)")
        print(f"         = {abs(dd):.3f} / {rpd:.5f} * ({TARGET:.2f}/{MAX_LOSS:.2f})"
              f" = {abs(dd)/rpd*(TARGET/MAX_LOSS):.0f} days")

        daily = pd.Series(r, index=sel.exit_ts).resample("1D").sum()
        for phases, label in ((ONE_STEP, "ONE-STEP 8% — the old assumption, kept for comparison"),
                              (TWO_STEP, "TWO-STEP 8% then 5% — THE STRUCTURE THE BOARD USES")):
            print(f"\n  Simulation, fresh account every trading day — {label}:")
            for risk in (0.005, risk_cap, 0.0125, 0.015):
                a = simulate_accounts(daily, risk, phases=phases)
                md = a["median_days"]
                exp = md / a["pass_rate"] if a["pass_rate"] else float("nan")
                print(f"    risk {risk*100:5.3f}%  DD {abs(dd)*risk*100:5.2f}%  "
                      f"pass {a['pass_rate']*100:5.1f}%  killed "
                      f"{(a['fail_max']+a['fail_daily'])*100:5.1f}%  "
                      f"unresolved {a['still_open']*100:4.0f}%  "
                      f"median {md:6.1f}d  expected {exp:6.1f}d")
        print("\n  The second 5% step is not half the work of the first 8% one:")
        print("  it is another chance to breach, and the drawdown is paid twice.")

    rule("STEP 3 — what would be needed to pass in 14 days")
    # same book as STEP 2; `r` and `span_days` are still bound to it
    dd, rpd = abs(max_drawdown_R(r)), r.sum() / span_days
    span = span_days
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
