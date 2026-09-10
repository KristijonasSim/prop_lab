"""ELEVEN YEARS on the candidates, not just on the shipped rule.

`longhistory.py` ran the traded rule over eleven years of gold and found the one
thing that has ever narrowed a band here - width 46.8% of the median on three
years, 24.5% on eleven - and that the honest number is WORSE: 20.0 expected days
rather than 14.5, sitting just outside the short window's band.

Every arm measured on 2026-09-10 has two years behind it. This runs the ones that
are candidates for adoption over the same eleven-year cache, on the same walk-
forward, so a decision is made on the honest number rather than the flattering one:

    baseline          the shipped rule, as the control
    partial 2R        win rate 20.3% -> 41.9% over three years
    asian range       75% pass over three years, and it is ORB-family, which is
                      dead on crypto and index futures - eleven years is exactly
                      the test that family has never survived
    pct band 20bps    the only squeeze arm faster than the baseline on both
                      timeframes

THE SIZING RULE IS NOT AN ARM HERE. It is an account overlay, not a signal, so it
is applied to whichever series wins rather than searched over.

Run: .venv/bin/python strategies/vwapbreak/research/longcandidates.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from core.markets import COSTS, EXEC_MODE, TF_BPH                  # noqa: E402
from core.noiseband import band                                    # noqa: E402
from core.pipeline import Market, Pipeline                         # noqa: E402
from core.prop_rules import PropRules                              # noqa: E402
from core.riskladder import run_accounts                           # noqa: E402
from core.run_hypothesis import best_cell, metrics                 # noqa: E402
from strategies.vwapbreak.research.exits import WIDE_SIGMA         # noqa: E402
from strategies.vwapbreak.research.exitshape import (ShapedExit,   # noqa: E402
                                                     payout_stats)
from strategies.vwapbreak.research.longhistory import FixedGrid    # noqa: E402
from strategies.vwapbreak.research.squeeze import Squeeze          # noqa: E402
from strategies.vwapbreak.research.volume import VolumeVariant     # noqa: E402

SYM, TF = "XAUUSD", "1h"
ASH = PropRules(profit_target=0.02, daily_loss=0.03, max_loss=0.06,
                min_trading_days=0)
RISK = 0.02


def sized(daily: pd.Series, risk: float, rules=ASH, max_days: int = 120) -> dict:
    """The adopted budget-linear sizing, on any daily series."""
    d = daily.values
    n = len(d)
    out = []
    for s in range(n):
        eq = peak = 0.0
        day = traded = 0
        res = "OPEN"
        for k in range(s, min(s + max_days, n)):
            day += 1
            dd = min(eq - peak, eq)
            mult = float(np.clip((rules.max_loss + dd) / rules.max_loss, 0.25, 1.0))
            step = d[k] * risk * mult
            if step != 0.0:
                traded += 1
            if min(step, 0.0) <= -rules.daily_loss:
                res = "FAIL_DAILY"
                break
            low = eq + min(step, 0.0)
            if low - peak <= -rules.max_loss or low <= -rules.max_loss:
                res = "FAIL_MAX"
                break
            eq += step
            peak = max(peak, eq)
            if eq >= rules.profit_target and traded >= rules.min_trading_days:
                res = "PASS"
                break
        out.append((res, day))
    df = pd.DataFrame(out, columns=["outcome", "days"])
    p = df[df.outcome == "PASS"]
    rate = len(p) / len(df) if len(df) else 0.0
    return {"pass_pct": round(rate * 100, 1),
            "blown_pct": round(float(df.outcome.isin(["FAIL_MAX", "FAIL_DAILY"]).mean()) * 100, 1),
            "still_open_pct": round(float((df.outcome == "OPEN").mean()) * 100, 1),
            "days": round(float(p.days.median()) / rate, 1) if rate else None}


ARMS = (
    ("baseline", lambda: ShapedExit("vb")),
    ("partial 2R", lambda: ShapedExit("vb_p2", partial_r=2.0)),
    ("asian range", lambda: VolumeVariant("vb_asia", "asia")),
    ("pct band 20bps", lambda: Squeeze("vb_pct", "pct")),
)


def study(df: pd.DataFrame, tag: str, make) -> dict:
    strat = make()
    c = COSTS[SYM]
    fee, slip = c.per_side(EXEC_MODE)
    g = [dict(x) for x in strat.grid(TF)]
    for x in g:
        x["min_risk_bps"] = c.min_risk_bps
    pad = int(max(20, round(24 * 4 * TF_BPH[TF])) * 2)
    m = Market(sym=SYM, tf=TF, df=df, fee_bps=fee, slip_bps=slip, pad_bars=pad)
    p = Pipeline(FixedGrid(strat, g), floors=(30,), topn=(5,))
    real = p.walk_forward(m)
    tr = best_cell(real.folds, real.trades)
    daily = pd.Series(tr.r.values,
                      index=pd.DatetimeIndex(tr.exit_ts)).resample("1D").sum()
    a = run_accounts(daily, RISK, ASH)
    b = band(daily, RISK, rules=ASH) or {}
    met = metrics(tr)
    q = daily.groupby(daily.index.to_period("Q")).sum()
    tot = float(q.sum())
    width = ((b["days_hi"] - b["days_lo"]) / b["days_med"] * 100
             if b.get("days_med") else None)
    return {"arm": tag, "bars": int(len(df)),
            "from": str(df.index[0].date()), "to": str(df.index[-1].date()),
            "quarters": int(real.folds.quarter.nunique()) if len(real.folds) else 0,
            "trades": int(len(tr)), "tpd": met.get("trades_per_day"),
            "pf": met.get("pf"), "pf_2x": met.get("pf_2x"),
            "win_pct": met.get("win_pct"),
            "pass_pct": round(a["pass_rate"] * 100, 1),
            "blown_pct": round((a["fail_max"] + a["fail_daily"]) * 100, 1),
            "days": round(a["median_days"] / a["pass_rate"], 1) if a["pass_rate"] else None,
            "band": b, "band_width_pct": round(width, 1) if width else None,
            "best_q_share": round(float(q.max()) / tot, 3) if tot > 0 else None,
            "sized": sized(daily, RISK),
            **payout_stats(daily.values * RISK)}


def main() -> int:
    path = ROOT / "data" / f"{SYM}10Y_dukascopy_{TF}.parquet"
    if not path.exists():
        sys.exit(f"missing {path}")
    long_df = pd.read_parquet(path).sort_index()
    print(f"{SYM} {TF}: {len(long_df):,} bars "
          f"{long_df.index[0].date()} -> {long_df.index[-1].date()}\n")
    print(f"{'arm':18}{'trades':>8}{'win%':>7}{'PF':>7}{'PF2x':>7}{'days':>7}"
          f"{'band':>12}{'width':>8}{'pass%':>7}{'sized days':>12}{'sized pass':>12}")
    rows = []
    for tag, make in ARMS:
        try:
            r = study(long_df, tag, make)
        except Exception as exc:                          # noqa: BLE001
            print(f"{tag:18} FAILED: {exc}", flush=True)
            continue
        rows.append(r)
        b = r["band"]
        print(f"{tag:18}{r['trades']:8}{(r['win_pct'] or 0):7.1f}{(r['pf'] or 0):7.3f}"
              f"{(r['pf_2x'] or 0):7.3f}{(r['days'] or 0):7.1f}"
              f"{('%.0f-%.0f' % (b.get('days_lo', 0), b.get('days_hi', 0))):>12}"
              f"{(r['band_width_pct'] or 0):7.0f}%{r['pass_pct']:7.1f}"
              f"{(r['sized']['days'] or 0):12.1f}{r['sized']['pass_pct']:12.1f}",
              flush=True)
        (ROOT / "backtests" / "vwapbreak" / "longcandidates.json").write_text(
            json.dumps({"rows": rows}, indent=1, default=str))
    print("\nwrote backtests/vwapbreak/longcandidates.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
