"""STEP 8 - THE FIVE AS ONE BOOK. Does trading them together pass faster?

Kris, 2026-10-09 (/goal). Each survivor trades only 0.1-0.2 times a day, so
the evaluation waits on trades. A book of all five trades ~0.8 a day.

PRE-REGISTERED 2026-10-09, before the first run:
  BOOKS   A = the five round-1 rules, each on its home cell.
          B = A plus the EURUSD pivot rule on USDJPY 1h and GBPUSD 1h, the two
              other markets where `deepdive` saw it hold (PF 1.47 / 1.20).
              B is SELECTED on the same data, so it is a note, not a result.
  SIZING  every trade at the same risk; the ladder picks the rung, as always.
  NULL    the same book with every leg's entries moved to random live bars
          (same count, the leg's own filter and exits kept), 40 seeds. That is
          what the gold drift and the filters give with no entry at all.
  A BOOK IS BETTER only if its expected days at the picked rung are below
  the best single leg's AND below the null's 10th percentile, and it uses no
  more accounts per pass than VWAP's 1.83.

    python -m factory.book5
"""
from __future__ import annotations

import json
import sys
from concurrent.futures import ProcessPoolExecutor
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core import noiseband, riskladder                                # noqa: E402
from factory import build, cells, check, improve, queue               # noqa: E402
from factory.rescore import from_record                               # noqa: E402

OUT = queue.DIR / "book5.json"
DEEP = queue.DIR / "deepdive.json"
OUT2 = queue.DIR / "book5_round2.json"
SEEDS = 40
EXTRA = (("Pivot high breakout against Supertrend down (rule 1)", "USDJPY"),
         ("Pivot high breakout against Supertrend down (rule 1)", "GBPUSD"))


def legs(extra=()) -> list[dict]:
    base = {i[0]["name"]: i for i in improve.load()}
    out = []
    for r in json.loads(DEEP.read_text()):
        m, tf = r["home"].split()
        ex = r["exits"].split()
        new = from_record({"name": r["name"], "idea": r["rule"], "stop_atr": float(ex[0][4:]),
                           "target_atr": float(ex[1][3:]), "max_hold": int(ex[2][4:])})
        _, b, _, _ = base[r["name"]]
        out.append({"name": r["name"], "market": m, "tf": tf, "rule": new,
                    "base": b, "extra": tuple(new.entry[len(b.entry):])})
    for name, m in extra:
        x = next(l for l in out if l["name"] == name)
        out.append({**x, "name": f"{name} [{m}]", "market": m})
    return out


def _trades(leg, seed=None) -> pd.DataFrame:
    m, tf = leg["market"], leg["tf"]
    dated = cells.load(m, tf)
    fr = dated.reset_index(drop=True)
    fire, atr = improve.signals(leg["base"], m, tf)
    mask = improve.mask(m, tf, leg["extra"])
    if seed is not None:
        rng = np.random.default_rng(seed)
        live = np.flatnonzero(fr["volume"].values > 0)
        r = np.zeros_like(fire)
        r[rng.choice(live, size=int(fire.sum()), replace=False)] = True
        fire = r
    tr = build.run(leg["rule"], fr, cost_bps=cells.cost_bps(m), signals=(fire & mask, atr))
    return pd.DataFrame({"t": dated.index[[t.exit_bar for t in tr]], "r": [t.r for t in tr]})


def pace(df: pd.DataFrame, band: bool = True) -> dict:
    if len(df) < 10:
        return {}
    df = df.sort_values("t")
    daily = pd.Series(df["r"].values, index=pd.DatetimeIndex(df["t"])).resample("1D").sum()
    rows = riskladder.ladder(daily, df["r"].values)
    best = riskladder.pick(rows) if rows else None
    if not best or not best.get("expected_days"):
        return {"n": len(df)}
    out = {"n": len(df), "risk_pct": round(best["risk"] * 100, 2),
           "pass_pct": round(best["pass_rate"] * 100, 1),
           "days": round(best["expected_days"], 1),
           "accounts": round(1 / best["pass_rate"], 2),
           "pf": round(df.r[df.r > 0].sum() / -df.r[df.r <= 0].sum(), 2),
           "tpd": round(len(df) / (daily.index[-1] - daily.index[0]).days * 7 / 5, 2)}
    if band:
        b = noiseband.band(daily, best["risk"]) or {}
        out["band"] = [b.get("days_lo"), b.get("days_hi")]
    return out


def _null(args):
    ls, seed = args
    return pace(pd.concat([_trades(l, seed * 100 + i) for i, l in enumerate(ls)]), band=False)


