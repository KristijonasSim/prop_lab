"""H-007 stage 2 — quarterly walk-forward, for board parity.

Stage 1 already answered the question; this exists so H-007 sits on the board on
the same footing as everything else, measured the way the board measures.

Fold rule, per the mistakes this repo has already paid for:
  * the config for quarter Q is chosen ONLY on trades that closed before Q;
  * it is chosen on 2x-COST profit factor, never on 1x;
  * a config needs >= MIN_TRAIN closed trades to be eligible;
  * the same procedure is run on paired-shuffled panels, so the null is a
    distribution and not one number.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from core import board                                        # noqa: E402
from strategies.xsec import xsec                               # noqa: E402
from strategies.xsec.stage1_grid import (COST_BPS, NSEEDS, OUT,  # noqa: E402
                                         grid, load_panel)

MIN_TRAIN = 30
GATE = 1.20


def all_series(panels) -> dict[tuple, pd.DataFrame]:
    out = {}
    for cfg in grid():
        tr = xsec.run(panels[cfg["tf"]], signal=cfg["signal"], L=cfg["L"],
                      H=cfg["H"], k=cfg["k"], mode=cfg["mode"], cost_bps=COST_BPS)
        if len(tr) >= MIN_TRAIN:
            out[(cfg["signal"], cfg["tf"], cfg["L"], cfg["k"], cfg["mode"], cfg["H"])] = tr
    return out


def walkforward(series: dict[tuple, pd.DataFrame]) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Returns (stitched out-of-sample trades, one row per fold)."""
    ends = pd.DatetimeIndex(sorted({t for d in series.values() for t in d.exit_ts}))
    if not len(ends):
        return pd.DataFrame(), pd.DataFrame()
    quarters = pd.period_range(ends.min(), ends.max(), freq="Q")

    picked, folds = [], []
    for q in quarters[1:]:
        lo, hi = q.start_time.tz_localize("UTC"), q.end_time.tz_localize("UTC")
        best, best_pf = None, -np.inf
        for key, d in series.items():
            tr = d[d.exit_ts < lo]
            if len(tr) < MIN_TRAIN:
                continue
            pf = xsec.pf_of(tr.r_2x.values)      # selection at DOUBLE cost
            if np.isfinite(pf) and pf > best_pf:
                best, best_pf = key, pf
        if best is None:
            continue
        d = series[best]
        test = d[(d.exit_ts >= lo) & (d.exit_ts <= hi)]
        if not len(test):
            continue
        picked.append(test)
        folds.append({"quarter": str(q), "cfg": "/".join(map(str, best)),
                      "train_pf_2x": best_pf, "trades": len(test),
                      "test_pf": xsec.pf_of(test.r.values),
                      "test_pf_2x": xsec.pf_of(test.r_2x.values)})
    if not picked:
        return pd.DataFrame(), pd.DataFrame()
    return pd.concat(picked).sort_values("exit_ts"), pd.DataFrame(folds)


