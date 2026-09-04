"""H-016 stage 5 - real against null, and the exposure control.

Two questions, and the second is the one that actually decides H-016.

1. DOES IT BEAT ITS NULL? The identical grid on five phase-randomised copies
   of every market. Counting gate-clearing configurations, not maxima: H-005
   found 1,702 real and its null found 19,062, which is what a search finding
   nothing looks like.

2. IS IT ANYTHING BUT EXPOSURE? The winning configurations hold a position
   76-80% of the time with a 16-ATR trailing stop, in markets that rose 130%
   (gold) and 1,671% (BTC) over the test window. A rule that is long most of
   the time in a market that went up does not need an edge to show a profit
   factor above 1. The control is a DIRECTION-BLIND twin: identical entries,
   identical exits, but the side is drawn at random with the same long share.
   If the ribbon is reading direction, it has to beat that.

   This is the control H-010 failed and H-009 passed, in the form that fits a
   directional trend rule.

Output: backtests/ribbon/stage5_verdict.csv
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from strategies.ribbon import engine as E                          # noqa: E402
from strategies.ribbon.sweep import (COSTS, OUT, TFS, build_grid,  # noqa: E402
                                     load_tf, metrics, ribbon_inputs, run_one)

GATE, MIN_TRADES, MIN_TPD = 1.20, 100, 0.10


def gate_mask(d: pd.DataFrame) -> pd.Series:
    """The repo's gate, with the floors that stop a 13-trade PF from counting."""
    return ((d.pf_2x >= GATE) & np.isfinite(d.pf_2x)
            & (d.trades >= MIN_TRADES) & (d.trades_per_day >= MIN_TPD))


def part1() -> pd.DataFrame:
    real = pd.read_csv(OUT / "stage2_real.csv")
    null = pd.read_csv(OUT / "stage3_null.csv")
    rg, ng = gate_mask(real), gate_mask(null)
    nseeds = null.seed.nunique()

    print("1. REAL AGAINST THE PAIRED NULL "
          f"({nseeds} seeds, gate PF>=1.20 at 2x, >={MIN_TRADES} trades, "
          f">={MIN_TPD} trades/day)\n")
    print(f"  configs clearing the gate    real {rg.sum():>6,}"
          f"     null {ng.sum() / nseeds:>8,.0f} per seed")
    print(f"  median PF at 2x              real {real.pf_2x.median():>6.3f}"
          f"     null {null.pf_2x.median():>8.3f}")
    fr = real.pf_2x.replace([np.inf, -np.inf], np.nan)
    fn = null.pf_2x.replace([np.inf, -np.inf], np.nan)
    print(f"  best PF at 2x (finite)       real {fr.max():>6.3f}"
          f"     null {fn.max():>8.3f}")

    rows = []
    print("\n  per timeframe, gate-clearing configs:")
    print(f"    {'tf':>5s}  {'real':>6s}  {'null/seed':>10s}  {'median PF@2x real/null':>24s}")
    for tf in TFS:
        r, n = real[real.tf == tf], null[null.tf == tf]
        if not len(r):
            continue
        rr, nn = gate_mask(r).sum(), gate_mask(n).sum() / nseeds
        print(f"    {tf:>5s}  {rr:>6,}  {nn:>10,.0f}  "
              f"{r.pf_2x.median():>11.3f} / {n.pf_2x.median():.3f}")
        rows.append({"cut": f"tf={tf}", "real_clears": int(rr),
                     "null_clears_per_seed": round(nn, 1),
                     "real_median": round(r.pf_2x.median(), 3),
                     "null_median": round(n.pf_2x.median(), 3)})

    print("\n  per market, gate-clearing configs:")
    for sym in sorted(real.symbol.unique()):
        r, n = real[real.symbol == sym], null[null.symbol == sym]
        rr, nn = gate_mask(r).sum(), gate_mask(n).sum() / nseeds
        flag = "  <-- beats null" if rr > nn else ""
        print(f"    {sym:>8s}  {rr:>6,}  {nn:>10,.0f}  "
              f"{r.pf_2x.median():>11.3f} / {n.pf_2x.median():.3f}{flag}")
        rows.append({"cut": f"sym={sym}", "real_clears": int(rr),
                     "null_clears_per_seed": round(nn, 1),
                     "real_median": round(r.pf_2x.median(), 3),
                     "null_median": round(n.pf_2x.median(), 3)})
    return pd.DataFrame(rows)


