"""THE BEST POOL OF 2-3 - from every rule that ever beat its luck check.

Kris, 2026-10-09: *"make pool of 2-3 best strategies we ever found"*.

PRE-REGISTERED 2026-10-09, before the first run:
  CANDIDATES  all 19 REAL rules under the 24h cap: `deepdive24.json` (5),
              `hunt_05_deep.json` (9), `hunt_deep.json` (5).
  POOLS       every combination of 2 and of 3 (171 + 969 = 1,140).
  PICK        on the OLDER half of the window only: among pools with >= 0.5
              trades/day and <= 14 expected days, the fewest accounts per
              pass; if none is that fast, the fewest days.
  JUDGE       the pick's NEWER-half pass %, days and accounts, beside the
              pool of 5 and EMA8+DEMA on the same newer half.
  LUCK CHECK  the identical pick on random-entry versions of all 19 rules
              (same counts, filters and exits), 20 seeds. The pick is REAL
              only if its newer-half accounts are below the random picks'
              10th percentile.
  NOTE        older years (before the window) for the pick - Kris's rule:
              a note, not a verdict.
  1,140 pools picked on 1.5 years is a lot of choice; the luck check is
  what prices it.

    python -m factory.bestpool
"""
from __future__ import annotations

import itertools
import json
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from factory import book5, cells, check, improve, queue               # noqa: E402

OUT = queue.DIR / "bestpool.json"
SEEDS = 20
SOURCES = (("deepdive24.json", "step8_list.json", "improve24.json", 0.1),
           ("hunt_05_deep.json", "hunt_05_list.json", "hunt_05.json", 0.5),
           ("hunt_deep.json", "hunt_list.json", "hunt.json", 1.0))
MID = None
TR: list[pd.DataFrame] = []


def legs() -> list[dict]:
    improve.MAX_HOURS = 24
    out = []
    for deep, lst, res, tpd in SOURCES:
        improve.LIST, improve.OUT, improve.MIN_TPD = queue.DIR / lst, queue.DIR / res, tpd
        book5.DEEP = queue.DIR / deep
        out += book5.legs()
    return out


def _half(df: pd.DataFrame, newer: bool) -> pd.DataFrame:
    return df[df.e >= MID] if newer else df[df.e < MID]


def score(combo, trs=None, newer=False) -> dict:
    trs = TR if trs is None else trs
    df = pd.concat([_half(trs[i], newer) for i in combo])
    return book5.pace(df[["t", "r"]], band=False)


def _score_old(combo):
    return combo, score(combo)


def pick(results: list[tuple]) -> tuple:
    ok = [(c, p) for c, p in results if p.get("days") and p.get("tpd", 0) >= 0.5]
    fast = [(c, p) for c, p in ok if p["days"] <= 14]
    if fast:
        return min(fast, key=lambda x: (x[1]["accounts"], x[1]["days"]))
    return min(ok, key=lambda x: x[1]["days"])


def _null(seed):
    global TR
    real = TR
    TR = [book5._trades_full(l, seed * 1000 + i) for i, l in enumerate(LEGS)]
    res = [(c, score(c)) for c in COMBOS]
    c, _ = pick(res)
    out = score(c, newer=True)
    TR = real
    return [list(c), out]


def main() -> int:
    global TR, MID, LEGS, COMBOS
    LEGS = legs()
    TR = [book5._trades_full(l) for l in LEGS]
    lo = min(d.e.min() for d in TR)
    hi = max(d.e.max() for d in TR)
    MID = lo + (hi - lo) / 2
    COMBOS = [c for k in (2, 3) for c in itertools.combinations(range(len(LEGS)), k)]
    print(f"{len(LEGS)} legs, {len(COMBOS)} pools, split {MID.date()}", flush=True)
    with ProcessPoolExecutor(max_workers=check.workers()) as pool:
        res = list(pool.map(_score_old, COMBOS, chunksize=8))
        c, p_old = pick(res)
        names = [LEGS[i]["name"] for i in c]
        p_new = score(c, newer=True)
        print("PICK", names, "\n  older half", p_old, "\n  newer half", p_new, flush=True)
        nul = list(pool.map(_null, range(SEEDS)))
    acc = np.array([x[1].get("accounts", np.nan) for x in nul], dtype=float)
    p10 = float(np.nanpercentile(acc, 10))
    real = bool(p_new.get("accounts", 99) < p10)
    name = {l["name"]: i for i, l in enumerate(LEGS)}
    refs = {}
    for key, ns in (("pool of 5", [l["name"] for l in LEGS[:5]]),
                    ("EMA8 + DEMA", [n for n in name if n.startswith(("5m EMA8", "DEMA ATR"))])):
        refs[key] = score([name[n] for n in ns], newer=True)
    full = book5.pace(pd.concat([TR[i] for i in c])[["t", "r"]])
    olds = []
    for i in c:
        l = LEGS[i]
        d = cells.load(l["market"], l["tf"])
        o = cells.holdout(l["market"], l["tf"])
        olds.append(book5._trades_full(l, frame=o[o.index < d.index[0]]))
    older = book5.pace(pd.concat(olds)[["t", "r"]])
    top = sorted([(c2, p) for c2, p in res if p.get("days") and p.get("tpd", 0) >= 0.5
                  and p["days"] <= 14], key=lambda x: x[1]["accounts"])[:10]
    out = {"pick": names, "older_half": p_old, "newer_half": p_new, "full": full,
           "older_years": older, "refs_newer_half": refs,
           "null_accounts_p10": p10, "null_accounts_med": float(np.nanmedian(acc)),
           "null_picks": [[LEGS[i]["name"] for i in x[0]] for x in nul], "real": real,
           "top10_older_half": [[[LEGS[i]["name"] for i in c2], p] for c2, p in top]}
    OUT.write_text(json.dumps(out, indent=1, default=str))
    print("refs newer half", refs)
    print("null accounts p10", p10, "median", out["null_accounts_med"], "REAL", real)
    print("full window", full)
    print("older years", older)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
