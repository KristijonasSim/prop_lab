"""H-024 — do the entry filters read a bar that has not closed yet?

Found while writing the NautilusTrader cross-check, by reading the kernel
rather than by running it.

THE CLAIM. `engine.simulate` decides on closed bar `i` and fills at the open of
bar `i+1`, setting `entry_i = i + 1`. It then evaluates three things at
`entry_i`:

    if min_rvol > 0.0 and rvol[entry_i] < min_rvol:   ...skip
    a = atr[entry_i]                                  ...stop size, stop_mode 1
    e = ema[entry_i]                                  ...ema_regime filter

and all three are functions of bar `entry_i`'s OWN completed data:

    rvol[k] = volume[k] / mean(volume[k-1920 : k])    numerator is bar k's volume
    atr[k]  = EWMA of true range INCLUDING bar k's high/low
    ema[k]  = EWMA of close INCLUDING close[k]

At the close of bar `i` — when the order is placed — none of bar `i+1`'s
volume, range or close exists yet. `atr_rank` is the one that is correct: it is
built with an explicit `.shift(1)`.

WHY IT MATTERS MORE THAN THE OTHER TWO BUGS FOUND TODAY. The `fill_mode=0`
look-ahead touched nothing on the board, because every board configuration is
`fill_mode=1`. This one is in the `fill_mode=1` path. `min_rvol` is a live
filter in the board's most-selected BTCUSDT 4h configuration (`rvol>2.5`), and
CLAUDE.md records the paired-lift study concluding that participation filters
are "the only family that lifts it", with the lift GROWING as the threshold
rises (+0.063 at rvol>2.5 against +0.038 at rvol>1.5). A filter that reads the
entry bar's own volume would produce exactly that pattern: the tighter the
threshold, the more it selects bars that turned out to be busy, and busy bars
are the ones that moved.

THE TEST. The same configurations twice, changed in one place only: the filter
arrays are shifted forward one bar, so `rvol[entry_i]` returns bar `i`'s
reading - the last one that had actually closed when the decision was made.
Nothing else moves. If participation is a real effect the lift survives; if it
was the bug, it does not.

Run: .venv/bin/python strategies/vwap/stage16_filterlook.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from strategies.vwap.sweep import features, run_one, trade_metrics, DEFAULTS  # noqa: E402
from strategies.vwap.stage3_timeframes import load_tf, FILTERS               # noqa: E402
from strategies.vwap.stage1_grid import ASSETS                               # noqa: E402

OUT = ROOT / "backtests" / "queue"
OUT.mkdir(parents=True, exist_ok=True)

# The board's most-selected BTCUSDT 4h configuration, verbatim from
# backtests/vwap/stage10_folds.parquet.
BOARD_CFG = dict(DEFAULTS)
BOARD_CFG.update(anchor_hour=-1, anchor_minute=24, mode=2, fill_mode=1,
                 band_k=1.5, stop_mode=0, stop_k=0.5, target_mode=0, rr=0.0,
                 max_hold_bars=0, warmup_bars=2, min_risk_bps=10.0)

LEGS = [("BTCUSDT", "4h"), ("BTCUSDT", "1h"), ("BTCUSDT", "30m"),
        ("ETHUSDT", "4h"), ("ETHUSDT", "1h"), ("ETHUSDT", "30m")]
RVOLS = (0.0, 1.5, 2.0, 2.5)


def shift1(a: np.ndarray) -> np.ndarray:
    """Value from the previous bar, so index `entry_i` returns bar `entry_i-1`.

    That is the last reading which had actually closed when the order was
    placed. The first element repeats rather than becoming NaN: a NaN would
    silently disable the filter on bar 0 instead of shifting it."""
    out = np.empty_like(a)
    out[0] = a[0]
    out[1:] = a[:-1]
    return out


def main():
    rows = []
    for sym, tf in LEGS:
        try:
            df = load_tf(sym, tf)
        except Exception as e:
            print(f"{sym} {tf}: {e}")
            continue
        if len(df) < 3000:
            continue
        fee, slip, minrisk = ASSETS.get(sym, (5.0, 2.0, 10.0))
        atr, rvol, atr_rank, ema = features(df)
        # ONLY the three look-ahead arrays are shifted. atr_rank is already
        # correct in the source and is deliberately left alone.
        feats_now = (atr, rvol, atr_rank, ema)
        feats_fix = (shift1(atr), shift1(rvol), atr_rank, shift1(ema))
        span = (df.index[-1] - df.index[0]).total_seconds() / 86400.0

        for rv in RVOLS:
            cfg = dict(BOARD_CFG)
            cfg.update(min_rvol=rv, min_risk_bps=minrisk)
            out = {}
            for label, feats in (("as_is", feats_now), ("fixed", feats_fix)):
                for mult in (1, 2):
                    tr = run_one(df, feats, {}, cfg, fee * mult, slip * mult)
                    m = trade_metrics(tr, df.index, span)
                    out[f"{label}_pf_{mult}x"] = m["pf"]
                    out[f"{label}_trades"] = m["trades"]
                    out[f"{label}_totalr"] = m["total_r"]
            rows.append({"sym": sym, "tf": tf, "min_rvol": rv, **out})
            print(f"{sym:8} {tf:4} rvol>{rv:<4} "
                  f"as-is PF {out['as_is_pf_1x']:6.3f}/{out['as_is_pf_2x']:6.3f}  "
                  f"fixed PF {out['fixed_pf_1x']:6.3f}/{out['fixed_pf_2x']:6.3f}  "
                  f"trades {out['as_is_trades']:5d} -> {out['fixed_trades']:5d}")

    res = pd.DataFrame(rows)
    res.to_csv(OUT / "stage16_filterlook.csv", index=False)

    print(f"\n{'=' * 78}\nTHE PARTICIPATION LIFT, BEFORE AND AFTER THE FIX (PF at 2x cost)\n{'=' * 78}")
    base = res[res.min_rvol == 0.0].set_index(["sym", "tf"])
    print(f"{'leg':14} {'rvol':>5} {'as-is':>8} {'lift':>7} {'fixed':>8} {'lift':>7}")
    for (sym, tf), g in res.groupby(["sym", "tf"], sort=False):
        b = base.loc[(sym, tf)]
        for _, r in g[g.min_rvol > 0].iterrows():
            print(f"{sym + ' ' + tf:14} {r.min_rvol:5.1f} "
                  f"{r.as_is_pf_2x:8.3f} {r.as_is_pf_2x - b.as_is_pf_2x:+7.3f} "
                  f"{r.fixed_pf_2x:8.3f} {r.fixed_pf_2x - b.fixed_pf_2x:+7.3f}")

    f = res[res.min_rvol > 0]
    m = res[res.min_rvol == 0].set_index(["sym", "tf"])
    lift_asis = [r.as_is_pf_2x - m.loc[(r.sym, r.tf)].as_is_pf_2x for _, r in f.iterrows()]
    lift_fix = [r.fixed_pf_2x - m.loc[(r.sym, r.tf)].fixed_pf_2x for _, r in f.iterrows()]
    print(f"\nmedian participation lift, as-is : {np.median(lift_asis):+.4f}")
    print(f"median participation lift, fixed : {np.median(lift_fix):+.4f}")
    print(f"share of cells where the filter helps, as-is : "
          f"{100 * np.mean(np.array(lift_asis) > 0):.1f}%")
    print(f"share of cells where the filter helps, fixed : "
          f"{100 * np.mean(np.array(lift_fix) > 0):.1f}%")
    print(f"\nwrote {OUT / 'stage16_filterlook.csv'}")


if __name__ == "__main__":
    main()
