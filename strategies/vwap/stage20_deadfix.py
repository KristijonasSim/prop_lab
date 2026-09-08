"""H-002 stage 20 — the two dead-bar fixes applied, and what they cost.

Stage 17 ported the kernel to NautilusTrader and found one disagreement in
twenty-five configurations, and the disagreement was the KERNEL'S. Stage 19
priced it. This stage applies the two fixes stage 19 wrote down and deliberately
did not apply, and re-runs the gold walk-forward on both sides so the difference
is measured rather than assumed.

THE TWO FIXES

  1. `strategies/vwap/engine.py`, the volatility guard. `vwstd` is
     sqrt(p2v/v - vwap^2): a difference of two nearly equal accumulated sums,
     so its floating-point cancellation floor is price*sqrt(eps), about 3e-5 on
     gold. A session made entirely of padded weekend bars has a TRUE sigma of
     exactly zero and returned 3.1e-5 of noise, which passed the old
     `if sd <= 0.0: skip` guard. Bands built on that noise are meaningless and
     the kernel was resolving trade decisions with them. The guard is now
     `sd <= vwap * SD_EPS_FRAC`, SD_EPS_FRAC = 1e-6 - roughly 70x above the
     cancellation floor and ~2,000x below the smallest real band on gold.

  2. `live` bars. Dukascopy pads the closed FX weekend with synthetic bars:
     zero volume, O=H=L=C at the last traded price. **21.5% of the XAUUSD
     series is these** (57,975 of 270,144 5m bars). A trade cannot be decided on
     one and cannot be filled at one. The kernel now refuses both.

WHY THIS IS RUN AS ITS OWN STAGE. Every gold number moves, and gold is the only
edge in the project. A fix that quietly improves a result is indistinguishable
from a fix that quietly breaks one, so the pre-fix walk-forward is kept
(`stage6_trades.parquet`) and the post-fix walk-forward is written beside it
(`stage6_trades_xauusd_deadfix.parquet`) and the two are compared cell by cell.

WHAT WOULD MAKE THIS A BAD RESULT. Stage 19 measured only 0.83% of gold's R on
dead-bar entries, so the honest prior is that this changes little on the board's
own book. If it changes a LOT, the suspicion is not that the fix found free
money - it is that the fold selector is now choosing different configurations,
which is a different walk-forward and not a corrected one. Both are reported:
the trade-level effect on FIXED configs, and the fold-level effect.

Run: .venv/bin/python strategies/vwap/stage20_deadfix.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from core import board                                # noqa: E402
from strategies.vwap.manifest import MANIFEST         # noqa: E402
from strategies.vwap.stage18_goldbook import (         # noqa: E402
    ASSUMED_RT, MEASURED_RT, GATE, TF_ORDER, SYM, BT,
    reprice, pf, maxdd, cells, combine, best_per_tf, score, build,
)

OLD = BT / "stage6_trades.parquet"
NEW = BT / "stage6_trades_xauusd_deadfix.parquet"
OLD_NULL = BT / "stage6_trades_shuffled_paired.parquet"
NEW_NULL = BT / "stage6_trades_xauusd_shuffled_paired_deadfix.parquet"


def cellframe(path: Path, rt_bps: float) -> pd.DataFrame:
    """One row per walk-forward cell, at `rt_bps` and at 2x `rt_bps`."""
    c1 = cells(path, rt_bps)
    c2 = cells(path, rt_bps * 2)
    rows = []
    for k, g in c1.items():
        r1 = g.rm.values
        r2 = c2[k].rm.values
        span = max((g.exit_ts.max() - g.exit_ts.min()).days, 1)
        rows.append({"tf": k[0], "floor": k[1], "topn": k[2],
                     "trades": len(r1), "pf": pf(r1), "pf_2x": pf(r2),
                     "total_r": float(r1.sum()), "max_dd_r": maxdd(r1),
                     "r_per_day": float(r1.sum()) / span,
                     "tpd": len(r1) / span})
    d = pd.DataFrame(rows)
    d["tf"] = pd.Categorical(d.tf, TF_ORDER, ordered=True)
    return d.sort_values(["tf", "floor", "topn"]).reset_index(drop=True)


def compare(a: pd.DataFrame, b: pd.DataFrame, la: str, lb: str) -> pd.DataFrame:
    k = ["tf", "floor", "topn"]
    m = a.merge(b, on=k, suffixes=(f"_{la}", f"_{lb}"))
    m["d_pf_2x"] = m[f"pf_2x_{lb}"] - m[f"pf_2x_{la}"]
    m["d_trades"] = m[f"trades_{lb}"] - m[f"trades_{la}"]
    return m


def gate_counts(d: pd.DataFrame) -> tuple[int, int]:
    return int((d.pf_2x >= GATE).sum()), len(d)


def main():
    if not NEW.exists():
        print(f"missing {NEW.name} — run:\n"
              f"  .venv/bin/python strategies/vwap/stage6_walkforward.py "
              f"--only=XAUUSD --tag=_deadfix")
        return 1

    print("=" * 78)
    print("STAGE 20 — the dead-bar fixes, measured")
    print("=" * 78)
    print(f"\nCost: MEASURED {MEASURED_RT}bps round trip "
          f"(the walk-forward charged {ASSUMED_RT}); every 2x column is "
          f"{MEASURED_RT * 2}bps.\n")

    old = cellframe(OLD, MEASURED_RT)
    new = cellframe(NEW, MEASURED_RT)

    print("--- every gold walk-forward cell, before and after ---")
    m = compare(old, new, "old", "new")
    show = m[["tf", "floor", "topn", "trades_old", "trades_new", "d_trades",
              "pf_2x_old", "pf_2x_new", "d_pf_2x",
              "r_per_day_old", "r_per_day_new"]]
    print(show.to_string(index=False,
                         float_format=lambda x: f"{x:8.3f}"))

    go, to = gate_counts(old)
    gn, tn = gate_counts(new)
    print(f"\ncells clearing PF {GATE} at 2x measured cost: "
          f"before {go}/{to}, after {gn}/{tn}")
    print(f"median PF@2x: before {old.pf_2x.median():.3f}, "
          f"after {new.pf_2x.median():.3f}")
    print(f"trades dropped: {old.trades.sum() - new.trades.sum()} of "
          f"{old.trades.sum()} ({100 * (1 - new.trades.sum() / old.trades.sum()):.1f}%)")

    # ---- the null, run through the identical change ----
    if NEW_NULL.exists():
        print("\n--- the paired null, same fixes, same procedure ---")
        on = cellframe(OLD_NULL, MEASURED_RT)
        nn = cellframe(NEW_NULL, MEASURED_RT)
        gon, ton = gate_counts(on)
        gnn, tnn = gate_counts(nn)
        print(f"null cells clearing PF {GATE} at 2x: "
              f"before {gon}/{ton}, after {gnn}/{tnn}")
        print(f"null best cell PF@2x: before {on.pf_2x.max():.3f}, "
              f"after {nn.pf_2x.max():.3f}")
        print(f"\nREAL {gn}/{tn} against NULL {gnn}/{tnn}.")
    else:
        print(f"\n(null not run yet: {NEW_NULL.name})")

    # ---- the board's own book ----
    print("\n--- the board's book (5m + 4h, equal weight), before and after ---")
    for label, path in (("before", OLD), ("after", NEW)):
        c1 = cells(path, MEASURED_RT)
        c2 = cells(path, MEASURED_RT * 2)
        lo = max(g.exit_ts.min() for g in c1.values())
        hi = min(g.exit_ts.max() for g in c1.values())
        rep = best_per_tf({k: g[(g.exit_ts >= lo) & (g.exit_ts <= hi)]
                           for k, g in c1.items()}, (lo, hi))
        picked = [rep[tf] for tf in ("5m", "4h") if tf in rep]
        if len(picked) != 2:
            print(f"  {label}: gold 5m/4h cells missing"); continue
        legs = [c1[k][(c1[k].exit_ts >= lo) & (c1[k].exit_ts <= hi)] for k in picked]
        bk = combine(legs, np.full(len(legs), 1.0 / len(legs)))
        legs2 = [c2[k][(c2[k].exit_ts >= lo) & (c2[k].exit_ts <= hi)] for k in picked]
        bk2 = combine(legs2, np.full(len(legs2), 1.0 / len(legs2)))
        s = score(bk.rm.values, bk.exit_ts, label, len(picked))
        print(f"  {label:6s} cells={[f'{k[0]} f{k[1]} t{k[2]}' for k in picked]}")
        print(f"         trades {s['trades']:5d}  PF {s['pf']:.3f}  "
              f"PF@2x {pf(bk2.rm.values):.3f}  R/day {s['r_per_day']:.4f}  "
              f"maxDD {s['max_dd_r']:.2f}R  "
              f"expected days {s.get('expected_days', float('nan'))}")

    # ---- the pairing re-chosen on the fixed data ----
    # The 100-day headline came from searching 78 one-cell-per-timeframe
    # combinations. Re-scoring the OLD winner on the NEW data answers "did this
    # book get slower"; re-running the SEARCH answers "is there still a fast
    # book". Both are needed, and only the second is comparable to the board.
    print("\n--- the 78-combination search, re-run on the fixed data ---")
    new_cells = cells(NEW, MEASURED_RT)
    s_new, b_new, rep_new = build(new_cells, "real_fixed")
    cols = ["book", "trades", "pf", "max_dd_r", "r_per_day", "tpd", "risk",
            "pass_rate", "median_days", "expected_days", "one_step_days"]
    b_new = b_new.sort_values("expected_days", na_position="last")
    print(b_new[cols].head(10).to_string(index=False))
    s_new.to_csv(BT / "stage20_gold_cells.csv", index=False)
    b_new.to_csv(BT / "stage20_gold_books.csv", index=False)

    if NEW_NULL.exists():
        s_nn, b_nn, _ = build(cells(NEW_NULL, MEASURED_RT), "null_fixed")
        s_nn.to_csv(BT / "stage20_gold_cells_null.csv", index=False)
        b_nn.to_csv(BT / "stage20_gold_books_null.csv", index=False)
        u_real = int((b_new.expected_days < 150).sum())
        u_null = int((b_nn.expected_days < 150).sum())
        print(f"\nbooks under 150 expected days: real {u_real}/{len(b_new)}, "
              f"null {u_null}/{len(b_nn)}")
        nb = b_nn[b_nn.expected_days.notna()]
        if not nb.empty:
            x = nb.loc[nb.expected_days.idxmin()]
            print(f"null's fastest book: {x.book} — {x.expected_days} d")

    fb = b_new[b_new.expected_days.notna()]
    if not fb.empty:
        x = fb.loc[fb.expected_days.idxmin()]
        print(f"\nFASTEST BOOK AFTER THE FIX: {x.book} — PF {x.pf:.3f}, "
              f"{x.tpd:.2f} trades/day, maxDD {x.max_dd_r:.2f}R, "
              f"{x.expected_days} expected days two-step, "
              f"{x.one_step_days} one-step.")

    print("\nEvery number above is on the MEASURED cost. Gold is the only market "
          "affected: crypto has zero zero-volume bars, so no crypto result moves.")
    return 0


if __name__ == "__main__" and "--board" not in sys.argv:
    raise SystemExit(main())


# ---------------------------------------------------------------------------
# The board record, rewritten on the FIXED walk-forward.
# ---------------------------------------------------------------------------

BOOK_NOTE = (
    "Gold, and only gold, on the kernel corrected 2026-09-07. Two defects that "
    "stage 17's NautilusTrader cross-check exposed are now fixed: the volatility "
    "guard let floating-point cancellation noise (~3e-5 on gold) act as a real "
    "band on sessions whose true sigma is exactly zero, and the kernel would both "
    "decide and fill on Dukascopy's padded weekend bars - zero volume, last price "
    "repeated, <strong>21.5% of the XAUUSD series</strong>. The edge survives the "
    "correction intact: 15 of 20 walk-forward cells still clear PF 1.20 at 2x "
    "measured cost against the paired null's 2 of 20, and the median cell IMPROVED, "
    "1.395 to 1.485. What does not survive is the pace headline. The old book's "
    "peak drawdown was 8.00R against an 8.00R cap - exactly on the line - so a 7.5% "
    "increase to 8.60R drops the risk ladder a rung and the same two cells go from "
    "100.2 expected days to 185.8. Re-running the whole 78-combination search on "
    "the corrected data finds a better book than re-scoring the old one: four legs "
    "weighted by signal-to-cost rather than equally, at 143.6 expected days. Read "
    "that with the same caveat as before - it is the fastest of 78 books chosen on "
    "the window it is scored on. The control is that the identical search on "
    "phase-randomised markets puts 0 of 78 books under 150 days against the real "
    "data's 3, and the null's fastest book needs 474.7 days. It is still 143.6 "
    "against a 45-day target, and 55.9 if the firm turns out to be one-step."
)


def write_gold_board(rt_bps: float = MEASURED_RT):
    """Rewrite `backtests/vwap/board.json` on the post-dead-bar-fix walk-forward.

    Same selection rule as stage 18 used: the fastest book in the 78-combination
    search. The rule is held fixed so the before/after is a like-for-like
    comparison and not a change of method dressed up as a result."""
    c1 = cells(NEW, rt_bps)
    c2 = cells(NEW, rt_bps * 2)
    lo = max(g.exit_ts.min() for g in c1.values())
    hi = min(g.exit_ts.max() for g in c1.values())
    cut = {k: g[(g.exit_ts >= lo) & (g.exit_ts <= hi)] for k, g in c1.items()}
    rep = best_per_tf(cut, (lo, hi))

    books = pd.read_csv(BT / "stage20_gold_books.csv")
    books = books[books.expected_days.notna()]
    win = books.loc[books.expected_days.idxmin()]
    combo = win.combo.split("+")
    wname = win.weighting
    picked = [rep[tf] for tf in combo if tf in rep]
    if len(picked) != len(combo):
        print("gold cells missing; board not written"); return None

    legs_r = [cut[k] for k in picked]
    rday = np.array([max(float(l.rm.sum()), 0.0) for l in legs_r])
    dd = np.array([max(maxdd(l.rm.values), 1e-9) for l in legs_r])
    n = len(picked)
    w = {"equal": np.ones(n) / n,
         "sig_cost": (rday / dd) / max((rday / dd).sum(), 1e-9),
         "by_r": rday / max(rday.sum(), 1e-9)}[wname]

    bk = combine(legs_r, w)
    legs2 = [c2[k][(c2[k].exit_ts >= lo) & (c2[k].exit_ts <= hi)] for k in picked]
    bk2 = combine(legs2, w)

    parts = []
    for k, wi in zip(picked, w):
        a = cut[k].copy()
        b = c2[k][(c2[k].exit_ts >= lo) & (c2[k].exit_ts <= hi)]
        a["r_2x"] = b.rm.values
        a["tf"] = k[0]
        a["w"] = wi
        parts.append(a)
    tr = pd.concat(parts, ignore_index=True).sort_values("exit_ts")

    # `leg_payload` wants each leg's OWN R, un-weighted; the page divides by the
    # number ticked. The book scored above is weighted, so the two differ - the
    # weighting is stated in the note rather than hidden in the trades.
    legs = board.leg_payload(
        pd.DataFrame({"sym": SYM, "tf": tr.tf, "exit_ts": tr.exit_ts,
                      "r": tr.rm.values, "r_2x": tr.r_2x.values}),
        picked=[(SYM, k[0]) for k in picked], cap=None)

    return board.write_board(
        sid="vwap", hid="H-002", name="VWAP — gold only",
        tagline="The one edge that survived the kernel fix, and then the dead-bar fix.",
        period=f"XAUUSD {'+'.join(combo)} [{wname}] · walk-forward 2024-09 → "
               f"2026-05 · MEASURED {rt_bps}bps round trip",
        report="", n_books=n,
        candidate=f"config re-chosen blind each quarter on train PF; the "
                  f"{'+'.join(combo)} book and its {wname} weighting chosen from "
                  f"78 combinations on the same window",
        r=bk.rm.values, r_2x=bk2.rm.values,
        entry_ts=bk.entry_ts, exit_ts=bk.exit_ts,
        null_margin=0.0, beats_null=True, consistency=0.0, legs=legs,
        markets={"traded": [{"sym": SYM, "tf": k[0], "asset": "XAU"} for k in picked],
                 "searched": "20 walk-forward cells on XAUUSD x 5 timeframes x "
                             "2 train-trade floors x top-1/top-10, then 78 "
                             "one-cell-per-timeframe combinations x 3 weightings",
                 "note": "Crypto is NOT here. It died to the 2026-09-06 kernel fix."},
        todo=[
            {"t": "Walk-forward, config chosen blind each quarter", "w": "Seven quarters, 2024-09 to 2026-05.", "done": True},
            {"t": "Paired null on the FIXED kernel", "w": "15 of 20 real cells clear PF 1.20 at 2x against the null's 2 of 20.", "done": True},
            {"t": "Measured cost, not assumed", "w": "1.83bps round trip from 478 sampled hours of Dukascopy ticks, against 3.00 assumed.", "done": True},
            {"t": "Independent-engine cross-check", "w": "stage17 matched 24 of 25 configurations bar for bar; the 25th disagreement was the kernel's and is what stage 20 fixes.", "done": True},
            {"t": "Dead weekend bars refused", "w": "21.5% of the XAUUSD series is zero-volume padding. The kernel no longer decides or fills on one.", "done": True},
            {"t": "Held-out check on the COMBINATION", "w": "The four-leg book and its weighting were chosen on the same window they are scored on. The null controls the search; a fresh window would settle it.", "done": False},
            {"t": "Pace", "w": "143.6 expected days two-step against a 45-day target. 55.9 one-step.", "done": False},
        ],
        note=BOOK_NOTE,
        manifest=MANIFEST,
    )


if "--board" in sys.argv:
    write_gold_board()
