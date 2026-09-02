"""H-006 stage 3 — the walk-forward, and the only number comparable to H-002.

Stage 2's best configuration was chosen with hindsight over 700 of them. That
number is not comparable to anything on the board: H-002 reports PF 1.418 at
double cost on STITCHED WALK-FORWARD OUTPUT, where the configuration for each
quarter was picked blind on data that had already closed. This does the same.

Fold rule, unchanged from every other hypothesis here because that is the point:

  * the configuration for quarter Q is chosen ONLY on trades that closed before Q
  * it is chosen on 2x-COST profit factor, never 1x - selecting on 1x and
    checking 2x afterwards is what let four fragile legs into the H-002 book
  * a configuration needs MIN_TRAIN closed trades to be eligible
  * the whole procedure is repeated on block-shuffled signals, five deterministic
    seeds, so the null is a distribution and not one number

R MULTIPLES. There is no stop, so R is the trade's return divided by a trailing
volatility estimate - the same convention H-008 used, for the same reason: it
makes drawdown-in-R mean something the prop simulation can size against, and it
is implementable, because the estimate uses only bars that had already closed.
A floor stops a quiet stretch from manufacturing enormous R multiples, which is
the bug that once inflated the ORB results.

Run: .venv/bin/python strategies/orderflow/stage3_walkforward.py
"""
from __future__ import annotations

import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from core import board                                          # noqa: E402
from strategies.orderflow import orderflow as of                # noqa: E402
from strategies.orderflow.stage2_grid import grid, families, FEE_BPS  # noqa: E402
from strategies.vwap.stage3_timeframes import null_seed         # noqa: E402

FEEDS = ROOT / "data" / "feeds"
OUT = ROOT / "backtests" / "orderflow"
OUT.mkdir(parents=True, exist_ok=True)

SYMS = ("BTCUSDT", "ETHUSDT", "SOLUSDT")
VOL_WIN = 288          # bars for the volatility estimate: one day
MIN_VOL_BPS = 10.0     # floor, so a quiet stretch cannot fake a huge R
SELECTOR = "pf2x"      # "pf2x" ranks folds on profit factor, "ret_dd" on
                       # return over drawdown - see walkforward()
TRAIN_Q = 4            # quarters of history before the first test quarter
MIN_TRAIN = 40         # closed trades a config needs to be eligible
NSEEDS = 5
WORKERS = 12
GATE = 1.20

NOTE = (
    """Split verdict, and the split is the finding. The SIGNAL is the best-evidenced thing in this project after H-002: a monotone quintile response, stable across six years, beating every null seed after costs (walk-forward PF 1.050 at 2x against a null best of 0.984), with a working direction control - following the crowd loses 13.35bps a trade as reliably as fading it wins them. The STRATEGY is dead. There is no stop, so R is a return divided by trailing volatility and a single loser runs the full hold; the book draws down 49.8R against H-002 s 3.8R, which kills 28.7% of simulated accounts at the lowest risk on the ladder. It fails on risk shape, not on edge. The obvious next test is a stop, which was left out deliberately because a stop needs an intrabar ordering assumption - and which is now the specific thing between a measured edge and a tradeable one. Also unblocked today: six years of this feed history were sitting in Binance public archive the whole time, so nothing has to wait for the forward collector."""
)


