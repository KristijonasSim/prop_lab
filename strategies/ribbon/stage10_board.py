"""H-016 stage 10 - the metals book, and its board record.

Gold and silver are the only markets in H-016 that survive. Stage 9 killed the
three US indices outright (all nine legs below breakeven) and stages 5-6 left
crypto and FX behind. So the book that goes on the board is metals only.

Everything here is walk-forward output: 12 months train / 3 months test,
quarterly, configuration chosen blind inside each training window on 2x-cost
profit factor and never re-chosen inside the test quarter. A fitted backtest
is not comparable to what is already on the board and does not go on it.

The book is chosen by the PHASE GATE - `days = maxDD_R / R_per_day` - among
subsets that clear PF 1.20 at double cost, which is how H-002's book was
chosen. Selection happens on the same window it is reported on, so the leg
CHOICE is in-sample even though every trade in it is out-of-sample. That is
stated on the board rather than hidden: it is the same caveat H-002 carries.

Output: backtests/ribbon/board.json, stage10_trades.parquet
"""
from __future__ import annotations

import itertools
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from core import board                                             # noqa: E402
from strategies.ribbon import engine as E                          # noqa: E402
from strategies.ribbon.sweep import (COSTS, OUT, TFS, build_grid,  # noqa: E402
                                     load_tf, ribbon_inputs, shuffled)
from strategies.ribbon.stage6_walkforward import (                 # noqa: E402
    FLOOR, PAD, TEST_MONTHS, TOPN, TRAIN_MONTHS, cost_adjusted, pf, run_window)

LEGS = [(s, tf) for s in ("XAUUSD", "XAGUSD")
        for tf in ("15m", "30m", "1h", "4h")]
RULES = ("single", "top10")
GATE = 1.20


def trades_for(sym, tf, rule, df=None):
    """Walk-forward trades for one leg, with timestamps and 1x/2x R."""
    if df is None:
        df = load_tf(sym, tf)
    inp = ribbon_inputs(df)
    fee, slip, mr = COSTS[sym]
    cfgs = build_grid(TFS[tf][1])
    for c in cfgs:
        c["min_risk_bps"] = mr

    start = df.index[0] + pd.DateOffset(months=TRAIN_MONTHS)
    start = (start + pd.offsets.QuarterBegin(startingMonth=1)).normalize()
    rows, qpf = [], []
    for q in pd.date_range(start, df.index[-1], freq="QS", tz="UTC"):
        tr_lo = q - pd.DateOffset(months=TRAIN_MONTHS)
        te_hi = q + pd.DateOffset(months=TEST_MONTHS)
        if te_hi > df.index[-1]:
            break
        train = run_window(inp, df, tr_lo, q, cfgs, fee, slip, mr)
        if not train:
            continue
        scored = sorted(((pf(r), cid) for cid, (r, _) in train.items()
                         if len(r) >= FLOOR and np.isfinite(pf(r))), reverse=True)
        if not scored:
            continue
        test = run_window(inp, df, q, te_hi, cfgs, fee, slip, mr)
        if not test:
            continue

        chosen = [scored[0][1]] if rule == "single" else [c for _, c in scored[:TOPN]]
        w = 1.0 / len(chosen)
        qr = []
        i0 = df.index.searchsorted(q)
        s0 = max(0, i0 - PAD)
        for cid in chosen:
            r2, tr = test.get(cid, (np.array([]), None))
            if tr is None or not tr.shape[0]:
                continue
            ei = (tr[:, E.T_ENTRY_I] + s0).astype(int)
            xi = (tr[:, E.T_EXIT_I] + s0).astype(int)
            ok = (ei < len(df)) & (xi < len(df))
            ei, xi, tr, r2 = ei[ok], xi[ok], tr[ok], r2[ok]
            if not len(ei):
                continue
            qr.append(r2 * w)
            rows.append(pd.DataFrame({
                "sym": sym, "tf": tf, "rule": rule, "quarter": q,
                "entry_ts": df.index[ei], "exit_ts": df.index[xi],
                "r": tr[:, E.T_R] * w, "r_2x": r2 * w}))
        if qr:
            qpf.append(pf(np.concatenate(qr)))

    out = pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()
    return out, qpf


def survivors(seed=None):
    """How many leg x rule series clear PF 1.20 at 2x. seed=None is the real data."""
    n = 0
    for sym, tf in LEGS:
        df = load_tf(sym, tf)
        if seed is not None:
            df = shuffled(df, sym, tf, "s10b", seed)
        for rule in RULES:
            t, _ = trades_for(sym, tf, rule, df)
            if len(t) >= 30 and pf(t.r_2x.values) >= GATE:
                n += 1
    return n


