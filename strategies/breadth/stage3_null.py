"""H-015 stage 3 — the null, the control and the held-out half.

Stage 2 produced the first thing this session that improves H-009 on the number
that sets days-to-funded: stacking a complex-wide crowd gate on top of H-009's
per-coin one takes return-over-drawdown from 29.97 to 42.53, with max drawdown
nearly halved. That is also exactly the point at which this project has been
wrong before. H-004 had the widest stage-1 null margin in the repo - 828
gate-clearing configurations against 2 - and died the moment anything had to be
chosen blind.

Three reasons to disbelieve stage 2, each tested here:

  1. IT WAS A SEARCH. Six gates x two placements, and the winner was picked
     after seeing all of them. `dsys_144` won at +41.9% while `dsys_12` and
     `dsys_48` as replacement gates were NEGATIVE, and there is no prior that
     says 12 hours rather than 4. So: the same gate driven by a BLOCK-SHUFFLED
     feed, five seeds, read as a distribution. If shuffled feeds also lift
     return-over-drawdown, the lift is the search and not the signal.
  2. THE DIRECTION MIGHT NOT MATTER. If keeping the trades the complex AGREES
     with helps too, the gate is selecting calm periods, not informed ones.
  3. IT MIGHT NOT PERSIST. The feature was chosen on the whole window, so the
     window is split and the second half is measured with the choice held.

Run: .venv/bin/python strategies/breadth/stage3_null.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from strategies.breadth import breadth as br                   # noqa: E402
from strategies.breadth.stage2_gate import asof, stats         # noqa: E402
from strategies.orderflow import orderflow as of               # noqa: E402
from strategies.vwap.stage3_timeframes import null_seed        # noqa: E402

FEEDS = ROOT / "data" / "feeds"
OUT = ROOT / "backtests" / "breadth"
TRADES = ROOT / "backtests" / "gated_vwap" / "stage6_trades.parquet"
NSEEDS = 5
GATES = ("sys", "dsys_144")


def apply_gate(t, v, invert=False):
    d = t.direction.values
    keep = np.where(d > 0, v < 0, v > 0)
    if invert:
        keep = ~keep
    keep = np.where(np.isnan(v), True, keep)
    return t[keep]


def line(label, s, base=None):
    if s is None:
        print(f"  {label:36s}  (too few trades)")
        return None
    m = ""
    if base is not None and base["ret_dd"] > 0:
        m = f"   {(s['ret_dd'] - base['ret_dd']) / base['ret_dd'] * 100:+6.1f}%"
    print(f"  {label:36s} n={s['trades']:5d}  PF2x {s['pf_2x']:.3f}  "
          f"maxDD {s['maxdd_r']:7.2f}R  R/day {s['r_per_day']:.4f}  "
          f"ret/DD {s['ret_dd']:6.2f}{m}")
    return s


def main():
    t = pd.read_parquet(TRADES)
    t["entry_ts"] = pd.to_datetime(t.entry_ts, utc=True)
    t["exit_ts"] = pd.to_datetime(t.exit_ts, utc=True)
    pan = br.panel(FEEDS)
    sysdf = br.systemic(pan)
    first = sysdf["sys"].dropna().index[0]
    t = t[t.entry_ts >= first].copy()
    tg = t[t.gated].copy()                     # H-009's book, common window
    base = stats(tg)
    print(f"common window {first:%Y-%m-%d} -> {t.exit_ts.max():%Y-%m-%d}")
    line("H-009 as it stands", base)

    for g in GATES:
        print(f"\n{'=' * 86}\nGATE = {g}\n{'=' * 86}")
        v = asof(sysdf[g], tg.entry_ts)
        real = line(f"H-009 + {g}", stats(apply_gate(tg, v)), base)
        line(f"  control: keep what it AGREES with", stats(apply_gate(tg, v, True)), base)

        print(f"  --- null: the same gate on a block-shuffled feed, {NSEEDS} seeds ---")
        nulls = []
        for s in range(NSEEDS):
            ns = of.block_shuffle(sysdf[g], null_seed("h015", g, s), block=288)
            nv = asof(ns, tg.entry_ts)
            st = stats(apply_gate(tg, nv))
            if st:
                nulls.append(st["ret_dd"])
                print(f"      seed {s}: n={st['trades']:5d}  PF2x {st['pf_2x']:.3f}  "
                      f"maxDD {st['maxdd_r']:7.2f}R  ret/DD {st['ret_dd']:6.2f}")
        if nulls and real:
            best = max(nulls)
            verdict = "BEATS every seed" if real["ret_dd"] > best else "LOSES to the null"
            print(f"      real {real['ret_dd']:.2f} vs null median "
                  f"{np.median(nulls):.2f}, null best {best:.2f}  ->  {verdict}")

        print("  --- held out: feature chosen on the whole window, so split it ---")
        mid = tg.entry_ts.quantile(0.5)
        for lbl, sub in (("first half", tg[tg.entry_ts < mid]),
                         ("second half", tg[tg.entry_ts >= mid])):
            b = stats(sub)
            vv = asof(sysdf[g], sub.entry_ts)
            line(f"    {lbl}: H-009", b)
            line(f"    {lbl}: H-009 + {g}", stats(apply_gate(sub, vv)), b)


if __name__ == "__main__":
    main()
