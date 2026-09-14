"""H-039 — mark the book to market, and see whether the board's caps survive it.

THE PRE-REGISTRATION IS `MARKTOMARKET.md` AND IT WAS WRITTEN FIRST. Read it
before reading any number this file prints; it fixes the claim, the kill
criterion and what counts as a false positive.

In one line: `core/board.py:45` builds the daily series by booking a trade's
whole R on the day it EXITS, so a position open for sixteen days contributes
nothing on the fifteen days in between. A real evaluation measures its daily and
maximum drawdown on EQUITY, which moves every day the position is open.

WHAT THIS FILE CHANGES: which day an R is attributed to. Nothing else. Same
trades, same folds, same configuration, same costs. No grid is searched and
nothing is re-selected - the same standing this repo gives the risk ladder.

Run: .venv/bin/python strategies/vwapbreak/research/marktomarket.py
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
from core.strategy import T_DIR, T_ENTRY_I, T_ENTRY_PX             # noqa: E402
from core.strategy import T_EXIT_I, T_EXIT_PX, T_R                 # noqa: E402
from strategies.vwapbreak.strategy import STRATEGY                 # noqa: E402

#: Thunderbolt, the firm chosen 2026-09-08 and the one `core/chosen.py` is
#: priced against. `exitshape.py` used Upcomers Ash (2% target) and its numbers
#: are therefore NOT comparable with anything here.
THUNDERBOLT = PropRules(profit_target=0.06, daily_loss=0.03, max_loss=0.06,
                        min_trading_days=0)
RISKS = (0.01, 0.015, 0.02, 0.03)
SYM, TF = "XAUUSD", "1h"


class Recorder:
    """The shipped strategy, plus a note of everything the kernel produced.

    A DELEGATE, NOT A COPY. `exitshape.py` copies the kernel because it changes
    the exit rule and must not touch the shipped one. This file changes no rule
    at all, so copying would introduce exactly the risk it is trying to measure
    - two kernels that might disagree. Every call goes to the shipped object and
    the array it returns is kept as a side effect.
    """

    def __init__(self, inner) -> None:
        self.inner, self.name = inner, inner.name
        self.seen: list[tuple[pd.DataFrame, np.ndarray]] = []

    def features(self, df, *a, **kw):
        return self.inner.features(df, *a, **kw)

    def grid(self, *a, **kw):
        return self.inner.grid(*a, **kw)

    def run(self, df, cfg, fee_bps, slip_bps, **kw):
        out = self.inner.run(df, cfg, fee_bps, slip_bps, **kw)
        if len(out):
            # THE COST IS KEPT WITH THE ARRAY. Risk in price terms is recovered
            # exactly from the kernel's own booking identity, which needs it:
            #   r = ((exit-entry)*side - (entry+exit)*cost/2) / risk
            self.seen.append((df, out, (fee_bps + slip_bps) / 1e4))
        return out


def match(tr: pd.DataFrame, seen: list) -> list[dict]:
    """Every selected trade, matched back to the kernel array that produced it.

    MATCHED ON ENTRY TIMESTAMP, EXIT TIMESTAMP AND R TOGETHER, and the caller
    requires 100%. Two of those three would be enough to be nearly right, and
    "nearly right" reconstruction is how this repo has produced numbers it later
    had to withdraw. A trade that cannot be matched exactly is not guessed at.

    THE BOOK'S R IS THE KERNEL'S R DIVIDED BY `topn`. Five settings run in
    parallel at a fifth of the risk each, so the pipeline scales every trade
    down before stitching. The first version of this matcher compared the two
    directly and matched 7 of 813; the factor is exact (5.0 to the last bit on
    the first trade checked) and it is read from the trade's own `topn` column
    rather than assumed, because the floors/topn grid is a parameter.
    """
    index: dict[tuple, dict] = {}
    for df, arr, cost in seen:
        idx = df.index
        for row in arr:
            ei, xi = int(row[T_ENTRY_I]), int(row[T_EXIT_I])
            if ei >= len(idx) or xi >= len(idx):
                continue
            key = (idx[ei], idx[xi], round(float(row[T_R]), 9))
            index.setdefault(key, {"bars": df, "row": row, "cost": cost})

    out, missed = [], 0
    for t in tr.itertuples():
        key = (t.entry_ts, t.exit_ts, round(float(t.r) * int(t.topn), 9))
        hit = index.get(key)
        if hit is None:
            missed += 1
            continue
        out.append({**hit, "topn": int(t.topn)})
    if missed:
        raise SystemExit(f"STOPPED: {missed} of {len(tr)} trades did not match "
                         f"exactly. The pre-registration says a partial match "
                         f"stops the study rather than reconstructing.")
    return out


def paths(matched: list) -> tuple[pd.Series, float]:
    """Daily change in equity, in book R, with open positions marked to market.

    RISK IN PRICE TERMS IS RECOVERED EXACTLY, not approximated. The kernel books
    `r = (gross - fees) / risk` with `gross = (exit - entry) * side` and
    `fees = (entry + exit) * cost / 2`, so `risk` follows from quantities the
    array already carries once the cost is kept alongside it. Every trade is
    then re-priced from that `risk` and checked back against the `r` the kernel
    wrote; a mismatch anywhere stops the study.

    THE FIRST VERSION USED THE BAR'S CLOSE AS THE EXIT PRICE and it was wrong:
    a stop exit fills at the stop level, which on a fast bar is nowhere near the
    close, so `risk` came out far too small and one day marked -67.9R - about
    twice the account at 3% risk, which is what made the error visible.

    Costs are charged in full at entry rather than split, so the path starts
    slightly negative and lands exactly on the realised `r` by construction.
    That is the conservative direction and it needs no fudge at the last bar.

    A bar where nothing traded is not a bar on which an account can breach, so
    dead bars carry the previous mark forward instead of creating a step.
    """
    per_day: dict[pd.Timestamp, float] = {}
    worst_err = 0.0
    excursions: list[dict] = []
    for m in matched:
        bars, row, cost, topn = m["bars"], m["row"], m["cost"], m["topn"]
        ei, xi = int(row[T_ENTRY_I]), int(row[T_EXIT_I])
        side = float(row[T_DIR])
        entry_px, exit_px = float(row[T_ENTRY_PX]), float(row[T_EXIT_PX])
        r_kernel = float(row[T_R])
        gross = (exit_px - entry_px) * side
        fees = (entry_px + exit_px) * cost / 2
        if r_kernel == 0.0:
            continue
        risk_px = (gross - fees) / r_kernel
        worst_err = max(worst_err,
                        abs((gross - fees) / risk_px - r_kernel))
        if not np.isfinite(risk_px) or risk_px <= 0:
            raise SystemExit(f"STOPPED: non-positive risk {risk_px} recovered "
                             f"at {bars.index[ei]}")

        px = bars.close.values[ei:xi + 1].astype(float).copy()
        px[-1] = exit_px                      # the last mark is the real fill
        vol = bars.volume.values[ei:xi + 1]
        ts = bars.index[ei:xi + 1]
        mark = ((px - entry_px) * side - fees) / risk_px / topn
        mark = pd.Series(np.where(vol > 0, mark, np.nan), index=ts)
        mark.iloc[-1] = r_kernel / topn        # exact, by the identity above
        mark = mark.ffill().fillna(mark.iloc[0] if np.isfinite(mark.iloc[0]) else 0.0)
        step = mark.diff()
        step.iloc[0] = mark.iloc[0]
        gross_mark = (px - entry_px) * side / risk_px
        excursions.append({
            "entry": str(ts[0]), "exit": str(ts[-1]), "risk_px": round(risk_px, 3),
            "r_kernel": round(r_kernel, 3), "bars": int(len(px)),
            "peak_unrealised_r": round(float(gross_mark.max()), 1),
            "trough_unrealised_r": round(float(gross_mark.min()), 1)})
        for day, v in step.groupby(step.index.normalize()).sum().items():
            per_day[day] = per_day.get(day, 0.0) + float(v)
    return pd.Series(per_day).sort_index(), worst_err, excursions


def score(daily: pd.Series, label: str) -> dict:
    best = None
    for risk in RISKS:
        a = run_accounts(daily, risk, THUNDERBOLT)
        if not a["pass_rate"]:
            continue
        exp = a["median_days"] / a["pass_rate"]
        line = {"label": label, "risk_pct": risk * 100,
                "pass_pct": round(a["pass_rate"] * 100, 1),
                "fail_max_pct": round(a["fail_max"] * 100, 1),
                "fail_daily_pct": round(a["fail_daily"] * 100, 1),
                "days": round(exp, 1),
                "band": band(daily, risk, rules=THUNDERBOLT)}
        if best is None or exp < best["days"]:
            best = line
    return best or {"label": label, "days": None}


def main() -> int:
    span = window([SYM], [TF])
    rec = Recorder(STRATEGY)
    res = run_market(rec, SYM, TF, pipe_kw={"floors": (30,), "topn": (5,)},
                     null_seeds=0, span=span)
    tr = res["_trades"]
    print(f"{SYM} {TF}: {len(tr)} selected trades, "
          f"{len(rec.seen)} kernel arrays recorded")

    matched = match(tr, rec.seen)
    print(f"matched {len(matched)}/{len(tr)} exactly on (entry, exit, R)")

    booked = pd.Series(tr.r.values,
                       index=pd.DatetimeIndex(tr.exit_ts)).resample("1D").sum()
    marked, worst_err, exc = paths(matched)
    print(f"booking identity re-checked on every trade, worst error {worst_err:.2e}")

    # the two series must describe the SAME total result
    print(f"total R  exit-booked {booked.sum():+.3f}   "
          f"marked {marked.sum():+.3f}   diff {marked.sum() - booked.sum():+.2e}")
    print(f"days with a step: {int((booked != 0).sum())} -> "
          f"{int((marked != 0).sum())}")
    print(f"worst single day (R): {booked.min():.3f} -> {marked.min():.3f}")
    pk = pd.Series([e["peak_unrealised_r"] for e in exc])
    gb = pd.Series([e["peak_unrealised_r"] - e["r_kernel"] for e in exc])
    print(f"peak unrealised R per trade: median {pk.median():.2f}  "
          f"p95 {pk.quantile(.95):.1f}  max {pk.max():.1f}")
    print(f"GIVE-BACK (peak unrealised - realised): median {gb.median():.2f}  "
          f"p95 {gb.quantile(.95):.1f}  max {gb.max():.1f}")

    rows = [score(booked, "exit-booked (the board)"),
            score(marked, "marked to market")]
    h = (f"{'series':26}{'risk%':>7}{'days':>7}{'band':>13}{'pass%':>7}"
         f"{'failMax%':>10}{'failDay%':>10}")
    print("\n" + h); print("-" * len(h))
    for r in rows:
        b = r.get("band") or {}
        print(f"{r['label']:26}{r.get('risk_pct', 0):7.2f}{r.get('days') or 0:7.1f}"
              f"{('%.1f-%.1f' % (b.get('days_lo', 0), b.get('days_hi', 0))):>13}"
              f"{r.get('pass_pct', 0):7.1f}{r.get('fail_max_pct', 0):10.1f}"
              f"{r.get('fail_daily_pct', 0):10.1f}")

    dest = ROOT / "backtests" / "vwapbreak" / "marktomarket.json"
    dest.write_text(json.dumps(
        {"sym": SYM, "tf": TF, "trades": len(tr), "rows": rows,
         "total_r_booked": float(booked.sum()),
         "total_r_marked": float(marked.sum()),
         "worst_day_booked": float(booked.min()),
         "worst_day_marked": float(marked.min()),
         "daily_booked": {str(k.date()): float(v) for k, v in booked.items()},
         "daily_marked": {str(k.date()): float(v) for k, v in marked.items()},
         "excursions": sorted(exc, key=lambda e: -e["peak_unrealised_r"])[:40]},
        indent=1, default=str))
    print(f"\nwrote {dest.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
