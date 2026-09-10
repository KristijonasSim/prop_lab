"""THE SQUEEZE — every VWAP variant still untested, in one blind walk-forward.

Kris, 2026-09-10: *"i want to finish with vwap, squeeze it as much as we can, launch
it on demo and move to other hypothesis"*.

This is the last entry-side run on H-027. Everything in `VWAP_BACKLOG.md` tier 2
that has not already been killed is an arm here, so that when it is done the axis
is closed with a measurement rather than with an opinion.

WHAT IS ALREADY DEAD, and is not re-run: clock anchors (8 arms, best on 1h is worst
on 4h), volume profile and point of control (value area loses to its own null),
daily+weekly agreement, fixed targets 1R-12R, 25 entry filters, six session
windows, fibonacci zones, and sub-hour timeframes (the horizon is wall-clock, so
the bar size changes trades per day by 2%).

THE ARMS. Each one changes what the band IS or where it is measured from. None of
them is a filter on the existing signal - that family is exhausted.

  swing anchor    Reset the VWAP at the last CONFIRMED swing high or low instead
                  of at a clock time. The clock-anchor sweep was flat, but every
                  arm in it was a time anchor; this is the anchored VWAP as
                  traders actually use it, and it measures the average price paid
                  since the market last turned - the quantity a trapped position
                  cares about. A pivot is confirmed k bars AFTER it prints, and
                  the anchor moves only on confirmation, so nothing is read early.
  sunday week     The weekly arm re-anchored to the real week open, 22:00 Sunday
                  UTC, rather than Monday 00:00. The old arm threw away the
                  weekend gap - the most information-dense moment of gold's week.
  confluence      Daily, weekly and monthly VWAPs, gated on how tightly they
                  cluster. Not a direction filter: a COMPRESSION detector built
                  from the strategy's own material.
  atr band        VWAP +- k x ATR(14). Sigma collapses early in a session and grows
                  all day, so the rule fires on a different-sized move at 02:00
                  than at 20:00 - an inconsistency nobody chose. ATR has no such
                  drift. ATR was tested as a STOP and never as the BAND.
  pct band        VWAP +- a fixed number of basis points. Crude on purpose: it
                  says how much of the edge is the band and how much is simply
                  distance from the mean.
  stderr band     VWAP +- k x sigma/sqrt(n). The opposite shape to sigma: wide
                  when little is known, tight once the session has accumulated
                  observations. If the real problem is firing too easily early,
                  this fixes it and the percentage band does not.
  asymmetric      Separate volume-weighted semi-deviations above and below. The
                  shipped rule uses one sigma for both directions, so the long and
                  short thresholds are not equally hard to reach and any
                  directional asymmetry in the result could be that artifact.
  compression     Take the break only when the band width sits in the bottom
                  quartile of its own recent history. The squeeze idea in VWAP
                  terms - a state, not a filter: the population changes rather
                  than merely shrinking.

Run: .venv/bin/python strategies/vwapbreak/research/squeeze.py
"""
from __future__ import annotations

import json
import sys
import time
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
from strategies.vwapbreak.research.anchors import _vwap_on         # noqa: E402

ASH = PropRules(profit_target=0.02, daily_loss=0.03, max_loss=0.06,
                min_trading_days=0)
RISKS = (0.01, 0.015, 0.02, 0.03)
CELLS = (("XAUUSD", "1h"), ("XAUUSD", "4h"))

ATR_LEN = 14
PCT_BAND_BPS = 20.0          # comparable to gold's median session sigma (18bps)
PIVOT_K = 12                 # bars either side for a confirmed swing
CONFLUENCE_PCT = 0.004       # daily/weekly/monthly within 0.4% of each other
COMPRESSION_Q = 0.25         # bottom quartile of trailing band width


def _daily_mask(df):
    return np.asarray(df.index.hour == 0)


def _weekly_mask(df):
    return np.asarray((df.index.dayofweek == 0) & (df.index.hour == 0))


def _sunday_mask(df):
    return np.asarray((df.index.dayofweek == 6) & (df.index.hour == 22))


def _monthly_mask(df):
    return np.asarray((df.index.day == 1) & (df.index.hour == 0))


def _atr(df, n=ATR_LEN):
    h, l, c = df.high.values, df.low.values, df.close.values
    pc = np.roll(c, 1)
    pc[0] = c[0]
    tr = np.maximum(h - l, np.maximum(np.abs(h - pc), np.abs(l - pc)))
    return pd.Series(tr).ewm(alpha=1.0 / n, adjust=False).mean().values


def _swing_mask(df, k=PIVOT_K):
    """True on the bar where a swing high or low k bars back becomes CONFIRMED.

    Causal by construction: bar i can only confirm a pivot at i-k, because the k
    bars after the pivot are what confirm it, and those are bars i-k+1..i.
    """
    h, l = df.high.values, df.low.values
    n = len(h)
    out = np.zeros(n, dtype=bool)
    for i in range(2 * k, n):
        p = i - k
        w_h, w_l = h[p - k:i + 1], l[p - k:i + 1]
        if h[p] >= w_h.max() or l[p] <= w_l.min():
            out[i] = True
    return out


def _semi_dev(df, mask):
    """Volume-weighted dispersion above and below the running VWAP, separately."""
    tp = ((df.high + df.low + df.close) / 3.0)
    vol = df.volume.replace(0, np.nan).ffill().fillna(1.0)
    sess = pd.Series(mask, index=df.index).cumsum()
    pv = (tp * vol).groupby(sess).cumsum()
    v = vol.groupby(sess).cumsum()
    vwap = pv / v
    dev = tp - vwap
    up = (np.maximum(dev, 0.0) ** 2 * vol).groupby(sess).cumsum() / v
    dn = (np.minimum(dev, 0.0) ** 2 * vol).groupby(sess).cumsum() / v
    return vwap.values, np.sqrt(up.values), np.sqrt(dn.values)


