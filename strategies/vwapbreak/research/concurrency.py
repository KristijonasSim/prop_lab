"""TASK 5 — how many positions may be open at once?

THE PROBLEM. The five settings trade one instrument in one direction most of the
time, so they lose together. Measured on the traded series at 2% risk, the worst
single day is -3.93% of balance against a 3% daily cap, and three days in 221
would have breached it. The daily cap, not the max drawdown, is what kills these
accounts.

THE FIX BEING TESTED. Refuse a new entry while K positions are already open. It
is a pure overlay on the existing signals - nothing about entries, stops or exits
changes, and a refused signal is simply not taken.

Each arm keeps the same TOTAL risk: with fewer concurrent positions the same 2%
is spread over fewer legs, which is the honest comparison (the alternative -
shrinking total exposure - would confound the cap with a risk cut).

Run: .venv/bin/python strategies/vwapbreak/research/concurrency.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

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
CAPS = (5, 3, 2, 1)
RISKS = (0.015, 0.02, 0.03)


def cap_open(tr: pd.DataFrame, k: int) -> pd.DataFrame:
    """Keep a trade only if fewer than k are already running when it opens."""
    open_until: list[pd.Timestamp] = []
    keep = []
    for _, t in tr.iterrows():
        open_until = [x for x in open_until if x > t.entry_ts]
        if len(open_until) < k:
            keep.append(True)
            open_until.append(t.exit_ts)
        else:
            keep.append(False)
    return tr[pd.Series(keep, index=tr.index)]


def main() -> int:
    span = window([s for v in UNIVERSE.values() for s in v], ["1h", "4h"])
    res = run_market(ExitVariant("wide", stops=WIDE_SIGMA), "XAUUSD", "1h",
                     pipe_kw={"floors": (30,), "topn": (5,)},
                     null_seeds=0, span=span)
    tr = res["_trades"].copy()
    tr["entry_ts"] = pd.to_datetime(tr.entry_ts, utc=True)
    tr["exit_ts"] = pd.to_datetime(tr.exit_ts, utc=True)
    tr = tr.sort_values("entry_ts").reset_index(drop=True)

    out = []
    print("XAUUSD 1h, five settings, Upcomers Ash (1-step 2%). Same signals; "
          "only the concurrency cap changes.\n")
    print(f"{'max open':>9}{'trades':>8}{'tr/day':>8}{'risk':>7}{'pass%':>8}"
          f"{'blown%':>8}{'worst day%':>12}{'days':>8}{'band':>14}")
    for k in CAPS:
        sub = cap_open(tr, k)
        daily = pd.Series(sub.r.values,
                          index=pd.DatetimeIndex(sub.exit_ts)).resample("1D").sum()
        span_days = max((sub.exit_ts.max() - sub.entry_ts.min()).days, 1)
        for risk in RISKS:
            a = run_accounts(daily, risk, ASH)
            if not a["pass_rate"]:
                continue
            b = band(daily, risk, rules=ASH) or {}
            worst = float((daily * risk * 100).min())
            row = {"cap": k, "trades": int(len(sub)),
                   "tpd": round(len(sub) / span_days, 2), "risk_pct": risk * 100,
                   "pass_pct": round(a["pass_rate"] * 100, 1),
                   "blown_pct": round((a["fail_max"] + a["fail_daily"]) * 100, 1),
                   "worst_day_pct": round(worst, 2),
                   "days": round(a["median_days"] / a["pass_rate"], 1),
                   "band": b}
            out.append(row)
            print(f"{k:9d}{row['trades']:8d}{row['tpd']:8.2f}{risk*100:7.2f}"
                  f"{row['pass_pct']:8.1f}{row['blown_pct']:8.1f}"
                  f"{worst:12.2f}{row['days']:8.1f}"
                  f"   {b.get('days_lo')}-{b.get('days_hi')}", flush=True)
        print()
    dest = ROOT / "backtests" / "vwapbreak" / "concurrency.json"
    dest.write_text(json.dumps(out, indent=1, default=str))
    print(f"wrote {dest.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
