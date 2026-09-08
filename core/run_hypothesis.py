"""Engine 2's last mile: a Strategy in, one hypothesis page out.

`core/pipeline.py` produces the blind walk-forward and its paired null.
This turns that into the row a human reads: pass rate, drawdown, profit factor,
CAGR, and the number that decides everything in this phase — expected days to a
funded account under the firm's real rules.

ONE ROW PER ASSET CLASS. Kris's layout, 2026-09-08: FX, Gold, Crypto. Within a
class every market is walk-forwarded separately and **the best is promoted** —
best by expected days, because that is the phase gate, not by profit factor.
The others are kept on the row so the choice is visible rather than implied.

PROMOTING THE BEST OF N IS A SEARCH, and it is scored as one: every market also
runs the identical procedure on a phase-randomised copy of itself, and the row
carries what the null achieved. A class whose best market does not beat its own
null has found the best of three coin flips.

Run:  .venv/bin/python core/run_hypothesis.py vwap
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core import fingerprint as FP                             # noqa: E402
from core.markets import (ASSET_CLASS, COSTS, EXEC_MODE,        # noqa: E402
                          TF_BPH, load)
from core.pipeline import Market, Pipeline, pf                 # noqa: E402
from core.riskladder import from_trades                        # noqa: E402

BT = ROOT / "backtests"
CLASSES = ("FX", "Gold", "Crypto")

#: HOW MUCH HISTORY EVERY MARKET GETS. Kris's standing rule, 2026-09-08: always
#: the last three years.
#:
#: Three years of DATA, not three years of out-of-sample. The first twelve months
#: are the initial training window, so what comes out is roughly TWO years of
#: blind quarterly tests. Three years of out-of-sample would need four years of
#: data and the FX/metals caches only reach back to 2023-09.
#:
#: It is also a hard limit, not a minimum: BTC has 9.1 years and gets the same
#: three as EURUSD. Before this, crypto quietly received an extra quarter because
#: its cache ends six days later than Dukascopy's, and "crypto beat FX" partly
#: meant "crypto was measured over a longer window".
YEARS = 3


def cagr(daily_r: pd.Series, risk: float) -> float:
    """Compounded annual growth at the chosen risk per trade.

    Compounded because that is what a real account does — each day's return is
    earned on the balance the previous days left behind. A simple sum would
    flatter a strategy whose good stretch comes early.
    """
    if not len(daily_r):
        return float("nan")
    eq = float(np.prod(1.0 + daily_r.values * risk))
    span = (daily_r.index[-1] - daily_r.index[0]).total_seconds() / 86400.0
    if span <= 0 or eq <= 0:
        return float("nan")
    return (eq ** (365.0 / span) - 1.0) * 100.0


def metrics(trades: pd.DataFrame) -> dict:
    """Everything the board reports, from one stitched walk-forward series."""
    if not len(trades):
        return {}
    t = trades.sort_values("exit_ts")
    r = t.r.values
    daily = pd.Series(r, index=pd.DatetimeIndex(t.exit_ts)).resample("1D").sum()
    rows, pick = from_trades(r, t.exit_ts)
    eq = np.concatenate(([0.0], np.cumsum(r)))
    dd_r = float((eq - np.maximum.accumulate(eq)).min())
    span = (t.exit_ts.max() - t.exit_ts.min()).total_seconds() / 86400.0
    sd = float(daily.std())
    return {
        "trades": int(len(r)),
        "pf": round(pf(r), 3),
        "pf_2x": round(pf(t.r_2x.values), 3) if t.r_2x.notna().all() else None,
        "win_pct": round(float((r > 0).mean()) * 100, 1),
        "avg_r": round(float(r.mean()), 4),
        "trades_per_day": round(len(r) / max(span, 1e-9), 2),
        "r_per_day": round(float(r.mean()) * len(r) / max(span, 1e-9), 4),
        "sharpe": round(float(daily.mean() / sd * np.sqrt(365)), 2) if sd > 0 else None,
        "risk_pct": round(pick["risk"] * 100, 2),
        "pass_pct": round(pick["pass_rate"] * 100, 1),
        "max_dd_pct": round(pick["max_dd"] * 100, 2),
        "days_to_pass": pick["expected_days"],
        "median_days": pick["median_days"],
        "fail_max_pct": round(pick["fail_max"] * 100, 1),
        "fail_daily_pct": round(pick["fail_daily"] * 100, 1),
        "cagr_pct": round(cagr(daily, pick["risk"]), 1),
        "span_days": round(span, 0),
    }


def best_cell(folds: pd.DataFrame, trades: pd.DataFrame) -> pd.DataFrame:
    """The single (floor, topn) selection rule with the most trades.

    NOT the best-scoring one. Picking the selection rule by its own result is
    the search-on-the-test-set mistake one level up; taking the busiest keeps
    the choice independent of the outcome.
    """
    if not len(trades):
        return trades
    counts = trades.groupby(["floor", "topn"]).size()
    floor, topn = counts.idxmax()
    return trades[(trades.floor == floor) & (trades.topn == topn)]


def window(syms, tfs, years: int = YEARS) -> tuple[pd.Timestamp, pd.Timestamp]:
    """The common [start, end] every market in this study is trimmed to.

    The end is the EARLIEST last bar across the universe, not the latest. Caches
    finish on different days and a fold boundary falling between two of them
    hands one market an extra quarter of testing that the others never get.
    """
    ends = []
    for s in syms:
        for t in tfs:
            try:
                d = load(s, t)
            except (FileNotFoundError, KeyError):
                continue
            if len(d):
                ends.append(d.index[-1])
    if not ends:
        raise ValueError("no market in the universe has data")
    end = min(ends)
    return end - pd.DateOffset(years=years), end


def run_market(strategy, sym: str, tf: str, pipe_kw: dict,
               null_seeds: int = 1, span=None) -> dict:
    df = load(sym, tf)
    if span is not None:
        lo, hi = span
        df = df[(df.index >= lo) & (df.index <= hi)]
    c = COSTS[sym]
    # Limit entry, market exit - a stop-loss cannot be a limit order.
    fee, slip = c.per_side(EXEC_MODE)
    bph = TF_BPH[tf]
    pad = int(max(20, round(24 * 4 * bph)) * 2)
    m = Market(sym=sym, tf=tf, df=df, fee_bps=fee, slip_bps=slip, pad_bars=pad)

    g = [dict(x) for x in strategy.grid(tf)]
    for x in g:
        x["min_risk_bps"] = c.min_risk_bps
    strat = _FixedGrid(strategy, g)

    p = Pipeline(strat, **pipe_kw)
    real = p.walk_forward(m)
    out = {"sym": sym, "tf": tf, "asset_class": ASSET_CLASS[sym],
           "cost_rt_bps": round(c.round_trip(EXEC_MODE), 2),
           "cost_taker_bps": round(c.round_trip("taker"), 2),
           "exec_mode": EXEC_MODE, "cost_measured": c.measured,
           "data_from": str(df.index[0].date()) if len(df) else None,
           "data_to": str(df.index[-1].date()) if len(df) else None,
           **metrics(best_cell(real.folds, real.trades))}

    nulls = []
    for s in range(null_seeds):
        n = p.walk_forward(m, shuffled="paired", tag=f"wf{s}")
        nm = metrics(best_cell(n.folds, n.trades))
        if nm:
            nulls.append(nm)
    if nulls:
        out["null_pf"] = round(float(np.median([x["pf"] for x in nulls])), 3)
        out["null_days"] = float(np.median(
            [x["days_to_pass"] for x in nulls if x["days_to_pass"]] or [np.nan]))
        out["beats_null"] = bool(out.get("pf") and out["pf"] > out["null_pf"])
    return out


class _FixedGrid:
    """Wraps a strategy so the grid carries this market's min-risk floor."""

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


