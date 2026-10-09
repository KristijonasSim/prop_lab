"""Pool of two: EMA8 pullback + DEMA ATR turn-up (hunt at 0.5 tpd). Kris, 2026-10-09.

Same tests as `book5.py`, nothing chosen after the fact: the book against the
same book on random entries (40 seeds), 1/2-open-trade caps, older years.

    python -m factory.pool_ema8_dema
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np                                                    # noqa: E402
import pandas as pd                                                   # noqa: E402

from factory import book5, cells, improve, queue                      # noqa: E402

improve.MAX_HOURS = 24
improve.MIN_TPD = 0.5
improve.LIST = queue.DIR / "hunt_05_list.json"
improve.OUT = queue.DIR / "hunt_05.json"
book5.DEEP = queue.DIR / "hunt_05_deep.json"
NAMES = ("5m EMA8 pullback", "DEMA ATR line turns up")
OUT = queue.DIR / "pool_ema8_dema.json"

if __name__ == "__main__":
    ls = [l for l in book5.legs() if l["name"].startswith(NAMES)]
    assert len(ls) == 2, [l["name"] for l in ls]
    tr = [book5._trades_full(l) for l in ls]
    df = pd.concat(tr)
    out = {}
    for k in (0, 1, 2):
        p = book5.pace((book5.cap(df, k) if k else df)[["t", "r"]])
        nul = [book5.pace((book5.cap(x, k) if k else x)[["t", "r"]], band=False)
               for x in (pd.concat([book5._trades_full(l, s * 100 + i) for i, l in enumerate(ls)])
                         for s in range(book5.SEEDS))]
        p["null_days_med"] = float(np.nanmedian([x.get("days", np.nan) for x in nul]))
        p["null_accounts_med"] = float(np.nanmedian([x.get("accounts", np.nan) for x in nul]))
        out[f"cap {k or 'none'}"] = p
        print(f"cap {k or 'none'}", p, flush=True)
    a, b = tr
    ov = np.mean([((b.e < r.t) & (b.t > r.e)).any() for r in a.itertuples()])
    out["overlap"] = float(ov)
    print(f"EMA8 trades that overlap a DEMA trade: {ov*100:.0f}%")
    olds = []
    for l in ls:
        d = cells.load(l["market"], l["tf"])
        o = cells.holdout(l["market"], l["tf"])
        olds.append(book5._trades_full(l, frame=o[o.index < d.index[0]]))
    for k in (0, 1):
        out[f"older cap {k or 'none'}"] = book5.pace((book5.cap(pd.concat(olds), k) if k else pd.concat(olds))[["t", "r"]])
        print(f"older cap {k or 'none'}", out[f"older cap {k or 'none'}"])
    OUT.write_text(json.dumps(out, indent=1, default=str))
