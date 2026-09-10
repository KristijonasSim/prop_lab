"""H-027 BELOW 1h — 30m, 15m, 5m. The hypothesis has never been run there.

Kris, 2026-09-10, after the ranked backlog: *"lets do tier 1 please, all of them"*.

THE GAP. The board holds twenty cells: ten markets x **1h and 4h only**. The
kernel, the grid (`grid_for` converts the horizon from hours per timeframe), the
walk-forward and the caches all support 5m, 15m and 30m - `data/` has
`XAUUSD_dukascopy_5min`, `15min` and `30min` sitting there untouched - and H-027
has never been run on any of them. H-002 used 5m through 4h routinely.

WHY IT SHOULD HELP. `expected days = median days to pass / pass rate`, and the
numerator is set by how often the strategy trades. At 1h the rule takes **0.93
trades a day** and 591 trades in two years, so the whole result rests on about
twenty large winners. Going to 15m is roughly four times the sessions and four
times the signals: four times the sample, and an evaluation that resolves on
trades rather than on luck.

WHY IT MIGHT NOT, and this is the honest half. Cost is charged per trade and does
not shrink with the bar. Gold's band sigma is ~18bps at 1h and roughly a third of
that at 15m, while the round trip stays at 1.06bps - so **sigma/cost falls from
17.2 towards 6**, which is the exact arithmetic that explains why the same rule
dies on BTC (3.8). This run applies the BTC diagnosis to gold's own timeframe axis.
If sub-hour dies, it dies for a reason already measured, and that is a result.

WHAT IS RUN: the traded rule unchanged - wide stop 2.5-8 sigma, floor 30 / top 5,
no target, horizon in HOURS so it means the same thing on every bar size - on
XAUUSD at 30m, 15m and 5m, against 1h as the control. Blind quarterly walk-forward,
paired null, same window and costs as the board.

Run: .venv/bin/python strategies/vwapbreak/research/subhour.py
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from core.markets import COSTS, EXEC_MODE, load                    # noqa: E402
from core.noiseband import band                                    # noqa: E402
from core.prop_rules import PropRules                              # noqa: E402
from core.riskladder import run_accounts                           # noqa: E402
from core.run_hypothesis import run_market, window                 # noqa: E402
from strategies.vwap.sweep import vwap_series                      # noqa: E402
from strategies.vwapbreak.research.exits import (UNIVERSE, WIDE_SIGMA,  # noqa: E402
                                                 ExitVariant)
from strategies.vwapbreak.research.exitshape import payout_stats   # noqa: E402

ASH = PropRules(profit_target=0.02, daily_loss=0.03, max_loss=0.06,
                min_trading_days=0)
RISKS = (0.01, 0.015, 0.02, 0.03)
SYM = "XAUUSD"
#: coarsest first, so the cheap answers land before the expensive one
TFS = ("1h", "30m", "15m", "5m")


def sigma_over_cost(sym: str, tf: str, span) -> tuple:
    """The diagnostic that predicts whether a timeframe can pay its costs."""
    df = load(sym, tf)
    df = df[(df.index >= span[0]) & (df.index <= span[1])]
    _, vwstd, _ = vwap_series(df, 0, 0)
    c = df.close.values
    live = df.volume.values > 0
    sd_bps = vwstd / np.where(c > 0, c, np.nan) * 1e4
    ok = np.isfinite(sd_bps) & live
    sig = float(np.nanmedian(sd_bps[ok]))
    cost = COSTS[sym].round_trip(EXEC_MODE)
    return round(sig, 1), round(cost, 2), round(sig / cost, 1)


def score(res: dict) -> dict:
    tr = res["_trades"]
    daily = pd.Series(tr.r.values,
                      index=pd.DatetimeIndex(tr.exit_ts)).resample("1D").sum()
    best = None
    for risk in RISKS:
        a = run_accounts(daily, risk, ASH)
        if not a["pass_rate"]:
            continue
        exp = a["median_days"] / a["pass_rate"]
        line = {"risk_pct": risk * 100, "pass_pct": round(a["pass_rate"] * 100, 1),
                "blown_pct": round((a["fail_max"] + a["fail_daily"]) * 100, 1),
                "days": round(exp, 1), "band": band(daily, risk, rules=ASH)}
        if best is None or exp < best["days"]:
            best = line
    return {**(best or {"days": None}), **payout_stats(daily.values * 0.02),
            "trades": res.get("trades"), "win_pct": res.get("win_pct"),
            "pf": res.get("pf"), "pf_2x": res.get("pf_2x"),
            "avg_r": res.get("avg_r"), "trades_per_day": res.get("trades_per_day"),
            "beats_null": res.get("beats_null"), "null_pf": res.get("null_pf")}


def main() -> int:
    span = window([s for v in UNIVERSE.values() for s in v], ["1h", "4h"])
    print(f"{SYM}, window {span[0].date()} -> {span[1].date()}, traded rule unchanged\n")
    print(f"{'tf':5}{'sigma':>7}{'s/cost':>8}{'trades':>8}{'tpd':>7}{'win%':>7}"
          f"{'PF2x':>7}{'null':>7}{'days':>7}{'band':>12}{'pass%':>7}{'mins':>6}")
    out = {}
    for tf in TFS:
        t0 = time.time()
        sig, cost, ratio = sigma_over_cost(SYM, tf, span)
        try:
            res = run_market(ExitVariant("wide", stops=WIDE_SIGMA), SYM, tf,
                             pipe_kw={"floors": (30,), "topn": (5,)},
                             null_seeds=1, span=span)
        except Exception as exc:                          # noqa: BLE001
            print(f"{tf:5} FAILED: {exc}", flush=True)
            continue
        s = score(res)
        s.update({"sigma_bps": sig, "cost_rt_bps": cost, "sigma_over_cost": ratio})
        out[tf] = s
        b = s.get("band") or {}
        print(f"{tf:5}{sig:7.1f}{ratio:8.1f}{s['trades'] or 0:8}"
              f"{(s['trades_per_day'] or 0):7.2f}{(s['win_pct'] or 0):7.1f}"
              f"{(s['pf_2x'] or 0):7.3f}{(s['null_pf'] or 0):7.3f}"
              f"{(s['days'] or 0):7.1f}"
              f"{('%.0f-%.0f' % (b.get('days_lo', 0), b.get('days_hi', 0))):>12}"
              f"{(s['pass_pct'] or 0):7.1f}{(time.time() - t0) / 60:6.1f}", flush=True)
        (ROOT / "backtests" / "vwapbreak" / "subhour.json").write_text(
            json.dumps({"sym": SYM, "rows": out}, indent=1, default=str))

    print("\nwrote backtests/vwapbreak/subhour.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
