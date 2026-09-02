"""H-006 stage 2 — the grid, and the control that matters.

Stage 1 said the crowd-positioning feed ranks forward returns monotonically over
8 to 24 hours, negatively, and that the top-minus-bottom spread is worth more
than a double-cost round trip. This turns that into trades and prices them.

WHAT IS BEING TESTED, and what is deliberately NOT:

  * entries come from trailing quantiles of the signal, never full-sample ones.
    Stage 1 cut its buckets on the whole sample, which answers "does this rank
    returns" and does not answer "could it have been traded".
  * exits are FIXED HOLD only. A stop needs an intrabar ordering assumption and
    this repo has been burned by a fill assumption once already.
  * every configuration is run BOTH ways - fading the crowd and following it.
    This is the control. If following the crowd pays about as well as fading it,
    then the entry filter is picking volatile bars rather than informative ones
    and the mechanism story is wrong.
  * the null block-shuffles the SIGNAL against untouched prices, five
    deterministic seeds, read as a distribution.

Reported at 0x, 1x, 2x and 3x cost. The 0x column is the diagnostic one: it says
whether there is any edge at all before the spread is paid, which is how H-001
was put down and how H-007 was correctly diagnosed as cost-limited rather than
signal-free.

Run: .venv/bin/python strategies/orderflow/stage2_grid.py [SYMBOLS...]
"""
from __future__ import annotations

import itertools
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from strategies.orderflow import orderflow as of                 # noqa: E402
from strategies.vwap.stage3_timeframes import null_seed          # noqa: E402


