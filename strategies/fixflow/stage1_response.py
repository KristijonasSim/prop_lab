"""H-046 stage 1 - is there anything at the 16:00 London fix? No strategy, no fit.

READ `PREREG.md` FIRST. Every parameter here was fixed before this file ran.

THE TEST. For one anchor hour, one market: measure the drift into the fix, and
the return after it. Bucket the after by the before. If dealers hedging a
concentrated, price-insensitive order push price and then let it go, the bottom
quintile of pre-drift must be followed by a positive return and the top quintile
by a negative one, and the spread has to be bigger than what it costs to trade.

THREE CONTROLS, all of them in this one file, because a spread on its own is not
evidence of anything:

  * the null PERMUTES the pre-drift across days at the SAME clock slot, so the
    hour, the session and the intraday volatility shape are all held. H-038's
    LESSON 2 is that a shifted-event null compares an hour-concentrated event
    against a population drawn from every hour, which gifts it about 5bps.
  * BTCUSDT has no benchmark fix and is the control MARKET.
  * the same test runs at all 24 London hours, which is the control CLOCK and
    also prices the search: 24 anchors x 6 markets at a 95th percentile expect
    7.2 false passes.

Run:  .venv/bin/python strategies/fixflow/stage1_response.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from core.markets import COSTS, EXEC_MODE, load                 # noqa: E402
from core.run_hypothesis import window                          # noqa: E402
from core.universe import STANDARD                              # noqa: E402

OUT = ROOT / "backtests" / "fixflow"

#: The anchor under test, and the 23 placebo clocks it must stand out from.
FIX_HOUR = 16                      # Europe/London, DST-aware
HOURS = list(range(24))
#: Exits, in minutes after the entry bar opens.
HORIZONS = (30, 60, 120)
PRIMARY_H = 60
#: Markets that carry the mechanism. BTCUSDT is the control and is excluded from
#: every pooled number by construction, not by result.
FIX_MARKETS = ["XAUUSD", "XAGUSD", "EURUSD", "GBPUSD", "USDJPY"]
CONTROL = "BTCUSDT"
#: 5m everywhere it exists. There is no crypto cache finer than 15m.
TF = {s: "5m" for s in FIX_MARKETS} | {CONTROL: "15m"}
BAR_MIN = {s: 5 for s in FIX_MARKETS} | {CONTROL: 15}
N_NULL = 500
NQ = 5


def round_trip(sym: str) -> float:
    """Round trip in bps at 1x, the way the kernels charge it."""
    return COSTS[sym].round_trip(EXEC_MODE)


def events(df: pd.DataFrame, hour: int, bar_min: int) -> pd.DataFrame:
    """One row per day: the drift into the anchor and the return after it.

    Timing is the kernel contract's, not a convenience. The signal is the CLOSE
    of the bar that ends `hour:05` London; the entry is the OPEN of the bar after
    it; every exit is the OPEN of a later bar. Nothing reads a bar it could not
    have seen.
    """
    step = pd.Timedelta(minutes=bar_min)
    days = pd.DatetimeIndex(df.index.tz_convert("Europe/London").normalize().unique())
    local = pd.DatetimeIndex([d.replace(hour=hour) for d in days])
    sig = local.tz_convert("UTC")                    # bar label, covers hour:00-:05

    o, c, v = df.open, df.close, df.volume

    def at(idx, s):
        return s.reindex(idx).to_numpy(dtype=float)

    pre_lab = sig - pd.Timedelta(minutes=60)
    ent_lab = sig + step
    rows = {"sig": sig,
            "pre": at(sig, c) / at(pre_lab, c) - 1.0,
            "entry": at(ent_lab, o)}
    live = (at(pre_lab, v) > 0) & (at(sig, v) > 0) & (at(ent_lab, v) > 0)
    for h in HORIZONS:
        ex_lab = ent_lab + pd.Timedelta(minutes=h)
        px = at(ex_lab, o)
        rows[f"post{h}"] = px / rows["entry"] - 1.0
        live &= at(ex_lab, v) > 0
    e = pd.DataFrame(rows)
    e["live"] = live
    return e[e.live & np.isfinite(e.pre) & np.isfinite(e.entry)].drop(columns="live")


def spread(pre: np.ndarray, post: np.ndarray, nq: int = NQ) -> float:
    """Bottom-quintile minus top-quintile forward return, in bps.

    Positive means the drift FADES: the days that fell into the fix rise after
    it. This is the quantity the hypothesis is about.
    """
    if len(pre) < nq * 10:
        return float("nan")
    q = pd.qcut(pd.Series(pre).rank(method="first"), nq, labels=False)
    lo, hi = post[q == 0], post[q == nq - 1]
    return float(lo.mean() - hi.mean()) * 1e4


def null_spreads(pre: np.ndarray, post: np.ndarray, seeds: int = N_NULL) -> np.ndarray:
    """The same statistic with the pre-drift permuted ACROSS DAYS, hour held."""
    rng = np.random.default_rng(20260915)
    out = np.empty(seeds)
    for i in range(seeds):
        out[i] = spread(rng.permutation(pre), post)
    return out


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    syms = list(FIX_MARKETS) + [CONTROL]
    t0, t1 = window(syms, ["1h"])
    print(f"window {t0.date()} -> {t1.date()}\n")

    bars = {}
    for s in syms:
        d = load(s, TF[s])
        bars[s] = d[(d.index >= t0) & (d.index <= t1)]
        print(f"{s:8s} {TF[s]:4s} {len(bars[s]):7d} bars "
              f"{bars[s].index[0].date()} -> {bars[s].index[-1].date()}  "
              f"round trip {round_trip(s):.2f}bps")

    rec: dict = {"window": [str(t0.date()), str(t1.date())],
                 "fix_hour": FIX_HOUR, "horizons": list(HORIZONS),
                 "n_null": N_NULL, "markets": {}, "clock": {}}

    # ---- the anchor under test, per market, with its own null -------------
    print(f"\n=== ANCHOR {FIX_HOUR:02d}:00 London, h={PRIMARY_H}m "
          f"(criterion 1: edge = spread/2 must beat the 2x round trip) ===")
    print(f"{'market':9s}{'n':>6s}{'spread':>9s}{'edge':>8s}{'RT@2x':>8s}"
          f"{'edge/RT':>9s}{'p':>8s}   pass")
    for s in syms:
        e = events(bars[s], FIX_HOUR, BAR_MIN[s])
        m = {"n": int(len(e)), "tf": TF[s], "rt_1x": round(round_trip(s), 4)}
        for h in HORIZONS:
            sp = spread(e.pre.to_numpy(), e[f"post{h}"].to_numpy())
            m[f"spread_{h}"] = round(sp, 3)
        sp = m[f"spread_{PRIMARY_H}"]
        nulls = null_spreads(e.pre.to_numpy(), e[f"post{PRIMARY_H}"].to_numpy())
        p = float((nulls >= sp).mean())
        rt2 = 2.0 * round_trip(s)
        edge = sp / 2.0
        m |= {"edge_60": round(edge, 3), "rt_2x": round(rt2, 3),
              "edge_over_rt2x": round(edge / rt2, 3), "p_null": p,
              "null_p95": round(float(np.percentile(nulls, 95)), 3),
              "passes_c1": bool(edge > rt2)}
        rec["markets"][s] = m
        tag = "CONTROL" if s == CONTROL else ""
        print(f"{s:9s}{m['n']:6d}{sp:9.2f}{edge:8.2f}{rt2:8.2f}"
              f"{edge / rt2:9.2f}{p:8.3f}   {'YES' if m['passes_c1'] else 'no':4s}{tag}")

    # ---- the clock control: the same test at all 24 London hours ----------
    print(f"\n=== ALL 24 LONDON HOURS, pooled over the 5 fix markets, h={PRIMARY_H}m ===")
    print("pooled statistic = mean over markets of (spread/2) / (2x round trip)")
    pooled = {}
    for hr in HOURS:
        ratios, ns = [], []
        for s in FIX_MARKETS:
            e = events(bars[s], hr, BAR_MIN[s])
            sp = spread(e.pre.to_numpy(), e[f"post{PRIMARY_H}"].to_numpy())
            ratios.append(sp / 2.0 / (2.0 * round_trip(s)))
            ns.append(len(e))
        pooled[hr] = float(np.mean(ratios))
        rec["clock"][hr] = {"pooled_edge_over_rt2x": round(pooled[hr], 4),
                            "per_market": [round(x, 3) for x in ratios],
                            "n": ns}
    order = sorted(HOURS, key=lambda h: -pooled[h])
    rank = order.index(FIX_HOUR) + 1
    for i, hr in enumerate(order, 1):
        mark = "  <-- THE FIX" if hr == FIX_HOUR else ""
        print(f"{i:3d}. {hr:02d}:00 London  {pooled[hr]:+.3f}{mark}")
    rec["fix_rank_of_24"] = rank

    # ---- pooled null at the fix hour --------------------------------------
    rng = np.random.default_rng(1)
    per = {s: events(bars[s], FIX_HOUR, BAR_MIN[s]) for s in FIX_MARKETS}
    real = pooled[FIX_HOUR]
    draws = np.empty(N_NULL)
    for i in range(N_NULL):
        rs = []
        for s in FIX_MARKETS:
            e = per[s]
            sp = spread(rng.permutation(e.pre.to_numpy()),
                        e[f"post{PRIMARY_H}"].to_numpy())
            rs.append(sp / 2.0 / (2.0 * round_trip(s)))
        draws[i] = np.mean(rs)
    p_pool = float((draws >= real).mean())
    rec["pooled"] = {"real": round(real, 4), "p": p_pool,
                     "null_p95": round(float(np.percentile(draws, 95)), 4),
                     "null_median": round(float(np.median(draws)), 4)}

    # ---- the four kill criteria, read out ---------------------------------
    c1 = sum(rec["markets"][s]["passes_c1"] for s in FIX_MARKETS)
    crit = {"1_three_of_five_markets": (c1 >= 3, f"{c1}/5 clear the 2x round trip"),
            "2_pooled_beats_null": (p_pool < 0.05, f"p={p_pool:.3f}"),
            "3_fix_in_top3_of_24": (rank <= 3, f"rank {rank}/24"),
            "4_control_silent": (not rec["markets"][CONTROL]["passes_c1"],
                                 f"BTCUSDT edge/RT2x = "
                                 f"{rec['markets'][CONTROL]['edge_over_rt2x']:.2f}")}
    print("\n=== GATE 1, against the criteria fixed in PREREG.md ===")
    for k, (ok, why) in crit.items():
        print(f"  {'PASS' if ok else 'FAIL'}  {k:26s} {why}")
    rec["criteria"] = {k: {"pass": bool(v[0]), "detail": v[1]} for k, v in crit.items()}
    rec["gate1"] = all(v[0] for v in crit.values())
    print(f"\nGATE 1: {'PASS - build the strategy' if rec['gate1'] else 'FAIL - dead here'}")

    (OUT / "stage1.json").write_text(json.dumps(rec, indent=1))
    print(f"\nwrote {OUT / 'stage1.json'}")


if __name__ == "__main__":
    main()
