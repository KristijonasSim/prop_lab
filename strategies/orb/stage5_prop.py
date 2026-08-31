"""ORB stage 5 — what a prop challenge actually does to it.

Take a config's real trade sequence and start a fresh challenge account on every
trading day. Fixed 1% risk per trade, real breaches, no size shrinking. Report
the PASS rate and how long a resolution takes. See core/prop_rules.py.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from core.prop_rules import PropRules                     # noqa: E402

RISK_FRAC = 0.01


def run_accounts(daily_r: pd.Series, rules: PropRules = PropRules(),
                 max_days: int = 180) -> pd.DataFrame:
    """daily_r: R gained per calendar day, indexed by date."""
    d = daily_r.values * RISK_FRAC
    dates = daily_r.index
    out = []
    for s in range(len(d)):
        eq, peak, day, res = 0.0, 0.0, 0, "OPEN"
        traded = 0
        for k in range(s, min(s + max_days, len(d))):
            day += 1
            step = d[k]
            if step != 0.0:
                traded += 1
            # worst case within the day: assume the whole day's loss happens
            # before any of its gain
            low = eq + min(step, 0.0)
            if min(step, 0.0) <= -rules.daily_loss:
                res = "FAIL_DAILY"; break
            if low - peak <= -rules.max_loss or low <= -rules.max_loss:
                res = "FAIL_MAX"; break
            eq += step
            peak = max(peak, eq)
            if eq >= rules.profit_target and traded >= rules.min_trading_days:
                res = "PASS"; break
        out.append({"start": dates[s], "outcome": res, "days": day,
                    "final_pct": round(eq * 100, 2)})
    return pd.DataFrame(out)


def summarise(acc: pd.DataFrame) -> dict:
    n = len(acc)
    passes = acc[acc.outcome == "PASS"]
    return {
        "accounts": n,
        "pass_rate": round(len(passes) / n, 4) if n else 0.0,
        "fail_daily": round((acc.outcome == "FAIL_DAILY").mean(), 4),
        "fail_max": round((acc.outcome == "FAIL_MAX").mean(), 4),
        "open": round((acc.outcome == "OPEN").mean(), 4),
        "median_days_to_pass": float(passes.days.median()) if len(passes) else np.nan,
    }


def main():
    from core import data
    from strategies.orb.sweep import features, run_one, DEFAULTS, trade_metrics
    from strategies.orb.engine import T_EXIT_I, T_R

    ROOT_ = Path(__file__).resolve().parents[2]
    df = data.load("BTC/USDT", "15m")
    w = df[df.index >= "2018-01-01"]
    feats = features(w)
    span = (w.index[-1] - w.index[0]).total_seconds() / 86400.0

    # The best config in the whole 8,160-config grid at realistic cost.
    # It is the best ORB there is on this data, not a good strategy.
    cands = {
        "best_1x_grid": dict(hour=0, or_bars=1, hold_bars=96, entry_mode=1,
                             stop_mode=2, stop_atr_mult=2.0, rr=0.0, fade=1),
        "classic_NY_30m": dict(hour=13, or_bars=2, hold_bars=32, entry_mode=0,
                               stop_mode=0, stop_atr_mult=0.0, rr=0.0, fade=0),
        "best_0x_fade": dict(hour=7, or_bars=16, hold_bars=32, entry_mode=0,
                             stop_mode=2, stop_atr_mult=1.0, rr=1.0, fade=1),
    }

    rows = []
    for name, over in cands.items():
        cfg = dict(DEFAULTS); cfg.update(over)
        for mult in (0.0, 1.0):
            tr = run_one(w, feats, cfg, 5.0 * mult, 2.0 * mult)
            m = trade_metrics(tr, w.index, span)
            daily = pd.Series(tr[:, T_R], index=w.index[tr[:, T_EXIT_I].astype(int)])
            daily = daily.resample("1D").sum()
            acc = run_accounts(daily)
            row = {"config": name, "cost": f"{mult:g}x", "pf": m["pf"],
                   "win_rate": m["win_rate"], "trades": m["trades"],
                   "trades_per_day": m["trades_per_day"],
                   "avg_hold_h": m["avg_hold_h"], "avg_r": m["avg_r"],
                   "max_dd": m["max_dd"], "sharpe": m["sharpe"],
                   "days_to_target": m["days_to_target"],
                   "days_to_breach": m["days_to_breach"]}
            row.update(summarise(acc))
            rows.append(row)
            print(f"{name:16s} {mult:g}x  PF {m['pf']:.3f}  pass {row['pass_rate']*100:5.1f}%  "
                  f"fail_daily {row['fail_daily']*100:5.1f}%  fail_max {row['fail_max']*100:5.1f}%  "
                  f"open {row['open']*100:5.1f}%", flush=True)

    out = pd.DataFrame(rows)
    out.to_csv(ROOT_ / "backtests" / "orb" / "stage5_prop.csv", index=False)
    print("saved stage5_prop.csv")


if __name__ == "__main__":
    main()