def main() -> int:
    A, B = legs(), legs(EXTRA)
    res = {"legs": {}, "books": {}}
    single = {}
    for l in B:
        single[l["name"]] = _trades(l)
        res["legs"][l["name"]] = pace(single[l["name"]])
    with ProcessPoolExecutor(max_workers=check.workers()) as pool:
        for key, ls in (("A five", A), ("B seven (note)", B))[:2 if EXTRA else 1]:
            real = pace(pd.concat([single[l["name"]] for l in ls]))
            nul = list(pool.map(_null, [(ls, s) for s in range(SEEDS)]))
            d = np.array([x.get("days", np.nan) for x in nul], dtype=float)
            real["null_days_p10"] = float(np.nanpercentile(d, 10))
            real["null_days_med"] = float(np.nanmedian(d))
            real["null_pass_med"] = float(np.nanmedian([x.get("pass_pct", np.nan) for x in nul]))
            res["books"][key] = real
        # leave-one-out on A, information only
        for l in A:
            rest = [x for x in A if x is not l]
            res["books"][f"A without {l['name'][:30]}"] = pace(
                pd.concat([single[x["name"]] for x in rest]))
    OUT.write_text(json.dumps(res, indent=1, default=str))
    for k, v in {**res["legs"], **res["books"]}.items():
        print(f"{k[:52]:52} {v}")
    return 0




# --------------------------------------------------------------------------
# ROUND 2 of the book, pre-registered 2026-10-09 after the first book run and
# before this was run:
#   OLDER   book A on the older years (`cells.holdout` before the window) -
#           the only data no step of step 8 has touched. A note, by Kris's rule.
#   CAP     at most K trades open at once (K = 1, 2, 3), taken in entry order.
#           Four of five legs are gold longs that fire together, so the book
#           can hold 8% of risk at once against a 3% daily cap. A cap is KEPT
#           only if it cuts accounts per pass below the uncapped book's AND
#           keeps expected days inside the uncapped band - and the same cap on
#           the random-entry book must not do as well (40 seeds, median).
# --------------------------------------------------------------------------
def _trades_full(leg, seed=None, frame=None) -> pd.DataFrame:
    m, tf = leg["market"], leg["tf"]
    dated = cells.load(m, tf) if frame is None else frame
    fr = dated.reset_index(drop=True)
    if frame is None:
        fire, atr = improve.signals(leg["base"], m, tf)
        mask = improve.mask(m, tf, leg["extra"])
    else:
        fire, atr = build.series(leg["base"], fr)
        mask = (build.series(replace(leg["base"], entry=leg["extra"]), fr)[0]
                if leg["extra"] else np.ones(len(fr), bool))
    if seed is not None:
        rng = np.random.default_rng(seed)
        live = np.flatnonzero(fr["volume"].values > 0)
        r = np.zeros_like(fire)
        r[rng.choice(live, size=int(fire.sum()), replace=False)] = True
        fire = r
    tr = build.run(leg["rule"], fr, cost_bps=cells.cost_bps(m), signals=(fire & mask, atr))
    return pd.DataFrame({"e": dated.index[[t.entry_bar for t in tr]],
                         "t": dated.index[[t.exit_bar for t in tr]], "r": [t.r for t in tr]})


def cap(df: pd.DataFrame, k: int) -> pd.DataFrame:
    df = df.sort_values("e").reset_index(drop=True)
    open_, keep = [], []
    for i, row in df.iterrows():
        open_ = [t for t in open_ if t > row.e]
        if len(open_) < k:
            open_.append(row.t)
            keep.append(i)
    return df.loc[keep]


def _null_cap(args):
    ls, seed = args
    df = pd.concat([_trades_full(l, seed * 100 + i) for i, l in enumerate(ls)])
    return {k: pace(cap(df, k) if k else df, band=False) for k in (0, 1, 2, 3)}


def round2() -> int:
    A = legs()
    real = pd.concat([_trades_full(l) for l in A])
    out = {"caps": {}, "older": {}}
    with ProcessPoolExecutor(max_workers=check.workers()) as pool:
        nul = list(pool.map(_null_cap, [(A, s) for s in range(SEEDS)]))
    for k in (0, 1, 2, 3):
        p = pace(cap(real, k) if k else real)
        p["null_days_med"] = float(np.nanmedian([x[k].get("days", np.nan) for x in nul]))
        p["null_accounts_med"] = float(np.nanmedian([x[k].get("accounts", np.nan) for x in nul]))
        out["caps"][f"cap {k or 'none'}"] = p
        print(f"cap {k or 'none':4} {p}", flush=True)
    olds = []
    for l in A:
        dated = cells.load(l["market"], l["tf"])
        old = cells.holdout(l["market"], l["tf"])
        old = old[old.index < dated.index[0]]
        olds.append(_trades_full(l, frame=old))
    od = pd.concat(olds)
    for k in (0, 2):
        out["older"][f"cap {k or 'none'}"] = pace(cap(od, k) if k else od)
        print(f"older years, cap {k or 'none'}: {out['older'][f'cap {k or chr(110)+chr(111)+chr(110)+chr(101)}']}", flush=True)
    for l, o in zip(A, olds):
        out["older"][l["name"]] = pace(o, band=False)
        print(f"  older {l['name'][:40]:40} {out['older'][l['name']]}")
    OUT2.write_text(json.dumps(out, indent=1, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(round2() if sys.argv[1:] == ["round2"] else main())
