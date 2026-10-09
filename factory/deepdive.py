"""STEP 8 DEEP DIVE - the five improvements worth a second look.

Kris, 2026-10-09: the three that beat the luck check in `factory/improve.py`
plus the two closest to it (NDX cross SMA10 p=0.07, Daily change up p=0.10).

PRE-REGISTERED 2026-10-09, before the first run:
  1. MARKETS   the improved rule beats the original's mean R on >= 4 of the
               6 standard markets, same timeframe            (kills it if not)
  2. OLDER     on the home market's older years the improved rule beats the
               original                                       (a note only)
  3. YEARS     profit factor per calendar year of the window  (shown)
  4. COSTS     profit factor at 1x / 2x / 3x cost; 2x must be >= 1.2
  5. ENTRY     with its filter and exits FIXED, the real entry's mean R beats
               200 random entries (same count, same filter, same exits) at
               the 95th percentile - is the ENTRY doing work, or the filter?

    python -m factory.deepdive          # writes backtests/factory/deepdive.json
"""
from __future__ import annotations

import json
import sys
from dataclasses import replace
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core import universe                                             # noqa: E402
from factory import build, cells, improve, queue                      # noqa: E402
from factory.rescore import from_record                               # noqa: E402
from factory.tweak import _stats                                      # noqa: E402

PICKS = ("Pivot high breakout against Supertrend down (rule 1)",
         "Hemant gold liquidity sweep long",
         "nonstop DCA long proxy",
         "NDX close crosses above SMA10, above EMA200",
         "Daily change up long (rule 1)")
SEEDS = 200
OUT = queue.DIR / "deepdive.json"


def _r(tr):
    return np.array([t.r for t in tr], dtype=float)


def one(name: str) -> dict:
    res = {r["name"]: r for r in json.loads(improve.OUT.read_text())}[name]
    item = next(i for i in improve.load() if i[0]["name"] == name)
    _, base, home, tf0 = item
    f = res["final"]
    tf = f["tf"]
    new = from_record({"name": name, "idea": f["rule"], "stop_atr": f["stop_atr"],
                       "target_atr": f["target_atr"], "max_hold": f["max_hold"]})
    orig_tf = replace(base, max_hold=improve.Ctx(base, home, tf0).hold_for(tf))
    assert new.entry[:len(base.entry)] == base.entry, "improved rule must extend the original"
    out = {"name": name, "home": f"{home} {tf}", "rule": new.label(),
           "exits": f"stop{new.stop_atr:g} tgt{new.target_atr:g} hold{new.max_hold}"}

    # 1. markets
    rows = []
    for m in universe.STANDARD:
        fr = cells.load(m, tf).reset_index(drop=True)
        c = cells.cost_bps(m)
        a, b = _stats(_r(build.run(orig_tf, fr, cost_bps=c))), _stats(_r(build.run(new, fr, cost_bps=c)))
        rows.append({"market": m, "orig": a, "new": b,
                     "better": (b["mean"] if b["mean"] is not None else -9)
                     > (a["mean"] if a["mean"] is not None else -9)})
    wins = sum(x["better"] for x in rows)
    out["markets"], out["markets_better"], out["pass_markets"] = rows, wins, wins >= 4

    # 2. older years
    dated = cells.load(home, tf)
    old = cells.holdout(home, tf)
    old = old[old.index < dated.index[0]].reset_index(drop=True)
    c = cells.cost_bps(home)
    oa, ob = _stats(_r(build.run(orig_tf, old, cost_bps=c))), _stats(_r(build.run(new, old, cost_bps=c)))
    out["older"] = {"orig": oa, "new": ob, "years": round(len(old) / max(1, len(dated)) * 3, 1),
                    "better": (ob["mean"] or -9) > (oa["mean"] or -9)}

    # 3. years, 4. costs
    fr = dated.reset_index(drop=True)
    tr = build.run(new, fr, cost_bps=c)
    yrs = {}
    for t in tr:
        yrs.setdefault(dated.index[t.entry_bar].year, []).append(t.r)
    out["years"] = {y: _stats(np.array(v)) for y, v in sorted(yrs.items())}
    out["costs"] = {f"{k}x": _stats(_r(build.run(new, fr, cost_bps=c * k)))["pf"] for k in (1, 2, 3)}
    out["pass_costs"] = (out["costs"]["2x"] or 0) >= 1.2

    # 5. entry vs random, filter and exits fixed
    extra = new.entry[len(base.entry):]
    m = improve.mask(home, tf, tuple(extra))
    fire, atr = improve.signals(base, home, tf)
    real = _stats(_r(build.run(new, fr, cost_bps=c, signals=(fire & m, atr))))
    live = np.flatnonzero(fr["volume"].values > 0)
    rng = np.random.default_rng(0)
    null = []
    for _ in range(SEEDS):
        rf = np.zeros_like(fire)
        rf[rng.choice(live, size=int(fire.sum()), replace=False)] = True
        s = _stats(_r(build.run(new, fr, cost_bps=c, signals=(rf & m, atr))))
        null.append(s["mean"] if s["mean"] is not None else np.nan)
    null = np.array(null)
    out["entry"] = {"real_mean": real["mean"], "real_n": real["n"],
                    "random_median": float(np.nanmedian(null)),
                    "random_p95": float(np.nanpercentile(null, 95)),
                    "p": float(np.nanmean(null >= real["mean"]))}
    out["pass_entry"] = real["mean"] > out["entry"]["random_p95"]
    out["pace"] = res["final"]["pace"]
    out["pace_before"] = res["base"]["pace"]
    return out


def main() -> int:
    from concurrent.futures import ProcessPoolExecutor
    with ProcessPoolExecutor(max_workers=len(PICKS)) as pool:
        res = list(pool.map(one, PICKS))
    OUT.write_text(json.dumps(res, indent=1, default=str))
    for r in res:
        print(f"\n## {r['name']}  [{r['home']}]  {r['rule']}  {r['exits']}")
        print("  markets better:", r["markets_better"], "/6",
              {x["market"]: (round(x["orig"]["pf"] or 0, 2), round(x["new"]["pf"] or 0, 2), x["new"]["n"])
               for x in r["markets"]})
        o = r["older"]
        print(f"  older {o['years']}y: orig pf {o['orig']['pf']} n {o['orig']['n']} -> "
              f"new pf {o['new']['pf']} n {o['new']['n']} better={o['better']}")
        print("  years:", {y: (round(v["pf"] or 0, 2), v["n"]) for y, v in r["years"].items()})
        print("  costs:", r["costs"])
        print("  entry:", r["entry"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
