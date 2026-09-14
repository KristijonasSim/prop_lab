"""H-041 — a daily-loss guard on the account. Pre-registration: DAILYGUARD.md.

Once the UTC day's realised R is at or below a threshold, take no new entries
until tomorrow. Open positions are left alone; closing them would be an exit
change and that axis is closed.

WHY THIS IS NOT AN ENTRY FILTER. It reads the ACCOUNT, never the market. That is
the class the risk ladder and budget-linear sizing belong to - a fixed trade
series re-simulated under a different account policy - and it is the only class
that has ever produced a keeper on this hypothesis.

Run: .venv/bin/python strategies/vwapbreak/research/dailyguard.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from core.noiseband import band as nb_band                          # noqa: E402
from core.prop_rules import PropRules                               # noqa: E402
from core.riskladder import run_accounts                            # noqa: E402
from core.run_hypothesis import run_market, window                  # noqa: E402
from strategies.vwapbreak.strategy import STRATEGY                  # noqa: E402

THUNDERBOLT = PropRules(profit_target=0.06, daily_loss=0.03, max_loss=0.06,
                        min_trading_days=0)
RISKS = (0.01, 0.015, 0.02, 0.03)
CELLS = [("XAUUSD", "1h"), ("XAUUSD", "4h")]
#: the day's loss, in ACCOUNT percent, that stops new entries. None = baseline.
GUARDS = (None, 0.010, 0.015, 0.020, 0.025)


def apply_guard(tr: pd.DataFrame, risk: float, limit: float | None) -> pd.DataFrame:
    """Drop entries taken after the day's realised loss passed `limit`.

    THE DECISION USES ONLY CLOSED TRADES. A trade is skipped when the losses
    ALREADY BOOKED that day - trades whose exit is at or before this trade's
    entry - are at or below the limit. Using the day's final total would be a
    look-ahead: it would let the guard know about losses that had not happened
    when the entry decision was made.
    """
    if limit is None:
        return tr
    t = tr.sort_values("entry_ts").copy()
    entry = pd.DatetimeIndex(t.entry_ts)
    exit_ = pd.DatetimeIndex(t.exit_ts)
    r = t.r.values * risk                       # account fraction per trade
    day_e = entry.normalize().values
    day_x = exit_.normalize().values
    keep = np.ones(len(t), dtype=bool)
    for i in range(len(t)):
        same = (day_x == day_e[i]) & (exit_.values <= entry.values[i]) & keep
        if same.any() and r[same].sum() <= -limit:
            keep[i] = False
    return t[keep]


def score(tr: pd.DataFrame, risk: float) -> dict | None:
    if not len(tr):
        return None
    daily = pd.Series(tr.r.values,
                      index=pd.DatetimeIndex(tr.exit_ts)).resample("1D").sum()
    a = run_accounts(daily, risk, THUNDERBOLT)
    if not a["pass_rate"]:
        return None
    return {"risk_pct": risk * 100, "trades": len(tr),
            "pass_pct": round(a["pass_rate"] * 100, 1),
            "blown_pct": round((a["fail_max"] + a["fail_daily"]) * 100, 1),
            "fail_daily_pct": round(a["fail_daily"] * 100, 1),
            "days": round(a["median_days"] / a["pass_rate"], 1),
            "band": nb_band(daily, risk, rules=THUNDERBOLT)}


def main() -> int:
    span = window(["XAUUSD"], ["1h", "4h"])
    out = {}
    for sym, tf in CELLS:
        res = run_market(STRATEGY, sym, tf,
                         pipe_kw={"floors": (30,), "topn": (5,)},
                         null_seeds=0, span=span)
        tr = res["_trades"].copy()
        tr["entry_ts"] = pd.to_datetime(tr.entry_ts, utc=True)
        tr["exit_ts"] = pd.to_datetime(tr.exit_ts, utc=True)
        print(f"\n=== {sym} {tf}  ({len(tr)} blind trades) " + "=" * 30, flush=True)
        hdr = (f"{'guard':>8}{'trades':>8}{'risk%':>7}{'days':>7}{'band':>13}"
               f"{'pass%':>7}{'blown%':>8}{'failDay%':>10}")
        print(hdr); print("-" * len(hdr), flush=True)
        for g in GUARDS:
            best = None
            for risk in RISKS:
                s = score(apply_guard(tr, risk, g), risk)
                if s and (best is None or s["days"] < best["days"]):
                    best = s
            tag = "none" if g is None else f"-{g*100:.1f}%"
            out[f"{sym}|{tf}|{tag}"] = best
            if not best:
                print(f"{tag:>8}   no passing rung", flush=True); continue
            b = best["band"]
            print(f"{tag:>8}{best['trades']:>8}{best['risk_pct']:>7.2f}"
                  f"{best['days']:>7.1f}"
                  f"{('%.1f-%.1f' % (b['days_lo'], b['days_hi'])):>13}"
                  f"{best['pass_pct']:>7.1f}{best['blown_pct']:>8.1f}"
                  f"{best['fail_daily_pct']:>10.1f}", flush=True)

    dest = ROOT / "backtests" / "vwapbreak" / "dailyguard.json"
    dest.write_text(json.dumps({"guards": [g for g in GUARDS], "rows": out},
                               indent=1, default=str))
    print(f"\nwrote {dest.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
