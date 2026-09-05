"""H-023 stage 12 — how many resting-limit fills are real? Measured on ticks.

THE ASSUMPTION THIS REPO HAS NEVER CHECKED, and has been burned by once.

`strategies/vwap/engine.py` says it plainly: a resting limit at the band is the
natural way to trade a fade, and it is exactly how the previous repo produced a
strategy that backtested at PF 3.0 and traded live at 0.7. Its answer was to
carry two fill modes and only ever use the pessimistic one. Every one of the
2,584 fold configurations behind H-002, H-009 and H-017 is `fill_mode=1`, so
the whole board is priced at a market fill on the next open - 5bps taker plus
2bps slippage per side, 14bps the round trip.

That is a defensible choice made without evidence, and it has a cost: 14bps is
the number that killed H-007 (a real 10% edge on profit factor), H-021 (2.67bps
against it) and H-022 (6.55bps against it). A maker round trip on Binance
USDT-M is 2bps a side. If resting fills are real, the gate every dead
hypothesis failed moves by a factor of three.

So this measures the fill assumption directly, on trades, with no book data and
no queue model where one can be avoided.

THE THREE CRITERIA, from weakest assumption to strongest:

  touch       the bar's low reaches the limit price. This is what the
              optimistic backtest counts, and it is not a fill: if price
              touches your bid and leaves, the queue in front of you ate it.
  through     price trades STRICTLY below the limit. Every resting order at
              that price is filled, whatever the queue held. This needs no
              book data and no assumption - it is a hard lower bound on the
              fill probability.
  queue(Q)    volume traded at or below the limit exceeds Q units resting
              ahead. Reported across a range of Q because the book depth is
              not in the archive (bookTicker is not published for USDT-M).

ADVERSE SELECTION is the second half, and it is the half that explains a 3.0
becoming a 0.7. The touches you miss are not a random sample of touches. If
price kisses your bid and reverses, you did not get filled but the backtest
books the winner; if price trades through you, you are filled and the move
continues against you. So this also reports the forward return after each kind
of fill. A gap there is the real cost of the assumption, and it is separate
from - and usually larger than - the fill rate itself.

Data: BTCUSDT USDT-M aggTrades, the archive's own tick record.
Run: .venv/bin/python strategies/vwap/stage12_queue.py [--workers N]
"""
from __future__ import annotations

import argparse
import sys
import zipfile
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

TICKS = ROOT / "data" / "ticks"
OUT = ROOT / "backtests" / "queue"
OUT.mkdir(parents=True, exist_ok=True)

BAR = "15min"                      # the repo's base timeframe
TICK_SIZE = 0.1                    # BTCUSDT USDT-M price increment
# limit distance below the bar open, in bps. The VWAP band legs sit at 1.5-2.5
# volume-weighted sigmas, which on 15m BTC is roughly the 10-60bps range.
DISTS = (5, 10, 15, 20, 30, 40, 60, 80, 120)
# queue ahead of us, in BTC. 0 = front of queue (the optimistic limit).
QUEUES = (0.0, 0.5, 2.0, 10.0)
FWD_BARS = 4                       # one hour, for the adverse-selection read


def load_day(path: Path) -> pd.DataFrame:
    with zipfile.ZipFile(path) as z:
        name = z.namelist()[0]
        df = pd.read_csv(z.open(name),
                         usecols=["price", "quantity", "transact_time"],
                         dtype={"price": np.float64, "quantity": np.float64,
                                "transact_time": np.int64})
    df["ts"] = pd.to_datetime(df.transact_time, unit="ms", utc=True)
    return df.set_index("ts")[["price", "quantity"]]


