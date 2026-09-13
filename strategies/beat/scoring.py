"""One scorer for every arm in `strategies/beat/`, band included.

WHY THIS EXISTS RATHER THAN `core.noiseband.band`. The band decides the kill
criterion in `notes.md` - an arm must be faster AND its band must not overlap the
baseline's. `noiseband.band` scores its resamples with `_states(r[idx] * risk)`,
a FLAT risk multiplier, because that is what the board quotes. The arms here are
scored under BUDGET-LINEAR sizing, which is what the strategy actually trades
since 2026-09-10.

Quoting a flat-risk band around a budget-linear number would be two different
measurements wearing one label, and the overlap test between them would mean
nothing. So the block structure is taken from the board - `_resample_index`, the
same stationary bootstrap at the same mean block length - and only the SCORER is
swapped for `tier1.run_scaled(..., "budget")`.

`run_scaled` is deliberately a copy of `riskladder.run_accounts` so research
cannot move board numbers; importing it here keeps that property. Verified on
the real walk-forward series from `objective.json`: it returns pass 77.0%, blown
16.9%, days 16.9, which is exactly what `core.chosen.CHOSEN["sizing"]["measured"]`
records. It is the adopted rule, not a lookalike.

ASH, NOT THUNDERBOLT. These research scripts score against `tier1.ASH` (2%
target, 3% daily, 6% max) and so does `subhour.py`, whose 11.7-day figure is the
baseline being attacked. Switching firm specs mid-comparison would make the
numbers incomparable, so ASH it is.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from core.noiseband import (HI_PCT, LO_PCT, MEAN_BLOCK,            # noqa: E402
                            RESAMPLES, _resample_index)
from strategies.vwapbreak.research.tier1 import (ASH, RISKS,       # noqa: E402
                                                 run_scaled)


def daily_from(res: dict) -> pd.Series:
    """The stitched walk-forward trade list, resampled to calendar days."""
    tr = res["_trades"]
    return pd.Series(tr.r.values,
                     index=pd.DatetimeIndex(tr.exit_ts)).resample("1D").sum()


def score_budget(daily: pd.Series, resamples: int = RESAMPLES,
                 seed: int = 0) -> dict:
    """Best rung of the risk ladder under budget-linear sizing, with its band.

    The band is computed at the CHOSEN rung only. Quoting a band from one rung
    beside a headline from another is the mistake `core/noiseband` was written to
    stop, and it would be just as wrong here.
    """
    best = None
    for risk in RISKS:
        a = run_scaled(daily, risk, "budget", ASH)
        if not a.get("days"):
            continue
        if best is None or a["days"] < best["days"]:
            best = {**a, "risk_pct": round(risk * 100, 2)}
    if best is None:
        return {"days": None, "band": None}

    r = np.asarray(daily.values, dtype=float)
    n = len(r)
    if n < 60:
        # same refusal as noiseband.band: a band from a handful of days invites
        # exactly the false confidence it exists to prevent.
        best["band"] = None
        return best

    risk = best["risk_pct"] / 100.0
    rng = np.random.default_rng(seed)
    idx = _resample_index(n, resamples, rng, MEAN_BLOCK)
    days, rates = [], []
    for row in idx:
        a = run_scaled(pd.Series(r[row]), risk, "budget", ASH)
        rates.append(a["pass_pct"])
        if a.get("days"):
            days.append(a["days"])
    never = (1.0 - len(days) / len(idx)) * 100.0
    best["band"] = {
        "days_lo": round(float(np.percentile(days, LO_PCT)), 1) if days else None,
        "days_hi": round(float(np.percentile(days, HI_PCT)), 1) if days else None,
        "days_med": round(float(np.median(days)), 1) if days else None,
        "pass_lo": round(float(np.percentile(rates, LO_PCT)), 1),
        "pass_hi": round(float(np.percentile(rates, HI_PCT)), 1),
        "pass_med": round(float(np.median(rates)), 1),
        "never_pct": round(never, 1),
        "resamples": int(resamples), "mean_block": int(MEAN_BLOCK),
        "sizing": "budget-linear", "rules": "ASH",
    }
    return best


def beats(arm: dict, base: dict) -> tuple[bool, list[str]]:
    """The pre-registered test: faster AND bands disjoint. Returns why not."""
    fails = []
    if not arm.get("days") or not base.get("days"):
        return False, ["no days"]
    if arm["days"] >= base["days"]:
        fails.append("not faster")
    a, b = arm.get("band"), base.get("band")
    if not a or not b or a.get("days_hi") is None or b.get("days_hi") is None:
        fails.append("no band")
    elif not (a["days_hi"] < b["days_lo"] or b["days_hi"] < a["days_lo"]):
        fails.append("band overlaps")
    return (not fails), fails


def row(name: str, s: dict) -> str:
    b = s.get("band") or {}
    lo, hi = b.get("days_lo"), b.get("days_hi")
    span = f"{lo:.0f}-{hi:.0f}" if lo is not None else "-"
    return (f"  {name:26}{s.get('risk_pct', 0):6.2f}{s.get('days') or 0:9.1f}"
            f"{span:>12}{s.get('pass_pct') or 0:8.1f}"
            f"{s.get('blown_pct') or 0:8.1f}{s.get('still_open_pct') or 0:8.1f}")


HEADER = (f"  {'arm':26}{'risk%':>6}{'days':>9}{'band':>12}"
          f"{'pass%':>8}{'blown%':>8}{'open%':>8}")
