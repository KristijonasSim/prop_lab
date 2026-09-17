"""H-049 — three macro feeds, long holds, on the standard universe.

WHY THESE AND WHY NOW. Today closed four scalping ideas and every one died the
same way: the effect was one to three bps and the spread was five. The shipped
bot survives to a **21 bps** round trip because it holds for up to sixteen days -
a long hold is what buys immunity to the spread. So the search moves to long
holds on feeds, which is also the only family that has ever worked in this repo.

THE THREE, each with its mechanism stated before any number:

  DFII10    US 10-year REAL yield. Gold pays no coupon, so the cost of holding
            it is the real yield available elsewhere. When real yields fall that
            cost falls. The most-cited driver of gold in the literature and this
            repo has never loaded it.
  DTWEXBGS  Broad trade-weighted dollar. Gold is quoted in dollars, so a weaker
            dollar mechanically lifts the quote before any demand story.
  T10YIE    10-year inflation breakeven. Gold as the inflation hedge - the
            oldest claim about it, and the one most likely to be already priced.

CHANGES, NOT LEVELS. A level is non-stationary and the repo has killed
level-based readings before (H-034's basis level, best pctile 78.2). The signal
is the change over a trailing window.

THE LAG IS THE TRAP AND IT IS HANDLED. FRED publishes a day's value after that
day's close, so a value dated T is not actionable until T+1. Everything here is
shifted one extra day and entry is at the NEXT day's open. Getting this wrong
manufactures an edge out of nothing.

ALL SIX STANDARD MARKETS, per the standing rule - a number from one market is a
hypothesis, not a result. The mechanism argues gold and silver up, dollar pairs
mixed; BTC is in because the rule says so.

Run: .venv/bin/python strategies/macro/screen.py
"""
from __future__ import annotations

import sys
import urllib.request
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from core.markets import COSTS, EXEC_MODE, load                    # noqa: E402
from core.universe import STANDARD                                 # noqa: E402

FRED = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}&cosd={start}"
SERIES = {"DFII10": "US 10y real yield",
          "DTWEXBGS": "broad dollar index",
          "T10YIE": "10y inflation breakeven"}
CACHE = ROOT / "data" / "macro"
LOOKBACKS = (5, 20)          # trading days over which the change is measured
HOLDS = (1, 3, 5, 10, 20)    # trading days held
DECILES = 5                  # quintiles: 3 years of daily data is ~750 rows
START = "2023-08-01"


def fetch(sid: str) -> pd.Series:
    CACHE.mkdir(parents=True, exist_ok=True)
    f = CACHE / f"{sid}.csv"
    if not f.exists():
        raw = urllib.request.urlopen(FRED.format(sid=sid, start="2015-01-01"),
                                     timeout=40).read()
        f.write_bytes(raw)
    d = pd.read_csv(f)
    d.columns = ["date", "val"]
    d["date"] = pd.to_datetime(d.date, utc=True)
    d["val"] = pd.to_numeric(d.val, errors="coerce")
    return d.dropna().set_index("date").val.sort_index()


def daily_close(sym: str) -> pd.Series:
    df = load(sym, "1h")
    c = df.close.resample("1D").last().dropna()
    o = df.open.resample("1D").first().dropna()
    return c, o


def screen(s: pd.Series, sym: str, lb: int, hold: int) -> dict | None:
    c, o = daily_close(sym)
    # THE LAG. A value dated T is published after T's close, so shift it one
    # day before it may be used, then enter at the NEXT day's open.
    chg = (s - s.shift(lb)).shift(1)
    idx = o.index.intersection(chg.index)
    if len(idx) < 300:
        return None
    x = chg.reindex(idx).dropna()
    entry = o.reindex(x.index)
    exit_ = o.shift(-hold).reindex(x.index)
    ret = (exit_ / entry - 1.0) * 1e4
    d = pd.DataFrame({"chg": x, "ret": ret}).replace(
        [np.inf, -np.inf], np.nan).dropna()
    d = d[d.index >= START]
    if len(d) < 200 or d.chg.nunique() < DECILES:
        return None
    try:
        d["b"] = pd.qcut(d.chg, DECILES, labels=False, duplicates="drop")
    except ValueError:
        return None
    m = d.groupby("b").ret.agg(["mean", "median", "count"])
    if len(m) < 3:
        return None
    lo, hi = m.iloc[0], m.iloc[-1]
    rho = float(pd.Series(m["mean"].values).corr(
        pd.Series(range(len(m))), method="spearman"))
    return {"n": int(len(d)), "spread_mean": float(hi["mean"] - lo["mean"]),
            "spread_med": float(hi["median"] - lo["median"]), "rho": rho,
            "buckets": [round(v, 1) for v in m["mean"].values]}


def main() -> int:
    print("H-049 — three macro feeds, long holds, all six standard markets.")
    print("Signal is a CHANGE, lagged one day past publication. Entry next open.")
    print("Bar: the quintile spread must clear 2x the market's round trip.\n")
    data = {k: fetch(k) for k in SERIES}
    for sid, name in SERIES.items():
        s = data[sid]
        print(f"\n{'='*78}\n{sid} — {name}   ({len(s)} daily values)\n{'='*78}")
        hdr = (f"{'market':9}{'lb':>4}{'hold':>6}{'n':>6}{'meanSprd':>10}"
               f"{'medSprd':>9}{'rho':>7}{'bar':>7}  verdict")
        print(hdr); print("-" * len(hdr))
        for sym in STANDARD:
            bar = COSTS[sym].round_trip(EXEC_MODE) * 2
            for lb in LOOKBACKS:
                for hold in HOLDS:
                    r = screen(s, sym, lb, hold)
                    if not r:
                        continue
                    ok = abs(r["spread_mean"]) > bar and abs(r["spread_med"]) > bar
                    mono = abs(r["rho"]) >= 0.8
                    v = "PASS" if (ok and mono) else (
                        "mean-only" if ok else "fail")
                    if v == "fail" and hold != HOLDS[-1]:
                        continue                     # keep the table readable
                    print(f"{sym:9}{lb:>4}{hold:>6}{r['n']:>6}"
                          f"{r['spread_mean']:>10.1f}{r['spread_med']:>9.1f}"
                          f"{r['rho']:>7.2f}{bar:>7.2f}  {v}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