def day_stats(path: Path) -> pd.DataFrame | None:
    """Per 15m bar: the open, and for each limit distance whether it was
    touched, traded through, and how much volume printed at or below it.

    The limit is placed AT THE BAR OPEN and rests for the bar. That is the
    honest analogue of what the backtest does - a signal off the previous
    closed bar, an order working through the next one."""
    try:
        t = load_day(path)
    except Exception as e:                       # a truncated download
        print(f"  skip {path.name}: {e}")
        return None
    if t.empty:
        return None

    g = t.groupby(pd.Grouper(freq=BAR))
    rows = []
    for ts, chunk in g:
        if len(chunk) < 2:
            continue
        p = chunk.price.to_numpy()
        q = chunk.quantity.to_numpy()
        op = float(p[0])
        rec = {"ts": ts, "open": op, "low": float(p.min()),
               "high": float(p.max()), "close": float(p[-1]),
               "vol": float(q.sum()), "ntrades": len(chunk)}
        for d in DISTS:
            lim = op * (1.0 - d / 1e4)
            rec[f"touch_{d}"] = bool(p.min() <= lim)
            # strictly through: at least one tick below the limit price
            rec[f"through_{d}"] = bool(p.min() <= lim - TICK_SIZE)
            rec[f"qvol_{d}"] = float(q[p <= lim].sum())
        rows.append(rec)
    if not rows:
        return None
    return pd.DataFrame(rows).set_index("ts")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=8)
    args = ap.parse_args()

    files = sorted(TICKS.glob("BTCUSDT-aggTrades-*.zip"))
    if not files:
        sys.exit(f"no tick files in {TICKS}")
    print(f"{len(files)} days of BTCUSDT aggTrades -> {BAR} bars")

    parts = []
    with ProcessPoolExecutor(max_workers=args.workers) as ex:
        for i, r in enumerate(ex.map(day_stats, files), 1):
            if r is not None:
                parts.append(r)
            if i % 20 == 0:
                print(f"  {i}/{len(files)} days")
    bars = pd.concat(parts).sort_index()
    bars = bars[~bars.index.duplicated(keep="first")]
    bars.to_parquet(OUT / "bars15_fills.parquet")
    print(f"\n{len(bars):,} bars  {bars.index[0]:%Y-%m-%d} -> {bars.index[-1]:%Y-%m-%d}")

    # forward return from the LIMIT price, for the adverse-selection read
    fwd_close = bars.close.shift(-FWD_BARS)

    rows = []
    for d in DISTS:
        lim = bars.open * (1.0 - d / 1e4)
        touch = bars[f"touch_{d}"]
        through = bars[f"through_{d}"]
        qv = bars[f"qvol_{d}"]
        # return earned by a long filled at the limit, in bps
        ret = (fwd_close / lim - 1.0) * 1e4
        n_t = int(touch.sum())
        if n_t < 50:
            continue
        row = {
            "dist_bps": d,
            "bars": len(bars),
            "touch_rate": float(touch.mean()),
            "through_rate": float(through.mean()),
            # THE HAIRCUT: of the fills the optimistic backtest books, how many
            # are certain rather than queue-dependent?
            "through_given_touch": float(through[touch].mean()),
            "fwd_touch_bps": float(ret[touch].mean()),
            "fwd_through_bps": float(ret[through].mean()),
            "fwd_touch_only_bps": float(ret[touch & ~through].mean())
            if int((touch & ~through).sum()) > 20 else np.nan,
        }
        # adverse selection: what the fills you actually get earn, minus what
        # the backtest thought all its fills would earn
        row["adverse_bps"] = row["fwd_through_bps"] - row["fwd_touch_bps"]
        for Q in QUEUES:
            filled = touch & (qv >= Q)
            row[f"fillrate_q{Q}"] = float(filled[touch].mean())
            row[f"fwd_q{Q}_bps"] = float(ret[filled].mean()) if filled.sum() > 20 else np.nan
        rows.append(row)

    res = pd.DataFrame(rows)
    res.to_csv(OUT / "stage12_fill_realism.csv", index=False)

    print(f"\n{'=' * 92}\nFILL REALISM — resting BUY limit d bps below the 15m open\n{'=' * 92}")
    print(f"{'dist':>5} {'touch%':>7} {'through%':>9} {'thru|touch':>11} "
          f"{'fwd@touch':>10} {'fwd@thru':>9} {'adverse':>8}")
    for _, r in res.iterrows():
        print(f"{int(r.dist_bps):5d} {100*r.touch_rate:7.2f} {100*r.through_rate:9.2f} "
              f"{100*r.through_given_touch:11.1f} {r.fwd_touch_bps:10.2f} "
              f"{r.fwd_through_bps:9.2f} {r.adverse_bps:8.2f}")

    print(f"\n{'=' * 92}\nFILL RATE GIVEN A TOUCH, by queue ahead (BTC)\n{'=' * 92}")
    print(f"{'dist':>5} " + " ".join(f"{'q=' + str(q):>10}" for q in QUEUES))
    for _, r in res.iterrows():
        print(f"{int(r.dist_bps):5d} " +
              " ".join(f"{100*r[f'fillrate_q{q}']:10.1f}" for q in QUEUES))

    print(f"\nwrote {OUT / 'stage12_fill_realism.csv'}")


if __name__ == "__main__":
    main()
