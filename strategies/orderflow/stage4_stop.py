"""H-006 stage 4 — does a stop turn a measured edge into a tradeable one?

Stage 3 settled that the signal is real and the strategy is not: walk-forward
PF 1.050 at double cost, beating every null seed, and 28.7% of simulated
accounts killed at the LOWEST risk on the ladder. It failed on the shape of the
risk, not on the edge. Without a stop, R is a return over trailing volatility
and one loser runs the entire hold, so the book drew down 49.8R where H-002
draws 3.8R - and

    days = maxDD_in_R / R_per_day x (target / cap)

makes that the whole story.

So this asks one question and nothing else: **does bounding the loss keep enough
of the edge?** A stop cannot be a free win - it converts some winners into losses
too - and the honest test is whether profit factor at 2x cost survives while
drawdown in R collapses.

THE ASSUMPTION, stated up front. A stop needs to know what happened inside a bar.
This takes the first bar whose low (long) or high (short) breaches the level and
fills AT the level. That is optimistic; a gap through fills worse. It is the
reason this repo left stops out of H-006 and H-008 in the first place, and it is
why nothing here is believable until a matching engine has seen it.

Run: .venv/bin/python strategies/orderflow/stage4_stop.py
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

from strategies.orderflow import orderflow as of                      # noqa: E402
from strategies.orderflow.stage2_grid import FEE_BPS                  # noqa: E402
from strategies.orderflow.stage3_walkforward import vol_unit          # noqa: E402
from strategies.vwap.stage3_timeframes import null_seed               # noqa: E402

FEEDS = ROOT / "data" / "feeds"
OUT = ROOT / "backtests" / "orderflow"
SYMS = ("BTCUSDT", "ETHUSDT", "SOLUSDT")
WORKERS = 8
NSEEDS = 3

# Only the region stage 2 and 3 actually selected: crowd_z and dcrowd, tight
# entry tails, long holds. Widening it again here would be searching, not
# testing, and the question is about the stop.
SIGNALS = (("crowd_z", 0, 864), ("crowd_z", 0, 288), ("dcrowd", 48, 288),
           ("dcrowd", 144, 288))
QS = (0.02, 0.05, 0.10)
BANDS = (8640,)
HOLDS = (288, 576, 864)
STOPS = (0.0, 1.0, 1.5, 2.0, 3.0)     # 0 = no stop, the stage-3 baseline


def grid():
    for (kind, look, win), q, band, hold, sk in itertools.product(
            SIGNALS, QS, BANDS, HOLDS, STOPS):
        yield {"signal": kind, "look": look, "win": win, "q": q,
               "band": band, "hold": hold, "stop_k": sk, "contrarian": True}


def families():
    fam = {}
    for cfg in grid():
        fam.setdefault((cfg["signal"], cfg["look"], cfg["win"], cfg["q"],
                        cfg["band"]), []).append(cfg)
    return fam


_D = {}


def _init(sym):
    _D[sym] = of.load(sym, FEEDS)


def _measure(df, sig, cfg, thr, vols, span):
    t = of.run_one(df, sig, hold=cfg["hold"], q=cfg["q"], band=cfg["band"],
                   fee_bps=FEE_BPS, cost_mult=0.0, contrarian=True, thr=thr,
                   stop_k=cfg["stop_k"], vol=vols[cfg["hold"]])
    if len(t) < 30:
        return None
    ei = t[:, 0].astype(int)
    v = vols[cfg["hold"]][np.maximum(ei - 1, 0)]
    ok = np.isfinite(v) & (v > 0)
    if ok.sum() < 30:
        return None
    t, v = t[ok], v[ok]
    gross = t[:, 5]
    row = {**cfg, "trades": int(len(t)), "tpd": round(len(t) / span, 3),
           "avg_bps": round(float(gross.mean()) * 1e4, 2),
           "win_rate": round(float((gross > 0).mean()), 4),
           "avg_hold_bars": round(float((t[:, 1] - t[:, 0]).mean()), 1)}
    for c in (0.0, 1.0, 2.0, 3.0):
        r = (gross - FEE_BPS * c / 1e4) / v
        row[f"pf_{c:.0f}x"] = round(of.pf_of(r), 4)
        if c == 1.0 or c == 2.0:
            eq = np.concatenate(([0.0], np.cumsum(r)))
            row[f"maxdd_r_{c:.0f}x"] = round(
                float((eq - np.maximum.accumulate(eq)).min()), 2)
            row[f"total_r_{c:.0f}x"] = round(float(r.sum()), 1)
    return row


def _job(args):
    sym, key, cfgs, span = args
    df = _D[sym]
    kind, look, win, q, band = key
    sig = of.signal_series(df, kind, look, win)
    thr = of.thresholds(sig, q, band)
    vols = {h: vol_unit(df, h).values for h in HOLDS}
    reals, nulls = [], []
    for cfg in cfgs:
        r = _measure(df, sig, cfg, thr, vols, span)
        if r:
            reals.append({"symbol": sym, **r})
    for seed in range(NSEEDS):
        ns = of.block_shuffle(sig, null_seed(sym, kind, look, win, seed, "stop"))
        nthr = of.thresholds(ns, q, band)
        for cfg in cfgs:
            r = _measure(df, ns, cfg, nthr, vols, span)
            if r:
                nulls.append({"symbol": sym, "seed": seed, **r})
    return reals, nulls


def main():
    reals, nulls = [], []
    for sym in SYMS:
        try:
            df = of.load(sym, FEEDS)
        except FileNotFoundError:
            continue
        span = max((df.index[-1] - df.index[0]).days, 1)
        fam = families()
        print(f"\n{sym}: {sum(len(v) for v in fam.values())} configs "
              f"in {len(fam)} families", flush=True)
        t0 = time.time()
        with ProcessPoolExecutor(WORKERS, initializer=_init, initargs=(sym,)) as ex:
            for a, b in ex.map(_job, [(sym, k, v, span) for k, v in fam.items()],
                               chunksize=1):
                reals.extend(a); nulls.extend(b)
        print(f"  done in {time.time()-t0:.0f}s", flush=True)

    real = pd.DataFrame(reals)
    null = pd.DataFrame(nulls)
    real.to_csv(OUT / "stage4_real.csv", index=False)
    null.to_csv(OUT / "stage4_null.csv", index=False)

    print("\n" + "=" * 86)
    print("WHAT THE STOP DOES  (medians across every configuration)")
    print("=" * 86)
    agg = real.groupby("stop_k").agg(
        n=("pf_2x", "size"), pf_1x=("pf_1x", "median"), pf_2x=("pf_2x", "median"),
        best_2x=("pf_2x", "max"), maxdd_r=("maxdd_r_2x", "median"),
        total_r=("total_r_2x", "median"), tpd=("tpd", "median"),
        hold=("avg_hold_bars", "median"), win=("win_rate", "median"))
    print(agg.round(3).to_string())

    print("\nRETURN OVER DRAWDOWN at 2x cost — the number that sets time-to-pass")
    real["rod"] = real.total_r_2x / real.maxdd_r_2x.abs().replace(0, np.nan)
    print(real.groupby("stop_k").rod.describe()[["50%", "max"]].round(2).to_string())

    print("\nREAL vs NULL, clearing PF 1.20 at 2x")
    for k, g in real.groupby("stop_k"):
        ng = null[null.stop_k == k]
        print(f"  stop {k:>4}   real {int((g.pf_2x >= 1.2).sum()):3d}/{len(g):3d}"
              f"   null {int((ng.pf_2x >= 1.2).sum()):3d}/{len(ng):3d}")

    cols = ["symbol", "signal", "win", "q", "hold", "stop_k", "trades", "tpd",
            "win_rate", "avg_hold_bars", "pf_1x", "pf_2x", "maxdd_r_2x",
            "total_r_2x", "rod"]
    print("\nTOP 15 BY RETURN OVER DRAWDOWN at 2x cost")
    print(real[real.pf_2x >= 1.2].sort_values("rod", ascending=False)
              .head(15)[cols].to_string(index=False))
    print(f"\nwrote {OUT/'stage4_real.csv'}")


if __name__ == "__main__":
    main()
