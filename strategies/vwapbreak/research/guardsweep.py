"""H-042 - the daily-loss guard, settled. Pre-registration: GUARDSWEEP.md.

H-041 found one arm that met its survival condition on both timeframes and then
listed three reasons to distrust it. This runs the two follow-ups its own result
section called NOT OPTIONAL - the finer threshold sweep, and every arm re-scored
at a FIXED risk rung - and adds the control H-041 never had.

THE CONTROL IS THE POINT. The -1.0% guard removes 38% of the trades on 1h.
Fewer trades is less exposure and less exposure lowers a blow-up rate by itself,
so "the guard lowers blow-ups" is not a finding - it is arithmetic. The matched-
drop null permutes the guard's own per-day drop counts across days and drops the
same trades from the wrong days. It keeps the count, keeps the end-of-day shape,
and destroys the only thing the guard claims to know: WHICH days were bad.

This study CANNOT make H-027 faster and is not trying to. H-041's speed
condition failed at every threshold on both timeframes and is settled.

Run: .venv/bin/python strategies/vwapbreak/research/guardsweep.py
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

from core.noiseband import (HI_PCT, LO_PCT, MEAN_BLOCK, RESAMPLES,   # noqa: E402
                            _per_row, _resample_index, _states)
from core.prop_rules import PropRules                                # noqa: E402
from core.riskladder import MAX_DAYS, run_accounts                   # noqa: E402
from core.run_hypothesis import run_market, window                   # noqa: E402
from strategies.vwapbreak.strategy import STRATEGY                   # noqa: E402

THUNDERBOLT = PropRules(profit_target=0.06, daily_loss=0.03, max_loss=0.06,
                        min_trading_days=0)

#: The free-rung ladder, identical to H-041 so the secondary table is comparable.
RISKS = (0.01, 0.015, 0.02, 0.03)

#: THE PRIMARY SCORING. The rung the baseline chose on both timeframes in H-041,
#: held fixed for every arm so the -1.0% arm cannot win by landing on a smaller
#: position size. That confound is reason 3 of three in DAILYGUARD.md.
FIXED_RISK = 0.03

CELLS = [("XAUUSD", "1h"), ("XAUUSD", "4h")]

#: The day's loss, in ACCOUNT percent, that stops new entries. None = baseline.
#: -0.5/-0.75/-1.25 are new; they are the neighbours that tell a curve from the
#: isolated step H-041 could not rule out.
GUARDS = (None, 0.005, 0.0075, 0.010, 0.0125, 0.015, 0.020, 0.025)

#: Permutations of the drop pattern per arm. 40 puts the 10th percentile of the
#: null inside its own Monte Carlo error by a wide margin at this effect size.
NULL_SEEDS = 40

#: Pre-registered threshold for "materially lower", in percentage points.
MATERIAL_PP = 5.0

# The guard's own overlay logic is IMPORTED, never re-implemented: it is pinned
# by tests/test_dailyguard.py, including the look-ahead test that a re-written
# copy would not inherit.
_spec = importlib.util.spec_from_file_location(
    "dailyguard", Path(__file__).with_name("dailyguard.py"))
_dg = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_dg)
apply_guard = _dg.apply_guard


def day_grid(tr: pd.DataFrame) -> pd.DatetimeIndex:
    """The calendar every arm is scored on - the UNGUARDED series' full span.

    Dropping trades must not shorten the calendar. `resample("1D")` on a subset
    spans that subset's own first and last exit, so an arm that happens to skip
    the first week would be handed a shorter series and a different set of
    account start days. Every arm is reindexed onto this one grid, zeros filled.
    """
    x = pd.DatetimeIndex(tr.exit_ts).normalize()
    return pd.date_range(x.min(), x.max(), freq="1D", tz="UTC")


def daily(tr: pd.DataFrame, grid: pd.DatetimeIndex) -> pd.Series:
    if not len(tr):
        return pd.Series(0.0, index=grid)
    s = pd.Series(tr.r.values, index=pd.DatetimeIndex(tr.exit_ts)).resample("1D").sum()
    return s.reindex(grid, fill_value=0.0)


def stats(d: pd.Series, risk: float) -> dict | None:
    """Point estimate, from the scalar `run_accounts` that every board number uses."""
    a = run_accounts(d, risk, THUNDERBOLT)
    if not a["pass_rate"]:
        return None
    return {"risk_pct": round(risk * 100, 2),
            "pass_pct": round(a["pass_rate"] * 100, 1),
            "blown_pct": round((a["fail_max"] + a["fail_daily"]) * 100, 1),
            "fail_daily_pct": round(a["fail_daily"] * 100, 1),
            "fail_max_pct": round(a["fail_max"] * 100, 1),
            "open_pct": round(a["still_open"] * 100, 1),
            "days": round(a["median_days"] / a["pass_rate"], 1)}


def bands(d: pd.Series, risk: float, seed: int = 0) -> dict:
    """10-90 bands for expected days AND for the blow-up rate, one bootstrap.

    Same stationary block bootstrap and same vectorised simulation
    `core.noiseband.band` uses, so the days band here is that function's number.
    THE BLOW-UP BAND IS THE ADDITION: H-041 quoted 49.3% -> 40.8% naked, and
    CLAUDE.md's rule is that a number without its band is not quotable.
    """
    r = np.asarray(d.values, dtype=float)
    n = len(r)
    if n < 60:
        return {}
    idx = _resample_index(n, RESAMPLES, np.random.default_rng(seed), MEAN_BLOCK)
    out, day = _states(r[idx] * risk, THUNDERBOLT, MAX_DAYS)
    rate, med = _per_row(out, day)
    blow = ((out == 2) | (out == 3)).mean(axis=1) * 100.0
    ok = np.isfinite(med) & (rate > 0)
    days = med[ok] / rate[ok]
    b = {"blown_lo": round(float(np.percentile(blow, LO_PCT)), 1),
         "blown_hi": round(float(np.percentile(blow, HI_PCT)), 1),
         "blown_med": round(float(np.median(blow)), 1),
         "never_pct": round(float((~ok).mean()) * 100, 1)}
    if len(days):
        b |= {"days_lo": round(float(np.percentile(days, LO_PCT)), 1),
              "days_hi": round(float(np.percentile(days, HI_PCT)), 1)}
    return b


def drops_per_day(tr: pd.DataFrame, kept: pd.DataFrame) -> pd.Series:
    """How many entries the real guard removed on each UTC day."""
    t = tr.sort_values("entry_ts")
    day = pd.DatetimeIndex(t.entry_ts).normalize()
    gone = ~t.index.isin(set(kept.index))
    return pd.Series(gone, index=day).groupby(level=0).sum()


def matched_null(tr: pd.DataFrame, d_day: pd.Series, seed: int) -> pd.DataFrame:
    """Drop the same trades from the WRONG days.

    The per-day drop counts are permuted across the trading days that have any
    entries, and each assigned day loses that many of its LAST entries - the
    same end-of-day shape the real guard produces. Capped at a day's own entry
    count, so the realised drop is <= the real one; `dropped` is reported.
    """
    t = tr.sort_values("entry_ts").copy()
    day = pd.DatetimeIndex(t.entry_ts).normalize()
    days = pd.Index(day.unique())
    counts = np.zeros(len(days), dtype=int)
    counts[:len(d_day)] = d_day.reindex(days, fill_value=0).values[:len(days)]
    perm = np.random.default_rng(seed).permutation(counts)
    assign = dict(zip(days, perm))
    keep = np.ones(len(t), dtype=bool)
    pos = {d: np.flatnonzero(day == d) for d in days}
    for d, k in assign.items():
        if k:
            keep[pos[d][-int(k):]] = False
    return t[keep]


def null_blowups(tr: pd.DataFrame, d_day: pd.Series, grid: pd.DatetimeIndex,
                 risk: float) -> dict:
    """Blow-up rate of NULL_SEEDS matched-drop permutations, simulated at once."""
    rows, dropped = [], []
    for s in range(NULL_SEEDS):
        k = matched_null(tr, d_day, s)
        rows.append(daily(k, grid).values)
        dropped.append(len(tr) - len(k))
    out, _ = _states(np.asarray(rows, dtype=float) * risk, THUNDERBOLT, MAX_DAYS)
    blow = ((out == 2) | (out == 3)).mean(axis=1) * 100.0
    return {"null_blown_lo": round(float(np.percentile(blow, LO_PCT)), 1),
            "null_blown_med": round(float(np.median(blow)), 1),
            "null_blown_hi": round(float(np.percentile(blow, HI_PCT)), 1),
            "null_dropped": int(np.median(dropped))}


def tag(g: float | None) -> str:
    return "none" if g is None else f"-{g*100:.2f}%"


def main() -> int:
    span = window(["XAUUSD"], ["1h", "4h"])
    out: dict[str, dict] = {}
    for sym, tf in CELLS:
        res = run_market(STRATEGY, sym, tf,
                         pipe_kw={"floors": (30,), "topn": (5,)},
                         null_seeds=0, span=span)
        tr = res["_trades"].copy()
        tr["entry_ts"] = pd.to_datetime(tr.entry_ts, utc=True)
        tr["exit_ts"] = pd.to_datetime(tr.exit_ts, utc=True)
        tr = tr.sort_values("entry_ts").reset_index(drop=True)
        grid = day_grid(tr)
        print(f"\n=== {sym} {tf}  ({len(tr)} blind trades, {len(grid)} days) "
              + "=" * 24, flush=True)

        print(f"\nPRIMARY - every arm at {FIXED_RISK*100:.2f}% risk "
              "(H-041 confound 3 removed)", flush=True)
        hdr = (f"{'guard':>8}{'trades':>8}{'days':>7}{'band':>13}{'pass%':>7}"
               f"{'blown%':>8}{'band':>13}{'null blown%':>14}{'failDay%':>10}")
        print(hdr); print("-" * len(hdr), flush=True)
        for g in GUARDS:
            kept = apply_guard(tr, FIXED_RISK, g)
            d = daily(kept, grid)
            s = stats(d, FIXED_RISK)
            if not s:
                print(f"{tag(g):>8}   no passing account"); continue
            s |= bands(d, FIXED_RISK)
            s["trades"] = len(kept)
            if g is not None:
                s |= null_blowups(tr, drops_per_day(tr, kept), grid, FIXED_RISK)
            out[f"{sym}|{tf}|fixed|{tag(g)}"] = s
            nb = ("" if g is None else
                  f"{s['null_blown_med']:.1f} [{s['null_blown_lo']:.1f}-{s['null_blown_hi']:.1f}]")
            print(f"{tag(g):>8}{s['trades']:>8}{s['days']:>7.1f}"
                  f"{('%.1f-%.1f' % (s.get('days_lo', 0), s.get('days_hi', 0))):>13}"
                  f"{s['pass_pct']:>7.1f}{s['blown_pct']:>8.1f}"
                  f"{('%.1f-%.1f' % (s['blown_lo'], s['blown_hi'])):>13}"
                  f"{nb:>14}{s['fail_daily_pct']:>10.1f}", flush=True)

        print("\nSECONDARY - free rung, H-041's convention. No claim is made "
              "from this table.", flush=True)
        hdr2 = (f"{'guard':>8}{'trades':>8}{'risk%':>7}{'days':>7}{'pass%':>7}"
                f"{'blown%':>8}{'failDay%':>10}")
        print(hdr2); print("-" * len(hdr2), flush=True)
        for g in GUARDS:
            best = None
            for risk in RISKS:
                kept = apply_guard(tr, risk, g)
                s = stats(daily(kept, grid), risk)
                if s and (best is None or s["days"] < best["days"]):
                    best = s | {"trades": len(kept)}
            out[f"{sym}|{tf}|free|{tag(g)}"] = best
            if not best:
                print(f"{tag(g):>8}   no passing rung"); continue
            print(f"{tag(g):>8}{best['trades']:>8}{best['risk_pct']:>7.2f}"
                  f"{best['days']:>7.1f}{best['pass_pct']:>7.1f}"
                  f"{best['blown_pct']:>8.1f}{best['fail_daily_pct']:>10.1f}",
                  flush=True)

    dest = ROOT / "backtests" / "vwapbreak" / "guardsweep.json"
    dest.write_text(json.dumps(
        {"guards": list(GUARDS), "fixed_risk": FIXED_RISK,
         "null_seeds": NULL_SEEDS, "material_pp": MATERIAL_PP,
         "rows": out}, indent=1, default=str))
    print(f"\nwrote {dest.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
