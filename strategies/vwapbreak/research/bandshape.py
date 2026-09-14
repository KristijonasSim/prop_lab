"""H-040 — swap the BAND, keep everything else. Pre-registration: BANDSHAPE.md.

The last untested axis on H-027. Four axes are already closed and every one of
them changed what happens AFTER price crosses the band; none changed the band.

HOW IT AVOIDS TOUCHING THE KERNEL. `VwapBreakStrategy.run` reads `z` and `sd`
out of the feature dict and nothing else about the band. So an arm only has to
override `features()` and hand back a different `z` and `sd`; `grid()` and
`run()` delegate to the shipped object. The kernel is not copied, so no manifest
hash moves and the board cannot go stale on the strength of this study.

Run: .venv/bin/python strategies/vwapbreak/research/bandshape.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from core.noiseband import band as nb_band                          # noqa: E402
from core.prop_rules import PropRules                               # noqa: E402
from core.riskladder import run_accounts                            # noqa: E402
from core.run_hypothesis import run_market, window                  # noqa: E402
from strategies.vwap.sweep import vwap_series                       # noqa: E402
from strategies.vwapbreak.strategy import STRATEGY                  # noqa: E402

THUNDERBOLT = PropRules(profit_target=0.06, daily_loss=0.03, max_loss=0.06,
                        min_trading_days=0)
RISKS = (0.01, 0.015, 0.02, 0.03)
CELLS = [("XAUUSD", "1h"), ("XAUUSD", "4h")]
PCT_BAND = 0.001                      # 10 bps, the `pct` arm's fixed width


def _rvol(df: pd.DataFrame) -> np.ndarray:
    """Identical to the shipped feature, including the shift that stops a bar
    being judged on its own completed volume."""
    v = pd.Series(df.volume.values, index=df.index)
    base = v.rolling(20 * 24, min_periods=120).mean().shift(1)
    return (v / base).fillna(0.0).values


def _atr(df: pd.DataFrame, n: int = 14) -> np.ndarray:
    h, l, c = df.high.values, df.low.values, df.close.values
    pc = np.concatenate([[c[0]], c[:-1]])
    tr = np.maximum(h - l, np.maximum(np.abs(h - pc), np.abs(l - pc)))
    return pd.Series(tr).rolling(n, min_periods=n).mean().values


def _semi(df: pd.DataFrame, vwap: np.ndarray, sess: pd.Series) -> tuple:
    """Volume-weighted semi-deviation above and below the running VWAP.

    Gold's up-moves and down-moves are not the same size; one symmetric band
    prices them as if they are. Each side is the dispersion of the bars that
    actually sat on that side of the VWAP, accumulated within the session.
    """
    tp = ((df.high + df.low + df.close) / 3.0).values
    vol = df.volume.replace(0, np.nan).ffill().fillna(1.0).values
    d = tp - vwap
    up, dn = np.where(d > 0, d, 0.0), np.where(d < 0, d, 0.0)
    g = pd.Series(sess.values, index=df.index)
    out = []
    for side in (up, dn):
        num = pd.Series(side * side * vol, index=df.index).groupby(g).cumsum()
        den = pd.Series(vol, index=df.index).groupby(g).cumsum()
        out.append(np.sqrt((num / den).clip(lower=0.0).values))
    return out[0], out[1]


class BandArm:
    """The shipped strategy with a different band. Everything else delegates."""

    def __init__(self, tag: str, kind: str) -> None:
        self.tag, self.kind = tag, kind
        self.name = f"vwapbreak_{tag}"
        self.extra_column = "z"

    def grid(self, tf: str):
        return STRATEGY.grid(tf)

    def run(self, df, cfg, fee_bps, slip_bps, feats=None, **kw):
        return STRATEGY.run(df, cfg, fee_bps, slip_bps,
                            feats=feats if feats is not None else self.features(df), **kw)

    def features(self, df: pd.DataFrame):
        if self.kind == "baseline":
            return STRATEGY.features(df)

        vwap, vwstd, _ = vwap_series(df, 0, 0)
        c = df.close.values
        at_anchor = (df.index.hour == 0) & (df.index.minute == 0)
        sess = pd.Series(at_anchor.cumsum(), index=df.index)

        if self.kind == "atr":
            width_up = width_dn = _atr(df)
        elif self.kind == "pct":
            width_up = width_dn = vwap * PCT_BAND
        elif self.kind == "sterr":
            k = sess.groupby(sess).cumcount().values + 1
            width_up = width_dn = vwstd / np.sqrt(k)
        elif self.kind == "asym":
            width_up, width_dn = _semi(df, vwap, sess)
        else:
            raise ValueError(self.kind)

        d = c - vwap
        floor = vwap * 1e-6                    # the PX_EPS_FRAC discipline
        wu = np.where(width_up > floor, width_up, np.nan)
        wd = np.where(width_dn > floor, width_dn, np.nan)
        with np.errstate(invalid="ignore", divide="ignore"):
            z = np.where(d >= 0, d / wu, d / wd)
        # the STOP uses the side the trade is on; one array, so take the side
        # the signal would be: a long is triggered above, a short below.
        sd = np.where(d >= 0, width_up, width_dn)
        return {"z": z, "sd": sd, "rvol": _rvol(df),
                "hour": df.index.hour.values.astype(np.int64),
                "live": (df.volume.values > 0).astype(np.uint8)}


ARMS = [BandArm("base", "baseline"), BandArm("atr", "atr"),
        BandArm("pct", "pct"), BandArm("sterr", "sterr"),
        BandArm("asym", "asym")]


def score(res: dict) -> dict:
    tr = res["_trades"]
    if not len(tr):
        return {"days": None, "trades": 0}
    daily = pd.Series(tr.r.values,
                      index=pd.DatetimeIndex(tr.exit_ts)).resample("1D").sum()
    best = None
    for risk in RISKS:
        a = run_accounts(daily, risk, THUNDERBOLT)
        if not a["pass_rate"]:
            continue
        exp = a["median_days"] / a["pass_rate"]
        line = {"risk_pct": risk * 100, "pass_pct": round(a["pass_rate"] * 100, 1),
                "blown_pct": round((a["fail_max"] + a["fail_daily"]) * 100, 1),
                "days": round(exp, 1),
                "band": nb_band(daily, risk, rules=THUNDERBOLT)}
        if best is None or exp < best["days"]:
            best = line
    return {**(best or {"days": None}), "trades": res.get("trades"),
            "win_pct": res.get("win_pct"), "pf_2x": res.get("pf_2x"),
            "beats_null": res.get("beats_null"), "null_pf": res.get("null_pf"),
            "trades_per_day": res.get("trades_per_day")}


def main() -> int:
    span = window(["XAUUSD"], ["1h", "4h"])
    out = {}
    for sym, tf in CELLS:
        print(f"\n=== {sym} {tf} " + "=" * 52, flush=True)
        hdr = (f"{'arm':10}{'trades':>7}{'tpd':>6}{'win%':>7}{'PF2x':>7}"
               f"{'null':>7}{'days':>7}{'band':>13}{'pass%':>7}{'blown%':>8}")
        print(hdr); print("-" * len(hdr), flush=True)
        for arm in ARMS:
            try:
                res = run_market(arm, sym, tf,
                                 pipe_kw={"floors": (30,), "topn": (5,)},
                                 null_seeds=1, span=span)
                s = score(res)
            except Exception as e:                     # an arm may produce nothing
                print(f"{arm.tag:10}  FAILED: {type(e).__name__}: {e}", flush=True)
                out[f"{sym}|{tf}|{arm.tag}"] = {"error": f"{type(e).__name__}: {e}"}
                continue
            out[f"{sym}|{tf}|{arm.tag}"] = s
            b = s.get("band") or {}
            print(f"{arm.tag:10}{s.get('trades') or 0:>7}"
                  f"{s.get('trades_per_day') or 0:>6.2f}{s.get('win_pct') or 0:>7.1f}"
                  f"{s.get('pf_2x') or 0:>7.3f}{s.get('null_pf') or 0:>7.3f}"
                  f"{s.get('days') or 0:>7.1f}"
                  f"{('%.1f-%.1f' % (b.get('days_lo', 0), b.get('days_hi', 0))):>13}"
                  f"{s.get('pass_pct') or 0:>7.1f}{s.get('blown_pct') or 0:>8.1f}",
                  flush=True)

    dest = ROOT / "backtests" / "vwapbreak" / "bandshape.json"
    dest.write_text(json.dumps({"cells": [list(c) for c in CELLS],
                                "pct_band": PCT_BAND, "rows": out},
                               indent=1, default=str))
    print(f"\nwrote {dest.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
