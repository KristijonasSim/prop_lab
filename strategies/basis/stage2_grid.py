"""H-013 stage 2 — does the perp-cash gap survive being turned into trades?

Deliberately the same shape as `strategies/orderflow/stage2_grid.py`: the same
kernel, the same cost multiples, the same block-shuffle null, the same gate. The
whole claim of this hypothesis is that it measures something H-006 does not, and
that only means anything if the two grids are read off the same ruler.

Stage 1 said, on six years and three coins:

  * prem_z beat its block-shuffle null in 15 of 15 cells and held its sign in
    ~90% of calendar years - a cleaner record than any H-006 feature.
  * the tail edge on BTC rises monotonically with BOTH tail depth and horizon,
    5.0bps at the 20% tail / 4h to 51.4bps at the 5% tail / 48h. A mechanism
    looks like that; H-008's flat z-response is what its absence looks like.
  * it correlates |0.05-0.16| with H-009's crowd feed, so it is not a
    re-measurement of the signal already in the best book.

What stage 1 could NOT say is whether any of that survives a round trip, a
trailing threshold instead of a full-sample one, and a control. That is here.

The control matters more than usual. `contrarian=False` takes every setup the
other way; if going WITH the dislocation pays too, then the premium is picking
volatile bars rather than informative ones and the mechanism story is wrong.

Run: .venv/bin/python strategies/basis/stage2_grid.py
"""
from __future__ import annotations

import itertools
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from concurrent.futures import ProcessPoolExecutor

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from strategies.basis import basis as bs                          # noqa: E402
from strategies.orderflow import orderflow as of                  # noqa: E402
from strategies.orderflow.stage2_grid import vol_unit             # noqa: E402
from strategies.vwap.stage3_timeframes import null_seed           # noqa: E402

FEEDS = ROOT / "data" / "feeds"
OUT = ROOT / "backtests" / "basis"
OUT.mkdir(parents=True, exist_ok=True)

SYMS = ("BTCUSDT", "ETHUSDT", "SOLUSDT")
FEE_BPS = bs.ROUND_TRIP_BPS
COSTS = (0.0, 1.0, 2.0, 3.0)
NSEEDS = 3
GATE = 1.20
WORKERS = 8

LOOKS = (12, 48, 144)                # 1h, 4h, 12h   (dprem / lead / gap)
WINS = (288, 864)                    # z baseline: 1 day, 3 days (prem_z)
QS = (0.02, 0.05, 0.10, 0.20)
BANDS = (2016, 8640)                 # trailing quantile window: 7d, 30d
# 8h, 24h, 48h, 72h. The first pass put EVERY top configuration at hold=864,
# the boundary, and median PF at 2x rose monotonically across the whole column
# (0.720 / 0.840 / 0.881 / 0.913) - the signature of a grid that is cutting off
# the region where the edge lives rather than bracketing it. So `--long`
# extends it outward ONCE and in ONE direction only, to 6, 10 and 14 days.
# Fourteen days is not arbitrary: it is the phase constraint in CLAUDE.md, so a
# hold beyond it could not be traded here even if it scored.
HOLDS = (96, 288, 576, 864)
HOLDS_LONG = (864, 1728, 2880, 4032)     # 72h, 6d, 10d, 14d
STOPS = (0.0, 2.0)                   # sigmas of trailing hold-vol; 0 = no stop


def grid():
    for sig in bs.SIGNALS:
        looks = LOOKS if sig != "prem_z" else (0,)
        wins = WINS if sig == "prem_z" else (0,)
        for look, win, q, band, hold, contra, stop in itertools.product(
                looks, wins, QS, BANDS, HOLDS, (True, False), STOPS):
            yield {"signal": sig, "look": look, "win": win, "q": q,
                   "band": band, "hold": hold, "contrarian": contra,
                   "stop_k": stop}


def families():
    """Configs sharing a signal and its trailing thresholds, so the rolling
    quantile - which is where the time goes - is computed once per family."""
    fam = {}
    for cfg in grid():
        fam.setdefault((cfg["signal"], cfg["look"], cfg["win"],
                        cfg["q"], cfg["band"]), []).append(cfg)
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