class Squeeze:
    extra_column = "z"

    def __init__(self, name, kind):
        self.name, self.kind = name, kind

    def features(self, df: pd.DataFrame):
        f = dict(STRATEGY.features(df))
        c = df.close.values
        k = self.kind
        if k == "baseline":
            return f

        if k == "swing":
            vwap, sd = _vwap_on(df, _swing_mask(df))
        elif k == "sunday":
            vwap, sd = _vwap_on(df, _sunday_mask(df))
        elif k in ("atr", "pct", "stderr", "compression", "confluence"):
            vwap, sd = _vwap_on(df, _daily_mask(df))
            if k == "atr":
                sd = _atr(df)
            elif k == "pct":
                sd = c * PCT_BAND_BPS / 1e4
            elif k == "stderr":
                n = pd.Series(1.0, index=df.index).groupby(
                    pd.Series(_daily_mask(df), index=df.index).cumsum()).cumsum().values
                sd = sd / np.sqrt(np.maximum(n, 1.0))
        elif k == "asym":
            vwap, up, dn = _semi_dev(df, _daily_mask(df))
            with np.errstate(invalid="ignore", divide="ignore"):
                side_sd = np.where(c >= vwap, up, dn)
                z = (c - vwap) / np.where(side_sd > np.abs(vwap) * 1e-6, side_sd, np.nan)
            f["z"], f["sd"] = z, side_sd
            return f
        else:                                            # pragma: no cover
            raise KeyError(k)

        with np.errstate(invalid="ignore", divide="ignore"):
            z = (c - vwap) / np.where(sd > np.abs(vwap) * 1e-6, sd, np.nan)

        if k == "compression":
            # band width in bps, against its own trailing distribution
            w = pd.Series(sd / np.where(c > 0, c, np.nan) * 1e4)
            q = w.rolling(24 * 20, min_periods=200).quantile(COMPRESSION_Q).shift(1)
            z = np.where(w.values <= q.values, z, np.nan)
        elif k == "confluence":
            dv, _ = _vwap_on(df, _daily_mask(df))
            wv, _ = _vwap_on(df, _weekly_mask(df))
            mv, _ = _vwap_on(df, _monthly_mask(df))
            spread = (np.nanmax(np.vstack([dv, wv, mv]), axis=0)
                      - np.nanmin(np.vstack([dv, wv, mv]), axis=0))
            z = np.where(spread <= np.abs(dv) * CONFLUENCE_PCT, z, np.nan)

        f["z"], f["sd"] = z, sd
        return f

    def new_cache(self):
        g = getattr(STRATEGY, "new_cache", None)
        return g() if callable(g) else {}

    def grid(self, tf):
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
                            feats=feats if feats is not None else self.features(df), **kw)


ARMS = (("baseline", "baseline"), ("swing anchor", "swing"),
        ("sunday week anchor", "sunday"), ("anchor confluence", "confluence"),
        ("atr band", "atr"), ("pct band 20bps", "pct"),
        ("standard-error band", "stderr"), ("asymmetric band", "asym"),
        ("compression only", "compression"))


def score(res):
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
    q = daily.groupby(daily.index.to_period("Q")).sum()
    tot = float(q.sum())
    return {**(best or {"days": None}), **payout_stats(daily.values * 0.02),
            "trades": res.get("trades"), "win_pct": res.get("win_pct"),
            "pf": res.get("pf"), "pf_2x": res.get("pf_2x"),
            "trades_per_day": res.get("trades_per_day"),
            "beats_null": res.get("beats_null"), "null_pf": res.get("null_pf"),
            "total_r": round(tot, 1),
            "best_q_share": round(float(q.max()) / tot, 3) if tot > 0 else None}


def main() -> int:
    span = window([s for v in UNIVERSE.values() for s in v], ["1h", "4h"])
    out = {}
    for sym, tf in CELLS:
        print(f"\n=== {sym} {tf} " + "=" * 52)
        print(f"{'arm':22}{'trades':>7}{'win%':>7}{'PF2x':>7}{'null':>7}{'days':>7}"
              f"{'band':>12}{'pass%':>7}{'blown%':>8}{'bestQ':>7}{'mins':>6}")
        for tag, kind in ARMS:
            t0 = time.time()
            try:
                res = run_market(Squeeze(f"vb_{kind}", kind), sym, tf,
                                 pipe_kw={"floors": (30,), "topn": (5,)},
                                 null_seeds=1, span=span)
            except Exception as exc:                     # noqa: BLE001
                print(f"{tag:22} FAILED: {exc}", flush=True)
                continue
            s = score(res)
            out[f"{sym}|{tf}|{tag}"] = s
            b = s.get("band") or {}
            print(f"{tag:22}{s['trades'] or 0:7}{s['win_pct'] or 0:7.1f}"
                  f"{s['pf_2x'] or 0:7.3f}{(s['null_pf'] or 0):7.3f}"
                  f"{s['days'] or 0:7.1f}"
                  f"{('%.0f-%.0f' % (b.get('days_lo', 0), b.get('days_hi', 0))):>12}"
                  f"{s['pass_pct'] or 0:7.1f}{(s['blown_pct'] or 0):8.1f}"
                  f"{(s['best_q_share'] or 0) * 100:6.0f}%{(time.time()-t0)/60:6.1f}",
                  flush=True)
            (ROOT / "backtests" / "vwapbreak" / "squeeze.json").write_text(
                json.dumps({"rows": out}, indent=1, default=str))
    print("\nwrote backtests/vwapbreak/squeeze.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
