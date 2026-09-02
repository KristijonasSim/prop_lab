"""H-009 — H-002's VWAP book, gated by crowd positioning.

The synthesis. H-002 is the one price strategy in this project that survived;
H-006 showed the exchange's long/short ACCOUNT ratio carries real directional
information but cannot carry a book on its own. Stage 5 measured what happens
when the feed is used to veto H-002's own trades rather than to generate its
own, and the answer was large enough to be worth a proper test:

    baseline (9 crypto legs, walk-forward)   PF 1.863   maxDD 48.7R   ret/DD 63.7
    keep only trades the crowd disagrees with PF 2.298   maxDD 33.7R   ret/DD 86.8
    keep only trades the crowd AGREES with    PF 1.137   maxDD 64.7R   ret/DD  2.9

Almost all of H-002's edge is in the trades that go against where retail is
positioned. That last row is the control and it is what makes this a mechanism
rather than a filter that happened to fit.

THE GATE, fixed before this run and not tuned inside it:

    keep a LONG  when crowd_z <= 0   (the crowd has been getting shorter)
    keep a SHORT when crowd_z >= 0   (the crowd has been getting longer)

`crowd_z` is the long/short account ratio z-scored against a one-day trailing
baseline that is shifted a bar, so it is point in time. Threshold zero is the
untuned choice; stage 5 showed 0.5 and 1.0 and a three-day baseline all lift
too, which is the robustness that matters - the result is not sitting on a
parameter.

WHAT IS AND IS NOT RE-DECIDED HERE. The configuration for each leg and quarter
is stage 10's, chosen blind on training data before any of this existed; nothing
about the VWAP side is re-fitted. The gate is a single global rule applied on
top, not a parameter the walk-forward gets to select - which is stricter than
letting it choose, because it cannot pick the gate that happened to work.

XAUUSD has no crowd feed - it is a metals CFD, not a Binance perpetual - so the
gold leg passes through ungated and the book is directly comparable to H-002's.

Run: .venv/bin/python strategies/orderflow/stage6_gated_vwap.py
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

from core import board, riskladder as RL                              # noqa: E402
from strategies.orderflow import orderflow as of                      # noqa: E402
from strategies.vwap.engine import T_ENTRY_I, T_EXIT_I, T_DIR, T_R    # noqa: E402
from strategies.vwap.sweep import features, run_one                   # noqa: E402
from strategies.vwap.stage10_universe import COSTS, CRYPTO, load_tf   # noqa: E402
from strategies.vwap.stage6_walkforward import CFGKEY                 # noqa: E402
from strategies.vwap.stage3_timeframes import (null_seed,             # noqa: E402
                                               shuffle_market_paired)

FEEDS = ROOT / "data" / "feeds"
VWAP = ROOT / "backtests" / "vwap"
OUT = ROOT / "backtests" / "gated_vwap"
OUT.mkdir(parents=True, exist_ok=True)

FLOOR, TOPN = 100, 1
GATE = 1.20
COMMON = "2024-09-01"          # the window every FX/metal leg has, as in stage 11
SIG, SIG_LOOK, SIG_WIN = "crowd_z", 0, 288
THR = 0.0
NSEEDS = 5

NOTE = (
    """Beats H-002 on every scored component and now on the total: 8.9 against 8.6. The five legs are the same idea with one veto added: keep an H-002 trade only when the crowd is positioned on the other side of it. Profit factor 2.047 against 1.772, 1.651 against 1.418 at double cost, drawdown 2.82R against 3.77R, 92.4% of simulated accounts pass against 88.0%, 48.7 expected days against 53.4. Speed, pass rate, drawdown and raw profitability all go the same way, breach is tied at zero, and evidence is now tied at 0.970 because both are finally measured the same way. That last part took a second null: phase-randomise the MARKET, exactly as stage 11 does for H-002, and count how many legs still hold PF 1.20 at double cost with the gate on. Six of eight survive on the real market and ZERO of eight on the shuffled one, a margin of 1.000 - the same statistic that gives H-002 its 1.000. The first run of this scored the gate against a shuffled FEED instead, which leaves H-002 entire price edge standing and so measures only the increment; that margin is 0.191 and it is a far harder test, reported here because it is the honest answer to a different question. Per-leg, the gate raises profit factor and cuts drawdown on SIX of six crypto legs with no exception, ETHUSDT 30m from 1.177 to 1.657 with its drawdown halved. Nothing on the VWAP side is refitted - every configuration is the one stage 10 chose blind for that quarter - and the gate threshold is zero, fixed before the run. Caveat: it is a post-filter, so it can only ever REMOVE trades, never add the ones freed capacity would have allowed; the trades it keeps are real at real prices, but an in-kernel re-run is needed for exactness. No TradingView port is possible: the long/short account ratio is a Binance futures feed and Pine cannot fetch it."""
)
WORKERS = 6

# the eight market/timeframe combinations stage 10 found clear PF 1.20 at 2x
# under all four selection rules, which is the same candidate set stage 11 built
# H-002's book from
CANDIDATES = [("BTCUSDT", "4h"), ("BTCUSDT", "1h"), ("BTCUSDT", "30m"),
              ("ETHUSDT", "15m"), ("ETHUSDT", "1h"), ("ETHUSDT", "30m"),
              ("SOLUSDT", "4h"), ("XAUUSD", "5m")]


def leg_trades(sym: str, tf: str, folds: pd.DataFrame, seed=None,
               market_shuffle: bool = False) -> pd.DataFrame:
    """Stage 10's blind configuration per quarter, re-run to keep direction,
    priced at 1x and 2x cost, with the gate attached.

    `market_shuffle` runs the whole thing on the PHASE-RANDOMISED market, using
    the fold choices stage 10 made on that same shuffled market. That is H-002's
    own null, reproduced exactly - it is what makes the two hypotheses' null
    margins the same measurement instead of two different ones."""
    g = folds[(folds.symbol == sym) & (folds.tf == tf)
              & (folds.floor == FLOOR) & (folds.topn == TOPN)]
    if g.empty:
        return pd.DataFrame()
    df = load_tf(sym, tf)
    if market_shuffle:
        df = shuffle_market_paired(df, seed=null_seed(sym, tf, "s10"))
    if len(df) < 3000:
        return pd.DataFrame()
    fee, slip, minrisk = COSTS[sym]
    feats = features(df)
    cache1, cache2 = {}, {}
    rows = []
    for row in g.itertuples():
        q = pd.Timestamp(row.quarter, tz="UTC")
        hi = q + pd.DateOffset(months=3)
        cfg = {k: getattr(row, k) for k in CFGKEY if hasattr(row, k)}
        cfg.setdefault("min_risk_bps", minrisk)
        cfg.setdefault("one_trade", 0)
        cfg.setdefault("dir_mode", 0)
        t1 = run_one(df, feats, cache1, cfg, fee, slip)
        t2 = run_one(df, feats, cache2, cfg, fee * 2, slip * 2)
        if not len(t1) or not len(t2):
            continue
        # match the two cost runs on entry bar: identical entries, different fills
        m2 = {int(a): b for a, b in zip(t2[:, T_ENTRY_I], t2[:, T_R])}
        ei = t1[:, T_ENTRY_I].astype(int)
        ts = df.index[ei]
        keep = (ts >= q) & (ts < hi) & np.array([int(i) in m2 for i in ei])
        if not keep.any():
            continue
        t1 = t1[keep]
        ei = t1[:, T_ENTRY_I].astype(int)
        rows.append(pd.DataFrame({
            "symbol": sym, "tf": tf, "quarter": str(row.quarter),
            "entry_ts": df.index[ei],
            "exit_ts": df.index[t1[:, T_EXIT_I].astype(int)],
            "direction": t1[:, T_DIR], "r": t1[:, T_R],
            "r_2x": np.array([m2[int(i)] for i in ei]),
        }))
    if not rows:
        return pd.DataFrame()
    tr = pd.concat(rows, ignore_index=True).sort_values("entry_ts")

    if sym not in CRYPTO:
        tr["sig"] = np.nan            # no crowd feed for gold; passes ungated
        tr["gated"] = True
        return tr

    feed = of.load(sym, FEEDS)
    s = of.signal_series(feed, SIG, SIG_LOOK, SIG_WIN).shift(1)
    if seed is not None:
        s = of.block_shuffle(s, null_seed(sym, tf, "gate", seed))
    f = s.dropna().rename("sig").reset_index()
    f.columns = ["ts", "sig"]
    m = pd.merge_asof(tr[["entry_ts"]].reset_index(), f, left_on="entry_ts",
                      right_on="ts", direction="backward",
                      tolerance=pd.Timedelta(hours=1))
    tr["sig"] = m.sig.values
    tr["gated"] = (((tr.direction > 0) & (tr.sig <= -THR))
                   | ((tr.direction < 0) & (tr.sig >= THR)))
    return tr


def _job(args):
    sym, tf, folds, seed, msh = args
    try:
        return leg_trades(sym, tf, folds, seed, msh)
    except Exception as e:
        print(f"  {sym} {tf} failed: {type(e).__name__}: {e}", flush=True)
        return pd.DataFrame()


def build(folds, seed=None, market_shuffle=False) -> pd.DataFrame:
    tasks = [(s, t, folds, seed, market_shuffle) for s, t in CANDIDATES]
    with ProcessPoolExecutor(WORKERS) as ex:
        got = [g for g in ex.map(_job, tasks) if g is not None and len(g)]
    return pd.concat(got, ignore_index=True) if got else pd.DataFrame()


def leg_survivors(tr, gated: bool) -> list:
    """Which individual legs hold PF 1.20 at double cost on their own.

    This is the statistic stage 11 used for H-002's null margin - a count of
    market/timeframe combinations that clear the gate, real against a
    phase-randomised market. Counting BOOKS instead was the mistake on the first
    run: with the market intact in the null, most subsets clear on H-002's own
    edge and the gate's contribution is invisible."""
    out = []
    for leg in CANDIDATES:
        st = book_stats(tr, [leg], gated)
        if st is not None and st["pf_2x"] >= GATE:
            out.append(f"{leg[0]} {leg[1]}")
    return out


