"""TASK 2 — eleven years of gold instead of three. Does the band narrow?

WHY THIS IS THE MOST VALUABLE DATA WE CAN BUY. Every headline in this project
comes with a band, and the band is what stops any of it being called proven: the
traded book is 12.4 expected days with a band of 10.5-15.7, and the measured luck
zone is 13.3-26.5. Re-slicing the same three years cannot narrow that - the band
is set by how few independent stretches the sample contains. Only more data can.

The three-year rule in `core.run_hypothesis.YEARS` exists so that markets are
comparable on the board and it stays exactly as it is. This is a separate study
of the ONE instrument being traded, on its own cache
(`data/XAUUSD10Y_dukascopy_1h.parquet`), so no board number moves.

WHAT IS COMPARED: the same strategy, same grid, same costs, same selection rule,
on 3 years and on 11 - and specifically the WIDTH of the band, not the headline.
A narrower band on a similar number is the win; a different number is a finding
of its own.

Run: .venv/bin/python strategies/vwapbreak/research/longhistory.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from core.markets import COSTS, EXEC_MODE, TF_BPH                  # noqa: E402
from core.noiseband import band                                    # noqa: E402
from core.pipeline import Market, Pipeline                         # noqa: E402
from core.prop_rules import PropRules                              # noqa: E402
from core.riskladder import run_accounts                           # noqa: E402
from core.run_hypothesis import best_cell, metrics                 # noqa: E402
from strategies.vwapbreak.research.exits import (WIDE_SIGMA,       # noqa: E402
                                                 ExitVariant)

SYM, TF = "XAUUSD", "1h"
ASH = PropRules(profit_target=0.02, daily_loss=0.03, max_loss=0.06,
                min_trading_days=0)
RISK = 0.02


class FixedGrid:
    """`run_market` wraps the strategy so the grid carries the market's min-risk
    floor; this study builds its own Market, so it does the same by hand."""

    def __init__(self, s, grid):
        self._s, self._grid = s, grid
        self.name = getattr(s, "name", "strategy")

    def features(self, df):
        return self._s.features(df)

    def grid(self, tf):
        return self._grid

    def new_cache(self):
        f = getattr(self._s, "new_cache", None)
        return f() if callable(f) else {}

    def run(self, *a, **k):
        return self._s.run(*a, **k)


def study(df: pd.DataFrame, label: str) -> dict:
    strat = ExitVariant("wide", stops=WIDE_SIGMA)
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
    width = ((b["days_hi"] - b["days_lo"]) / b["days_med"] * 100
             if b.get("days_med") else None)
    out = {"label": label, "bars": int(len(df)),
           "from": str(df.index[0].date()), "to": str(df.index[-1].date()),
           "folds": int(real.folds.quarter.nunique()) if len(real.folds) else 0,
           "trades": int(len(tr)), "tpd": met.get("trades_per_day"),
           "pf": met.get("pf"), "win_pct": met.get("win_pct"),
           "pass_pct": round(a["pass_rate"] * 100, 1),
           "blown_pct": round((a["fail_max"] + a["fail_daily"]) * 100, 1),
           "days": round(a["median_days"] / a["pass_rate"], 1) if a["pass_rate"] else None,
           "band": b, "band_width_pct": round(width, 1) if width else None}
    print(f"\n{label}: {out['bars']:,} bars {out['from']} -> {out['to']}, "
          f"{out['folds']} quarters, {out['trades']} trades")
    print(f"  PF {out['pf']}  win {out['win_pct']}%  {out['tpd']}/day  "
          f"pass {out['pass_pct']}%  blown {out['blown_pct']}%")
    print(f"  expected days {out['days']}  band {b.get('days_lo')}-{b.get('days_hi')}"
          f"  (width {out['band_width_pct']}% of the median)", flush=True)
    return out


def main() -> int:
    long_path = ROOT / "data" / f"{SYM}10Y_dukascopy_{TF}.parquet"
    if not long_path.exists():
        sys.exit(f"missing {long_path} - run the downloader first")
    long_df = pd.read_parquet(long_path).sort_index()
    short_df = long_df[long_df.index >= long_df.index[-1] - pd.DateOffset(years=3)]

    rows = [study(short_df, "3 years (the board's window)"),
            study(long_df, "full history")]
    dest = ROOT / "backtests" / "vwapbreak" / "longhistory.json"
    dest.write_text(json.dumps(rows, indent=1, default=str))

    a, b = rows
    if a["band_width_pct"] and b["band_width_pct"]:
        print(f"\nBAND WIDTH: {a['band_width_pct']}% of the median on 3 years, "
              f"{b['band_width_pct']}% on {b['bars']/(24*252):.0f} years "
              f"({b['band_width_pct']/a['band_width_pct']-1:+.0%}).")
    print(f"wrote {dest.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
