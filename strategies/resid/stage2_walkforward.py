"""H-008 stage 2 — quarterly walk-forward and the board record.

Same fold discipline as everywhere else in this repo:
  * the config for quarter Q is chosen only on trades that closed before Q;
  * chosen on 2x-COST profit factor, never 1x — selecting on 1x and checking 2x
    afterwards is what let four fragile legs into the H-002 book;
  * a config needs MIN_TRAIN closed trades to be eligible;
  * the whole procedure is repeated on paired-shuffled panels so the null is a
    distribution, not one number.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from core import board                                          # noqa: E402
from strategies.resid import resid                              # noqa: E402
from strategies.resid.stage1_grid import (COINS, COST_BPS, NSEEDS,  # noqa: E402
                                          OUT, grid, load_panels)

MIN_TRAIN = 50
GATE = 1.20

NOTE = (
    "Rejected at stage 1. Zero of 1,152 configurations clear the gate at 2x cost and the paired-shuffle null beats the real data on every cut — more configs profitable before costs (55.4% vs 51.6%), higher median, higher best. This is the H-005 result again: a fade rule is EASIER to satisfy on shuffled data, because permuted series revert around their extremes more readily than real trending ones. The decisive diagnostic is the z-response, and it is flat — profit factor before any costs runs 1.000 / 0.997 / 1.006 / 1.013 as the entry threshold goes 1.5σ → 3.0σ. A three-sigma residual reverts no harder than a 1.5-sigma one, so the size of the deviation carries no information about what comes next. Nothing here is cost-limited; there is no edge to protect. Note every walk-forward fold selected a config whose TRAIN profit factor was already below 1.0 — the selector could not find a winner even in sample. Taken with H-007 this closes a family: continuation and reversion on the same relative structure, in opposite directions, both dead at retail cost."
)


def all_series(panels) -> dict[tuple, pd.DataFrame]:
    out = {}
    for cfg in grid():
        tr = resid.run(panels[cfg["tf"]], COINS, beta_win=cfg["beta_win"],
                       L=cfg["L"], H=cfg["H"], z_thr=cfg["z_thr"],
                       hedged=cfg["hedged"], cost_bps=COST_BPS)
        if len(tr) >= MIN_TRAIN:
            key = (cfg["tf"], cfg["beta_win"], cfg["L"], cfg["z_thr"],
                   cfg["H"], cfg["hedged"])
            out[key] = tr
    return out


def walkforward(series: dict[tuple, pd.DataFrame]):
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
            pf = resid.pf_of(tr.r_2x.values)
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
                      "test_pf": resid.pf_of(test.r.values),
                      "test_pf_2x": resid.pf_of(test.r_2x.values)})
    if not picked:
        return pd.DataFrame(), pd.DataFrame()
    return pd.concat(picked).sort_values("exit_ts"), pd.DataFrame(folds)


def main():
    print("real walk-forward ...")
    stitched, folds = walkforward(all_series(load_panels()))
    if stitched.empty:
        print("no folds resolved"); return
    stitched.to_parquet(OUT / "stage2_trades.parquet")
    folds.to_csv(OUT / "stage2_folds.csv", index=False)

    n = len(COINS)
    r, r2 = stitched.r.values / n, stitched.r_2x.values / n
    real_pf, real_pf2 = resid.pf_of(r), resid.pf_of(r2)
    print(folds.to_string(index=False))
    print(f"\nreal stitched: {len(stitched)} trades  PF {real_pf:.3f}  PF@2x {real_pf2:.3f}")

    null_pf2 = []
    for seed in range(NSEEDS):
        st, _f = walkforward(all_series(load_panels(shuffle_seed=seed)))
        if st.empty:
            continue
        p = resid.pf_of(st.r_2x.values / n)
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
    rows = [{"label": (f"{r_.tf} beta{int(r_.beta_win)} L{int(r_.L)} "
                       f"z{r_.z_thr} H{int(r_.H)} {'hedged' if r_.hedged else 'naked'}"),
             "cols": [round(float(r_.pf_0x), 3), round(float(r_.pf), 3),
                      round(float(r_.pf_2x), 3), round(float(r_.tpd), 2)],
             "worst": round(float(r_.pf_2x), 3),
             "clears": bool(r_.pf_2x >= GATE)} for r_ in top.head(12).itertuples()]

    board.write_board(
        sid="resid", hid="H-008", name="Beta-residual reversion",
        tagline="Strip out BTC, fade what is left.",
        period="ETH/SOL/BNB/XRP against BTC · 15m-4h · 2020-08 → 2026-08",
        report="", candidate="config re-chosen blind each quarter on 2x-cost train PF",
        r=r, r_2x=r2, entry_ts=stitched.entry_ts, exit_ts=stitched.exit_ts,
        n_books=len(COINS), null_margin=margin, beats_null=beats,
        consistency=float((folds.test_pf > 1).mean()) if len(folds) else 0.0,
        grid={"title": "Best 12 configurations of 1,152, by profit factor at 2x cost",
              "note": ("<strong>0x</strong> is the diagnostic column: it says whether "
                       "the residual reverts at all before the spread is paid. "
                       "<strong>hedged</strong> trades the coin against a beta-weighted "
                       "BTC leg and crosses two spreads; <strong>naked</strong> trades "
                       "the coin alone and crosses one, keeping the BTC exposure."),
              "cols": ["PF 0x", "PF 1x", "PF 2x", "trades/day"],
              "label": "Configuration", "rows": rows},
        todo=[
            {"t": "Full grid, 1,152 configs × 6 panels", "w": "4 timeframes × 3 beta windows × 4 lookbacks × 4 z thresholds × 3 holds × hedged/naked.", "done": True},
            {"t": "Paired-shuffle null, 5 seeds", "w": "The decisive test — a fade rule is easier to satisfy on shuffled data, which is what killed H-005.", "done": True},
            {"t": "Cost stress 0x/1x/2x/3x", "w": "Hedged pays two round trips, naked pays one; both priced.", "done": True},
            {"t": "Walk-forward", "w": "Quarterly, config re-chosen blind on 2x-cost train profit factor.", "done": True},
            {"t": "Two-step prop simulation", "w": "core/riskladder.run_accounts_two_step — 8% then 5%, the structure firms actually sell.", "done": False},
            {"t": "NautilusTrader cross-check", "w": "Independent matching engine has not verified this kernel.", "done": False},
        ],
        note=NOTE,
    )
    print("\nwrote backtests/resid/board.json")


if __name__ == "__main__":
    main()
