"""H-041b — the daily-loss guard at a FIXED rung, on a finer sweep, against a
day-shuffled control. Pre-registration: DAILYGUARD.md, section H-041b.

H-041 found blow-ups falling 49.3 -> 40.8 (1h) and 70.5 -> 48.3 (4h) at a -1.0%
guard, and its own write-up gave three reasons to distrust it. This answers all
three:

  1. the risk rung was chosen per arm, so a lower rung may be doing the work -
     the full 4x8 matrix is reported and the headline is read at a rung FIXED in
     advance (3.0%, the rung the baseline itself selected on both timeframes);
  2. the curve was not monotone - four more thresholds are added between -0.5%
     and -1.25% to tell a curve from a spike;
  3. THERE WAS NO CONTROL. A guard can only remove trades, and removing trades
     cuts blow-ups on its own. The day-shuffled control blocks the same number
     of days chosen at random, so "the account signal is informative" is finally
     separable from "trading less is safer".

`apply_guard` is imported from `dailyguard.py`, not re-implemented, so
`tests/test_dailyguard.py`'s look-ahead guard still covers the logic that
decides which trades are dropped.

Run: .venv/bin/python strategies/vwapbreak/research/dailyguard2.py
"""
from __future__ import annotations

import importlib.util
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

_spec = importlib.util.spec_from_file_location(
    "dailyguard", Path(__file__).with_name("dailyguard.py"))
_dg = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_dg)
apply_guard = _dg.apply_guard

THUNDERBOLT = PropRules(profit_target=0.06, daily_loss=0.03, max_loss=0.06,
                        min_trading_days=0)
RISKS = (0.01, 0.015, 0.02, 0.03)
#: FIXED BEFORE THE MATRIX WAS SEEN. The rung the BASELINE selected on both
#: timeframes in H-041, so it cannot have been picked to suit an arm.
FIXED_RISK = 0.03
CELLS = [("XAUUSD", "1h"), ("XAUUSD", "4h")]
#: the finer sweep. -0.5/-0.75/-1.25 are new and bracket H-041's -1.0% step.
GUARDS = (None, 0.005, 0.0075, 0.010, 0.0125, 0.015, 0.020, 0.025)
SEEDS = 25


def tag_of(g: float | None) -> str:
    return "none" if g is None else f"-{g*100:.2f}%"


def blocked_days(tr: pd.DataFrame, kept: pd.DataFrame) -> int:
    """How many distinct UTC entry-days the guard took at least one trade off.

    The control has to remove the same amount of trading in the same shape, and
    the guard blocks whole days, not individual trades - matching on trade count
    alone would hand the control a freedom the guard does not have.
    """
    gone = tr.index.difference(kept.index)
    if not len(gone):
        return 0
    return int(pd.DatetimeIndex(tr.loc[gone].entry_ts).normalize().nunique())


def shuffle_days(tr: pd.DataFrame, n_days: int, rng) -> pd.DataFrame:
    """Block `n_days` entry-days chosen at random. Carries no information."""
    if n_days <= 0:
        return tr
    days = pd.DatetimeIndex(tr.entry_ts).normalize().values
    uniq = np.unique(days)
    chosen = rng.choice(uniq, size=min(n_days, len(uniq)), replace=False)
    return tr[~np.isin(days, chosen)]


def score(tr: pd.DataFrame, risk: float, with_band: bool = True) -> dict | None:
    if not len(tr):
        return None
    daily = pd.Series(tr.r.values,
                      index=pd.DatetimeIndex(tr.exit_ts)).resample("1D").sum()
    a = run_accounts(daily, risk, THUNDERBOLT)
    if not a["pass_rate"]:
        return None
    out = {"risk_pct": risk * 100, "trades": len(tr),
           "pass_pct": round(a["pass_rate"] * 100, 1),
           "blown_pct": round((a["fail_max"] + a["fail_daily"]) * 100, 1),
           "fail_daily_pct": round(a["fail_daily"] * 100, 1),
           "days": round(a["median_days"] / a["pass_rate"], 1)}
    if with_band:
        out["band"] = nb_band(daily, risk, rules=THUNDERBOLT)
    return out


def spearman(x, y) -> float:
    """Rank correlation, written out rather than pulled from scipy, which this
    project does not pin."""
    rx = pd.Series(x).rank().values
    ry = pd.Series(y).rank().values
    if np.std(rx) == 0 or np.std(ry) == 0:
        return float("nan")
    return float(np.corrcoef(rx, ry)[0, 1])