def vol_unit(df, hold, win=288, floor_bps=10.0):
    """Trailing volatility of `hold`-bar returns, shifted - the unit the stop is
    measured in and the same one stage 3 divides by to get R."""
    lr = np.log(df.close).diff(hold)
    v = lr.rolling(win, min_periods=win // 2).std().shift(1)
    return v.clip(lower=floor_bps / 1e4)

FEEDS = ROOT / "data" / "feeds"
OUT = ROOT / "backtests" / "orderflow"
OUT.mkdir(parents=True, exist_ok=True)

SYMS = ("BTCUSDT", "ETHUSDT", "SOLUSDT")
FEE_BPS = of.ROUND_TRIP_BPS          # 14bps round trip at 1x
COSTS = (0.0, 1.0, 2.0, 3.0)
NSEEDS = 3          # per config across the whole grid; the walk-forward uses 5
GATE = 1.20
# 12, not one per core. Each worker holds its own copy of a 630k-row frame and
# the rolling quantiles over a 30-day window are not cheap; at 24 workers this
# box went to swap and the run died without writing anything.
WORKERS = 8

LOOKS = (12, 48, 144)                # 1h, 4h, 12h  (dcrowd only)
WINS = (288, 864)                    # z baseline: 1 day, 3 days
# The first pass put every one of its best configurations at the EDGE of this
# grid - q = 0.05 and a 24h hold, both the extreme end of what was tried - which
# means the grid was cutting off the region where the edge lives rather than
# bracketing it. Extended outward once, deliberately and in one direction only.
QS = (0.02, 0.05, 0.10, 0.20, 0.30)  # how far into the tail an entry needs
BANDS = (2016, 8640)                 # trailing quantile window: 7d, 30d
HOLDS = (96, 144, 288, 576, 864)     # 8h, 12h, 24h, 48h, 72h
# Stage 4 showed a stop is what this hypothesis was missing - wider is better,
# median PF at 2x 1.042 with none against 1.079 at 3 sigma, and return over
# drawdown 0.31 against 0.90 - but stage 3 walk-forwarded the NO-STOP version and
# that is the record the board has been scoring. So the stop is a dimension the
# fold selector can choose blind, like every other one, rather than a separate
# in-sample study nobody folded back in.
# TESTED AND REVERTED, 2026-09-02. Stage 4 showed a stop helps IN SAMPLE, and it
# does not survive blind selection. With the stop available the walk-forward book
# went PF@2x 1.050 -> 1.007 ranking folds on profit factor, and 1.050 -> 0.990
# with a drawdown-aware selector, while max drawdown went 49.8R -> 57.1R and
# return over drawdown 1.69 -> 1.02. Four times as many configurations is four
# times as many chances to fit the training quarter, and that is mostly what the
# extra dimension bought. Left as one value so the board record stays
# reproducible; the tuple is kept so the test can be repeated, not rerun.
STOPS = (0.0,)                       # sigmas beyond entry; 0 = no stop


def grid():
    for kind in of.SIGNALS:
        looks = LOOKS if kind == "dcrowd" else (0,)
        wins = (288,) if kind == "dcrowd" else WINS
        for look, win, q, band, hold, contra, stop in itertools.product(
                looks, wins, QS, BANDS, HOLDS, (True, False), STOPS):
            yield {"signal": kind, "look": look, "win": win, "q": q,
                   "band": band, "hold": hold, "contrarian": contra,
                   "stop_k": stop}


def families():
    """Configurations grouped by what they share.

    Everything inside a family uses the same signal and the same trailing
    quantile thresholds, and differs only in hold and direction - so the
    expensive part is computed once per family instead of once per
    configuration. That is a 10x saving here, and without it the grid does not
    fit in this box's memory."""
    fam = {}
    for cfg in grid():
        key = (cfg["signal"], cfg["look"], cfg["win"], cfg["q"], cfg["band"])
        fam.setdefault(key, []).append(cfg)
    return fam


def evaluate(df, sig, cfg, span_days, thr=None, vols=None) -> dict:
    row = {**cfg}
    base = of.run_one(df, sig, hold=cfg["hold"], q=cfg["q"], band=cfg["band"],
                      fee_bps=FEE_BPS, cost_mult=0.0,
                      contrarian=cfg["contrarian"], thr=thr,
                      stop_k=cfg.get("stop_k", 0.0),
                      vol=None if vols is None else vols[cfg["hold"]])
    if len(base) < 30:
        return {}
    gross = base[:, 5]
    row["trades"] = int(len(base))
    row["tpd"] = round(len(base) / span_days, 3)
    row["avg_bps"] = round(float(gross.mean()) * 1e4, 2)
    row["win_rate"] = round(float((gross > 0).mean()), 4)
    for c in COSTS:
        r = gross - (FEE_BPS * c / 1e4)
        row[f"pf_{c:.0f}x"] = round(of.pf_of(r), 4)
        row[f"tot_{c:.0f}x"] = round(float(r.sum()) * 1e4, 1)
    return row


_DF = {}


def _init(sym, path):
    """Each worker loads the market once; the frames are large and passing them
    per task would cost more than the backtest does."""
    _DF[sym] = of.load(sym, path)


def _job(args):
    """One family: build the signal and its thresholds once, then price every
    hold and both directions against them, real and null."""
    sym, key, cfgs, span = args
    df = _DF[sym]
    kind, look, win, q, band = key
    sig = of.signal_series(df, kind, look, win)
    thr = of.thresholds(sig, q, band)
    vols = {h: vol_unit(df, h).values for h in HOLDS}
    reals, nulls = [], []
    for cfg in cfgs:
        r = evaluate(df, sig, cfg, span, thr, vols)
        if r:
            reals.append({"symbol": sym, **r})
    for seed in range(NSEEDS):
        ns = of.block_shuffle(sig, null_seed(sym, kind, look, win, seed))
        nthr = of.thresholds(ns, q, band)
        for cfg in cfgs:
            nr = evaluate(df, ns, cfg, span, nthr, vols)
            if nr:
                nulls.append({"symbol": sym, "seed": seed, **nr})
    return reals, nulls


def main():
    syms = sys.argv[1:] or list(SYMS)
    all_rows, null_rows = [], []
    for sym in syms:
        try:
            df = of.load(sym, FEEDS)
        except FileNotFoundError:
            print(f"{sym}: no feed on disk - run core/binance_metrics.py")
            continue
        span = max((df.index[-1] - df.index[0]).days, 1)
        fam = families()
        print(f"\n{sym}: {len(df):,} bars over {span} days, "
              f"{sum(len(v) for v in fam.values())} configs in {len(fam)} families "
              f"x {NSEEDS} null seeds", flush=True)
        t0 = time.time()
        tasks = [(sym, k, v, span) for k, v in fam.items()]
        with ProcessPoolExecutor(WORKERS, initializer=_init,
                                 initargs=(sym, FEEDS)) as ex:
            for k, (reals, nulls) in enumerate(ex.map(_job, tasks, chunksize=1)):
                all_rows.extend(reals)
                null_rows.extend(nulls)
                if (k + 1) % 10 == 0:
                    print(f"  {k+1}/{len(tasks)} families  "
                          f"[{time.time()-t0:.0f}s]", flush=True)
        print(f"  {sym} done in {time.time()-t0:.0f}s", flush=True)

    if not all_rows:
        print("nothing ran")
        return
    real = pd.DataFrame(all_rows)
    null = pd.DataFrame(null_rows)
    real.to_csv(OUT / "stage2_real.csv", index=False)
    null.to_csv(OUT / "stage2_null.csv", index=False)

    print("\n" + "=" * 78)
    print("REAL vs NULL — the whole grid")
    print("=" * 78)
    for c in COSTS:
        k = f"pf_{c:.0f}x"
        rc, nc = real[k].dropna(), null[k].dropna()
        print(f"  cost {c:.0f}x   real median {rc.median():.3f}  >1.0 {(rc>1).mean():6.1%}"
              f"  clears {GATE} {int((rc>=GATE).sum()):5d}"
              f"   |   null median {nc.median():.3f}  >1.0 {(nc>1).mean():6.1%}"
              f"  clears {GATE} {int((nc>=GATE).sum()):5d}")

    print("\nTHE CONTROL — fading the crowd vs following it (PF at 2x cost)")
    for contra, g in real.groupby("contrarian"):
        lab = "fade the crowd" if contra else "follow the crowd"
        print(f"  {lab:18s} median {g.pf_2x.median():.3f}  "
              f">1.0 {(g.pf_2x>1).mean():6.1%}  best {g.pf_2x.max():.3f}  "
              f"mean bps/trade {g.avg_bps.mean():+.2f}")

    print("\nBY SIGNAL (PF at 2x cost, contrarian only)")
    con = real[real.contrarian]
    print(con.groupby("signal").pf_2x.describe()[["count", "50%", "max"]].round(3).to_string())

    print("\nBY HOLD (PF at 2x cost, contrarian only)")
    print(con.groupby("hold").agg(n=("pf_2x", "size"), median=("pf_2x", "median"),
                                  best=("pf_2x", "max"),
                                  tpd=("tpd", "median")).round(3).to_string())

    print("\nTOP 15 BY PF AT 2x COST (contrarian only)")
    cols = ["symbol", "signal", "look", "win", "q", "band", "hold", "trades",
            "tpd", "avg_bps", "win_rate", "pf_0x", "pf_1x", "pf_2x", "pf_3x"]
    print(con.sort_values("pf_2x", ascending=False).head(15)[cols].to_string(index=False))
    print(f"\nwrote {OUT/'stage2_real.csv'} and {OUT/'stage2_null.csv'}")


if __name__ == "__main__":
    main()
