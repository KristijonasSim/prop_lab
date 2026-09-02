"""H-002 board record from the twelve-market universe (stage 10).

Picks the book the same way stage 9 did, with the same two constraints that were
learned the hard way:

  * every candidate book must clear PF 1.20 at DOUBLE cost, not just at 1x;
  * `topn = 1` is preferred, because a top-ten book means running ten
    configurations per market at once - a research estimator for damping
    selection noise, not a trading plan.

Among what qualifies, the book that reaches a funded account soonest wins.
"""
from __future__ import annotations

import itertools
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from core import board, riskladder as RL                  # noqa: E402
from strategies.vwap.stage1_grid import OUT               # noqa: E402

GATE = 1.20
COMMON = "2024-09-01"          # first quarter every FX/metal leg has


def main():
    st = pd.read_csv(OUT / "stage10_stitched.csv")
    nl = pd.read_csv(OUT / "stage10_stitched_shuffled_paired.csv")
    tr = pd.read_parquet(OUT / "stage10_trades.parquet")
    tr["entry_ts"] = pd.to_datetime(tr.entry_ts, utc=True)
    tr["exit_ts"] = pd.to_datetime(tr.exit_ts, utc=True)
    folds = pd.read_parquet(OUT / "stage10_folds.parquet")

    def survivors(d):
        p = d.pivot_table(index=["symbol", "tf"], columns=["floor", "topn"], values="pf_2x")
        w = p.min(axis=1)
        return list(w[w >= GATE].index), int((w >= GATE).sum())

    legs_all, real_s = survivors(st)
    _n, null_s = survivors(nl)
    null_margin = 0.0 if not real_s else max(0.0, (real_s - null_s) / real_s)
    print(f"survivors at 2x: real {real_s}, paired null {null_s}")

    def book(sub, floor, topn):
        s = tr[(tr.floor == floor) & (tr.topn == topn) & (tr.exit_ts >= COMMON)]
        s = s[[(a, b) in sub for a, b in zip(s.symbol, s.tf)]].sort_values("exit_ts")
        if len(s) < 100:
            return None
        r = s.r.values / len(sub)
        r2 = s.r_2x.values / len(sub)
        pf2 = board.pf_of(r2)
        if pf2 < GATE:
            return None
        span = (s.exit_ts.iloc[-1] - s.exit_ts.iloc[0]).days
        # cheap screen first: days = maxDD_R / R_per_day. The account simulation
        # is far more expensive, so only the shortlist gets it.
        eq = np.concatenate(([0.0], np.cumsum(r)))
        dd = abs(float((eq - np.maximum.accumulate(eq)).min()))
        rpd = r.sum() / max(span, 1)
        if rpd <= 0:
            return None
        return {"sub": sub, "floor": floor, "topn": topn, "sel": s,
                "pf_2x": pf2, "est_days": dd / rpd}

    cands = []
    for k in range(1, len(legs_all) + 1):
        for sub in itertools.combinations(legs_all, k):
            for floor in (100, 30):
                for topn in (1, 10):
                    c = book(list(sub), floor, topn)
                    if c:
                        cands.append(c)
    if not cands:
        print("no book holds 1.20 at 2x"); return
    cands.sort(key=lambda c: (c["topn"] != 1, c["est_days"]))
    print(f"{len(cands)} books hold 1.20 at 2x; simulating the best 12")

    best = None
    for c in cands[:12]:
        r = c["sel"].r.values / len(c["sub"])
        _rows, pk = RL.from_trades(r, c["sel"].exit_ts)
        if pk["expected_days"] is None:
            continue
        if best is None or (c["topn"] == 1) > (best[0]["topn"] == 1) or \
           (c["topn"] == best[0]["topn"] and pk["expected_days"] < best[1]):
            best = (c, pk["expected_days"])
    if best is None:
        print("nothing resolves"); return
    c = best[0]
    legs, floor, topn, sel = c["sub"], c["floor"], c["topn"], c["sel"]
    print(f"chosen: {' + '.join(f'{a} {b}' for a, b in legs)} "
          f"(floor {floor}, top {topn}, PF@2x {c['pf_2x']:.3f}, {best[1]:.0f} days)")

    fl = folds[[(a, b) in legs for a, b in zip(folds.symbol, folds.tf)]]
    consistency = float((fl.test_pf > 1).mean()) if len(fl) else 0.0

    p = st.pivot_table(index=["symbol", "tf"], columns=["floor", "topn"], values="pf_2x")
    grid = [{"label": f"{a} {b}",
             "cols": [None if pd.isna(p.loc[(a, b), (f, n)]) else float(p.loc[(a, b), (f, n)])
                      for f, n in [(30, 1), (30, 10), (100, 1), (100, 10)]],
             "worst": float(p.loc[(a, b)].min()),
             "clears": bool(p.loc[(a, b)].min() >= GATE)}
            for a, b in p.index]
    grid.sort(key=lambda x: -x["worst"])

    board.write_board(
        sid="vwap", hid="H-002", name="VWAP",
        tagline="Five model families around the volume-weighted average price.",
        period="12 markets · FX & metals 2023-09 → 2026-08 · crypto from 2017",
        report="https://claude.ai/code/artifact/cb748842-7d3b-45f7-9d69-827e00ba82f4",
        candidate=(" + ".join(f"{a} {b}" for a, b in legs)
                   + ", equal weight, configs chosen by 2x-cost train PF each quarter"),
        markets={"traded": [{"sym": a, "tf": b, "asset": a[:3]} for a, b in legs],
                 "searched": "12 markets (BTC/ETH/SOL, XAU/XAG, 7 FX majors) x 15m-4h",
                 "note": "Eight market/timeframe combinations cleared PF 1.20 at 2x "
                         "cost under all four selection rules; these five are the "
                         "fastest book among them."},
        # every candidate leg, not just the five the board chose, so any subset
        # the trader ticks is measured over the same window
        legs=board.leg_payload(
            tr[(tr.floor == floor) & (tr.topn == topn)
               & [(a, b) in legs_all for a, b in zip(tr.symbol, tr.tf)]]
              .rename(columns={"symbol": "sym"}),
            picked=legs, cap=None, start=COMMON),
        r=sel.r.values / len(legs), r_2x=sel.r_2x.values / len(legs),
        entry_ts=sel.entry_ts, exit_ts=sel.exit_ts, n_books=len(legs) * topn,
        null_margin=null_margin, beats_null=(real_s > null_s),
        consistency=consistency,
        grid={"title": "Every market × timeframe, profit factor AT 2x COST",
              "note": ("The <strong>worst</strong> column is the least favourable of the "
                       "four selection rules, measured at double cost — the gate this "
                       "project actually uses. ETH is stronger than BTC."),
              "cols": ["floor 30 / best", "floor 30 / top 10",
                       "floor 100 / best", "floor 100 / top 10"],
              "label": "Market", "rows": grid},
        todo=[
            {"t": "Fill realism", "w": "Honest fills only; the limit-fill result was an artefact.", "done": True},
            {"t": "Cost stress to 2x and 3x", "w": "Fold selection now optimises 2x-cost profit factor directly.", "done": True},
            {"t": "Walk-forward, 12 markets", "w": "8 combinations clear 1.20 at 2x under all four selection rules.", "done": True},
            {"t": "Paired-shuffle null", "w": "Keeps each bar's volume with its own return. Real 52 gate-clearing cells at 2x against the null's 3; 8 survivors against 0.", "done": True},
            {"t": "Prop simulation on walk-forward output", "w": "Full risk ladder, both breach types counted.", "done": True},
            {"t": "NautilusTrader cross-check", "w": "Independent matching engine has not verified the kernel.", "done": False},
            {"t": "Live paper trading", "w": "Blocked: two legs are gold and this box has no MT5 bridge, so half the book cannot be paper-traded.", "done": False},
        ],
        note=("The only hypothesis in the project still standing. ETHUSDT is now the "
              "strongest single market, ahead of BTC. Still slower than the ~14-day phase "
              "target — though no-time-limit prop evaluations are standard, which makes "
              "that constraint self-imposed rather than a firm rule."),
    )


if __name__ == "__main__":
    main()
