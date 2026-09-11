"""H-031 stage 1 — the drawdown study, run before the return study.

The screen (2026-09-10) said a 30-minute open-interest collapse with price down
is followed by +28bps over 24h, against -6bps when price falls as far with OI
stable. H-006 had a signal of the same shape and died on RISK SHAPE: no stop, a
24h hold, 63.5R of drawdown and 548 days. So this asks one question first: with
a stop and the adopted sizing, does the drawdown fit a 6% cap at a pace the
business can use? The kill criterion was written into `notes.md` before this
file was run.

WHAT IS FIXED, taken from the screen and not searched: bottom 2% of 30m OI
change, price down over the same 30m, long at the next 5m open, 24h hold, one
position per coin at a time, ten coins, the last three years to a common end.

WHAT IS VARIED: the stop, and only the stop. Seven multiples of the trailing 1h
sigma (0 = none) and one structural stop under the flush's own low. Every arm is
reported.

NO LOOK-AHEAD. The 2% threshold is a TRAILING 30-day quantile shifted one bar -
the screen used a whole-sample cut, which says whether the feed ranks returns
and not whether it could have been traded. OI at a bar's index is the snapshot
at that bar's open, so it is known when the bar closes. Entry is the next open.

FILLS. A stop is a stop-market order: a bar that opens through it fills at the
open, not at the level (CLAUDE.md, 2026-09-08). The horizon exit is the open 24h
after entry. Zero-volume bars are never decided, filled or stopped on.

Run: .venv/bin/python strategies/liqflush/stage1_drawdown.py
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
from numba import njit

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from core.nulls import null_seed                                   # noqa: E402
from core.prop_rules import THUNDERBOLT                            # noqa: E402
from core.riskladder import run_accounts                           # noqa: E402
from strategies.orderflow.orderflow import block_shuffle, load     # noqa: E402

FEEDS = ROOT / "data" / "feeds"
OUT = ROOT / "backtests" / "liqflush"
COINS = ("BTC", "ETH", "SOL", "BNB", "XRP", "ADA", "DOGE", "LINK", "LTC", "DOT")

LOOK = 6              # 30 minutes of 5m bars
Q = 0.02              # the flush is the bottom 2% of OI change
BAND = 8640           # trailing 30 days for the threshold
HOLD = 288            # 24h
VOLWIN = 288          # trailing day of 5m returns for sigma
K_REF = 3.0           # R unit for the no-stop arm, in 1h sigmas
MIN_RISK_BPS = 3.0    # same floor as the gold kernel
WICK_BUF = 0.25       # structural stop: flush low minus a quarter sigma
STOPS = (0.0, 1.0, 1.5, 2.0, 3.0, 4.0, 6.0, -1.0)   # -1 = under the flush low
RT_BPS = 14.0         # 1x round trip, the repo's crypto assumption
COST_MULTS = (0, 1, 2, 3)
#: `--full` re-reads the whole metrics history (2021-12 on nine coins) as a
#: cross-check. The verdict is read on the 3-year window only.
FULL = "--full" in sys.argv
START = pd.Timestamp("2021-12-01" if FULL else "2023-09-01", tz="UTC")
END = pd.Timestamp("2026-08-31 23:55", tz="UTC")      # earliest last bar
RISKS = (0.0025, 0.005, 0.01, 0.02)
SEEDS = 20
MAX_DAYS = 400


def arm_name(k: float) -> str:
    return "none" if k == 0 else ("wick" if k < 0 else f"{k:g}sig")


# --------------------------------------------------------------------------- #
# data
# --------------------------------------------------------------------------- #
def prepare(coin: str) -> dict:
    df = load(f"{coin}USDT", FEEDS)
    df = df.reindex(pd.date_range(df.index[0], df.index[-1], freq="5min"))
    oi = df["sum_open_interest"].where(df["sum_open_interest"] > 0)
    live = (df.volume > 0) & df.open.notna() & oi.notna()
    doi = np.log(oi / oi.shift(LOOK))
    ret = np.log(df.close / df.close.shift(LOOK))
    roll = doi.rolling(BAND, min_periods=BAND // 2)
    thr = roll.quantile(Q).shift(1)
    flush = (doi <= thr) & (ret < 0) & live

    # THE CONTROL: the same fall, open interest stable. Price down at least as
    # far as the median flush on this coin, OI change inside its trailing
    # 40-60% band. The median is a whole-sample number, which is fine for a
    # control and would not be fine for a rule.
    stable = (doi >= roll.quantile(0.40).shift(1)) & (doi <= roll.quantile(0.60).shift(1))
    idx = df.index
    inwin = (idx >= START) & (idx <= END)
    cut = float(ret[flush & inwin].median())
    control = stable & (ret <= cut) & live

    lr = np.log(df.close).diff()
    sig = lr.rolling(VOLWIN, min_periods=VOLWIN // 2).std(ddof=0) * np.sqrt(12)
    return {"coin": coin, "idx": idx, "inwin": inwin,
            "o": df.open.values, "h": df.high.values, "l": df.low.values,
            "c": df.close.values, "live": live.values,
            "flush": flush.values, "control": control.values,
            "sig": sig.values, "wick": df.low.rolling(LOOK).min().values,
            "cut_bps": cut * 1e4}


# --------------------------------------------------------------------------- #
# the kernel
# --------------------------------------------------------------------------- #
@njit(cache=True)
def kernel(o, h, l, c, live, flag, sig, wick, inwin, k, hold):
    """Long after every flagged bar, one position at a time.

    Returns (entry_i, exit_i, gross, unit, stopped): gross and unit are
    fractions of the entry price; R = (gross - cost) / unit."""
    n = len(o)
    ei = np.empty(n, np.int64)
    xi = np.empty(n, np.int64)
    gr = np.empty(n)
    un = np.empty(n)
    st = np.empty(n, np.bool_)
    m = 0
    i = 1
    while i < n - 1:
        if not (flag[i] and live[i] and inwin[i]):
            i += 1
            continue
        e = i + 1
        v = sig[i]
        if not live[e] or not (v == v and v > 0):
            i += 1
            continue
        pe = o[e]
        if k > 0:
            level = pe * (1.0 - k * v)
        elif k < 0:
            level = wick[i] - WICK_BUF * v * pe
            if not level == level:         # a missing low in the flush window
                i += 1
                continue
        else:
            level = -1.0
        risk = pe - level if k != 0 else K_REF * v * pe
        floor = pe * MIN_RISK_BPS / 1e4
        if risk < floor:
            risk = floor
            if k != 0:
                level = pe - risk
        last = min(e + hold, n - 1)
        px = np.nan
        x = last
        stopped = False
        if k != 0:
            for j in range(e, last):
                if not live[j]:
                    continue
                if o[j] <= level:          # opened through it: stop-market at the open
                    px, x, stopped = o[j], j, True
                    break
                if l[j] <= level:
                    px, x, stopped = level, j, True
                    break
        if not stopped:
            while x > e and not live[x]:
                x -= 1
            px = o[x] if x == last and live[x] else c[x]
        ei[m], xi[m], gr[m], un[m], st[m] = e, x, (px - pe) / pe, risk / pe, stopped
        m += 1
        i = x if x > i else i + 1
    return ei[:m], xi[:m], gr[:m], un[:m], st[:m]


@njit(cache=True)
def prop_sim(d, risk, sized, target, daily, maxloss, max_days):
    """`riskladder.run_accounts`, and with `sized` the budget-linear overlay of
    `core/chosen.py["sizing"]`. A fresh account every day, real breaches, the
    day's loss landing before its gain. 0 open, 1 pass, 2 daily, 3 max."""
    n = len(d)
    res = np.zeros(n, np.int64)
    days = np.zeros(n, np.int64)
    for s in range(n):
        eq = 0.0
        peak = 0.0
        day = 0
        for kk in range(s, min(s + max_days, n)):
            day += 1
            mult = 1.0
            if sized:
                dd = min(eq - peak, eq)
                mult = min(1.0, max(0.25, (maxloss + dd) / maxloss))
            step = d[kk] * risk * mult
            if min(step, 0.0) <= -daily:
                res[s] = 2
                break
            low = eq + min(step, 0.0)
            if low - peak <= -maxloss or low <= -maxloss:
                res[s] = 3
                break
            eq += step
            if eq > peak:
                peak = eq
            if eq >= target:
                res[s] = 1
                break
        days[s] = day
    return res, days