def _init(sym):
    _DF["df"] = bs.load(sym, FEEDS)
    _DF["sym"] = sym
    _DF["span"] = max((_DF["df"].index[-1] - _DF["df"].index[0]).days, 1)
    _DF["vols"] = {h: vol_unit(_DF["df"], h).values for h in HOLDS}


def _job(args):
    key, cfgs = args
    df, span, vols = _DF["df"], _DF["span"], _DF["vols"]
    sig_name, look, win, q, band = key
    sig = bs.signal_series(df, sig_name, look, win)
    thr = of.thresholds(sig, q, band)
    rows = []
    for cfg in cfgs:
        r = evaluate(df, sig, cfg, span, thr, vols)
        if not r:
            continue
        r["symbol"] = _DF["sym"]
        r["kind"] = "real"
        rows.append(r)
    for s in range(NSEEDS):
        ns = of.block_shuffle(sig, null_seed(_DF["sym"], sig_name, look, win, s, "h013"))
        nthr = of.thresholds(ns, q, band)
        for cfg in cfgs:
            r = evaluate(df, ns, cfg, span, nthr, vols)
            if not r:
                continue
            r["symbol"] = _DF["sym"]
            r["kind"] = f"shuffled_s{s}"
            rows.append(r)
    return rows


def main():
    global HOLDS
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    long = "--long" in sys.argv
    if long:
        HOLDS = HOLDS_LONG
    syms = args or list(SYMS)
    fam = families()
    print(f"H-013 stage 2: {sum(len(v) for v in fam.values())} configs x "
          f"{len(syms)} symbols x (1 real + {NSEEDS} null)", flush=True)
    allrows = []
    for sym in syms:
        print(f"\n{sym}: {len(fam)} families ...", flush=True)
        with ProcessPoolExecutor(WORKERS, initializer=_init,
                                 initargs=(sym,)) as ex:
            for i, rows in enumerate(ex.map(_job, fam.items(), chunksize=1), 1):
                allrows.extend(rows)
                if i % 10 == 0:
                    print(f"  {sym}: {i}/{len(fam)} families", flush=True)
    res = pd.DataFrame(allrows)
    res.to_csv(OUT / ("stage2_grid_long.csv" if long else "stage2_grid.csv"),
               index=False)

    real = res[res.kind == "real"]
    null = res[res.kind != "real"]
    con = real[real.contrarian]
    nco = null[null.contrarian]

    print("\n" + "=" * 92)
    print("GATE COUNTS — configs clearing PF 1.20, contrarian only")
    print("=" * 92)
    for c in (1.0, 2.0, 3.0):
        col = f"pf_{c:.0f}x"
        nper = (nco[col] >= GATE).sum() / max(NSEEDS, 1)
        print(f"  {c:.0f}x cost:  real {int((con[col] >= GATE).sum()):5d} of "
              f"{len(con):5d}    null {nper:8.1f} per seed    "
              f"real best {con[col].max():.3f}  null best {nco[col].max():.3f}")

    print("\nTHE CONTROL — same setups taken the other way (median PF at 2x)")
    print(f"  contrarian  {real[real.contrarian].pf_2x.median():.4f}")
    print(f"  with-trend  {real[~real.contrarian].pf_2x.median():.4f}")

    print("\nBY SIGNAL (contrarian, median PF at 2x, and gate count)")
    g = (con.groupby("signal")
            .agg(median_pf2x=("pf_2x", "median"), best_pf2x=("pf_2x", "max"),
                 clears=("pf_2x", lambda s: int((s >= GATE).sum())),
                 n=("pf_2x", "size"), median_tpd=("tpd", "median")))
    print(g.round(4).to_string())

    print("\nBY HOLD (contrarian, median PF at 2x)")
    print(con.groupby("hold").pf_2x.median().round(4).to_string())

    print("\nTOP 20 BY PF AT 2x COST (contrarian, >= 200 trades)")
    top = con[con.trades >= 200].sort_values("pf_2x", ascending=False).head(20)
    print(top[["symbol", "signal", "look", "win", "q", "band", "hold", "stop_k",
               "trades", "tpd", "avg_bps", "win_rate", "pf_1x", "pf_2x",
               "pf_3x"]].to_string(index=False))
    print(f"\nwrote {'stage2_grid_long' if long else 'stage2_grid'}.csv in {OUT}")


if __name__ == "__main__":
    main()