def main() -> int:
    span = window(["XAUUSD"], ["1h", "4h"])
    out: dict = {}
    for sym, tf in CELLS:
        res = run_market(STRATEGY, sym, tf,
                         pipe_kw={"floors": (30,), "topn": (5,)},
                         null_seeds=0, span=span)
        tr = res["_trades"].copy().reset_index(drop=True)
        tr["entry_ts"] = pd.to_datetime(tr.entry_ts, utc=True)
        tr["exit_ts"] = pd.to_datetime(tr.exit_ts, utc=True)
        key = f"{sym}|{tf}"
        print(f"\n=== {sym} {tf}  ({len(tr)} blind trades) " + "=" * 34, flush=True)

        # ---- 1. the full matrix. No rung is selected anywhere in it. ------- #
        print("\n-- blown% by guard x rung (the confound, shown rather than "
              "collapsed) --", flush=True)
        hdr = f"{'guard':>9}" + "".join(f"{r*100:>9.2f}%" for r in RISKS)
        print(hdr); print("-" * len(hdr), flush=True)
        matrix: dict = {}
        for g in GUARDS:
            row = []
            for risk in RISKS:
                s = score(apply_guard(tr, risk, g), risk)
                matrix[f"{tag_of(g)}|{risk}"] = s
                row.append("     n/a" if not s else f"{s['blown_pct']:>8.1f}")
            print(f"{tag_of(g):>9}" + "".join(f"{c:>10}" for c in row), flush=True)

        # ---- 2. the fixed rung, with the day-shuffled control -------------- #
        print(f"\n-- at the FIXED {FIXED_RISK*100:.1f}% rung, against a "
              f"day-shuffled control ({SEEDS} seeds) --", flush=True)
        hdr = (f"{'guard':>9}{'trades':>8}{'days':>7}{'band':>13}{'pass%':>7}"
               f"{'blown%':>8}{'ctrl blown% (p10-p90)':>25}")
        print(hdr); print("-" * len(hdr), flush=True)
        fixed: dict = {}
        for g in GUARDS:
            kept = apply_guard(tr, FIXED_RISK, g)
            s = score(kept, FIXED_RISK)
            if not s:
                print(f"{tag_of(g):>9}   no passing rung", flush=True); continue
            nb = blocked_days(tr, kept)
            ctrl = []
            if g is not None:
                for seed in range(SEEDS):
                    rng = np.random.default_rng(seed)
                    cs = score(shuffle_days(tr, nb, rng), FIXED_RISK,
                               with_band=False)
                    if cs:
                        ctrl.append(cs["blown_pct"])
            s["blocked_days"] = nb
            s["ctrl_blown"] = ctrl
            s["ctrl_med"] = round(float(np.median(ctrl)), 1) if ctrl else None
            s["ctrl_p10"] = round(float(np.percentile(ctrl, 10)), 1) if ctrl else None
            s["ctrl_p90"] = round(float(np.percentile(ctrl, 90)), 1) if ctrl else None
            fixed[tag_of(g)] = s
            b = s["band"] or {}
            bs = ("%.1f-%.1f" % (b["days_lo"], b["days_hi"])) if b else "-"
            cs = ("-" if not ctrl else
                  f"{s['ctrl_med']:.1f} ({s['ctrl_p10']:.1f}-{s['ctrl_p90']:.1f})")
            print(f"{tag_of(g):>9}{s['trades']:>8}{s['days']:>7.1f}{bs:>13}"
                  f"{s['pass_pct']:>7.1f}{s['blown_pct']:>8.1f}{cs:>25}", flush=True)

        # ---- 3. monotonicity, the pre-registered test --------------------- #
        arms = [g for g in GUARDS if g is not None and tag_of(g) in fixed]
        rho = spearman([g for g in arms],
                       [fixed[tag_of(g)]["blown_pct"] for g in arms])
        print(f"\n   Spearman(threshold, blown%) at the fixed rung = {rho:+.3f}"
              f"   (pre-registered bar: >= +0.700)", flush=True)
        out[key] = {"matrix": matrix, "fixed": fixed, "spearman": rho,
                    "fixed_risk": FIXED_RISK, "seeds": SEEDS,
                    "n_trades": int(len(tr))}

    dest = ROOT / "backtests" / "vwapbreak" / "dailyguard2.json"
    dest.write_text(json.dumps({"guards": list(GUARDS), "risks": list(RISKS),
                                "fixed_risk": FIXED_RISK, "seeds": SEEDS,
                                "cells": out}, indent=1, default=str))
    print(f"\nwrote {dest.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