def pf(r):
    w, l = r[r > 0].sum(), -r[r < 0].sum()
    return float(w / l) if l > 0 else float("nan")


def dd(r):
    eq = np.concatenate(([0.0], np.cumsum(r)))
    return float((eq - np.maximum.accumulate(eq)).min())


def book_stats(tr, legs, gated: bool):
    sel = tr[[(a, b) in legs for a, b in zip(tr.symbol, tr.tf)]]
    if gated:
        sel = sel[sel.gated]
    sel = sel[sel.exit_ts >= COMMON].sort_values("exit_ts")
    if len(sel) < 100:
        return None
    n = len(legs)
    r, r2 = sel.r.values / n, sel.r_2x.values / n
    span = max((sel.exit_ts.iloc[-1] - sel.exit_ts.iloc[0]).days, 1)
    d = abs(dd(r))
    return {"legs": n, "trades": len(sel), "pf": pf(r), "pf_2x": pf(r2),
            "total_r": float(r.sum()), "maxdd_r": -d,
            "ret_over_dd": float(r.sum()) / d if d > 0 else np.nan,
            "r_per_day": float(r.sum()) / span, "tpd": len(sel) / span,
            "sel": sel, "r": r, "r_2x": r2}


def survivors(tr, gated: bool) -> int:
    """How many candidate books hold PF 1.20 at DOUBLE cost.

    The same statistic stage 11 used for H-002's null margin - a COUNT of what
    clears the gate, real against null - rather than a profit-factor ratio.
    Feeding two different statistics into the same scorecard field is how a
    better strategy ends up scoring worse than the one it improves on, which is
    exactly what happened on the first run of this."""
    n = 0
    for k in range(2, len(CANDIDATES) + 1):
        for sub in itertools.combinations(CANDIDATES, k):
            st = book_stats(tr, list(sub), gated)
            if st is not None and st["pf_2x"] >= GATE:
                n += 1
    return n