def accounts(daily: np.ndarray, risk: float, sized: bool) -> dict:
    r = THUNDERBOLT
    res, days = prop_sim(daily, risk, sized, r.profit_target, r.daily_loss,
                         r.max_loss, MAX_DAYS)
    p = res == 1
    rate = float(p.mean())
    med = float(np.median(days[p])) if p.any() else None
    return {"pass_pct": round(rate * 100, 1),
            "blown_pct": round(float((res >= 2).mean()) * 100, 1),
            "open_pct": round(float((res == 0).mean()) * 100, 1),
            "days": round(med / rate, 1) if med else None}


# --------------------------------------------------------------------------- #
# one arm across the book
# --------------------------------------------------------------------------- #
def run_arm(data: list[dict], k: float, flags: list[np.ndarray]) -> pd.DataFrame:
    rows = []
    for d, flag in zip(data, flags):
        ei, xi, gr, un, st = kernel(d["o"], d["h"], d["l"], d["c"], d["live"],
                                    flag, d["sig"], d["wick"], d["inwin"], k, HOLD)
        if not len(ei):
            continue
        rows.append(pd.DataFrame({"coin": d["coin"], "entry_ts": d["idx"][ei],
                                  "exit_ts": d["idx"][xi], "gross": gr,
                                  "unit": un, "stopped": st}))
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()


