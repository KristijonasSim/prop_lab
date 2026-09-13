"""ARM 3b — the one unresolved thing, re-measured on 43 quarters instead of 8.

Arm 3 killed `rday_capped` at every rung, but left one honest ambiguity. At 1.5%
risk the dd<=20R arm was BETTER than the shipped selector on every axis except
resolvability:

    baseline   11.8 days [10-16]   67.8% pass   27.6% blown
    dd<=20R    10.1 days [9.1-13.3] 69.2% pass   24.4% blown

Faster, fewer blow-ups, same pass rate - and the bands overlap, so under this
repo's rules it is NOT shown to differ. It is also not worse.

WHAT RESOLVES AN OVERLAPPING BAND IS MORE DATA, NOT ANOTHER ARM. The band is
9.1-13.3 because the walk-forward runs three years and eight quarters.
`XAUUSD10Y` holds eleven years - 78,120 bars, ~43 quarters, five times the folds.
`RESEARCH_NEXT` 2.1 names gold history as the single biggest lever for exactly
this reason.

EXPECTATIONS ARE LOW AND STATED FIRST. The null margin on this arm is 1.526
against 1.289, or 1.18x, and that ratio is rung-independent. More history can
narrow a band; it cannot manufacture an edge over shuffled data. This run can
resolve an ambiguity. It cannot create a result.

NO RUNG IS PICKED IN ADVANCE. Both arms print their full ladder and the same four
conditions are applied. Choosing 1.5% because it looked best on three years would
be the cherry-pick this study exists to avoid.

XAUUSD10Y IS NOT A REGISTERED SYMBOL - it is not in COSTS, ASSET_CLASS or
TF_RULE, so `run_market` would KeyError. The same pattern `longhistory.py` and
`longcandidates.py` use is followed here: keep SYM="XAUUSD" for the cost model,
load the long frame directly, and build the Market by hand.

Run: .venv/bin/python strategies/beat/eleven_years.py
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from core.markets import COSTS, EXEC_MODE, TF_BPH                  # noqa: E402
from core.noiseband import (LO_PCT, HI_PCT, MEAN_BLOCK,            # noqa: E402
                            _resample_index)
from core.pipeline import Market, Pipeline                         # noqa: E402
from core.run_hypothesis import best_cell, metrics                 # noqa: E402
from strategies.beat.scoring import ASH, RISKS, run_scaled         # noqa: E402
from strategies.vwapbreak.research.exits import (WIDE_SIGMA,       # noqa: E402
                                                 ExitVariant)

SYM, TF = "XAUUSD", "1h"
MAX_DD_R = 20.0
BASELINE_BLOWN_GUARD = True      # condition 4 compares to the baseline's own rate


class FixedGrid:
    """Same wrapper `longhistory.py` uses: this study builds its own Market, so
    it carries the market's min-risk floor into the grid by hand."""

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


def walk(df: pd.DataFrame, select_on: str, max_dd_r: float | None) -> pd.Series:
    """One arm's stitched walk-forward, as a daily R series."""
    strat = ExitVariant("wide", stops=WIDE_SIGMA)
    c = COSTS[SYM]
    fee, slip = c.per_side(EXEC_MODE)
    g = [dict(x) for x in strat.grid(TF)]
    for x in g:
        x["min_risk_bps"] = c.min_risk_bps
    pad = int(max(20, round(24 * 4 * TF_BPH[TF])) * 2)
    m = Market(sym=SYM, tf=TF, df=df, fee_bps=fee, slip_bps=slip, pad_bars=pad)
    kw = {"floors": (30,), "topn": (5,), "select_on": select_on}
    if max_dd_r is not None:
        kw["max_dd_r"] = max_dd_r
    p = Pipeline(FixedGrid(strat, g), **kw)
    real = p.walk_forward(m)
    tr = best_cell(real.folds, real.trades)
    daily = pd.Series(tr.r.values,
                      index=pd.DatetimeIndex(tr.exit_ts)).resample("1D").sum()
    return daily, tr, real


def ladder(daily: pd.Series, resamples: int = 200) -> list[dict]:
    """Every rung, with a band scored under the SAME budget-linear sizing."""
    r = np.asarray(daily.values, dtype=float)
    n = len(r)
    rows = []
    for risk in RISKS:
        a = run_scaled(daily, risk, "budget", ASH)
        if not a.get("days"):
            rows.append({"risk_pct": risk * 100, "days": None})
            continue
        rng = np.random.default_rng(0)
        idx = _resample_index(n, resamples, rng, MEAN_BLOCK)
        days = []
        for row in idx:
            b = run_scaled(pd.Series(r[row]), risk, "budget", ASH)
            if b.get("days"):
                days.append(b["days"])
        rows.append({
            "risk_pct": round(risk * 100, 2), "days": a["days"],
            "pass_pct": a["pass_pct"], "blown_pct": a["blown_pct"],
            "still_open_pct": a["still_open_pct"],
            "days_lo": round(float(np.percentile(days, LO_PCT)), 1) if days else None,
            "days_hi": round(float(np.percentile(days, HI_PCT)), 1) if days else None,
        })
    return rows


