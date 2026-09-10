"""VOLUME PROFILE, VOLUME PRESSURE, AND THE ASIAN RANGE — the untested volume work.

Kris, 2026-09-10: *"do whatever it takes and try to make it even better, maybe play
with volume, volume profiles, volume pressures, see what is going on in asian
session, maybe some fibonaccis, ETC ETC".*

THREE OF THOSE ARE ALREADY DEAD AND ARE NOT RE-RUN HERE:

  * **Fibonacci** - retracement and extension zones were in the 25-filter screen of
    2026-09-08. fib100 beyond .618 scored -25.7 days on 1h and **+344.6 on 4h**. A
    sign that flips across timeframes is this repo's signature for no effect.
  * **Session windows, Asia included** - six windows screened as entry filters
    (London, NY, the overlap, Asia, and two more). **Every one is slower on both
    timeframes.** "Trade only in session X" is closed by measurement.
  * **Relative volume as a minimum** - `min_rvol` is already an axis of the shipped
    grid and the blind selector picks it per fold.

WHAT IS ACTUALLY UNTESTED, and why each one is different in kind from a filter.
The lesson of the last three days is that filters do not work here - 25 screened,
24 made the evaluation slower - while things that change WHAT A SIGNAL IS are worth
running. All four arms below change the signal or the level it is measured from.

  value area    Replace the VWAP band with a real VOLUME PROFILE. Bucket the
                session's volume by price, find the point of control, expand
                until 70% of the session's volume is covered, and trade the break
                of that value area. This is the standard volume-profile trade and
                it is NOT what H-027 does today: a standard deviation about the
                VWAP assumes a shape, a value area measures one. On a session with
                two distinct trading shelves they disagree completely.
  poc           The same profile, but only its centre: replace the VWAP with the
                point of control and keep the sigma band. Isolates whether the
                gain (if any) is the CENTRE or the WIDTH.
  pressure      A volume-pressure proxy: split each bar's volume into buying and
                selling by where the close sits in the bar's range, accumulate,
                and require the break to agree with the pressure. **This is a
                PROXY and it must be labelled one** - there is no bid/ask on gold
                anywhere in this repo, so real order flow is untestable and no
                number here may be described as one.
  asia range    The Asian session's high and low as a LEVEL rather than as a
                filter. Trade the break of the 00:00-07:00 UTC range during the
                European and US day. This is the ORB family, which is dead on
                crypto and on real futures - but it has never been tested with
                gold's own overnight range as the reference.

Each arm is scored the same way everything else here is: blind quarterly
walk-forward, paired null, identical folds, grid and costs, days band from the
same bootstrap. The noise floor governs - an arm whose band overlaps the
baseline's has not been shown to differ.

Run: .venv/bin/python strategies/vwapbreak/research/volume.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from core.markets import TF_BPH                                    # noqa: E402
from core.noiseband import band                                    # noqa: E402
from core.prop_rules import PropRules                              # noqa: E402
from core.riskladder import run_accounts                           # noqa: E402
from core.run_hypothesis import run_market, window                 # noqa: E402
from strategies.vwapbreak.strategy import STRATEGY, grid_for       # noqa: E402
from strategies.vwapbreak.research.exits import UNIVERSE, WIDE_SIGMA  # noqa: E402
from strategies.vwapbreak.research.exitshape import payout_stats   # noqa: E402

ASH = PropRules(profit_target=0.02, daily_loss=0.03, max_loss=0.06,
                min_trading_days=0)
RISKS = (0.01, 0.015, 0.02, 0.03)
CELLS = (("XAUUSD", "1h"), ("XAUUSD", "4h"))

#: price bucket for the volume histogram, as a fraction of price. 5bps on gold is
#: about $1.70 - fine enough to separate two shelves, coarse enough that a session
#: of 24 hourly bars still fills buckets.
BUCKET_FRAC = 5e-4
#: share of session volume inside the value area. 70% is the convention.
VA_SHARE = 0.70
#: bars of volume-pressure memory, in hours
PRESSURE_H = 24


def _session_id(df: pd.DataFrame) -> np.ndarray:
    return np.asarray(df.index.hour == 0).cumsum()


def value_area(df: pd.DataFrame):
    """Running point of control and value-area edges, causal to the bar.

    At every bar the profile contains that bar and every earlier bar of the same
    session, and nothing else - the same information the kernel is allowed to
    decide on. Rebuilt incrementally, so it is one pass over the series.
    """
    tp = ((df.high + df.low + df.close) / 3.0).values
    vol = df.volume.replace(0, np.nan).ffill().fillna(1.0).values
    sess = _session_id(df)
    n = len(tp)
    poc = np.full(n, np.nan)
    vah = np.full(n, np.nan)
    val = np.full(n, np.nan)

    # ONE step for the whole series, not one per bar. `tp[i] / (tp[i]*frac)` is
    # the constant 1/frac, which put every bar in the same bucket and made the
    # first version of this function return nothing at all.
    step = float(np.nanmedian(tp)) * BUCKET_FRAC

    hist: dict[int, float] = {}
    cur = -1
    for i in range(n):
        if sess[i] != cur:
            cur, hist = sess[i], {}
        b = int(round(tp[i] / step))
        hist[b] = hist.get(b, 0.0) + vol[i]
        if len(hist) < 3:
            continue
        ks = np.fromiter(hist.keys(), dtype=np.int64)
        vs = np.fromiter(hist.values(), dtype=np.float64)
        order = np.argsort(ks)
        ks, vs = ks[order], vs[order]
        total = vs.sum()
        p = int(np.argmax(vs))
        lo = hi = p
        acc = vs[p]
        # expand from the point of control, always toward the heavier neighbour
        while acc < VA_SHARE * total and (lo > 0 or hi < len(ks) - 1):
            left = vs[lo - 1] if lo > 0 else -1.0
            right = vs[hi + 1] if hi < len(ks) - 1 else -1.0
            if right >= left:
                hi += 1
                acc += vs[hi]
            else:
                lo -= 1
                acc += vs[lo]
        poc[i] = ks[p] * step
        val[i] = ks[lo] * step
        vah[i] = ks[hi] * step
    return poc, val, vah


def pressure(df: pd.DataFrame, bars: int) -> np.ndarray:
    """Volume split into buying and selling by where the close sits in the bar.

    A PROXY, not order flow. `data/feeds/` holds no bid/ask for any FX or metals
    symbol, so the real quantity is not measurable here and this stands in for it:
    a bar that closes on its high is counted as buying, one that closes on its low
    as selling, and the accumulation is normalised by the volume it is made of.
    """
    h, l, c = df.high.values, df.low.values, df.close.values
    vol = df.volume.replace(0, np.nan).ffill().fillna(1.0).values
    rng = np.where(h > l, h - l, np.nan)
    frac = np.clip((c - l) / rng, 0.0, 1.0)
    signed = np.where(np.isfinite(frac), vol * (2.0 * frac - 1.0), 0.0)
    num = pd.Series(signed).rolling(bars, min_periods=max(2, bars // 4)).sum()
    den = pd.Series(vol).rolling(bars, min_periods=max(2, bars // 4)).sum()
    return (num / den.replace(0, np.nan)).fillna(0.0).values


def asia_range(df: pd.DataFrame):
    """High and low of 00:00-07:00 UTC, available only after the window closes."""
    hour = df.index.hour.values
    sess = _session_id(df)
    h, l = df.high.values, df.low.values
    n = len(h)
    hi = np.full(n, np.nan)
    lo = np.full(n, np.nan)
    cur, chi, clo, done = -1, -np.inf, np.inf, False
    for i in range(n):
        if sess[i] != cur:
            cur, chi, clo, done = sess[i], -np.inf, np.inf, False
        if hour[i] < 7:
            chi = max(chi, h[i])
            clo = min(clo, l[i])
        else:
            done = np.isfinite(chi) and chi > -np.inf
            if done:
                hi[i], lo[i] = chi, clo
    return hi, lo


class VolumeVariant:
    """H-027's kernel, with the level and band it measures from replaced."""

    extra_column = "z"

    def __init__(self, name: str, kind: str):
        self.name, self.kind = name, kind

    def features(self, df: pd.DataFrame):
        f = dict(STRATEGY.features(df))
        c = df.close.values
        if self.kind == "baseline":
            return f
        if self.kind in ("va", "poc"):
            poc, val, vah = value_area(df)
            if self.kind == "poc":
                # centre swapped, width kept: z measured about the point of
                # control in units of the existing volume-weighted sigma
                sd = f["sd"]
                with np.errstate(invalid="ignore", divide="ignore"):
                    z = (c - poc) / np.where(sd > np.abs(poc) * 1e-6, sd, np.nan)
                f["z"] = z
                return f
            half = (vah - val) / 2.0
            mid = (vah + val) / 2.0
            with np.errstate(invalid="ignore", divide="ignore"):
                z = (c - mid) / np.where(half > np.abs(mid) * 1e-6, half, np.nan)
            f["z"], f["sd"] = z, half
            return f
        if self.kind == "pressure":
            bars = max(2, int(round(PRESSURE_H * TF_BPH[_TF[0]])))
            p = pressure(df, bars)
            z = f["z"]
            # the break must agree with the accumulated pressure; blanking z is
            # how the gate is applied, so the shipped kernel is untouched
            f["z"] = np.where(np.sign(z) == np.sign(p), z, np.nan)
            return f
        if self.kind == "asia":
            hi, lo = asia_range(df)
            mid = (hi + lo) / 2.0
            half = (hi - lo) / 2.0
            with np.errstate(invalid="ignore", divide="ignore"):
                z = (c - mid) / np.where(half > np.abs(mid) * 1e-6, half, np.nan)
            f["z"], f["sd"] = z, half
            return f
        raise KeyError(self.kind)                      # pragma: no cover

    def new_cache(self):
        g = getattr(STRATEGY, "new_cache", None)
        return g() if callable(g) else {}

    def grid(self, tf: str):
        base, seen, out = grid_for(TF_BPH[tf]), set(), []
        for cfg in base:
            for s in WIDE_SIGMA:
                c = dict(cfg)
                c["stop_sig"] = s
                key = tuple(sorted(c.items()))
                if key not in seen:
                    seen.add(key)
                    out.append(c)
        return out

    def run(self, df, cfg, fee_bps, slip_bps, feats=None, **kw):
        return STRATEGY.run(df, cfg, fee_bps, slip_bps,
                            feats=feats if feats is not None else self.features(df),
                            **kw)


