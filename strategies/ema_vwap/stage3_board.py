"""H-003 board record — rejected, and put on the board saying so.

The board scores every hypothesis on walk-forward output, so H-003 goes on it
with the best combination it actually produced: gold at 1h, the only one of 48
that cleared PF 1.20 under all four selection rules. The point of putting a
rejected idea on the board is that the failures are the denominator - a score
next to H-002's is what makes H-002's score mean anything.

`null_margin` is 0 by construction here and that is the whole finding: the
phase-randomised walk-forward produced MORE gate-clearing cells than the real
one (17 of 198 against 10 of 192), and two combinations clearing under every
selection rule against one. Finding a single survivor in 48 combinations is what
noise gives you.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from core import board                                       # noqa: E402
from core import riskladder as RL                            # noqa: E402
from strategies.ema_vwap.stage1_grid import OUT              # noqa: E402

GATE = 1.20


def main():
    st = pd.read_csv(OUT / "stage2_stitched.csv")
    nl = pd.read_csv(OUT / "stage2_stitched_shuffled.csv")
    tr = pd.read_parquet(OUT / "stage2_trades.parquet")
    tr["entry_ts"] = pd.to_datetime(tr.entry_ts, utc=True)
    tr["exit_ts"] = pd.to_datetime(tr.exit_ts, utc=True)
    folds = pd.read_parquet(OUT / "stage2_folds.parquet")

    def worst(d):
        p = d.pivot_table(index=["symbol", "tf"], columns=["floor", "topn"], values="pf")
        return p, p.min(axis=1)

    pr, wr = worst(st)
    _pn, wn = worst(nl)
    survivors = list(wr[wr >= GATE].index)
    real_s, null_s = len(survivors), int((wn >= GATE).sum())
    null_margin = 0.0 if not real_s else max(0.0, (real_s - null_s) / real_s)

    if not survivors:
        print("nothing cleared under all four rules - no board record")
        return
    sym, tf = survivors[0]

    # among that combination's four selection rules, the one that reaches a
    # funded account soonest
    # A board candidate needs enough trades to mean anything. Without this the
    # "fewest expected days" rule picked a 55-trade cell whose headline profit
    # factor was 4.292 - the narrowest, luckiest slice the filter produced.
    MIN_TRADES = 150

    best = None
    for _, row in st[(st.symbol == sym) & (st.tf == tf)].iterrows():
        g = tr[(tr.symbol == sym) & (tr.tf == tf) &
               (tr.floor == row.floor) & (tr.topn == row.topn)].sort_values("exit_ts")
        if len(g) < MIN_TRADES:
            continue
        _rows, pk = RL.from_trades(g.r.values, g.exit_ts)
        if pk["expected_days"] is None:
            continue
        if best is None or pk["expected_days"] < best[0]:
            best = (pk["expected_days"], row, g)
    if best is None:
        print("no risk level resolves - no board record")
        return
    _, row, g = best

    fq = folds[(folds.symbol == sym) & (folds.tf == tf) &
               (folds.floor == row.floor) & (folds.topn == row.topn)]
    consistency = float((fq.test_pf > 1).mean()) if len(fq) else 0.0

    grid_rows = []
    for (s2, t2), gg in st.groupby(["symbol", "tf"]):
        cols = [float(gg[(gg.floor == f) & (gg.topn == n)].pf.iloc[0])
                if len(gg[(gg.floor == f) & (gg.topn == n)]) else None
                for f, n in [(30, 1), (30, 10), (100, 1), (100, 10)]]
        nb = nl[(nl.symbol == s2) & (nl.tf == t2)].pf
        grid_rows.append({"label": f"{s2} {t2}", "cols": cols,
                          "worst": float(gg.pf.min()),
                          "null_best": round(float(nb.max()), 3) if len(nb) else None,
                          "clears": bool(gg.pf.min() >= GATE)})
    grid_rows.sort(key=lambda x: -x["worst"])

    board.write_board(
        sid="ema_vwap", hid="H-003", name="EMA × VWAP cross",
        tagline="Enter when the EMA crosses the volume-weighted average price.",
        period="FX & metals 2023-09 → 2026-08 · BTC from 2017",
        report="",
        candidate=f"{sym} {tf}, config re-chosen blind each quarter",
        # H-003's book is one combination, but 44 were walk-forwarded; offering
        # the best of them lets the rejection be checked rather than taken on
        # trust - build a book out of them and watch it still not clear the gate
        legs=board.leg_payload(
            tr[(tr.floor == row.floor) & (tr.topn == row.topn)]
              .rename(columns={"symbol": "sym"}),
            picked=[(sym, tf)], cap=8),
        markets={"traded": [{"sym": sym, "tf": tf, "asset": sym[:3]}],
                 "searched": "9 markets x 3m-1d, 284k backtests",
                 "note": "One survivor in 48 market/timeframe combinations - and the "
                         "phase-randomised null produced two."},
        r=g.r.values, r_2x=g.r_2x.values, n_books=int(row.topn),
        entry_ts=g.entry_ts, exit_ts=g.exit_ts,
        # the null produced MORE gate-clearing cells and more survivors
        null_margin=null_margin, beats_null=(real_s > null_s),
        consistency=consistency,
        grid={
            "title": "Every market × timeframe, under all four ways of choosing",
            "note": ("The <strong>worst</strong> column is how the combination does under "
                     "the least favourable of the four selection rules. Only one of 48 "
                     "clears the gate that way — and the phase-randomised null produced "
                     "<strong>two</strong>."),
            "cols": ["floor 30 / best", "floor 30 / top 10",
                     "floor 100 / best", "floor 100 / top 10"],
            "label": "Market", "rows": grid_rows,
        },
        todo=[
            {"t": "Full grid, 4 exits × slope filter", "w": "All five variants. Every exit's median profit factor is below breakeven (0.62–0.75).", "done": True},
            {"t": "Cost stress to 2x and 3x", "w": "At 2× cost, zero configurations clear PF 1.20 with a usable trade frequency.", "done": True},
            {"t": "Null benchmark on the grid", "w": "Real median 0.705 against a shuffled 0.757 — the real markets score WORSE than randomised copies.", "done": True},
            {"t": "Slope filter (variant E)", "w": "Paired lift on the median: −0.024, only 49.2% of configs improved. Negative.", "done": True},
            {"t": "Walk-forward, all 48 combinations", "w": "Median stitched 0.808. Gold 1h reaches 2.356 but is 1 survivor in 48.", "done": True},
            {"t": "Null benchmark on the walk-forward", "w": "The null produced MORE gate-clearing cells than the real data (17 vs 10) and more survivors (2 vs 1).", "done": True},
            {"t": "Gold-only re-test on fresh data", "w": "The only thing that could rescue the gold 1h pocket is out-of-sample data that does not exist yet.", "done": False},
        ],
        note=("Rejected. Gold at 1h walk-forwards to 2.356 with 7 of 7 quarters positive, and "
              "beats its own shuffled twin decisively — but it is one survivor out of 48 "
              "combinations, and the phase-randomised null produced two. That is not a "
              "distinguishable edge; it is what searching 192 stitched series gives you. "
              "The mechanism was weak going in: two lagging averages of the same price "
              "series carry no information the price does not already have."),
    )


if __name__ == "__main__":
    main()
