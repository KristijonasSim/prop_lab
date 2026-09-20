"""The top-N study, rebuilt so it exists as code, plus the two things it owed.

PRE-REGISTRATION: `TOPN_NULL.md`. Read it before reading any number below.

The 2026-09-15 run produced `backtests/vwapbreak/topn_wide.json`,
`topn_oos.json` and `topn_universe.json` and **committed no script**. Its
headline - 8.9 expected days on gold against the shipped 15.3 - is the fastest
number this project has, is the entry in `COMPETITION.md`, and could not be
re-run by anybody. This file is that study written down.

It adds the two items `COMPETITION.md` lists as owed:

  1. BTCUSDT, the sixth standard market, skipped last time with no reason given.
  2. A paired null on the top-N ladder - the test of whether trading twenty
     settings in parallel is faster because of the EDGE or merely because more
     trades per day resolve an account sooner. `days = median_days / pass_rate`,
     and the numerator falls with frequency whether or not the trades are any
     good. Nothing in the 2026-09-15 run separates those.

COST. One walk-forward per market covers EVERY (floor, topn) cell, because
floors and topn select from a grid the pipeline runs regardless. So the whole
ladder costs the same as one cell, and the nulls are the only real expense.

Run: .venv/bin/python strategies/vwapbreak/research/topn.py
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

from core.markets import COSTS, EXEC_MODE, load                     # noqa: E402
from core.noiseband import band as nb_band                          # noqa: E402
from core.pipeline import Market, Pipeline                          # noqa: E402
from core.prop_rules import HOUSE                                   # noqa: E402
from core.riskladder import run_accounts                            # noqa: E402
from core.run_hypothesis import TF_BPH, _FixedGrid, window          # noqa: E402
from core.universe import STANDARD                                  # noqa: E402
from strategies.vwapbreak.strategy import STRATEGY                  # noqa: E402

TF = "1h"
RISKS = (0.01, 0.015, 0.02, 0.03, 0.04, 0.05, 0.06)
FLOORS = (30, 100)
TOPN = (1, 5, 10, 15, 20)
#: The two cells the claim is about: what is traded, and what is proposed.
SHIPPED = (30, 5)
WIDE = (100, 20)
#: Gold carries the headline, so it gets the extra seed.
SEEDS = {"XAUUSD": 3}
DEFAULT_SEEDS = 2


def score(tr: pd.DataFrame) -> dict:
    """Expected days at the best rung of the ladder, with its band.

    Identical in shape to `bandshape.py`'s scorer so the two are comparable:
    the rung is chosen by its own expected days, and the band is computed at
    that rung, so forcing a different risk moves the band with the number.
    """
    if tr is None or not len(tr):
        return {"days": None, "trades": 0}
    daily = pd.Series(tr.r.values,
                      index=pd.DatetimeIndex(tr.exit_ts)).resample("1D").sum()
    best = None
    for risk in RISKS:
        a = run_accounts(daily, risk, HOUSE)
        if not a["pass_rate"]:
            continue
        exp = a["median_days"] / a["pass_rate"]
        if best is None or exp < best["days"]:
            best = {"risk_pct": risk * 100,
                    "pass_pct": round(a["pass_rate"] * 100, 1),
                    "blown_pct": round((a["fail_max"] + a["fail_daily"]) * 100, 1),
                    "days": round(exp, 1),
                    "band": nb_band(daily, risk, rules=HOUSE)}
    if best is None:
        return {"days": None, "trades": int(len(tr))}
    r = tr.r.values
    w, l = r[r > 0].sum(), -r[r < 0].sum()
    span_d = max(1.0, (pd.Timestamp(tr.exit_ts.max())
                       - pd.Timestamp(tr.exit_ts.min())).total_seconds() / 86400)
    return {**best, "trades": int(len(tr)),
            "tpd": round(len(tr) / span_d, 2),
            "pf": round(float(w / l), 3) if l > 0 else None,
            "win_pct": round(float((r > 0).mean() * 100), 1)}


def cells(trades: pd.DataFrame) -> dict:
    """Every (floor, topn) cell of one walk-forward, scored."""
    out = {}
    if trades is None or not len(trades):
        return out
    for (fl, tn), g in trades.groupby(["floor", "topn"]):
        out[f"{int(fl)}/{int(tn)}"] = score(g)
    return out


def run_one(sym: str, span, seeds: int) -> dict:
    """Real walk-forward plus `seeds` paired nulls, all cells, one market."""
    df = load(sym, TF)
    lo, hi = span
    df = df[(df.index >= lo) & (df.index <= hi)]
    c = COSTS[sym]
    fee, slip = c.per_side(EXEC_MODE)
    pad = int(max(20, round(24 * 4 * TF_BPH[TF])) * 2)
    m = Market(sym=sym, tf=TF, df=df, fee_bps=fee, slip_bps=slip, pad_bars=pad)

    g = [dict(x) for x in STRATEGY.grid(TF)]
    for x in g:
        x["min_risk_bps"] = c.min_risk_bps
    p = Pipeline(_FixedGrid(STRATEGY, g), floors=FLOORS, topn=TOPN)

    real = cells(p.walk_forward(m).trades)
    nulls = []
    for s in range(seeds):
        nulls.append(cells(p.walk_forward(m, shuffled="paired",
                                          tag=f"topn{s}").trades))
    return {"sym": sym, "cost_rt_bps": round(c.round_trip(EXEC_MODE), 2),
            "data_from": str(df.index[0].date()), "data_to": str(df.index[-1].date()),
            "real": real, "nulls": nulls}


def speedup(cs: dict) -> float | None:
    """days(shipped) / days(wide). Above 1 means the wide ladder is faster."""
    a = cs.get(f"{SHIPPED[0]}/{SHIPPED[1]}", {}).get("days")
    b = cs.get(f"{WIDE[0]}/{WIDE[1]}", {}).get("days")
    return round(a / b, 2) if a and b else None


def _row(tag: str, s: dict) -> str:
    b = s.get("band") or {}
    bs = ("%.0f-%.0f" % (b.get("days_lo", 0), b.get("days_hi", 0))) if b else "-"
    return (f"{tag:16}{s.get('trades') or 0:>7}{s.get('tpd') or 0:>7.2f}"
            f"{s.get('pf') or 0:>7.3f}{(s.get('risk_pct') or 0):>6.1f}%"
            f"{s.get('days') or 0:>8.1f}{bs:>10}"
            f"{s.get('pass_pct') or 0:>8.1f}{s.get('blown_pct') or 0:>8.1f}")


HDR = (f"{'cell':16}{'trades':>7}{'tpd':>7}{'PF2x':>7}{'risk':>7}"
       f"{'days':>8}{'band':>10}{'pass%':>8}{'blown%':>8}")


def main() -> int:
    span = window(STANDARD, [TF])
    print(f"window {span[0].date()} -> {span[1].date()}   spec HOUSE "
          f"8/3/6   tf {TF}", flush=True)
    out = {}
    for sym in STANDARD:
        seeds = SEEDS.get(sym, DEFAULT_SEEDS)
        t0 = time.time()
        print(f"\n=== {sym} {TF}  ({seeds} null seeds) " + "=" * 30, flush=True)
        try:
            res = run_one(sym, span, seeds)
        except Exception as e:
            print(f"  FAILED: {type(e).__name__}: {e}", flush=True)
            out[sym] = {"error": f"{type(e).__name__}: {e}"}
            continue
        print(HDR); print("-" * len(HDR), flush=True)
        for fl in FLOORS:
            for tn in TOPN:
                k = f"{fl}/{tn}"
                if k in res["real"]:
                    print(_row(k, res["real"][k]), flush=True)
        sr = speedup(res["real"])
        ns = [speedup(n) for n in res["nulls"]]
        ns = [x for x in ns if x]
        res["speedup_real"] = sr
        res["speedup_nulls"] = ns
        res["speedup_null_median"] = round(float(np.median(ns)), 2) if ns else None
        print(f"  speed-up  real {sr}   null {ns} "
              f"median {res['speedup_null_median']}   ({time.time()-t0:.0f}s)",
              flush=True)
        out[sym] = res

    # THE PRE-REGISTERED VERDICT, applied by the code and not by the reader.
    print("\n" + "=" * 72)
    print(f"{'market':10}{'shipped d':>11}{'wide d':>9}{'real':>7}"
          f"{'null med':>10}  verdict", flush=True)
    for sym, r in out.items():
        if "error" in r:
            print(f"{sym:10}  {r['error']}"); continue
        sh = r["real"].get(f"{SHIPPED[0]}/{SHIPPED[1]}", {}).get("days")
        wd = r["real"].get(f"{WIDE[0]}/{WIDE[1]}", {}).get("days")
        nm, sr = r.get("speedup_null_median"), r.get("speedup_real")
        if nm is None or sr is None:
            v = "no result"
        elif nm >= 1.4:
            v = "FAIL - the null speeds up too"
        elif nm < 1.25:
            v = "PASS - gain survives the null"
        else:
            v = "UNRESOLVED"
        print(f"{sym:10}{sh or 0:>11.1f}{wd or 0:>9.1f}{sr or 0:>7.2f}"
              f"{nm or 0:>10.2f}  {v}", flush=True)

    dest = ROOT / "backtests" / "vwapbreak" / "topn_rebuilt.json"
    dest.write_text(json.dumps({"tf": TF, "floors": FLOORS, "topn": TOPN,
                                "spec": "HOUSE 8/3/6", "risks": RISKS,
                                "span": [str(span[0]), str(span[1])],
                                "markets": out}, indent=1, default=str))
    print(f"\nwrote {dest.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