DAYS_IN_WINDOW = (END - START).total_seconds() / 86400


def daily_r(tr: pd.DataFrame, cm: float) -> np.ndarray:
    r = (tr.gross - RT_BPS * cm / 1e4) / tr.unit
    s = pd.Series(r.values, index=pd.DatetimeIndex(tr.exit_ts)).resample("1D").sum()
    s = s.reindex(pd.date_range(START.normalize(), END.normalize(), freq="1D",
                                tz="UTC"), fill_value=0.0)
    return s.values


def pf(r: np.ndarray) -> float | None:
    w, lo = r[r > 0].sum(), -r[r < 0].sum()
    return round(float(w / lo), 3) if lo > 0 else None


def summarise(tr: pd.DataFrame, *, full: bool = True) -> dict:
    out = {"trades": int(len(tr))}
    if not len(tr):
        return out
    tr = tr.sort_values("exit_ts")
    for cm in COST_MULTS:
        out[f"pf_{cm}x"] = pf(((tr.gross - RT_BPS * cm / 1e4) / tr.unit).values)
    r2 = ((tr.gross - RT_BPS * 2 / 1e4) / tr.unit).values
    eq = np.concatenate(([0.0], np.cumsum(r2)))
    dd = float((eq - np.maximum.accumulate(eq)).min())
    rpd = float(r2.sum()) / DAYS_IN_WINDOW
    out.update({
        "avg_r_2x": round(float(r2.mean()), 4),
        "net_bps_2x": round(float((tr.gross.mean() - RT_BPS * 2 / 1e4) * 1e4), 2),
        "r_per_day_2x": round(rpd, 4),
        "max_dd_r_2x": round(dd, 2),
        "days_proxy": round(abs(dd) / rpd, 1) if rpd > 0 else None,
    })
    d2 = daily_r(tr, 2)
    out["sized"] = {f"{r:g}": accounts(d2, r, True) for r in RISKS}
    if not full:
        return out
    hold_h = (tr.exit_ts - tr.entry_ts).dt.total_seconds() / 3600
    # concurrency across the book: a cascade fires every coin at once
    ev = pd.concat([pd.Series(1, index=tr.entry_ts), pd.Series(-1, index=tr.exit_ts)]).sort_index()
    out.update({
        "trades_per_day": round(len(tr) / DAYS_IN_WINDOW, 2),
        "win_pct_2x": round(float((r2 > 0).mean()) * 100, 1),
        "avg_hold_h": round(float(hold_h.mean()), 1),
        "stopped_pct": round(float(tr.stopped.mean()) * 100, 1),
        "unit_bps": round(float(tr.unit.median() * 1e4), 1),
        "sharpe_2x": round(float(d2.mean() / d2.std() * np.sqrt(365)), 2) if d2.std() > 0 else None,
        "worst_day_r_2x": round(float(d2.min()), 2),
        "max_concurrent": int(ev.groupby(level=0).sum().cumsum().max()),
        "flat": {f"{r:g}": accounts(d2, r, False) for r in RISKS},
        "per_coin": {c: {"trades": int(len(g)),
                         "pf_2x": pf(((g.gross - RT_BPS * 2 / 1e4) / g.unit).values),
                         "net_bps_2x": round(float((g.gross.mean() - RT_BPS * 2 / 1e4) * 1e4), 1)}
                     for c, g in tr.groupby("coin")},
    })
    return out


