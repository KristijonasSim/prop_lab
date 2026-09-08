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
CLASSES = ("FX", "Metals/Energy", "Crypto")

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
    ladder, pick = from_trades(r, t.exit_ts)
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
        # EVERY risk level, not just the chosen one, so the board can be
        # re-scored in the browser without re-running anything.
        #
        # Risk per trade is the only lever left once a configuration has been
        # chosen blind, and it moves speed and survival in OPPOSITE directions:
        # more risk reaches 6% sooner and blows more accounts on the way. PF,
        # win rate, average R, trades per day and Sharpe are all R-based and do
        # NOT move with risk - only pass rate, drawdown, days and CAGR do.
        "ladder": [{
            "risk_pct": round(x["risk"] * 100, 2),
            "pass_pct": round(x["pass_rate"] * 100, 1),
            "max_dd_pct": round(x["max_dd"] * 100, 2),
            "days_to_pass": x["expected_days"],
            "median_days": x["median_days"],
            "fail_max_pct": round(x["fail_max"] * 100, 1),
            "fail_daily_pct": round(x["fail_daily"] * 100, 1),
            "still_open_pct": round(x["still_open"] * 100, 1),
            "cagr_pct": round(cagr(daily, x["risk"]), 1),
            "picked": x["risk"] == pick["risk"],
        } for x in ladder],
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

    # SNAPPED TO A MONTH BOUNDARY, and this is the point of the function.
    #
    # Caches end on whatever day their last download finished. XAGUSD ends
    # 2026-08-25 and everything else ends 2026-08-30, so ADDING SILVER TO THE
    # METALS CLASS MOVED CRYPTO'S NUMBERS - five fewer days at the end changed
    # the final fold, which changed the trades, which changed the profit factor
    # and the days-to-pass of markets that have nothing to do with silver.
    #
    # A study's window must not depend on which markets happen to be in it.
    # Snapping down to the first of the month absorbs that jitter: 2026-08-25 and
    # 2026-08-30 both become 2026-08-01, so adding a leg changes nothing unless
    # its history is genuinely shorter by a month or more. Folds already begin on
    # month starts, so nothing is lost but the ragged tail.
    end = min(ends).normalize().replace(day=1)
    if end.tz is None:
        end = end.tz_localize("UTC")
    return end - pd.DateOffset(years=years), end


def basket(legs: list[pd.DataFrame], names: list[str]) -> pd.DataFrame:
    """Combine several markets into ONE book, equally weighted.

    Each leg's R is divided by the leg count, so a book of N is directly
    comparable to a single market: the same 1% of equity is split across N
    positions rather than staked on one.

    THIS IS THE THING THAT KILLED H-012, and the arithmetic is worth stating
    because it is not obvious. Equal weighting divides the BOOK's R per day by
    the leg count while the drawdown falls by much less than that (the legs are
    correlated and the bad stretches overlap). H-012's median leg had R/day
    -0.0013, so every leg added cost more R per day than it saved in drawdown
    and the book got SLOWER: 15.9 days in-window against 130.7 held out.

    Why it is worth re-running anyway: the binding constraint has changed. Under
    the old modelled 8%+5% firm, drawdown was not what stopped a book. Under
    Thunderbolt's 6% cap it is - crypto's chosen risk sits at 0.50% with 55% of
    accounts STALLING, purely to keep the curve inside the cap. If a basket cuts
    drawdown per unit of R, it buys a higher risk level, and risk is what buys
    days. That route did not exist when H-012 ran. It may still lose.
    """
    if not legs:
        return pd.DataFrame()
    n = len(legs)
    parts = []
    for name, g in zip(names, legs):
        if not len(g):
            continue
        h = g.copy()
        h["r"] = h.r / n
        h["r_2x"] = h.r_2x / n
        h["leg"] = name
        parts.append(h)
    if not parts:
        return pd.DataFrame()
    out = pd.concat(parts, ignore_index=True).sort_values("exit_ts")
    return out.reset_index(drop=True)