def part2(rows: list[dict]) -> None:
    """The exposure control: same entries and exits, random side."""
    print("\n\n2. THE EXPOSURE CONTROL — same entries, same exits, RANDOM side\n")
    print("   If the ribbon reads direction, the real side must beat a coin")
    print("   flip that trades at the same times with the same long share.\n")
    print(f"  {'market':>9s} {'tf':>4s} {'trail':>6s}  {'real PF2x':>9s}  "
          f"{'random PF2x (5 seeds)':>22s}  {'time in mkt':>11s}  {'long share':>10s}")

    for sym, tf, tk in (("XAUUSD", "15m", 16.0), ("XAUUSD", "1h", 16.0),
                        ("XAUUSD", "30m", 12.0), ("XAGUSD", "1h", 12.0),
                        ("BTCUSDT", "4h", 16.0), ("ETHUSDT", "4h", 12.0),
                        ("SOLUSDT", "1h", 12.0), ("USDJPY", "1h", 8.0)):
        df = load_tf(sym, tf)
        if len(df) < 5000:
            continue
        inp = ribbon_inputs(df)
        fee, slip, mr = COSTS[sym]
        cfg = dict(mode=E.MODE_AGREE, entry_thr=1.0, require_flip=1,
                   squeeze_n=0, min_strength=0.0, trail_mode=E.TRAIL_CHAND,
                   trail_k=tk, stop_k=tk, trail_start_r=0.0, rr=0.0,
                   max_hold_bars=int(TFS[tf][1] * 7), flip_exit=0,
                   dir_mode=E.DIR_BOTH, cfg=0)
        tr = run_one(inp, cfg, fee, slip, mr)
        if tr.shape[0] < 50:
            continue
        m = metrics(tr, df.index, fee, slip)
        ei = tr[:, E.T_ENTRY_I].astype(int)
        xi = tr[:, E.T_EXIT_I].astype(int)
        tim = (xi - ei).sum() / len(df)
        share = float((tr[:, E.T_DIR] > 0).mean())

        # Random side, same entry timing, exits SIMULATED - not negated. The
        # kernel is re-run with the side forced per bar at the real long share,
        # so each control trade gets its own stop path and its own exit bar.
        pfs = []
        for seed in range(5):
            rng = np.random.default_rng(seed)
            so = np.where(rng.random(len(df)) < share, 1.0, -1.0)
            ctr = run_one(inp, cfg, fee, slip, mr, side_override=so)
            if ctr.shape[0] < 20:
                continue
            cm = metrics(ctr, df.index, fee, slip)
            pfs.append(cm["pf_2x"])
        print(f"  {sym:>9s} {tf:>4s} {tk:>6.0f}  {m['pf_2x']:>9.3f}  "
              f"{np.mean(pfs):>10.3f} +/- {np.std(pfs):<8.3f}  "
              f"{tim:>10.1%}  {share:>9.1%}")
        rows.append({"cut": f"exposure {sym} {tf}", "real_pf2x": m["pf_2x"],
                     "random_side_pf2x": round(float(np.mean(pfs)), 3),
                     "time_in_market": round(tim, 3), "long_share": round(share, 3),
                     "pf_long": m["pf_long"], "pf_short": m["pf_short"],
                     "days_to_target": m["days_to_target"]})


def main() -> int:
    df = part1()
    rows = df.to_dict("records")
    part2(rows)
    pd.DataFrame(rows).to_csv(OUT / "stage5_verdict.csv", index=False)
    print(f"\nwrote {OUT / 'stage5_verdict.csv'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
