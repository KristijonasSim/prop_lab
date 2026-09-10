"""Does this strategy ever become PAYOUT ELIGIBLE under a 20% best-day rule?

Kris's question, 2026-09-10: "do we beat best day scenario if it is 20% if we go
with this strategy live". FIRMS.md answered it for the gold leg only, ad hoc and
without a script. This answers it for every cell in the cross-asset table, so the
answer sits in the same table as the edge numbers.

THE RULE, as firms write it. At withdrawal, no single trading day may account for
more than `CAP` (20% is the common number) of the profit being withdrawn. It bites
on the FUNDED account, not on the evaluation - passing the evaluation is not the
problem, getting paid afterwards is.

HOW IT IS SIMULATED. A funded account at the same fixed risk the study table uses.
Profit accumulates from the last payout. A payout is taken on the first day where

    profit since last payout >= PAYOUT_MIN   (a withdrawal worth asking for)
    largest single day in that window        <= CAP x that profit

and the window resets. If the largest day is over the cap the account simply keeps
trading: the rule can cure itself, because the big day's SHARE falls as later days
add profit. That is the generous reading - if a cell fails here it fails outright.

WHAT IS REPORTED PER CELL:

    best_day_share_net  largest single day as a share of NET profit over the span
    best_day_share      the same over gross winnings - defined even when it loses
    top5_share          the five best days as a share of gross winnings
    windows             withdrawals the series affords at all (profit >= PAYOUT_MIN)
    windows_payable     how many of those would have passed the 20% cap
    payouts_ruled       payouts taken when the rule is enforced from the start

`best_day_share_net` is the headline: it is the quantity the rule tests, it needs
no threshold to interpret, and it is comparable across cells. `windows_payable /
windows` is the practical reading - of the withdrawals this series affords, how
many a firm with the rule would actually pay.

Run: .venv/bin/python strategies/vwapbreak/research/bestday.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from core.run_hypothesis import run_market, window                 # noqa: E402
from strategies.vwapbreak.research.exits import (UNIVERSE, WIDE_SIGMA,  # noqa: E402
                                                 ExitVariant)

RISK = 0.02          # same size the cross-asset table is scored at
CAP = 0.20           # the firms' best-day cap
PAYOUT_MIN = 0.01    # 1% of balance - a withdrawal worth making
TFS = ("1h", "4h")


def daily_of(sym: str, tf: str, span) -> pd.Series:
    """Daily R of the TRADED rule - wide stop, floor 30 / top 5 - as in book.py."""
    res = run_market(ExitVariant("wide", stops=WIDE_SIGMA), sym, tf,
                     pipe_kw={"floors": (30,), "topn": (5,)},
                     null_seeds=0, span=span)
    tr = res["_trades"]
    return pd.Series(tr.r.values,
                     index=pd.DatetimeIndex(tr.exit_ts)).resample("1D").sum()


def payouts(pct: np.ndarray, cap: float | None) -> tuple[int, int | None, list[float]]:
    """Payouts taken over the series, day of the first one, and each one's share.

    `cap` None switches the best-day rule off, which is the control: it answers
    "of the withdrawals you would actually have made, how many pass the rule".
    """
    taken, first, shares = 0, None, []
    acc, best = 0.0, 0.0
    for i, step in enumerate(pct):
        acc += step
        best = max(best, step)
        if acc < PAYOUT_MIN or acc <= 0.0:
            continue
        share = best / acc
        if cap is not None and share > cap:
            continue                      # keep trading, the share can still fall
        taken += 1
        shares.append(round(share, 3))
        if first is None:
            first = i + 1
        acc, best = 0.0, 0.0
    return taken, first, shares


def row(sym: str, tf: str, daily: pd.Series) -> dict:
    pct = daily.values * RISK
    total = float(pct.sum())
    gains = pct[pct > 0]
    ruled, first, _ = payouts(pct, CAP)
    free, first_free, shares = payouts(pct, None)
    payable = sum(1 for s in shares if s <= CAP)
    return {
        "sym": sym, "tf": tf,
        "trading_days": int(len(pct)),
        "total_profit_pct": round(total * 100, 2),
        # THE HEADLINE: the single best day as a share of NET profit over the
        # whole span - the quantity the rule actually tests. Over 20% means the
        # whole span, taken as one withdrawal, would fail.
        "best_day_share_net": round(float(pct.max() / total), 3) if total > 0 else None,
        # the same over GROSS winnings, which is defined even when the cell loses
        "best_day_share": round(float(gains.max() / gains.sum()), 3) if len(gains) else None,
        "top5_share": (round(float(np.sort(gains)[-5:].sum() / gains.sum()), 3)
                       if len(gains) >= 5 else None),
        # withdrawals: how many the series affords at all, and how many of those
        # would have passed a 20% best-day cap
        "windows": free,
        "windows_payable": payable,
        "window_shares": shares,
        "payouts_ruled": ruled,
        "first_payout_day": first,
        "first_payout_day_free": first_free,
    }


def main() -> int:
    span = window([s for v in UNIVERSE.values() for s in v], list(TFS))
    out, cache = [], {}
    for group in UNIVERSE.values():
        for sym in group:
            for tf in TFS:
                try:
                    d = daily_of(sym, tf, span)
                except Exception as exc:                      # noqa: BLE001
                    print(f"  {sym} {tf}: SKIPPED ({exc})", flush=True)
                    continue
                # cached so a change of RULE never needs the walk-forward again
                cache[f"{sym}|{tf}"] = {"t0": str(d.index[0].date()),
                                        "r": [round(float(x), 6) for x in d.values]}
                r = row(sym, tf, d)
                out.append(r)
                net = r["best_day_share_net"]
                print(f"  {sym:8}{tf:4} best day "
                      f"{('%.1f%%' % (net * 100)) if net else '  n/a':>7} of net profit  "
                      f"withdrawals {r['windows_payable']:3} payable / {r['windows']:3} "
                      f"available", flush=True)

    (ROOT / "backtests" / "vwapbreak" / "daily_traded.json").write_text(
        json.dumps(cache, indent=0, default=str))
    dest = ROOT / "backtests" / "vwapbreak" / "bestday.json"
    dest.write_text(json.dumps({"risk_pct": RISK * 100, "cap": CAP,
                                "payout_min_pct": PAYOUT_MIN * 100,
                                "rows": out}, indent=1, default=str))
    print(f"\nwrote {dest.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