def show(name: str, rows: list[dict]) -> None:
    print(f"\n  {name}")
    print(f"    {'risk%':>6}{'days':>8}{'band':>13}{'pass%':>8}"
          f"{'blown%':>8}{'open%':>8}")
    for x in rows:
        if not x.get("days"):
            print(f"    {x['risk_pct']:6.1f}   no pass")
            continue
        span = (f"{x['days_lo']:.1f}-{x['days_hi']:.1f}"
                if x["days_lo"] is not None else "-")
        print(f"    {x['risk_pct']:6.1f}{x['days']:8.1f}{span:>13}"
              f"{x['pass_pct']:8.1f}{x['blown_pct']:8.1f}"
              f"{x['still_open_pct']:8.1f}")


def main() -> int:
    path = ROOT / "data" / f"{SYM}10Y_dukascopy_{TF}.parquet"
    if not path.exists():
        sys.exit(f"missing {path}")
    df = pd.read_parquet(path).sort_index()
    print(f"ARM 3b - eleven years. {len(df):,} bars "
          f"{df.index[0].date()} -> {df.index[-1].date()}")
    print("Both arms, full ladder, no rung picked in advance.\n")

    dst = ROOT / "backtests" / "beat"
    dst.mkdir(parents=True, exist_ok=True)
    partial = dst / "eleven_years.json"

    # RESULTS ARE WRITTEN AFTER EVERY ARM, NOT AT THE END. The first attempt at
    # this study wrote its JSON only after both arms and was killed by the OOM
    # reaper 30 minutes in - with the first arm's walk-forward complete and
    # entirely lost. An eleven-year fold is expensive enough that losing one to
    # a crash is worth a `write_text` per arm.
    out = {}
    if partial.exists():
        try:
            out = json.loads(partial.read_text())
            if out:
                print(f"  resuming: {list(out)} already on disk\n", flush=True)
        except json.JSONDecodeError:
            out = {}

    for label, sel, cap in (("baseline select_on=2x", "2x", None),
                            (f"capped dd<={MAX_DD_R:.0f}R", "rday_capped", MAX_DD_R)):
        if label in out and out[label].get("rows"):
            print(f"  {label}: already done, skipping", flush=True)
            show(label, out[label]["rows"])
            continue
        t0 = time.time()
        daily, tr, real = walk(df, sel, cap)
        met = metrics(tr)
        rows = ladder(daily)
        out[label] = {"rows": rows, "pf": met.get("pf"),
                      "pf_2x": met.get("pf_2x"), "win_pct": met.get("win_pct"),
                      "tpd": met.get("trades_per_day"), "trades": int(len(tr)),
                      "folds": int(real.folds.quarter.nunique()) if len(real.folds) else 0}
        partial.write_text(json.dumps(out, indent=1, default=str))
        print(f"  {label}: {len(tr)} trades, "
              f"{out[label]['folds']} quarters, PF {met.get('pf')}, "
              f"{met.get('trades_per_day')}/day  ({(time.time()-t0)/60:.1f} min) "
              f"[saved]", flush=True)
        show(label, rows)

    # ---- the same four conditions, applied out loud --------------------- #
    base = out["baseline select_on=2x"]["rows"]
    arm = out[f"capped dd<={MAX_DD_R:.0f}R"]["rows"]
    best_base = min([x for x in base if x.get("days")],
                    key=lambda x: x["days"], default=None)
    print("\n" + "=" * 74)
    if best_base:
        print(f"CONDITIONS vs the baseline's best rung: {best_base['days']:.1f} days, "
              f"band {best_base['days_lo']:.1f}-{best_base['days_hi']:.1f}, "
              f"blown {best_base['blown_pct']:.1f}%\n")
        winners = []
        for x in arm:
            if not x.get("days"):
                continue
            faster = x["days"] < best_base["days"]
            disjoint = (x["days_hi"] < best_base["days_lo"]
                        or best_base["days_hi"] < x["days_lo"])
            survivable = x["blown_pct"] <= best_base["blown_pct"]
            ok = faster and disjoint and survivable
            fails = [n for n, v in (("faster", faster), ("band disjoint", disjoint),
                                    ("blown<=base", survivable)) if not v]
            print(f"  risk {x['risk_pct']:4.1f}%  "
                  f"{'CLEARS' if ok else 'fail':7} "
                  + ("all three" if ok else "- " + ", ".join(fails)))
            if ok:
                winners.append(x)
        print()
        if winners:
            print("  A rung clears every condition on eleven years. That is a "
                  "candidate for gate 3 and a second engine - NOT a decision.")
        else:
            print("  NOTHING CLEARS on eleven years either. The ambiguity at "
                  "1.5% on three years was sample size, not an edge.")

    dst = ROOT / "backtests" / "beat"
    dst.mkdir(parents=True, exist_ok=True)
    (dst / "eleven_years.json").write_text(json.dumps(out, indent=1, default=str))
    print("\nwrote backtests/beat/eleven_years.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
