"""THE ANCHOR — the one VWAP-native axis H-027 has never tested.

Kris, 2026-09-10: *"lets stay with baseline of no R:R... what could be our next
steps to improve this and go even deeper into vwap?"*

WHAT THE STRATEGY ACTUALLY READS TODAY. `STRATEGY.features` calls
`vwap_series(df, 0, 0)` - a VWAP that resets at **00:00 UTC**, every day, on every
market. Every result this hypothesis has ever produced is measured against that
one definition of "the VWAP", and both the signal AND the stop come from it: the
entry is `|close - vwap| >= thr x vwstd` and the risk is `stop_sig x vwstd`.

WHY THE ANCHOR IS THE RIGHT PLACE TO LOOK NEXT, and not another filter. Twenty-five
entry FILTERS have been screened on this hypothesis and 24 of 25 raised profit
factor while LOWERING R per day; the one survivor lost to its own shuffled control.
Filters are exhausted. The anchor is different in kind: it does not select among
the existing signals, it changes what a signal IS. A gold bar sits 1.5 sigma above
its midnight VWAP and 0.3 sigma above its London-open VWAP - those are different
trades, not the same trade filtered.

AND THERE IS A PRIOR. H-001 established on this repo's own data that the NY cash
open (13:30 UTC) is the only session clock carrying anything on FX and metals, and
midnight UTC is not a moment any gold desk cares about. If the anchor matters at
all, the US open is where it should show - snapped to 13:00 on 1h bars and 12:00
on 4h, because a 13:30 anchor does not exist on either grid (see `_snap`).

THE ARMS, all on the same folds, same costs, same grid, entries otherwise
untouched:

    utc 00:00     the shipped anchor - the baseline every other arm is read against
    london 07:00  the European open (04:00 on 4h bars)
    ny 13:00      the US cash open, H-001's only surviving clock (12:00 on 4h)
    weekly        one anchor per week (Monday 00:00) - a much longer memory
    rolling 96    a trailing 4-day VWAP, no session reset at all
    rolling 384   a trailing fortnight, matching the traded horizon
    daily+weekly  the daily anchor for the signal, but the trade is only taken
                  when price sits on the SAME side of the weekly VWAP. A
                  VWAP-native agreement gate rather than a foreign indicator -
                  implemented by blanking z, so the kernel is untouched.
    unweighted    the shipped anchor with NO volume weighting - a session TWAP.
                  The mechanism check of 2026-09-10 found the two z series
                  correlate 0.998 on gold and that the unweighted one has better
                  follow-through, so this arm asks whether the "V" in VWAP earns
                  its place at all.

HOW TO READ THE RESULT. The noise floor governs: an arm whose expected-days band
overlaps the baseline's has not been shown to differ. The paired null is the
primary gate, as always. A win here would be an arm that beats the baseline AND
its own null on both timeframes.

Run: .venv/bin/python strategies/vwapbreak/research/anchors.py
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
from strategies.vwap.sweep import rolling_vwap, vwap_series        # noqa: E402
from strategies.vwapbreak.strategy import STRATEGY, grid_for       # noqa: E402
from strategies.vwapbreak.research.exits import UNIVERSE, WIDE_SIGMA  # noqa: E402
from strategies.vwapbreak.research.exitshape import payout_stats   # noqa: E402

ASH = PropRules(profit_target=0.02, daily_loss=0.03, max_loss=0.06,
                min_trading_days=0)
RISKS = (0.01, 0.015, 0.02, 0.03)
CELLS = (("XAUUSD", "1h"), ("XAUUSD", "4h"))


def _weekly_mask(df: pd.DataFrame) -> np.ndarray:
    """Monday at the first bar boundary of the day - the weekly reset."""
    return np.asarray((df.index.dayofweek == 0) & (df.index.hour == 0))


def _snap(hour: int, tf: str) -> int:
    """The nearest anchor hour that EXISTS on this timeframe.

    THIS GUARD EXISTS BECAUSE THE FIRST RUN OF THIS FILE PRODUCED A NUMBER FROM A
    BUG. `vwap_series` masks on (hour, minute), and 13:30 never occurs on a 1h
    series - so the mask was empty, `cumsum` gave one session for the whole three
    years, and the "NY anchor" arm was silently measuring a VWAP anchored at the
    start of the data. It printed 64.5% win rate and 402 expected days, which is
    what a nonsense arm looks like when nothing checks it.
    """
    step = max(1, int(round(1.0 / TF_BPH[tf])))
    return (hour // step) * step


def _vwap_on(df: pd.DataFrame, mask: np.ndarray, twap: bool = False):
    """VWAP and volume-weighted sigma resetting wherever `mask` is True.

    The same arithmetic as `vwap_series`, generalised from an (hour, minute) to
    an arbitrary reset mask so a weekly anchor is expressible. Kept here rather
    than pushed into `strategies/vwap/sweep.py`, because that file is imported by
    the board's own kernel and this is research.
    """
    tp = (df.high + df.low + df.close) / 3.0
    vol = (pd.Series(1.0, index=df.index) if twap
           else df.volume.replace(0, np.nan).ffill().fillna(1.0))
    sess = pd.Series(mask, index=df.index).cumsum()
    pv = (tp * vol).groupby(sess).cumsum()
    v = vol.groupby(sess).cumsum()
    vwap = pv / v
    p2v = (tp * tp * vol).groupby(sess).cumsum()
    vwstd = np.sqrt(((p2v / v) - vwap * vwap).clip(lower=0.0))
    return vwap.values, vwstd.values


class AnchorVariant:
    """H-027 with the VWAP anchored somewhere else. Nothing else changes."""

    extra_column = "z"

    def __init__(self, name: str, kind: str, arg=None, agree_weekly: bool = False,
                 twap: bool = False):
        self.twap = twap
        self.name = name
        self.kind = kind            # "session" | "weekly" | "rolling"
        self.arg = arg
        self.agree_weekly = agree_weekly

    def features(self, df: pd.DataFrame):
        f = dict(STRATEGY.features(df))
        if self.kind == "session":
            hour = int(self.arg)
            mask = np.asarray(df.index.hour == hour)
            if mask.sum() < 10:
                raise ValueError(f"anchor hour {hour} never occurs on this series")
            vwap, vwstd = _vwap_on(df, mask, twap=self.twap)
        elif self.kind == "weekly":
            vwap, vwstd = _vwap_on(df, _weekly_mask(df))
        elif self.kind == "rolling":
            vwap, vwstd, _ = rolling_vwap(df, int(self.arg))
        else:                                     # pragma: no cover
            raise KeyError(self.kind)

        c = df.close.values
        with np.errstate(invalid="ignore", divide="ignore"):
            z = (c - vwap) / np.where(vwstd > vwap * 1e-6, vwstd, np.nan)

        if self.agree_weekly:
            # the trade is only allowed when price is on the same side of the
            # WEEKLY vwap as of the signal bar. Blanking z is how the gate is
            # applied: the shipped kernel skips a bar whose z is not finite, so
            # no kernel change is needed and no other behaviour moves.
            wv, _ = _vwap_on(df, _weekly_mask(df))
            same = np.sign(c - wv) == np.sign(z)
            z = np.where(same, z, np.nan)

        f["z"], f["sd"] = z, vwstd
        return f

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


def ARMS(tf: str):
    bph = TF_BPH[tf]
    ldn, ny = _snap(7, tf), _snap(13, tf)
    return [
        ("utc 00:00 (shipped)", AnchorVariant("vb_utc", "session", 0)),
        (f"london {ldn:02d}:00", AnchorVariant("vb_ldn", "session", ldn)),
        (f"ny {ny:02d}:00", AnchorVariant("vb_ny", "session", ny)),
        ("weekly", AnchorVariant("vb_wk", "weekly")),
        (f"rolling {int(96 * bph)} bars", AnchorVariant("vb_r96", "rolling", int(96 * bph))),
        (f"rolling {int(384 * bph)} bars", AnchorVariant("vb_r384", "rolling", int(384 * bph))),
        ("daily + weekly agree", AnchorVariant("vb_agree", "session", 0,
                                               agree_weekly=True)),
        # free to run beside the anchors and it answers 1.2 of NEXT_VWAP.md:
        # the same band with no volume weighting at all.
        ("utc 00:00, unweighted", AnchorVariant("vb_twap", "session", 0, twap=True)),
    ]


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
        print(f"\n=== {sym} {tf} " + "=" * 46)
        print(f"{'anchor':24}{'trades':>7}{'win%':>7}{'PF2x':>7}{'null':>7}"
              f"{'days':>7}{'band':>12}{'pass%':>7}{'bestday':>9}")
        for tag, arm in ARMS(tf):
            res = run_market(arm, sym, tf, pipe_kw={"floors": (30,), "topn": (5,)},
                             null_seeds=1, span=span)
            s = score(res)
            out[f"{sym}|{tf}|{tag}"] = s
            b = s.get("band") or {}
            print(f"{tag:24}{s['trades'] or 0:7}{s['win_pct'] or 0:7.1f}"
                  f"{s['pf_2x'] or 0:7.3f}{(s['null_pf'] or 0):7.3f}"
                  f"{s['days'] or 0:7.1f}"
                  f"{('%.0f-%.0f' % (b.get('days_lo', 0), b.get('days_hi', 0))):>12}"
                  f"{s['pass_pct'] or 0:7.1f}"
                  f"{(s['best_day_share_net'] or 0):9.3f}", flush=True)

    dest = ROOT / "backtests" / "vwapbreak" / "anchors.json"
    dest.write_text(json.dumps({"cells": [list(c) for c in CELLS], "rows": out},
                               indent=1, default=str))
    print(f"\nwrote {dest.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
