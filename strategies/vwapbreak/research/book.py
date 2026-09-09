"""TASK 4 — a two-market book: XAUUSD 1h + ETHUSDT 1h.

WHY THESE TWO. They are the only two cells in the whole universe that clear
profit factor 2.0 at double cost AND beat their own phase-randomised null
(`backtests/vwapbreak/assets.json`). They run on different clocks - gold's
liquidity is the London/NY session, ETH's is continuous - so their drawdowns have
no structural reason to coincide.

WHY IT MIGHT FAIL ANYWAY. H-012 established that widening a book DILUTES: equal
weighting divides the book's R per day by the leg count while drawdown falls by
much less, and 57 legs gated and greedily chosen still went from 15.9 in-window
days to 130.7 held out. That was a wide book of mostly weak legs. Two strong legs
is a different proposition and has never been measured here.

WHAT IS COMPARED, on identical folds and costs:

    gold alone          the strategy as traded
    ETH alone           the other survivor
    50/50 book          each leg at half the risk, one account

Read the correlation of their daily returns first: if it is high the book cannot
help, whatever the headline says.

Run: .venv/bin/python strategies/vwapbreak/research/book.py
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
from strategies.vwapbreak.research.exits import (UNIVERSE, WIDE_SIGMA,  # noqa: E402
                                                 ExitVariant)

ASH = PropRules(profit_target=0.02, daily_loss=0.03, max_loss=0.06,
                min_trading_days=0)
RISKS = (0.01, 0.015, 0.02, 0.03)


def daily_of(sym: str, tf: str, span) -> pd.Series:
    res = run_market(ExitVariant("wide", stops=WIDE_SIGMA), sym, tf,
                     pipe_kw={"floors": (30,), "topn": (5,)},
                     null_seeds=0, span=span)
    tr = res["_trades"]
    return pd.Series(tr.r.values,
                     index=pd.DatetimeIndex(tr.exit_ts)).resample("1D").sum()


def row(tag: str, daily: pd.Series) -> dict:
    best = None
    for risk in RISKS:
        a = run_accounts(daily, risk, ASH)
        if not a["pass_rate"]:
            continue
        exp = a["median_days"] / a["pass_rate"]
        line = {"tag": tag, "risk_pct": risk * 100,
                "pass_pct": round(a["pass_rate"] * 100, 1),
                "blown_pct": round((a["fail_max"] + a["fail_daily"]) * 100, 1),
                "never_pct": round(a["still_open"] * 100, 1),
                "median_days": a["median_days"], "days": round(exp, 1),
                "band": band(daily, risk, rules=ASH)}
        print(f"  {tag:22}{risk*100:5.2f}%  pass {line['pass_pct']:5.1f}%  "
              f"blown {line['blown_pct']:5.1f}%  days {line['days']:6.1f}  "
              f"band {line['band']['days_lo']}-{line['band']['days_hi']}", flush=True)
        if best is None or exp < best["days"]:
            best = line
    return best or {"tag": tag}


def main() -> int:
    span = window([s for v in UNIVERSE.values() for s in v], ["1h", "4h"])
    gold = daily_of("XAUUSD", "1h", span)
    eth = daily_of("ETHUSDT", "1h", span)

    both = pd.concat([gold.rename("gold"), eth.rename("eth")], axis=1).fillna(0.0)
    trading = both[(both.gold != 0) | (both.eth != 0)]
    corr = float(both.gold.corr(both.eth))
    overlap = float(((both.gold != 0) & (both.eth != 0)).mean())
    print(f"daily-return correlation gold vs ETH: {corr:+.3f}")
    print(f"days where both trade: {overlap*100:.1f}%   "
          f"gold trades {float((both.gold!=0).mean())*100:.0f}% of days, "
          f"ETH {float((both.eth!=0).mean())*100:.0f}%\n")

    # equal weight, one account: each leg carries half the risk
    book = (both.gold + both.eth) / 2.0

    out = {"corr": corr, "both_trade_share": overlap, "rows": []}
    for tag, series in (("gold 1h alone", both.gold),
                        ("ETH 1h alone", both.eth),
                        ("50/50 book", book)):
        out["rows"].append(row(tag, series))

    dest = ROOT / "backtests" / "vwapbreak" / "book.json"
    dest.write_text(json.dumps(out, indent=1, default=str))
    print(f"\nwrote {dest.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
