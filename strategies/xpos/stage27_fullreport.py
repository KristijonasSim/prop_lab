"""Stages 23-26, every mandatory field, on the blind test half.

CLAUDE.md lists eight fields that every backtest reports with no exceptions.
The stage scripts printed the phase gate and the nulls, which is what decides
whether an idea lives, but not the rest. This recomputes all of them for each
variant on the SAME window and the SAME leg set, so the rows are comparable
side by side rather than each being read on its own terms.

Nothing is chosen here. Every configuration is the one its own stage picked
inside the fit window; this only measures them.

Costs are reported at 1x, 2x and 3x as CLAUDE.md requires. The archive stores
R at 1x and 2x, and the per-trade cost increment is linear, so
r_3x = 2*r_2x - r recovers the third column exactly rather than by assumption.

Volatility-managed sizing changes the SIZE of each trade, not which trades are
taken, so its trade-level R is the raw R scaled by the multiplier in force on
that trade's exit day. Reporting its profit factor off the unscaled trades
would print the baseline's numbers under a different name.

Output: backtests/xpos/stage27_fullreport.csv
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from core import board, riskladder as RL                            # noqa: E402
from strategies.xpos.stage18_nested import (allin, build, gated,    # noqa: E402
                                            rank_legs)
from strategies.xpos.stage23_volmanaged import multiplier           # noqa: E402
from strategies.xpos.stage24_commonflow import (apply_gate, attach, # noqa: E402
                                                common_factor)
from strategies.xpos.stage25_rvol import (attach_rvol, keep_rank,   # noqa: E402
                                          rvol_panel)

OUT = ROOT / "backtests" / "xpos"
LEG_COUNTS = (4, 6, 8, 10, 12, 14, 17, 20, 25)
RISKS = (0.0025, 0.005, 0.0075, 0.01, 0.015)


def daily(s: pd.DataFrame, lo, hi, col="r_2x") -> pd.Series:
    d = pd.Series(s[col].values,
                  index=pd.DatetimeIndex(s.exit_ts)).resample("1D").sum()
    idx = pd.date_range(pd.Timestamp(lo).normalize(),
                        pd.Timestamp(hi).normalize(), freq="1D", tz="UTC")
    return d.reindex(idx).fillna(0.0)


def measure(s: pd.DataFrame, lo, hi, risk: float, mult=None) -> dict:
    """Every mandatory field for one variant."""
    s = s.sort_values("exit_ts").copy()
    if mult is not None:
        # each trade is sized by the multiplier in force on the day it closes
        dser = daily(s, lo, hi)
        m = pd.Series(mult, index=dser.index)
        k = m.reindex(pd.DatetimeIndex(s.exit_ts).normalize()).values
        for c in ("r", "r_2x"):
            s[c] = s[c].values * k
    r1, r2 = s.r.values, s.r_2x.values
    r3 = 2 * r2 - r1
    f = board.stitched_fields(r2, s.entry_ts, s.exit_ts, risk)
    dser = daily(s, lo, hi)
    two = RL.run_accounts_two_step(dser, risk)
    a = allin(dser.values, risk)
    eq = np.concatenate(([0.0], np.cumsum(r2)))
    dd_r = float((eq - np.maximum.accumulate(eq)).min())
    span = max((pd.Timestamp(hi) - pd.Timestamp(lo)).days, 1)
    return {
        "pf_1x": round(board.pf_of(r1), 3),
        "pf_2x": round(board.pf_of(r2), 3),
        "pf_3x": round(board.pf_of(r3), 3),
        "trades": f["trades"],
        "tpd": f["trades_per_day"], "tpw": f["trades_per_week"],
        "avg_hold_h": f["avg_hold_h"], "win_rate": f["win_rate"],
        "avg_r": f["avg_r"], "total_r": f["total_r"],
        "max_dd_r": round(dd_r, 2),
        "max_dd_pct": round(dd_r * risk, 4),
        "sharpe": f["sharpe"],
        "r_per_day": round(float(r2.sum() / span), 4),
        "K": round(float((r2.sum() / span) / abs(dd_r)), 5) if dd_r else None,
        "pass_rate": two.get("pass_rate"),
        "fail_max": two.get("fail_max"), "fail_daily": two.get("fail_daily"),
        "median_days": a.get("median_days"),
        "allin_days": a.get("allin_days"),
        "accounts": a.get("accounts"),
    }


def main() -> int:
    t = pd.read_parquet(OUT / "stage14_trades.parquet")
    t["entry_ts"] = pd.to_datetime(t.entry_ts, utc=True)
    t["exit_ts"] = pd.to_datetime(t.exit_ts, utc=True)
    t = t[t.topn == 1].sort_values("exit_ts")
    t = attach(t, common_factor(), "cflow")
    t = attach_rvol(t, rvol_panel())

    g0 = gated(t)
    mid = g0.exit_ts.quantile(0.5)
    f_lo, f_hi, s_lo, s_hi = g0.exit_ts.min(), mid, mid, g0.exit_ts.max()

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
    keys, risk = order[:best["n"]], best["risk"]
    print(f"TEST window {s_lo:%Y-%m-%d} -> {s_hi:%Y-%m-%d}   "
          f"{best['n']} legs at {risk*100:.2f}% risk\n")

    # each variant exactly as its own stage chose it on the fit window
    s_base, dv_base = build(g0[g0.exit_ts > mid], keys, s_lo, s_hi)
    m23, _ = multiplier(dv_base, 10, 0.25, 3.0, target=6.7286)

    # stage 24 and 26 both chose STACK on the fit window - the flow gate on top
    # of the crowd gate, not instead of it - so it is applied to g0, not to t.
    gate = apply_gate(g0, "cflow", 0.0, +1)            # stage 24: stack, mom
    rv = keep_rank(g0, 8)                              # stage 25: crossX top-8

    variants = [
        ("H-017 baseline", g0, None),
        ("23 vol-managed sizing", g0, m23),
        ("24 common flow gate", gate, None),
        ("25 relative volume", rv, None),
        ("26 flow gate + sizing", gate, None),
    ]
    rows = []
    for name, src, mult in variants:
        s, dv = build(src[src.exit_ts > mid], keys, s_lo, s_hi)
        if dv is None:
            print(f"{name}: too few trades")
            continue
        mm = mult
        if name.startswith("26"):
            mm, _ = multiplier(dv, 10, 0.5, 3.0, target=5.0645)
        rows.append({"variant": name, **measure(s, s_lo, s_hi, risk, mm)})

    d = pd.DataFrame(rows).set_index("variant")
    d.to_csv(OUT / "stage27_fullreport.csv")

    blocks = [
        ("COST ROBUSTNESS   (gate: PF >= 1.20 at 2x)",
         ["pf_1x", "pf_2x", "pf_3x"]),
        ("ACTIVITY", ["trades", "tpd", "tpw", "avg_hold_h"]),
        ("TRADE QUALITY", ["win_rate", "avg_r", "total_r"]),
        ("RISK", ["max_dd_r", "max_dd_pct", "sharpe"]),
        ("SPEED   (K = R/day over |maxDD_R|)", ["r_per_day", "K"]),
        ("PROP SIMULATION, two-step",
         ["pass_rate", "fail_max", "fail_daily", "median_days",
          "allin_days", "accounts"]),
    ]
    for title, cols in blocks:
        print(title)
        print(d[cols].to_string())
        print()
    print(f"wrote {OUT / 'stage27_fullreport.csv'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