def best_rung(s: dict) -> tuple[str | None, float | None]:
    """The rung with fewest budget-linear expected days, and those days."""
    rungs = [(r, v["days"]) for r, v in s.get("sized", {}).items() if v["days"]]
    return min(rungs, key=lambda x: x[1]) if rungs else (None, None)


# --------------------------------------------------------------------------- #
def screen(data: list[dict]) -> dict:
    """The 2026-09-10 screen, re-run on the 3-year window with the causal
    threshold: mean forward return from the next open, flush vs control."""
    out = {}
    for name in ("flush", "control"):
        acc = {12: [], 48: [], 288: []}
        for d in data:
            o = pd.Series(d["o"])
            ok = d[name] & d["inwin"]
            for hz in acc:
                fwd = np.log(o.shift(-1 - hz) / o.shift(-1)).values
                acc[hz].append(fwd[ok])
        out[name] = {f"{hz * 5 // 60}h": round(float(np.nanmean(np.concatenate(v))) * 1e4, 2)
                     for hz, v in acc.items()}
        out[name]["bars"] = int(sum(len(x) for x in acc[12]))
    return out


def main() -> int:
    t0 = time.time()
    OUT.mkdir(parents=True, exist_ok=True)
    data = [prepare(c) for c in COINS]
    print(f"data ready in {time.time() - t0:.0f}s  window {START.date()} -> {END.date()}")

    # the prop simulator here must be the repo's: pin it on one flat case
    probe = np.random.default_rng(0).normal(0.05, 1.0, 600)
    mine = accounts(probe, 0.01, False)
    ref = run_accounts(pd.Series(probe), 0.01, THUNDERBOLT, MAX_DAYS)
    assert abs(mine["pass_pct"] - ref["pass_rate"] * 100) < 0.05, (mine, ref)

    result = {"window": [str(START), str(END)], "screen": screen(data),
              "control_cut_bps": {d["coin"]: round(d["cut_bps"], 1) for d in data},
              "arms": {}, "control": {}, "null": {}}
    print("screen:", json.dumps(result["screen"]))

    flush = [d["flush"] for d in data]
    ctrl = [d["control"] for d in data]
    for k in STOPS:
        name = arm_name(k)
        result["arms"][name] = summarise(run_arm(data, k, flush))
        result["control"][name] = summarise(run_arm(data, k, ctrl), full=False)
        nulls = []
        for s in range(SEEDS):
            fl = [block_shuffle(pd.Series(f.astype(float)), null_seed("H-031", d["coin"], s))
                  .fillna(0.0).values > 0.5 for d, f in zip(data, flush)]
            nulls.append(summarise(run_arm(data, k, fl), full=False))
        result["null"][name] = nulls
        a = result["arms"][name]
        print(f"{name:6} trades {a['trades']:5}  PF@2x {a['pf_2x']}  "
              f"DD {a['max_dd_r_2x']}R  R/day {a['r_per_day_2x']}  "
              f"days {a['days_proxy']}  sized {best_rung(a)}  "
              f"[{time.time() - t0:.0f}s]")

    # the verdict, exactly as written in notes.md
    verdict = {}
    for name, a in result["arms"].items():
        rung, days = best_rung(a)
        null_days = []
        for nl in result["null"][name]:
            v = nl.get("sized", {}).get(rung, {}).get("days") if rung else None
            null_days.append(v if v is not None else np.inf)
        med = float(np.median(null_days)) if null_days else np.inf
        c1 = a.get("days_proxy") is not None and a["days_proxy"] <= 50
        c2 = days is not None and days <= 50 and (a.get("pf_2x") or 0) >= 1.2
        c3 = days is not None and days < med
        verdict[name] = {"c1_days_proxy": c1, "c2_sized_days": c2,
                         "c3_beats_null": c3, "rung": rung, "sized_days": days,
                         "null_median_days": None if np.isinf(med) else round(med, 1),
                         "null_pf_2x_median": float(np.median([nl.get("pf_2x") or 0
                                                               for nl in result["null"][name]])),
                         "survives": bool(c1 and c2 and c3)}
    result["verdict"] = verdict
    result["alive"] = any(v["survives"] for v in verdict.values())
    (OUT / ("stage1_full.json" if FULL else "stage1.json")).write_text(json.dumps(result, indent=1, default=str))
    print(json.dumps(verdict, indent=1))
    print(f"ALIVE: {result['alive']}   [{time.time() - t0:.0f}s]  -> {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