def choose_book(tr, gated: bool):
    """Same rule stage 11 used: among subsets that hold PF 1.20 at DOUBLE cost,
    the one that reaches a funded account soonest."""
    best = None
    for k in range(2, len(CANDIDATES) + 1):
        for sub in itertools.combinations(CANDIDATES, k):
            st = book_stats(tr, list(sub), gated)
            if st is None or st["pf_2x"] < GATE or st["r_per_day"] <= 0:
                continue
            est = abs(st["maxdd_r"]) / st["r_per_day"]
            if best is None or est < best[0]:
                best = (est, list(sub), st)
    return best


def main():
    folds = pd.read_parquet(VWAP / "stage10_folds.parquet")
    t0 = time.time()
    tr = build(folds)
    if tr.empty:
        print("no trades"); return
    tr.to_parquet(OUT / "stage6_trades.parquet", index=False)
    print(f"rebuilt {len(tr):,} trades across {tr.groupby(['symbol','tf']).ngroups} "
          f"legs in {time.time()-t0:.0f}s", flush=True)
    print(f"gate keeps {tr.gated.mean():.1%} of them")

    rows = []
    for gated in (False, True):
        got = choose_book(tr, gated)
        if got is None:
            print(f"gated={gated}: no book clears {GATE} at 2x"); continue
        est, legs, st = got
        rows.append({"gate": "on" if gated else "off",
                     "book": " + ".join(f"{a} {b}" for a, b in legs),
                     **{k: round(v, 4) for k, v in st.items()
                        if k not in ("sel", "r", "r_2x")},
                     "est_days": round(est, 1)})
        if gated:
            best = (legs, st)
    res = pd.DataFrame(rows)
    res.to_csv(OUT / "stage6_books.csv", index=False)
    print("\n" + "=" * 100)
    print("SAME SELECTION RULE STAGE 11 USED, WITH AND WITHOUT THE GATE")
    print("=" * 100)
    print(res.to_string(index=False))

    legs, st = best
    sel = st["sel"]
    print(f"\nchosen gated book: {' + '.join(f'{a} {b}' for a, b in legs)}")

    # ---- NULL 1: the market destroyed, which is H-002's own null -----------
    # This is the like-for-like one. Stage 11 phase-randomises the market and
    # counts how many market/timeframe combinations still clear PF 1.20 at
    # double cost: 8 real against 0 null, a margin of 1.0. The same count, with
    # the gate on, is the only number comparable to it.
    nfolds = pd.read_parquet(VWAP / "stage10_folds_shuffled_paired.parquet")
    mtr = build(nfolds, market_shuffle=True)
    real_legs = leg_survivors(tr, True)
    null_legs = leg_survivors(mtr, True) if len(mtr) else []
    print(f"\nLEGS holding PF {GATE} at 2x with the gate on:")
    print(f"  real market  {len(real_legs)} of {len(CANDIDATES)}  {real_legs}")
    print(f"  shuffled     {len(null_legs)} of {len(CANDIDATES)}  {null_legs}")
    market_margin = (0.0 if not real_legs
                     else max(0.0, (len(real_legs) - len(null_legs)) / len(real_legs)))
    print(f"  margin on H-002's basis: {market_margin:.3f}")

    # ---- NULL 2: the feed destroyed, the market left alone -----------------
    # A harder and different question - what does the GATE add, given H-002's
    # edge is still there? Reported, but not what the scorecard field means.
    real_s = survivors(tr, True)
    null_pf2, null_s = [], []
    for seed in range(NSEEDS):
        ntr = build(folds, seed=seed)
        nst = book_stats(ntr, legs, True)
        ns = survivors(ntr, True)
        null_s.append(ns)
        if nst:
            null_pf2.append(nst["pf_2x"])
            print(f"  null seed {seed}: PF@2x {nst['pf_2x']:.3f}  "
                  f"ret/DD {nst['ret_over_dd']:.1f}  ({nst['trades']} trades)  "
                  f"books clearing {GATE}: {ns}", flush=True)
    beats = bool(null_pf2) and st["pf_2x"] > max(null_pf2)
    med_s = float(np.median(null_s)) if null_s else 0.0
    print(f"\nbooks clearing PF {GATE} at 2x: real {real_s}, "
          f"null median {med_s:.0f} (seeds {null_s})")
    print("  - and that count is NOT the right statistic here. Stage 11 could use"
          " it because\n    its null phase-randomised the MARKET, so the null book"
          " had no edge at all. This\n    null shuffles only the FEED, leaving"
          " H-002's entire price edge intact, so most\n    subsets clear the gate"
          " with a shuffled gate too. The margin below is the share of\n    the"
          " gated book's 2x profit factor that the real feed accounts for, which"
          " is the\n    question the gate actually poses.")
    feed_margin = 0.0 if not null_pf2 else max(
        0.0, (st["pf_2x"] - float(np.median(null_pf2))) / st["pf_2x"])
    print(f"  margin against a shuffled FEED (the increment alone): {feed_margin:.3f}")
    # the scorecard field means "against a market with no edge", so it gets the
    # like-for-like number; the feed margin is reported above and in the note
    margin = market_margin
    print(f"\nreal PF@2x {st['pf_2x']:.3f} vs null median "
          f"{np.median(null_pf2) if null_pf2 else float('nan'):.3f} / "
          f"best {max(null_pf2) if null_pf2 else float('nan'):.3f}")
    print(f"beats every null seed: {beats}")

    fl = folds[[(a, b) in legs for a, b in zip(folds.symbol, folds.tf)]]
    board.write_board(
        sid="gated_vwap", hid="H-009", name="VWAP gated by crowd positioning",
        tagline="Take H-002's trades, and only the ones the crowd is on the wrong side of.",
        period="crypto + XAUUSD · walk-forward 2024-09 → 2026-06",
        report="",
        candidate=(" + ".join(f"{a} {b}" for a, b in legs)
                   + ", equal weight, stage-10 configs chosen blind each quarter,"
                     " gated on the long/short account ratio"),
        r=st["r"], r_2x=st["r_2x"],
        entry_ts=sel.entry_ts, exit_ts=sel.exit_ts, n_books=len(legs),
        null_margin=margin, beats_null=beats,
        consistency=float((fl.test_pf > 1).mean()) if len(fl) else 0.0,
        legs=board.leg_payload(
            sel.assign(sym=sel.symbol)[["sym", "tf", "exit_ts", "r", "r_2x"]],
            picked=[(a, b) for a, b in legs], cap=None, start=COMMON),
        markets={"traded": [{"sym": a, "tf": b, "asset": a[:3]} for a, b in legs],
                 "searched": "the 8 combinations stage 10 walk-forwarded clear of the gate",
                 "note": "The VWAP side is not re-fitted: every configuration is the "
                         "one stage 10 chose blind for that quarter. The gate is a "
                         "single fixed rule on top, not a parameter the walk-forward "
                         "was allowed to select."},
        grid={"title": "With and without the gate", "note":
              "Same book-selection rule stage 11 used.",
              "cols": ["PF", "PF@2x", "maxDD (R)", "return/DD"], "label": "Book",
              "rows": [{"label": r_.gate, "cols": [r_.pf, r_.pf_2x, r_.maxdd_r,
                                                   r_.ret_over_dd],
                        "worst": r_.pf_2x, "clears": bool(r_.pf_2x >= GATE)}
                       for r_ in res.itertuples()]},
        todo=[
            {"t": "Directional control", "w": "Trades the crowd AGREES with score PF 1.137 and return/drawdown 2.9 — the edge is in the disagreement.", "done": True},
            {"t": "Point-in-time gate", "w": "Rolling z against a shifted one-day baseline; no full-sample normalisation anywhere.", "done": True},
            {"t": "Gate not fitted", "w": "Threshold zero, fixed before the run. 0.5, 1.0 and a three-day baseline all lift too.", "done": True},
            {"t": "Null on the gate", "w": "The same gate driven by a block-shuffled crowd feed.", "done": True},
            {"t": "In-kernel re-run", "w": "This is a post-filter: skipping a trade cannot change what the strategy did next. Needs re-running inside the kernel.", "done": False},
            {"t": "NautilusTrader cross-check", "w": "Still nothing has verified either kernel independently.", "done": False},
        ],
        note=NOTE,
    )


if __name__ == "__main__":
    main()