def _assemble(cells, *, sid, hid, name, tagline, tfs, universe,
              manifest=None, done=True) -> dict:
    """Rows from whatever cells exist so far. Safe to call mid-run."""
    rows = []
    for cls in CLASSES:
        got = [c for c in cells if c["asset_class"] == cls and c.get("days_to_pass")]
        if not got:
            empty = [c for c in cells if c["asset_class"] == cls]
            rows.append({"asset_class": cls, "sym": None,
                         "note": ("no market in this class resolved an account"
                                  if empty else "not run yet"),
                         "considered": [{"sym": c["sym"], "tf": c["tf"],
                                         "pf": c.get("pf"),
                                         "days_to_pass": c.get("days_to_pass")}
                                        for c in empty]})
            continue
        # best by DAYS TO PASS - the phase gate - not by profit factor
        best = dict(min(got, key=lambda c: c["days_to_pass"]))
        best["considered"] = [
            {"sym": c["sym"], "tf": c["tf"], "pf": c.get("pf"),
             "days_to_pass": c.get("days_to_pass")}
            for c in cells if c["asset_class"] == cls]
        rows.append(best)

    rec = {"sid": sid, "hid": hid, "name": name, "tagline": tagline,
           "when": pd.Timestamp.utcnow().isoformat(),
           "structure": "one_step_6pct", "complete": bool(done),
           "years": YEARS,
           "timeframes": tfs, "universe": universe,
           "rows": rows, "cells": cells}
    if manifest:
        rec["fingerprint"] = FP.make(**manifest)
    return rec