def main():
    print("real walk-forward ...")
    stitched, folds = walkforward(all_series(load_panel()))
    if stitched.empty:
        print("no folds resolved"); return
    stitched.to_parquet(OUT / "stage2_trades.parquet")
    folds.to_csv(OUT / "stage2_folds.csv", index=False)

    real_pf = xsec.pf_of(stitched.r.values)
    real_pf2 = xsec.pf_of(stitched.r_2x.values)
    print(folds.to_string(index=False))
    print(f"\nreal stitched: {len(stitched)} trades  PF {real_pf:.3f}  PF@2x {real_pf2:.3f}")

    null_pf2 = []
    for seed in range(NSEEDS):
        st, _f = walkforward(all_series(load_panel(shuffle_seed=seed)))
        if st.empty:
            continue
        p = xsec.pf_of(st.r_2x.values)
        null_pf2.append(p)
        print(f"  null seed {seed}: PF@2x {p:.3f}  ({len(st)} trades)")

    beats = bool(null_pf2) and real_pf2 > max(null_pf2)
    margin = 0.0 if not null_pf2 or real_pf2 <= 0 else max(
        0.0, (real_pf2 - float(np.median(null_pf2))) / real_pf2)
    print(f"\nreal PF@2x {real_pf2:.3f} vs null median "
          f"{np.median(null_pf2) if null_pf2 else float('nan'):.3f} "
          f"/ best {max(null_pf2) if null_pf2 else float('nan'):.3f}")
    print(f"beats every null seed: {beats}")

    top = pd.read_csv(OUT / "stage1_real.csv").sort_values("pf_2x", ascending=False)
    rows = [{"label": f"{r.signal} {r.tf} L{int(r.L)} k{int(r.k)} {r.mode} H{int(r.H)}",
             "cols": [round(float(r.pf_0x), 3), round(float(r.pf), 3),
                      round(float(r.pf_2x), 3), round(float(r.tpd), 3)],
             "worst": round(float(r.pf_2x), 3),
             "clears": bool(r.pf_2x >= GATE)} for r in top.head(12).itertuples()]

    board.write_board(
        sid="xsec", hid="H-007", name="Cross-sectional crypto ranking",
        tagline="Rank the coins, buy the leaders, sell the laggards.",
        period="5 coins (BTC, ETH, SOL, BNB, XRP) · 1h/4h/1d · 2020-08 → 2026-08",
        report="", candidate="config re-chosen blind each quarter on 2x-cost train PF",
        r=stitched.r.values, r_2x=stitched.r_2x.values,
        entry_ts=stitched.entry_ts, exit_ts=stitched.exit_ts,
        n_books=1, null_margin=margin, beats_null=beats,
        consistency=float((folds.test_pf > 1).mean()) if len(folds) else 0.0,
        grid={"title": "Best 12 configurations of 360, by profit factor at 2x cost",
              "note": ("The <strong>0x</strong> column is the diagnostic. The ranking "
                       "does carry a little information — 95% of real configs beat 1.0 "
                       "before costs against 59% of null ones — but it is far too small "
                       "to survive a 14bps round trip, and every cell that clears the "
                       "gate is a 7-day hold."),
              "cols": ["PF 0x", "PF 1x", "PF 2x", "trades/day"],
              "label": "Configuration", "rows": rows},
        todo=[
            {"t": "Full grid, 360 configs × 6 panels", "w": "2 signals × 3 timeframes × 5 lookbacks × 2 basket sizes × 2 modes × 3 holds.", "done": True},
            {"t": "Paired-shuffle null, 5 seeds", "w": "Read as a distribution: null cleared the 2x gate on 0/1/2/9/14 configs against the real 23.", "done": True},
            {"t": "Cost stress 0x/1x/2x/3x", "w": "Median profit factor falls 1.10 → 0.83 → 0.62. Costs, not the signal, are the whole story.", "done": True},
            {"t": "Walk-forward", "w": "Run for board parity, not because stage 1 justified it.", "done": True},
            {"t": "Wide universe (50+ coins)", "w": "Not run. Five majors is not a cross-section; the published edge ranks hundreds of names.", "done": False},
        ],
        note=("Rejected. The ranking is not noise — before costs it beats its paired "
              "null cleanly — but the edge is roughly 10% on profit factor and a round "
              "trip costs more than that. Everything that survives 2x cost is 1d with a "
              "7-day hold and ~0.14 trades/day, which is a longer-hold idea CLAUDE.md "
              "says to log rather than build this phase, and its time-to-target is in "
              "the hundreds of days against H-002's 25. The best single null cell also "
              "still beats the best real cell. Five highly-correlated majors is the "
              "known weakness: the published version ranks hundreds of names."),
    )
    print("\nwrote backtests/xsec/board.json")


if __name__ == "__main__":
    main()