def main() -> int:
    print("walk-forward on the metals legs ...\n")
    all_tr, cons = [], {}
    for sym, tf in LEGS:
        for rule in RULES:
            t, qpf = trades_for(sym, tf, rule)
            if len(t) < 30:
                continue
            t["leg"] = f"{sym} {tf} {rule}"
            all_tr.append(t)
            cons[(sym, tf, rule)] = qpf
            print(f"  {sym} {tf:>4s} {rule:>6s}  {len(t):>5d} trades  "
                  f"PF@2x {pf(t.r_2x.values):.3f}  "
                  f"quarters>1 {sum(x > 1 for x in qpf)}/{len(qpf)}")
    tr = pd.concat(all_tr, ignore_index=True)
    tr.to_parquet(OUT / "stage10_trades.parquet")

    print("\nnull benchmark: identical walk-forward on phase-randomised metals")
    real_s = survivors()
    null_s = [survivors(s) for s in range(3)]
    ns = float(np.mean(null_s))
    total = len(LEGS) * len(RULES)
    print(f"  survivors clearing PF {GATE} at 2x: real {real_s}/{total}, "
          f"null {ns:.1f}/{total} (seeds {null_s})")
    null_margin = max(0.0, (real_s - ns) / real_s) if real_s else 0.0

    # ---- choose the book on the phase gate, among subsets that clear 1.20 ----
    keys = sorted({(a, b, c) for a, b, c in
                   zip(tr.sym, tr.tf, tr.rule)})
    common = max(tr[(tr.sym == a) & (tr.tf == b) & (tr.rule == c)].exit_ts.min()
                 for a, b, c in keys)
    # Pre-split once. Filtering the frame inside 2^16 combinations took longer
    # than the entire walk-forward that produced it; slicing prebuilt arrays and
    # merging by timestamp is the same answer in seconds.
    win = tr[tr.exit_ts >= common].sort_values("exit_ts").reset_index(drop=True)
    key_of = list(zip(win.sym, win.tf, win.rule))
    idx = {k: np.array([i for i, x in enumerate(key_of) if x == k]) for k in keys}
    R, R2 = win.r.values, win.r_2x.values
    TS = win.exit_ts.values

    # Capped at 4 legs. H-012 established that widening a book DILUTES it here -
    # equal weighting divides R by the leg count and a weak leg costs more R per
    # day than it saves in drawdown - so more legs is not a free improvement and
    # the search should not be allowed to pile them on.
    best = None
    for k in range(1, 5):
        for sub in itertools.combinations(keys, k):
            sel = np.sort(np.concatenate([idx[x] for x in sub]))
            if len(sel) < 100:
                continue
            r, r2 = R[sel] / len(sub), R2[sel] / len(sub)
            if board.pf_of(r2) < GATE:
                continue
            span = max((TS[sel][-1] - TS[sel][0]).astype("timedelta64[D]").astype(int), 1)
            eq = np.concatenate(([0.0], np.cumsum(r)))
            dd = abs(float((eq - np.maximum.accumulate(eq)).min()))
            rpd = r.sum() / span
            if rpd <= 0:
                continue
            days = dd / rpd
            if best is None or days < best["days"]:
                best = {"sub": list(sub), "sel": win.iloc[sel], "r": r,
                        "r_2x": r2, "days": days, "pf_2x": board.pf_of(r2)}
    if best is None:
        print("no subset clears the gate - nothing to put on the board")
        return 1

    sub = best["sub"]
    print(f"\nbook: {len(sub)} legs, PF@2x {best['pf_2x']:.3f}, "
          f"{best['days']:.0f} days by the cheap estimate")
    for a, b, c in sub:
        print(f"    {a} {b} {c}")

    qall = [x for k, v in cons.items()
            if (k[0], k[1], k[2]) in sub for x in v]
    consistency = float(np.mean([x > 1 for x in qall])) if qall else 0.0

    legpay = best["sel"].copy()
    legpay["tf"] = [f"{b} {c}" for b, c in zip(legpay.tf, legpay.rule)]
    legpay["r"] = legpay.r * len(sub)          # leg_payload divides by the count
    legpay["r_2x"] = legpay.r_2x * len(sub)

    board.write_board(
        sid="ribbon", hid="H-016",
        name="Trend-following MA ribbon",
        tagline="Twenty moving averages agreeing across timescales. Beats its "
                "null and beats buy-and-hold under a drawdown cap - on metals "
                "only, and far too slow for the current phase.",
        period=f"{best['sel'].exit_ts.min():%Y-%m} to "
               f"{best['sel'].exit_ts.max():%Y-%m}, walk-forward",
        report="strategies/ribbon/notes.md",
        candidate="no - fails the phase gate and the walk-forward null margin "
                  "is thin",
        r=best["r"], r_2x=best["r_2x"],
        entry_ts=best["sel"].entry_ts.values,
        exit_ts=best["sel"].exit_ts.values,
        n_books=len(sub),
        null_margin=null_margin, beats_null=(real_s > ns),
        consistency=consistency,
        legs=board.leg_payload(legpay, picked=[(a, f"{b} {c}") for a, b, c in sub],
                               cap=None, start=common),
        markets={"traded": [{"sym": a, "tf": f"{b} {c}", "asset": a[:3]}
                            for a, b, c in sub],
                 "searched": "12 markets x 5 timeframes x 660 configurations "
                             "(37,620 backtests), plus S&P 500, US30 and "
                             "Nasdaq added later - all three rejected"},
        grid={"title": "Metals walk-forward, profit factor AT 2x COST",
              "note": "Every US index leg tested was below breakeven; crypto "
                      "and FX majors did not survive stage 6."},
        note="Kris's original rule - gold 15m, enter when every EMA turns "
             "green, exit on a trailing TP - LOSES as stated at any normal "
             "trail width. It only turns positive with an 8-16 ATR chandelier "
             "trail, which holds a position 76% of all bars. Under the 8% prop "
             "cap the gold book returns +84.5% over the last two years against "
             "buy-and-hold's +21.4%, but UNCAPPED at 1% risk holding gold wins "
             "+77.1% to +36.3%. It reduces drawdown; it does not beat gold.",
        todo=[
            "Phase gate fails: best leg is ~69 days to +8% against a ~14-day "
            "constraint.",
            "Walk-forward null margin is thin - on all 32 series it was 7 "
            "survivors against the null's 5.7.",
            "The gold cache starts 2023-09 and contains one bull market. There "
            "is no gold bear market anywhere in the data to test on.",
            "Drawdown assumes every stop fills at its price; gold gaps over "
            "weekends and the -2.00R is optimistic by an unknown amount.",
            "trail_k improves monotonically to the edge of the grid, so the "
            "best configurations are near-permanent exposure, not timing.",
        ])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