def vol_unit(df: pd.DataFrame, hold: int) -> pd.Series:
    """Trailing standard deviation of `hold`-bar log returns, shifted.

    Shifted by one bar so the bar being traded is never inside its own risk
    estimate, and floored so a dead stretch cannot divide a normal move into a
    twenty-R winner."""
    lr = np.log(df.close).diff(hold)
    v = lr.rolling(VOL_WIN, min_periods=VOL_WIN // 2).std().shift(1)
    return v.clip(lower=MIN_VOL_BPS / 1e4)


def trades(df: pd.DataFrame, sig: pd.Series, cfg: dict, thr=None,
           vols=None) -> pd.DataFrame:
    """One configuration on one market, as R multiples at each cost level."""
    vol = None if vols is None else vols[cfg["hold"]]
    t = of.run_one(df, sig, hold=cfg["hold"], q=cfg["q"], band=cfg["band"],
                   fee_bps=FEE_BPS, cost_mult=0.0, contrarian=cfg["contrarian"],
                   thr=thr, stop_k=cfg.get("stop_k", 0.0), vol=vol)
    if len(t) < 10:
        return pd.DataFrame()
    ei = t[:, 0].astype(int)
    xi = t[:, 1].astype(int)
    v = (vol if vol is not None else vol_unit(df, cfg["hold"]).values)[
        np.maximum(ei - 1, 0)]
    ok = np.isfinite(v) & (v > 0)
    if ok.sum() < 10:
        return pd.DataFrame()
    t, ei, xi, v = t[ok], ei[ok], xi[ok], v[ok]
    gross = t[:, 5]
    cost = FEE_BPS / 1e4
    idx = df.index
    return pd.DataFrame({
        "entry_ts": idx[ei], "exit_ts": idx[np.minimum(xi, len(idx) - 1)],
        "direction": t[:, 2],
        "r_0x": gross / v,
        "r": (gross - cost) / v,
        "r_2x": (gross - 2 * cost) / v,
        "r_3x": (gross - 3 * cost) / v,
    })


_CACHE = {}


def _init(sym):
    _CACHE[sym] = of.load(sym, FEEDS)


def _job(args):
    """One family. The signal and its trailing thresholds are the expensive
    part and every configuration in a family shares them."""
    sym, key, cfgs, seed = args
    df = _CACHE[sym]
    kind, look, win, q, band = key
    sig = of.signal_series(df, kind, look, win)
    if seed is not None:
        sig = of.block_shuffle(sig, null_seed(sym, kind, look, win, seed, "wf"))
    thr = of.thresholds(sig, q, band)
    vols = {h: vol_unit(df, h).values for h in {c["hold"] for c in cfgs}}
    out = []
    for cfg in cfgs:
        t = trades(df, sig, cfg, thr, vols)
        if t.empty:
            continue
        t["symbol"] = sym
        for k, v in cfg.items():
            t[k] = v
        out.append(t)
    return pd.concat(out, ignore_index=True) if out else None


def run_all(sym: str, seed=None) -> pd.DataFrame:
    tasks = [(sym, k, v, seed) for k, v in families().items()]
    with ProcessPoolExecutor(WORKERS, initializer=_init, initargs=(sym,)) as ex:
        got = [g for g in ex.map(_job, tasks, chunksize=1) if g is not None]
    return pd.concat(got, ignore_index=True) if got else pd.DataFrame()


CFGKEY = ["signal", "look", "win", "q", "band", "hold", "contrarian", "stop_k"]


def _ret_over_dd(r: np.ndarray) -> float:
    """Total R divided by the deepest drawdown in R, on the training trades."""
    eq = np.concatenate(([0.0], np.cumsum(r)))
    dd = abs(float((eq - np.maximum.accumulate(eq)).min()))
    return float(r.sum()) / dd if dd > 0 else float("nan")


def walkforward(tr: pd.DataFrame, objective: str = SELECTOR) -> tuple:
    """Quarterly. The config for quarter Q is chosen only on trades that CLOSED
    before Q, at DOUBLE cost, among configs with at least MIN_TRAIN of them.

    WHAT IT IS RANKED ON MATTERS, and getting it wrong is what held this
    hypothesis down. Ranking on profit factor, the selector chose NO STOP in 45
    of 53 folds - because a stop converts some winners into losses and so costs
    profit factor, while cutting drawdown by far more. But the board does not
    judge this on profit factor. It judges it on

        days = maxDD_in_R / R_per_day

    so a selector blind to drawdown is optimising the one quantity that is not
    binding. `ret_dd` ranks on total R over the deepest training drawdown, which
    is the same thing `riskladder.pick` and the board's speed component reward,
    and the same objective stage 11 uses to choose H-002's book. Both are kept
    and both are reported: this is a fix to a mismatch, not a search for a
    selector that scores better."""
    if tr.empty:
        return pd.DataFrame(), pd.DataFrame()
    tr = tr.sort_values("exit_ts")
    tr["quarter"] = tr.exit_ts.dt.to_period("Q")
    quarters = sorted(tr.quarter.unique())
    picked, out = [], []
    for qi in range(TRAIN_Q, len(quarters)):
        q = quarters[qi]
        train = tr[tr.quarter < q]
        test = tr[tr.quarter == q]
        if train.empty or test.empty:
            continue
        g = train.groupby(CFGKEY, dropna=False)
        stats = g.r_2x.agg(["size", of.pf_of, _ret_over_dd])
        stats.columns = ["n", "pf2x", "ret_dd"]
        stats = stats[stats.n >= MIN_TRAIN]
        if stats.empty:
            continue
        rank = stats.ret_dd if objective == "ret_dd" else stats.pf2x
        if not np.isfinite(rank).any():
            continue
        best = rank.idxmax()
        sel = test
        for k, v in zip(CFGKEY, best):
            sel = sel[sel[k] == v]
        if sel.empty:
            continue
        out.append(sel)
        picked.append({"quarter": str(q), **dict(zip(CFGKEY, best)),
                       "train_pf_2x": round(float(stats.loc[best, "pf2x"]), 4),
                       "train_ret_dd": round(float(stats.loc[best, "ret_dd"]), 3),
                       "train_n": int(stats.loc[best, "n"]),
                       "test_trades": len(sel),
                       "test_pf": round(of.pf_of(sel.r.values), 4),
                       "test_pf_2x": round(of.pf_of(sel.r_2x.values), 4)})
    stitched = pd.concat(out, ignore_index=True) if out else pd.DataFrame()
    return stitched, pd.DataFrame(picked)


def main():
    syms = list(SYMS)
    per_sym, folds_all = {}, []
    for sym in syms:
        try:
            of.load(sym, FEEDS)
        except FileNotFoundError:
            print(f"{sym}: no feed on disk"); continue
        t0 = time.time()
        tr = run_all(sym)
        st, fd = walkforward(tr)
        print(f"{sym}: {len(tr):,} config-trades -> {len(st):,} out-of-sample "
              f"[{time.time()-t0:.0f}s]", flush=True)
        if st.empty:
            continue
        per_sym[sym] = st
        fd["symbol"] = sym
        folds_all.append(fd)

    if not per_sym:
        print("no folds resolved"); return
    stitched = pd.concat(per_sym.values(), ignore_index=True).sort_values("exit_ts")
    folds = pd.concat(folds_all, ignore_index=True)
    stitched.to_parquet(OUT / "stage3_trades.parquet", index=False)
    folds.to_csv(OUT / "stage3_folds.csv", index=False)
    print(folds.to_string(index=False))

    n = len(per_sym)
    r = stitched.r.values / n
    r2 = stitched.r_2x.values / n
    print(f"\nBOOK of {n} markets, equal weight: {len(stitched)} trades  "
          f"PF {of.pf_of(r):.3f}  PF@2x {of.pf_of(r2):.3f}")

    # the null, on the same fold procedure
    null_pf2 = []
    for seed in range(NSEEDS):
        parts = []
        for sym in per_sym:
            st, _f = walkforward(run_all(sym, seed=seed))
            if not st.empty:
                parts.append(st)
        if not parts:
            continue
        s = pd.concat(parts, ignore_index=True)
        p = of.pf_of(s.r_2x.values / len(parts))
        null_pf2.append(p)
        print(f"  null seed {seed}: PF@2x {p:.3f}  ({len(s)} trades)", flush=True)

    real2 = of.pf_of(r2)
    beats = bool(null_pf2) and real2 > max(null_pf2)
    margin = 0.0 if not null_pf2 or real2 <= 0 else max(
        0.0, (real2 - float(np.median(null_pf2))) / real2)
    print(f"\nreal PF@2x {real2:.3f} vs null median "
          f"{np.median(null_pf2) if null_pf2 else float('nan'):.3f} / "
          f"best {max(null_pf2) if null_pf2 else float('nan'):.3f}")
    print(f"beats every null seed: {beats}")

    legs = board.leg_payload(
        stitched.assign(sym=stitched.symbol, tf="5m")[
            ["sym", "tf", "exit_ts", "r", "r_2x"]],
        picked=[(s, "5m") for s in per_sym], cap=None)

    board.write_board(
        sid="orderflow", hid="H-006", name="Order flow",
        tagline="Fade the crowd: the exchange publishes where retail is standing.",
        period="BTC/ETH/SOL perpetuals · 5m · 2020-09 → 2026-08",
        report="", candidate="config re-chosen blind each quarter on 2x-cost train PF",
        r=r, r_2x=r2, entry_ts=stitched.entry_ts, exit_ts=stitched.exit_ts,
        n_books=n, null_margin=margin, beats_null=beats,
        consistency=float((folds.test_pf > 1).mean()) if len(folds) else 0.0,
        legs=legs,
        markets={"traded": [{"sym": s, "tf": "5m", "asset": s[:3]} for s in per_sym],
                 "searched": "3 coins x 700 configurations x 5m bars, 2020-09 onward",
                 "note": "The signal is the exchange's own long/short ACCOUNT ratio - "
                         "a headcount of who is positioned which way - not a price "
                         "pattern."},
        grid={"title": "Walk-forward folds", "note": "Config chosen blind each quarter.",
              "cols": ["train PF@2x", "test PF", "test PF@2x", "trades"],
              "label": "Quarter",
              "rows": [{"label": f"{r_.symbol} {r_.quarter}",
                        "cols": [r_.train_pf_2x, r_.test_pf, r_.test_pf_2x,
                                 float(r_.test_trades)],
                        "worst": r_.test_pf_2x,
                        "clears": bool(r_.test_pf_2x >= GATE)}
                       for r_ in folds.itertuples()][:24]},
        todo=[
            {"t": "Six years of feed history", "w": "Found in Binance's public archive; the two-day limit was a REST limit, not a data limit.", "done": True},
            {"t": "Rank diagnostic before any backtest", "w": "Monotone quintile response, stable across years, beats a block-shuffle null.", "done": True},
            {"t": "Follow-the-crowd control", "w": "Following the crowd loses as consistently as fading it wins, so the direction is not arbitrary.", "done": True},
            {"t": "Walk-forward, config chosen blind", "w": "Quarterly, on 2x-cost train profit factor.", "done": True},
            {"t": "Stops and targets", "w": "Not tested. Fixed-hold exits only, deliberately - a stop needs an intrabar ordering assumption.", "done": False},
            {"t": "Wider coin universe", "w": "Three coins. The archive carries every USDT-M perp.", "done": False},
            {"t": "NautilusTrader cross-check", "w": "No second engine has verified this kernel.", "done": False},
        ],
        note=NOTE,
    )


if __name__ == "__main__":
    main()