_TF = ["1h"]        # set by main() so `pressure` knows the bar size

ARMS = (
    ("baseline (vwap band)", "baseline"),
    ("value area 70%", "va"),
    ("point of control", "poc"),
    ("volume pressure agrees", "pressure"),
    ("asian range break", "asia"),
)


def score(res: dict) -> dict:
    tr = res["_trades"]
    daily = pd.Series(tr.r.values,
                      index=pd.DatetimeIndex(tr.exit_ts)).resample("1D").sum()
    best = None
    for risk in RISKS:
        a = run_accounts(daily, risk, ASH)
        if not a["pass_rate"]:
            continue
        exp = a["median_days"] / a["pass_rate"]
        line = {"risk_pct": risk * 100, "pass_pct": round(a["pass_rate"] * 100, 1),
                "blown_pct": round((a["fail_max"] + a["fail_daily"]) * 100, 1),
                "days": round(exp, 1), "band": band(daily, risk, rules=ASH)}
        if best is None or exp < best["days"]:
            best = line
    return {**(best or {"days": None}), **payout_stats(daily.values * 0.02),
            "trades": res.get("trades"), "win_pct": res.get("win_pct"),
            "pf": res.get("pf"), "pf_2x": res.get("pf_2x"),
            "avg_r": res.get("avg_r"), "trades_per_day": res.get("trades_per_day"),
            "beats_null": res.get("beats_null"), "null_pf": res.get("null_pf")}