def run(strategy, *, sid: str, hid: str, name: str, tagline: str,
        universe: dict[str, list[str]], tfs: list[str],
        pipe_kw: dict | None = None, manifest: dict | None = None,
        null_seeds: int = 1, years: int = YEARS) -> dict:
    """Walk-forward every market, promote the best per asset class, write the page.

    THE PAGE IS WRITTEN AFTER EVERY CELL, not at the end. A full universe takes
    ten to twenty minutes and the first version of this only wrote on completion,
    so the board sat empty the whole time and there was no way to tell a slow run
    from a hung one. `complete: false` marks a partial record.
    """
    pipe_kw = dict(pipe_kw or {})
    all_syms = [s for v in universe.values() for s in v]
    span = window(all_syms, tfs, years)
    # every market is trimmed to the same window, so the pipeline derives its own
    # fold boundaries from it rather than being handed hardcoded dates
    pipe_kw.pop("first_test", None)
    pipe_kw.pop("last_test", None)
    print(f"  window: {span[0].date()} -> {span[1].date()}  ({years} years, "
          f"first 12 months are the initial training window)\n")

    out = BT / sid / "hypothesis.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    cells = []
    for cls, syms in universe.items():
        for sym in syms:
            for tf in tfs:
                try:
                    df = load(sym, tf)
                except (FileNotFoundError, KeyError):
                    continue
                if not len(df):
                    continue
                t = time.time()
                print(f"  {cls:6s} {sym:8s} {tf:3s} ...", end=" ", flush=True)
                cell = run_market(strategy, sym, tf, pipe_kw, null_seeds, span)
                cell["asset_class"] = cls
                cells.append(cell)
                print(f"{cell.get('trades', 0):5d} trades  "
                      f"PF {cell.get('pf', float('nan'))}  "
                      f"{cell.get('days_to_pass')} d  [{time.time()-t:.0f}s]",
                      flush=True)
                out.write_text(json.dumps(
                    _assemble(cells, sid=sid, hid=hid, name=name,
                              tagline=tagline, tfs=tfs, universe=universe,
                              done=False), indent=1, default=str))

    rec = _assemble(cells, sid=sid, hid=hid, name=name, tagline=tagline,
                    tfs=tfs, universe=universe, manifest=manifest, done=True)
    out.write_text(json.dumps(rec, indent=1, default=str))
    print(f"\n  wrote {out.relative_to(ROOT)}")
    return rec
