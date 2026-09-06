"""H-026 stage 1 — Power of Three (accumulation, manipulation, distribution).

Kris's own model, and the one he says has worked for him. It is built here with
the conditioning that makes it a testable claim rather than a picture.

THE PATTERN. A session is read in three parts. Price ACCUMULATES in a range,
then MANIPULATES — sweeping one side of that range to trigger the stops resting
beyond it — then DISTRIBUTES in the other direction, which is the real move.
The trade is: after the sweep reverses back inside the range, take the reversal.

WHY THIS IS NOT ALLOWED TO BE BUILT BARE. Read literally, "enter against a sweep
of a range extreme" is fading an extreme, and this project has already killed
that family twice on two different definitions of extreme — a rolling 10-100 bar
high/low (H-005, where the paired null cleared the gate 19,062 times against the
real data's 1,702) and the previous day/week high/low (H-011, a real edge at
0.897 walk-forward, too small for 28bps). CLAUDE.md says not to re-propose it
without a genuinely new ingredient. Eleven price hypotheses have now died here.

THE NEW INGREDIENT is the feed, and it is a mechanism, not a filter. A stop run
is only worth trading if there were stops to run. The pattern says nothing about
that; the feeds say it directly:

    crowd long/short   how one-sided the account base is (H-009's gate, the
                       one thing in this project that ever worked)
    premium / funding  what that positioning is PAYING to stay on. Crowded and
                       expensive is a different state from crowded and free.
    depth imbalance    what is resting on the side about to be swept (H-024)
    DVOL               how much movement the option market has priced (H-025)

So the claim under test is sharper than the pattern: **a sweep against crowded,
expensively financed positioning is a liquidation of that positioning and should
revert; a sweep against flat positioning is noise and should not.** If the
conditioners do nothing, the pattern is a price pattern and dies with the other
eleven, and that is a result worth having.

arXiv 2601.06084 argues the same shape from the other direction — funding aligned
with the 4-hour context gives expansion, funding divergent gives compression and
range — though it is a qualitative paper and no effect size in it survives
reading.

SESSION MAP. The default is the ICT reading, in UTC: Asia accumulates, London
manipulates, New York distributes. Three alternatives are run beside it so the
answer is not an artifact of one arbitrary clock, including a pure UTC-day split
with no session story at all.

CONTROLS, both reported beside every number:
  * CONTINUATION — sweeps that never close back inside. If those pay as well,
    the reversal is not what is being measured.
  * INVERSE — the same events traded the other way. If that is no worse, there
    is nothing here.

NO LOOKAHEAD. The accumulation range is fixed at the close of the accumulation
window and never updated. A sweep is confirmed only on a CLOSED bar back inside
the range. Entry is the NEXT bar's open. Conditioners are read at the decision
bar, and the crowd feed is joined as-of with its own publication lag.

Run: .venv/bin/python strategies/po3/stage1_response.py
     .venv/bin/python strategies/po3/stage1_response.py BTCUSDT ETHUSDT
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from strategies.orderflow import orderflow as of                # noqa: E402

FEEDS = ROOT / "data" / "feeds"
OUT = ROOT / "backtests" / "po3"
OUT.mkdir(parents=True, exist_ok=True)

SYMS = ("BTCUSDT", "ETHUSDT", "SOLUSDT")
BARS_PER_HOUR = 12
COSTS = {"taker1x": 14.0, "taker2x": 28.0, "mixed": 9.0, "maker2x": 8.0}
NBUCKET = 5
NSEEDS = 10
ZWIN = 288

#: (label, accumulation hours [start, end), manipulation window end hour,
#:  distribution end hour) — all UTC.
SESSIONS = (
    ("ict",     0,  7, 12, 21),   # Asia accumulate, London manipulate, NY deliver
    ("ict_lat", 0,  8, 14, 22),   # the same story, an hour looser each way
    ("utc_day", 0,  8, 16, 24),   # no session story: thirds of the UTC day, and
                                  # also the 00/08/16 funding clock, which is the
                                  # same split
    ("fast",    0,  4,  8, 16),   # a faster cycle: 4h accumulation. Holds on the
                                  # session versions run ~12h, which is long for
                                  # this project's phase constraint, and a
                                  # shorter cycle gives more events per day.
)


def load(sym: str) -> pd.DataFrame:
    """Perp bars with every conditioner joined, each at its own honest lag."""
    df = pd.read_parquet(FEEDS / f"{sym}_perp_5m.parquet").sort_index()
    df = df[~df.index.duplicated(keep="last")]

    # Crowd positioning and taker aggression: same 5-minute grid, joined not
    # interpolated, exactly as strategies/orderflow does it.
    mp = FEEDS / f"{sym}_metrics_5m.parquet"
    if mp.exists():
        df = df.join(pd.read_parquet(mp), how="left")

    # Perp premium: what the positioning is paying.
    pp = FEEDS / f"{sym}_premium_5m.parquet"
    if pp.exists():
        prem = pd.read_parquet(pp)["close"].rename("premium")
        df = df.join(prem, how="left")

    # Book depth (H-024), where it exists.
    dp = FEEDS / f"{sym}_depth_5m.parquet"
    if dp.exists():
        d = pd.read_parquet(dp)
        df = df.join(d[d.n_snap >= 5][["imb_1", "dep_1"]], how="left")

    # DVOL (H-025), hourly, lagged by its own bar duration.
    cur = {"BTCUSDT": "BTC", "ETHUSDT": "ETH"}.get(sym)
    vp = FEEDS / f"{cur}_dvol_3600s.parquet" if cur else None
    if vp is not None and vp.exists():
        dv = pd.read_parquet(vp)
        obs = pd.DataFrame({"ts": dv.index + pd.Timedelta(hours=1),
                            "dvol": dv.dvol_close.to_numpy(float)}).sort_values("ts")
        left = pd.DataFrame({"i": np.arange(len(df)), "t": df.index}).sort_values("t")
        j = pd.merge_asof(left, obs, left_on="t", right_on="ts",
                          direction="backward", tolerance=pd.Timedelta(hours=6))
        df["dvol"] = j.sort_values("i").dvol.to_numpy()
    return df


def _z(s: pd.Series, win: int = ZWIN) -> pd.Series:
    m = s.rolling(win, min_periods=win // 2).mean().shift(1)
    v = s.rolling(win, min_periods=win // 2).std(ddof=0).shift(1)
    return (s - m) / v.replace(0.0, np.nan)


def conditioners(df: pd.DataFrame) -> pd.DataFrame:
    """Everything the feeds can say about how crowded and how paid-for the
    positioning is. All point-in-time, all z-scored against a shifted baseline."""
    c = pd.DataFrame(index=df.index)
    if "count_long_short_ratio" in df:
        c["crowd_z"] = _z(np.log(df.count_long_short_ratio.replace(0.0, np.nan)))
    if "sum_open_interest" in df:
        c["oi_z"] = _z(np.log(df.sum_open_interest.replace(0.0, np.nan)))
        c["doi_1d"] = _z(np.log(df.sum_open_interest.replace(0.0, np.nan))
                         - np.log(df.sum_open_interest.replace(0.0, np.nan).shift(288)))
    if "premium" in df:
        c["prem_z"] = _z(df.premium)
    if "imb_1" in df:
        c["imb_z"] = _z(df.imb_1)
    if "dvol" in df:
        c["dvol_z"] = _z(df.dvol, ZWIN * 7)
    return c


def events(df: pd.DataFrame, label: str, acc_start: int, acc_end: int,
           man_end: int, dist_end: int) -> pd.DataFrame:
    """Every sweep-and-reclaim in the sample, with its outcome.

    One event per session per side at most. The range is frozen when the
    accumulation window closes. A sweep is a bar whose HIGH exceeds the range
    high (or LOW below the range low) inside the manipulation window; the
    reclaim is the first CLOSED bar after that whose close is back inside the
    range. Entry is the next open, exit is the distribution window's close.
    """
    hour = df.index.hour.to_numpy()
    day = df.index.normalize()
    o, h, l, c = (df.open.to_numpy(float), df.high.to_numpy(float),
                  df.low.to_numpy(float), df.close.to_numpy(float))
    idx = np.arange(len(df))

    rows = []
    for _, pos in pd.Series(idx, index=day).groupby(level=0):
        p = pos.to_numpy()
        if len(p) < 100:
            continue
        hh = hour[p]
        acc = p[(hh >= acc_start) & (hh < acc_end)]
        man = p[(hh >= acc_end) & (hh < man_end)]
        dis = p[(hh >= man_end) & (hh < dist_end)]
        if len(acc) < 12 or len(man) < 12 or len(dis) < 12:
            continue
        rng_hi, rng_lo = h[acc].max(), l[acc].min()
        if not (rng_hi > rng_lo > 0):
            continue
        width = (rng_hi - rng_lo) / c[acc[-1]]

        for side_name, swept in (("high", True), ("low", False)):
            # the sweep: first manipulation bar to trade beyond the range
            beyond = man[h[man] > rng_hi] if swept else man[l[man] < rng_lo]
            if not len(beyond):
                continue
            s0 = beyond[0]
            # the reclaim: first CLOSED bar after the sweep back inside
            after = man[man > s0]
            inside = after[(c[after] < rng_hi) if swept else (c[after] > rng_lo)]
            reclaimed = bool(len(inside))
            # CONTINUATION control: no reclaim inside the manipulation window
            k = int(inside[0]) if reclaimed else int(man[-1])
            if k + 1 >= len(df) or dis[-1] <= k:
                continue
            entry_i = k + 1
            exit_i = int(dis[-1])
            pe, px = o[entry_i], c[exit_i]
            if not (pe > 0 and px > 0):
                continue
            # a swept HIGH is a bull trap -> the reversal trade is SHORT
            d = -1 if swept else 1
            ret = d * (px - pe) / pe * 1e4
            depth = (h[s0] - rng_hi) / c[acc[-1]] if swept else \
                    (rng_lo - l[s0]) / c[acc[-1]]
            rows.append({
                "session": label, "ts": df.index[entry_i], "side": side_name,
                "dir": d, "reclaimed": reclaimed, "ret_bps": ret,
                "range_w": width * 1e4, "sweep_depth": depth * 1e4,
                "decide_i": k, "entry_i": entry_i, "exit_i": exit_i,
                "hold_bars": exit_i - entry_i,
            })
    return pd.DataFrame(rows)


def summarise(e: pd.DataFrame, label: str) -> dict:
    r = e.ret_bps
    return {"what": label, "n": len(e), "mean_bps": r.mean(),
            "median_bps": r.median(), "win": (r > 0).mean(),
            "hold_h": e.hold_bars.mean() / BARS_PER_HOUR,
            **{f"net_{k}": r.mean() - v for k, v in COSTS.items()}}


def main():
    syms = sys.argv[1:] or list(SYMS)
    allev, summary, cond_rows = [], [], []

    for sym in syms:
        try:
            df = load(sym)
        except FileNotFoundError as ex:
            print(f"{sym}: {ex}")
            continue
        C = conditioners(df)
        print(f"\n{sym}: {len(df):,} bars  {df.index[0]:%Y-%m-%d} -> "
              f"{df.index[-1]:%Y-%m-%d}  conditioners: {list(C.columns)}", flush=True)

        for label, a0, a1, m1, d1 in SESSIONS:
            e = events(df, label, a0, a1, m1, d1)
            if not len(e):
                continue
            e["sym"] = sym
            rec = e[e.reclaimed]
            con = e[~e.reclaimed]
            summary.append({"sym": sym, **summarise(rec, f"{label} reversal")})
            summary.append({"sym": sym, **summarise(con, f"{label} continuation")})
            inv = rec.copy()
            inv["ret_bps"] = -inv.ret_bps
            summary.append({"sym": sym, **summarise(inv, f"{label} INVERSE")})

            # attach every conditioner as it stood on the DECISION bar
            for cname in C.columns:
                v = C[cname].to_numpy()
                rec = rec.copy()
                rec[cname] = v[rec.decide_i.to_numpy()]
            allev.append(rec)

            # does any conditioner rank the reversal's payoff?
            for cname in C.columns:
                sub = rec[[cname, "ret_bps"]].dropna()
                if len(sub) < 400:
                    continue
                try:
                    b = pd.qcut(sub[cname], NBUCKET, labels=False, duplicates="drop")
                except ValueError:
                    continue
                g = sub.ret_bps.groupby(b).mean()
                spread = float(g.iloc[-1] - g.iloc[0])
                nulls = []
                rng = np.random.default_rng(0)
                for s in range(NSEEDS):
                    perm = rng.permutation(sub[cname].to_numpy())
                    bb = pd.qcut(pd.Series(perm, index=sub.index), NBUCKET,
                                 labels=False, duplicates="drop")
                    gg = sub.ret_bps.groupby(bb).mean()
                    nulls.append(abs(float(gg.iloc[-1] - gg.iloc[0])))
                cond_rows.append({
                    "sym": sym, "session": label, "cond": cname, "n": len(sub),
                    "q1": float(g.iloc[0]), "q5": float(g.iloc[-1]),
                    "spread": spread, "null_max": max(nulls),
                    "beats_null": abs(spread) > max(nulls),
                    "best_bucket_bps": float(g.max()),
                })

    if not summary:
        print("no events found")
        return
    S = pd.DataFrame(summary)
    S.to_csv(OUT / "stage1_events.csv", index=False)
    print(f"\n{'=' * 104}\nTHE PATTERN ITSELF, mean bps per event, before and "
          f"after cost\n{'=' * 104}")
    print(f"{'sym':9} {'what':26} {'n':>6} {'mean':>8} {'win':>6} {'hold_h':>7} "
          f"{'net14':>8} {'net28':>8} {'net8':>8}")
    for _, r in S.iterrows():
        print(f"{r['sym']:9} {r.what:26} {r.n:6d} {r.mean_bps:8.1f} "
              f"{r.win:6.3f} {r.hold_h:7.1f} {r.net_taker1x:8.1f} "
              f"{r.net_taker2x:8.1f} {r.net_maker2x:8.1f}")

    if cond_rows:
        C = pd.DataFrame(cond_rows)
        C.to_csv(OUT / "stage1_conditioners.csv", index=False)
        print(f"\n{'=' * 104}\nDOES ANY FEED RANK THE REVERSAL'S PAYOFF? "
              f"(q5 - q1, bps per event)\n{'=' * 104}")
        print(f"{'sym':9} {'session':9} {'cond':9} {'n':>6} {'q1':>8} {'q5':>8} "
              f"{'spread':>8} {'null':>8} {'best_q':>8}")
        for _, r in C.sort_values("spread", key=abs, ascending=False).head(30).iterrows():
            star = "*" if r.beats_null else " "
            print(f"{r['sym']:9} {r.session:9} {r['cond']:9} {r.n:6d} "
                  f"{r.q1:8.1f} {r.q5:8.1f} {r.spread:8.1f} "
                  f"{r.null_max:8.1f}{star} {r.best_bucket_bps:8.1f}")
        print(f"\n  {int(C.beats_null.sum())} of {len(C)} conditioner cells beat "
              f"their permutation null")
        print(f"  best single bucket, any conditioner: "
              f"{C.best_bucket_bps.max():.1f} bps "
              f"(cost gates: taker1x 14, maker2x 8)")

    if allev:
        pd.concat(allev, ignore_index=True).to_parquet(OUT / "stage1_trades.parquet")
    print(f"\nwrote {OUT / 'stage1_events.csv'}")


if __name__ == "__main__":
    main()