def main() -> int:
    span = window([s for v in UNIVERSE.values() for s in v], ["1h", "4h"])
    out = {}
    for sym, tf in CELLS:
        _TF[0] = tf
        print(f"\n=== {sym} {tf} " + "=" * 46)
        print(f"{'arm':26}{'trades':>7}{'win%':>7}{'PF2x':>7}{'null':>7}"
              f"{'days':>7}{'band':>12}{'pass%':>7}{'bestday':>9}")
        for tag, kind in ARMS:
            try:
                res = run_market(VolumeVariant(f"vb_{kind}", kind), sym, tf,
                                 pipe_kw={"floors": (30,), "topn": (5,)},
                                 null_seeds=1, span=span)
            except Exception as exc:                    # noqa: BLE001
                print(f"{tag:26} FAILED: {exc}", flush=True)
                continue
            s = score(res)
            out[f"{sym}|{tf}|{tag}"] = s
            b = s.get("band") or {}
            print(f"{tag:26}{s['trades'] or 0:7}{s['win_pct'] or 0:7.1f}"
                  f"{s['pf_2x'] or 0:7.3f}{(s['null_pf'] or 0):7.3f}"
                  f"{s['days'] or 0:7.1f}"
                  f"{('%.0f-%.0f' % (b.get('days_lo', 0), b.get('days_hi', 0))):>12}"
                  f"{s['pass_pct'] or 0:7.1f}"
                  f"{(s['best_day_share_net'] or 0):9.3f}", flush=True)

    dest = ROOT / "backtests" / "vwapbreak" / "volume.json"
    dest.write_text(json.dumps({"cells": [list(c) for c in CELLS],
                                "bucket_frac": BUCKET_FRAC, "va_share": VA_SHARE,
                                "rows": out}, indent=1, default=str))
    print(f"\nwrote {dest.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
