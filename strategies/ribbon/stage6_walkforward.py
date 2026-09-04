"""H-016 stage 6 - walk-forward, the only number here with no hindsight in it.

Stage 5 found the ribbon beating its paired null 2,362 to 781 per seed, and
beating a direction control on 7 of 8 panels. Neither of those is an
out-of-sample result: both describe a search over the whole history.

Quarterly folds, 12 months train / 3 months test. The configuration is chosen
BLIND inside each training window on 2x-cost profit factor - the rule
HANDOFF.md fixes, because selecting on 1x and checking 2x afterwards let four
fragile legs into H-002's book. The test quarter is then scored on that choice
and never consulted again. Stitching the test quarters gives one out-of-sample
series per market and timeframe.

Two selection rules, so the answer does not depend on one arbitrary choice:
  single  the best configuration in the fold
  top10   an equal-weight book of the fold's best ten

A trade floor per fold stops a 3-trade profit factor from winning a selection.

Output: backtests/ribbon/stage6_folds.csv, stage6_stitched.csv
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from strategies.ribbon.sweep import (COSTS, OUT, TFS, build_grid,   # noqa: E402
                                     load_tf, metrics, ribbon_inputs, run_one)

TRAIN_MONTHS, TEST_MONTHS = 12, 3
FLOOR = 30                      # minimum trades in the training window
TOPN = 10

#: Everything that beat its null in stage 5, plus two that did not, kept as
#: controls so the walk-forward is not run only on the winners.
PANELS = [("XAUUSD", tf) for tf in ("15m", "30m", "1h", "4h")] + \
         [("XAGUSD", tf) for tf in ("30m", "1h", "4h")] + \
         [("BTCUSDT", tf) for tf in ("30m", "1h", "4h")] + \
         [("ETHUSDT", tf) for tf in ("1h", "4h")] + \
         [("SOLUSDT", tf) for tf in ("1h", "4h")] + \
         [("EURUSD", "1h"), ("AUDUSD", "1h")]

#: Enough warm-up for the slowest thing in the ribbon: a 100-bar MA, then a
#: 20-bar trend window, on top of the 280-bar channel. 600 bars is comfortable.
PAD = 600


def pf(r):
    w, l = r[r > 0].sum(), -r[r < 0].sum()
    return float(w / l) if l > 0 else np.nan


def cost_adjusted(tr, fee, slip):
    """R after DOUBLE cost, per trade, without moving any stop."""
    if tr.shape[0] == 0:
        return np.array([])
    from strategies.ribbon import engine as E
    r = tr[:, E.T_R]
    px = tr[:, E.T_ENTRY_PX] + tr[:, E.T_EXIT_PX]
    gross = (tr[:, E.T_EXIT_PX] - tr[:, E.T_ENTRY_PX]) * np.where(
        tr[:, E.T_DIR] > 0, 1.0, -1.0)
    with np.errstate(divide="ignore", invalid="ignore"):
        risk = np.abs((gross - px * (fee + slip) / 1e4)
                      / np.where(r == 0, np.nan, r))
        extra = np.where(np.isfinite(risk) & (risk > 0),
                         px * (fee + slip) / 1e4 / risk, 0.0)
    return r - extra


def run_window(inp_full, df, lo, hi, cfgs, fee, slip, mr):
    """Every config over one date window, returning R after 2x cost.

    The ribbon is computed ONCE on the full series and sliced, with `PAD` bars
    of history in front of every window: recomputing it inside a window would
    give the fold a different indicator from the one live trading would see,
    and a shorter warm-up on every fold boundary.
    """
    i0 = df.index.searchsorted(lo)
    i1 = df.index.searchsorted(hi)
    s0 = max(0, i0 - PAD)
    if i1 - i0 < 50:
        return {}
    sl = {k: v[s0:i1] for k, v in inp_full.items()}
    offset = i0 - s0
    out = {}
    from strategies.ribbon import engine as E
    for c in cfgs:
        tr = run_one(sl, c, fee, slip, mr)
        if tr.shape[0]:
            # keep only trades that ENTER inside the window, not in the pad
            tr = tr[tr[:, E.T_ENTRY_I] >= offset]
        out[c["cfg"]] = (cost_adjusted(tr, fee, slip), tr)
    return out


def main(shuffle_seed: int | None = None) -> int:
    """`shuffle_seed` re-runs the identical walk-forward on a phase-randomised
    copy of every market. H-003 died here and not before: its real data cleared
    the gate in 10 cells and its NULL cleared it in 17. A walk-forward number
    means nothing until the same procedure has been run on noise."""
    OUT.mkdir(parents=True, exist_ok=True)
    fold_rows, stitched_rows, t0 = [], [], time.time()

    for sym, tf in PANELS:
        df = load_tf(sym, tf)
        if len(df) < 5000:
            print(f"  skip {sym} {tf}")
            continue
        if shuffle_seed is not None:
            from strategies.ribbon.sweep import shuffled
            df = shuffled(df, sym, tf, "s6wf", shuffle_seed)
        inp = ribbon_inputs(df)
        fee, slip, mr = COSTS[sym]
        cfgs = build_grid(TFS[tf][1])
        for c in cfgs:
            c["min_risk_bps"] = mr

        start = df.index[0] + pd.DateOffset(months=TRAIN_MONTHS)
        start = (start + pd.offsets.QuarterBegin(startingMonth=1)).normalize()
        ends = pd.date_range(start, df.index[-1], freq="QS", tz="UTC")

        oos = {"single": [], "top10": []}
        nfolds = 0
        first_test = last_test = None
        for q in ends:
            tr_lo = q - pd.DateOffset(months=TRAIN_MONTHS)
            te_hi = q + pd.DateOffset(months=TEST_MONTHS)
            if te_hi > df.index[-1]:
                break
            train = run_window(inp, df, tr_lo, q, cfgs, fee, slip, mr)
            if not train:
                continue
            scored = [(pf(r), cid) for cid, (r, _) in train.items()
                      if len(r) >= FLOOR and np.isfinite(pf(r))]
            if not scored:
                continue
            scored.sort(reverse=True)
            test = run_window(inp, df, q, te_hi, cfgs, fee, slip, mr)
            if not test:
                continue
            nfolds += 1
            if first_test is None:
                first_test = q
            last_test = min(te_hi, df.index[-1])

            best = scored[0][1]
            oos["single"].append(test.get(best, (np.array([]), None))[0])
            book = [test.get(cid, (np.array([]), None))[0]
                    for _, cid in scored[:TOPN]]
            book = [b / TOPN for b in book if len(b)]
            oos["top10"].append(np.concatenate(book) if book else np.array([]))

            fold_rows.append({
                "symbol": sym, "tf": tf, "quarter": q.date(),
                "train_pf_2x": round(scored[0][0], 4), "cfg": best,
                "test_pf_2x": round(pf(oos["single"][-1]), 4)
                if len(oos["single"][-1]) else np.nan,
                "test_trades": len(oos["single"][-1]),
            })

        for rule, chunks in oos.items():
            r = np.concatenate([c for c in chunks if len(c)]) if chunks else np.array([])
            if len(r) < 30:
                continue
            eq = np.concatenate(([0.0], np.cumsum(r)))
            dd = float((eq - np.maximum.accumulate(eq)).min())
            qpf = [pf(c) for c in chunks if len(c) >= 5]
            # The span is the STITCHED OUT-OF-SAMPLE window, not the whole
            # series. R only accrues during test quarters, so dividing by the
            # full history (which includes the first training year, and every
            # quarter the fold could not score) understates R per day and
            # inflates days-to-target - by roughly 1.7x on the gold legs.
            span = max((last_test - first_test).days, 1) if first_test else 1
            rpd = float(r.sum()) / span
            stitched_rows.append({
                "symbol": sym, "tf": tf, "rule": rule, "folds": nfolds,
                # The phase gate: days = maxDD_R / R_per_day. Risk is set so the
                # book's drawdown exactly fills the 8% cap, and time to +8%
                # follows. CLAUDE.md calls this the field that decides whether
                # an idea fits this phase at all.
                "r_per_day": round(rpd, 4),
                "days_to_target": (round(abs(dd) / rpd, 1)
                                   if rpd > 0 and dd < 0 else np.nan),
                "trades": len(r), "pf_2x": round(pf(r), 4),
                "total_r": round(float(r.sum()), 2), "max_dd_r": round(dd, 2),
                "q_above_1": int(np.sum([x > 1 for x in qpf if np.isfinite(x)])),
                "q_scored": int(np.sum(np.isfinite(qpf))),
            })
        s = [x for x in stitched_rows if x["symbol"] == sym and x["tf"] == tf]
        msg = "  ".join(f"{x['rule']} PF2x {x['pf_2x']:.3f} ({x['trades']}t)"
                        for x in s)
        print(f"  {sym:8s} {tf:4s} {nfolds:>2d} folds   {msg}", flush=True)

    tag = "" if shuffle_seed is None else f"_null{shuffle_seed}"
    pd.DataFrame(fold_rows).to_csv(OUT / f"stage6_folds{tag}.csv", index=False)
    st = pd.DataFrame(stitched_rows)
    st.to_csv(OUT / f"stage6_stitched{tag}.csv", index=False)
    print(f"\n{len(st)} stitched series, {time.time() - t0:.0f}s")
    if len(st):
        print(f"median stitched PF at 2x: {st.pf_2x.median():.3f}")
        print(f"clearing 1.20: {(st.pf_2x >= 1.2).sum()} of {len(st)}")
    return 0


if __name__ == "__main__":
    seed = int(sys.argv[1]) if len(sys.argv) > 1 else None
    raise SystemExit(main(seed))