def common_rule(per_leg: dict) -> tuple:
    """One (floor, topn) selection rule for the whole basket.

    Every leg must be scored under the SAME rule or the book is a mix of
    selection policies and the comparison against a single market means nothing.
    The busiest rule across the class is used - busiest, not best, because
    choosing the rule by its own result is the search-on-the-test-set mistake one
    level up.
    """
    counts: dict[tuple, int] = {}
    for tr in per_leg.values():
        if not len(tr):
            continue
        for k, g in tr.groupby(["floor", "topn"]):
            counts[k] = counts.get(k, 0) + len(g)
    return max(counts, key=counts.get) if counts else (30, 1)


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
    keep_trades = real.trades
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
    out["_trades"] = keep_trades          # stripped before the record is written
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
              manifest=None, done=True, mode="single") -> dict:
    """One record - one page - from whatever cells exist so far.

    `mode="single"` promotes the best market in each class. `mode="basket"`
    trades every market in the class together, equally weighted, on one common
    selection rule. THEY ARE SEPARATE PAGES, on Kris's instruction: mixing a
    four-leg book into the same table as the single markets it is built from
    invites reading one row against another as if they were alternatives at the
    same risk, which they are not.
    """
    rows = []
    for cls in CLASSES:
        mine = [c for c in cells if c["asset_class"] == cls]
        considered = [{"sym": c["sym"], "tf": c["tf"], "pf": c.get("pf"),
                       "days_to_pass": c.get("days_to_pass")} for c in mine]
        if not mine:
            rows.append({"asset_class": cls, "sym": None,
                         "note": "not run yet", "considered": []})
            continue

        if mode == "single":
            got = [c for c in mine if c.get("days_to_pass")]
            if got:
                best = {k: v for k, v in min(
                    got, key=lambda c: c["days_to_pass"]).items() if k != "_trades"}
                best["considered"] = considered
                rows.append(best)
            else:
                rows.append({"asset_class": cls, "sym": None,
                             "note": "no market in this class resolved an account",
                             "considered": considered})
            continue

        # ---- basket ---------------------------------------------------- #
        per_leg = {f"{c['sym']} {c['tf']}": c["_trades"]
                   for c in mine if c.get("_trades") is not None and len(c["_trades"])}
        if len(per_leg) < 2:
            rows.append({"asset_class": cls, "sym": None,
                         "note": (f"only {len(per_leg)} leg has trades - a basket "
                                  f"needs two" if per_leg else "not run yet"),
                         "considered": considered})
            continue
        floor, topn = common_rule(per_leg)
        sel = {k: v[(v.floor == floor) & (v.topn == topn)] for k, v in per_leg.items()}
        sel = {k: v for k, v in sel.items() if len(v)}
        if len(sel) < 2:
            rows.append({"asset_class": cls, "sym": None,
                         "note": "no common selection rule covers two legs",
                         "considered": considered})
            continue
        bk = basket(list(sel.values()), list(sel))
        rows.append({"asset_class": cls,
                     "sym": " + ".join(sorted(sel)), "tf": f"{len(sel)} legs",
                     "legs": sorted(sel), "rule": f"floor {floor} / top {topn}",
                     "cost_rt_bps": None, "cost_measured": False,
                     "considered": considered, **metrics(bk)})

    rec = {"sid": sid, "hid": hid, "name": name, "tagline": tagline,
           "when": pd.Timestamp.utcnow().isoformat(),
           "structure": "one_step_6pct", "complete": bool(done),
           "years": YEARS, "mode": mode,
           "timeframes": tfs, "universe": universe,
           "rows": rows,
           "cells": [{k: v for k, v in c.items() if k != "_trades"} for c in cells]}
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
    bout = BT / f"{sid}_basket" / "hypothesis.json"
    bout.parent.mkdir(parents=True, exist_ok=True)
    cells = []

    def _write(done: bool):
        """Both pages, from the same cells. Separate files, separate tabs."""
        out.write_text(json.dumps(_assemble(
            cells, sid=sid, hid=hid, name=name, tagline=tagline, tfs=tfs,
            universe=universe, manifest=manifest if done else None,
            done=done, mode="single"), indent=1, default=str))
        bout.write_text(json.dumps(_assemble(
            cells, sid=f"{sid}_basket", hid=f"{hid}B",
            name=f"{name} — basket",
            tagline=("Every market in the class traded together, equally "
                     "weighted, on one common selection rule."),
            tfs=tfs, universe=universe,
            manifest=manifest if done else None,
            done=done, mode="basket"), indent=1, default=str))
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
                _write(done=False)

    _write(done=True)
    rec = json.loads(out.read_text())
    print(f"\n  wrote {out.relative_to(ROOT)}")
    print(f"  wrote {bout.relative_to(ROOT)}")
    return rec
