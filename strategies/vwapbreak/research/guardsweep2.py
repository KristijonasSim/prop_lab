"""H-043 - is the -0.50% guard a curve or one lucky cell? Pre-reg: GUARDSWEEP2.md.

H-042 measured sixteen cells and exactly one beat its own matched-drop null on
both timeframes: the -0.50% guard, which is NOT the arm H-041 nominated. Its
looser neighbour is flat on 4h, and nothing TIGHTER than -0.50% has ever been
run - so the cliff has only ever been seen from one side.

This sweeps the other side. Same cells, same fixed 3% rung, same matched-drop
null, arms down to -0.15%. THE KILL CRITERION IS CONDITION 1: if -0.50% stands
alone between flat neighbours on both sides it is one cell in sixteen clearing a
10th-percentile null, which twenty-eight cells produce 2.8 of by construction.

NEW HERE: the half-sample split. The advantage is measured separately on the
first and second half of the calendar, because an effect that lives entirely in
one half is the failure mode that cleared thirty quarters of BTC 30m and then
lost money from 2024.

Run: .venv/bin/python strategies/vwapbreak/research/guardsweep2.py
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from core.run_hypothesis import run_market, window                   # noqa: E402
from strategies.vwapbreak.strategy import STRATEGY                   # noqa: E402

_spec = importlib.util.spec_from_file_location(
    "guardsweep", Path(__file__).with_name("guardsweep.py"))
_gs = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_gs)

apply_guard, daily, day_grid = _gs.apply_guard, _gs.daily, _gs.day_grid
stats, bands, drops_per_day, null_blowups = (_gs.stats, _gs.bands,
                                             _gs.drops_per_day, _gs.null_blowups)
FIXED_RISK, CELLS, tag = _gs.FIXED_RISK, _gs.CELLS, _gs.tag

#: Tighter than anything ever swept. -0.15% at 3% risk stops the day after about
#: a twentieth of a stop-out - deliberately past where a mechanism is plausible,
#: because a curve that keeps improving into the absurd says size is doing the
#: work, not timing.
GUARDS = (None, 0.0015, 0.0025, 0.0035, 0.0050, 0.0065, 0.0075)


def half_blowups(tr: pd.DataFrame, grid: pd.DatetimeIndex) -> tuple:
    """Blow-up rate on the first and second half of the CALENDAR, not of the
    trades. Both arms are cut at the same date and accounts spanning the cut are
    truncated identically, so the two halves are comparable to each other and to
    the same half of any other arm - never to the full-sample number."""
    cut = len(grid) // 2
    out = []
    for lo, hi in ((0, cut), (cut, len(grid))):
        g = grid[lo:hi]
        s = stats(daily(tr, g).reindex(g, fill_value=0.0), FIXED_RISK)
        out.append(None if not s else s["blown_pct"])
    return tuple(out)


def main() -> int:
    span = window(["XAUUSD"], ["1h", "4h"])
    out: dict[str, dict] = {}
    for sym, tf in CELLS:
        res = run_market(STRATEGY, sym, tf,
                         pipe_kw={"floors": (30,), "topn": (5,)},
                         null_seeds=0, span=span)
        tr = res["_trades"].copy()
        tr["entry_ts"] = pd.to_datetime(tr.entry_ts, utc=True)
        tr["exit_ts"] = pd.to_datetime(tr.exit_ts, utc=True)
        tr = tr.sort_values("entry_ts").reset_index(drop=True)
        grid = day_grid(tr)
        print(f"\n=== {sym} {tf}  ({len(tr)} blind trades, {len(grid)} days, "
              f"every arm at {FIXED_RISK*100:.2f}% risk) " + "=" * 10, flush=True)
        hdr = (f"{'guard':>8}{'trades':>8}{'tpd':>6}{'days':>7}{'pass%':>7}"
               f"{'blown%':>8}{'band':>13}{'null blown%':>15}"
               f"{'1st half':>10}{'2nd half':>10}{'failMax%':>10}{'failDay%':>10}")
        print(hdr); print("-" * len(hdr), flush=True)
        for g in GUARDS:
            kept = apply_guard(tr, FIXED_RISK, g)
            d = daily(kept, grid)
            s = stats(d, FIXED_RISK)
            if not s:
                print(f"{tag(g):>8}   no passing account", flush=True); continue
            s |= bands(d, FIXED_RISK)
            s["trades"] = len(kept)
            s["tpd"] = round(len(kept) / len(grid), 2)
            h1, h2 = half_blowups(kept, grid)
            s["blown_h1"], s["blown_h2"] = h1, h2
            if g is not None:
                s |= null_blowups(tr, drops_per_day(tr, kept), grid, FIXED_RISK)
            out[f"{sym}|{tf}|{tag(g)}"] = s
            nb = ("" if g is None else
                  f"{s['null_blown_med']:.1f} [{s['null_blown_lo']:.1f}-{s['null_blown_hi']:.1f}]")
            print(f"{tag(g):>8}{s['trades']:>8}{s['tpd']:>6.2f}{s['days']:>7.1f}"
                  f"{s['pass_pct']:>7.1f}{s['blown_pct']:>8.1f}"
                  f"{('%.1f-%.1f' % (s['blown_lo'], s['blown_hi'])):>13}{nb:>15}"
                  f"{(h1 if h1 is not None else float('nan')):>10.1f}"
                  f"{(h2 if h2 is not None else float('nan')):>10.1f}"
                  f"{s['fail_max_pct']:>10.1f}{s['fail_daily_pct']:>10.1f}",
                  flush=True)

    dest = ROOT / "backtests" / "vwapbreak" / "guardsweep2.json"
    dest.write_text(json.dumps({"guards": list(GUARDS), "fixed_risk": FIXED_RISK,
                                "rows": out}, indent=1, default=str))
    print(f"\nwrote {dest.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
