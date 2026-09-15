"""H-044 — the ANCHOR family. Same rule, a different centre line.

Kris, 2026-09-15: *"if its possible with vwap it might be possible with order
flow, EMA, fibonaci RSI or some other instrument"*.

THE REFRAME IS THE IDEA, AND IT IS A GOOD ONE. H-027 is not "VWAP works". It is
"a band breakout with a very wide stop and a long hold works on gold". The VWAP
is only the line the band is drawn around. Swap that line, keep everything else
identical, and the question becomes whether the EDGE lives in the VWAP or in the
STRUCTURE.

WHAT IS ALREADY DEAD AND IS NOT BEING RE-RUN:
  * EMA x VWAP CROSS (H-003) - 284k backtests, real median PF 0.705 against a
    phase-randomised 0.757. Worse than noise. That was a CROSS rule, not this
    structure with an EMA anchor, so it does not settle this.
  * Fibonacci as a FILTER on H-027 - sign-flipped across timeframes (-25.7 days
    on 1h, +344.6 on 4h). Dead as a gate; never tried as an anchor.
  * Order flow on GOLD - not testable. `data/dukascopy_raw/XAUUSD` holds bid
    candles, not ticks; there is no bid/ask volume on disk. Backlog H-030.
  * The eight VWAP ANCHOR definitions (`anchors.py`) - session, London, NY,
    weekly, rolling, TWAP. All VWAP-family. None of them left the family.
  * The band SCALE (H-040, `bandshape.py`) - atr, pct, sterr, asym. All four
    dead. THAT STUDY CHANGED THE BAND WIDTH; THIS ONE CHANGES THE CENTRE.

RSI has never been tested in this repo at all.

THE HONEST PRIOR IS POOR. H-040 swapped the band width and all four arms died.
Seven axes on H-027 are closed. If the edge is structural rather than VWAP-
specific, some arm here should come close to the baseline; if VWAP is doing the
work, they will all be worse and that closes the eighth axis.

## Arms, fixed before the run

Each arm supplies (anchor, width). `z = (close - anchor) / width` and the stop is
`stop_sig x width`, exactly as shipped. Nothing else changes: same grid, same
folds, same costs, same floors-30 / top-5 selection, same blind walk-forward.

  baseline   session VWAP        + volume-weighted sd      (shipped)
  ema        EMA(24)             + rolling sd(24) of close
  sma        SMA(24)             + rolling sd(24) of close
  keltner    EMA(24)             + ATR(14)
  donchian   mid of 24-bar range + half the 24-bar range
  prevclose  previous day close  + ATR(14)
  rsi        price where RSI(14) = 50, approximated by EMA(24), banded by the
             RSI distance from 50 in ATR units - the only arm that is not a
             price line, and it is included because Kris named it and because
             nothing in this repo has ever tested RSI.

N = 24 BARS IS FIXED, NOT SWEPT. It matches the shipped anchor's memory - a UTC
session VWAP on 1h bars carries about a day. Sweeping N would multiply seven
arms into thirty-five cells and H-038's lesson is that 96 tests at a 95th
percentile expect 4.8 false passes.

## What counts as a win - both, on BOTH timeframes

1. fewer expected days with a band that does NOT overlap the baseline's;
2. the blow-up rate does not rise.

Same conditions H-040 used, so the two studies are directly comparable.

## Kill criterion

> If no arm clears both on both timeframes, the edge is VWAP-specific rather
> than structural, the anchor axis closes as the eighth, and "the same idea with
> a different indicator" is answered by measurement rather than by opinion.

Run: .venv/bin/python strategies/vwapbreak/research/anchorfamily.py
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
from core.prop_rules import HOUSE                                   # noqa: E402
from core.riskladder import run_accounts                            # noqa: E402
from core.run_hypothesis import run_market, window                  # noqa: E402
from strategies.vwapbreak.strategy import STRATEGY                  # noqa: E402

RISKS = (0.005, 0.01, 0.015, 0.02, 0.03, 0.04)
CELLS = [("XAUUSD", "1h"), ("XAUUSD", "4h")]
N = 24


def _rvol(df: pd.DataFrame) -> np.ndarray:
    v = df.volume.replace(0, np.nan)
    return (v / v.rolling(96, min_periods=24).mean().shift(1)).fillna(1.0).values


def _atr(df: pd.DataFrame, n: int = 14) -> np.ndarray:
    pc = df.close.shift(1)
    tr = pd.concat([df.high - df.low, (df.high - pc).abs(),
                    (df.low - pc).abs()], axis=1).max(axis=1)
    return tr.rolling(n, min_periods=n // 2).mean().bfill().values


def _rsi(df: pd.DataFrame, n: int = 14) -> np.ndarray:
    d = df.close.diff()
    up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    rs = up / dn.replace(0, np.nan)
    return (100 - 100 / (1 + rs)).fillna(50.0).values


class AnchorArm:
    """The shipped strategy with a different centre line. All else delegates."""

    def __init__(self, tag: str) -> None:
        self.tag = tag
        self.name = f"vwapbreak_anchor_{tag}"
        self.extra_column = "z"

    def grid(self, tf: str):
        return STRATEGY.grid(tf)

    def run(self, df, cfg, fee_bps, slip_bps, feats=None, **kw):
        return STRATEGY.run(df, cfg, fee_bps, slip_bps,
                            feats=feats if feats is not None else self.features(df), **kw)

    def features(self, df: pd.DataFrame):
        if self.tag == "baseline":
            return STRATEGY.features(df)
        c = df.close
        if self.tag == "ema":
            anchor = c.ewm(span=N, adjust=False).mean().values
            width = c.rolling(N, min_periods=N // 2).std(ddof=0).bfill().values
        elif self.tag == "sma":
            anchor = c.rolling(N, min_periods=N // 2).mean().bfill().values
            width = c.rolling(N, min_periods=N // 2).std(ddof=0).bfill().values
        elif self.tag == "keltner":
            anchor = c.ewm(span=N, adjust=False).mean().values
            width = _atr(df)
        elif self.tag == "donchian":
            hi = df.high.rolling(N, min_periods=N // 2).max()
            lo = df.low.rolling(N, min_periods=N // 2).min()
            anchor = ((hi + lo) / 2.0).bfill().values
            width = ((hi - lo) / 2.0).bfill().values
        elif self.tag == "prevclose":
            anchor = c.resample("1D").last().reindex(df.index, method="ffill").shift(1).bfill().values
            width = _atr(df)
        elif self.tag == "rsi":
            # NOT A PRICE LINE. z is the RSI's own distance from 50, scaled so a
            # 10-point RSI move is one unit; the STOP still has to be in price,
            # so the width is ATR. Stated here because mixing units silently is
            # exactly how a result becomes unreadable.
            r = _rsi(df)
            z = (r - 50.0) / 10.0
            sd = _atr(df)
            return {"z": z, "sd": sd, "rvol": _rvol(df),
                    "hour": df.index.hour.values.astype(np.int64),
                    "live": (df.volume.values > 0).astype(np.uint8)}
        else:
            raise ValueError(self.tag)
        floor = c.values * 1e-6                  # the PX_EPS_FRAC discipline
        w = np.where(width > floor, width, np.nan)
        with np.errstate(invalid="ignore", divide="ignore"):
            z = (c.values - anchor) / w
        return {"z": z, "sd": w, "rvol": _rvol(df),
                "hour": df.index.hour.values.astype(np.int64),
                "live": (df.volume.values > 0).astype(np.uint8)}


ARMS = [AnchorArm(t) for t in ("baseline", "ema", "sma", "keltner",
                               "donchian", "prevclose", "rsi")]


def score(res: dict) -> dict:
    tr = res["_trades"]
    if not len(tr):
        return {"days": None, "trades": 0}
    daily = pd.Series(tr.r.values,
                      index=pd.DatetimeIndex(tr.exit_ts)).resample("1D").sum()
    best = None
    for risk in RISKS:
        a = run_accounts(daily, risk, HOUSE)
        if not a["pass_rate"]:
            continue
        exp = a["median_days"] / a["pass_rate"]
        line = {"risk_pct": risk * 100, "pass_pct": round(a["pass_rate"] * 100, 1),
                "blown_pct": round((a["fail_max"] + a["fail_daily"]) * 100, 1),
                "days": round(exp, 1), "band": nb_band(daily, risk, rules=HOUSE)}
        if best is None or exp < best["days"]:
            best = line
    return {**(best or {"days": None}), "trades": res.get("trades"),
            "win_pct": res.get("win_pct"), "pf_2x": res.get("pf_2x"),
            "null_pf": res.get("null_pf"),
            "trades_per_day": res.get("trades_per_day")}


def main() -> int:
    span = window(["XAUUSD"], ["1h", "4h"])
    out = {}
    for sym, tf in CELLS:
        print(f"\n=== {sym} {tf} " + "=" * 52, flush=True)
        hdr = (f"{'anchor':11}{'trades':>7}{'tpd':>6}{'win%':>7}{'PF2x':>7}"
               f"{'null':>7}{'days':>7}{'band':>13}{'pass%':>7}{'blown%':>8}")
        print(hdr); print("-" * len(hdr), flush=True)
        for arm in ARMS:
            try:
                res = run_market(arm, sym, tf,
                                 pipe_kw={"floors": (30,), "topn": (5,)},
                                 null_seeds=1, span=span)
                s = score(res)
            except Exception as e:
                print(f"{arm.tag:11}  FAILED: {type(e).__name__}: {e}", flush=True)
                out[f"{sym}|{tf}|{arm.tag}"] = {"error": f"{type(e).__name__}: {e}"}
                continue
            out[f"{sym}|{tf}|{arm.tag}"] = s
            b = s.get("band") or {}
            print(f"{arm.tag:11}{s.get('trades') or 0:>7}"
                  f"{s.get('trades_per_day') or 0:>6.2f}{s.get('win_pct') or 0:>7.1f}"
                  f"{s.get('pf_2x') or 0:>7.3f}{s.get('null_pf') or 0:>7.3f}"
                  f"{s.get('days') or 0:>7.1f}"
                  f"{('%.1f-%.1f' % (b.get('days_lo', 0), b.get('days_hi', 0))):>13}"
                  f"{s.get('pass_pct') or 0:>7.1f}{s.get('blown_pct') or 0:>8.1f}",
                  flush=True)
    dest = ROOT / "backtests" / "vwapbreak" / "anchorfamily.json"
    dest.write_text(json.dumps({"n": N, "rows": out}, indent=1, default=str))
    print(f"\nwrote {dest.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

# =========================================================================== #
# RESULT - 2026-09-15. Dead. The edge is VWAP-specific, not structural.
#
# XAUUSD 1h                              XAUUSD 4h
#   anchor      PF2x   null    days        PF2x   null    days
#   baseline   1.987  1.097    17.7       1.077  1.711    36.5
#   ema        0.877  1.043    35.9       3.005  0.498    40.9
#   sma        0.813  0.765    56.1       2.258  1.012    38.9
#   keltner    1.028  1.088    32.6       0.997  0.906    60.2
#   donchian   1.437  0.897    67.7       1.539  0.734   103.8
#   prevclose  0.581  0.471   154.5       0.628  0.484   123.8
#   rsi        1.678  0.983    51.1       1.132  0.883    35.5
#
# NO ARM CLEARS THE PRE-REGISTERED CONDITION. It required fewer expected days
# with a band that does not overlap the baseline's, on BOTH timeframes, without
# raising blow-ups. On 1h every arm is slower than the baseline and the nearest
# is RSI at 51.1 days against 17.7 - three times slower. On 4h every band
# overlaps the baseline's 27.3-55.0, so nothing there is resolvable either way.
#
# THE EMA 4h CELL IS THE MOST INSTRUCTIVE NUMBER IN THE STUDY AND IT IS NOISE.
# PF@2x 3.005 against a null of 0.498 looks like the best result this repo has
# ever produced. The same arm on 1h scores 0.877. A quantity that moves from
# 0.877 to 3.005 between two timeframes of the same market is the signature this
# project has recorded three times - H-026's fibonacci, H-035's alternating
# netflow, H-040's atr and pct arms - and it means no effect. SMA does the same
# thing, 0.813 to 2.258. Two arms flipping together is not two findings.
#
# AND THE 4h COLUMN IS UNRELIABLE ON ITS OWN TERMS. The 4h BASELINE loses to its
# own null seed, 1.077 against 1.711, which `BANDSHAPE.md` flagged on 2026-09-14
# and which has still not been re-run over multiple seeds. Any 4h number here
# inherits that doubt.
#
# RSI, TESTED HERE FOR THE FIRST TIME IN THIS REPO, IS THE BEST OF THE
# NEWCOMERS AND IS NOT A STRATEGY. 1h PF@2x 1.678 against a null of 0.983 is a
# genuine margin over its own control, and it takes 51.1 days against the
# baseline's 17.7. Worth recording; not worth trading, and not worth a second
# study without a mechanism that explains why a 14-bar oscillator on gold should
# pay when the same structure on seven other lines does not.
#
# WHAT IT SETTLES. Kris's reframe was right in form - H-027 is a structure, not
# a line - and the answer is that the structure alone is worth nothing. Seven
# centre lines, two timeframes, identical grid, folds, costs and selection: the
# VWAP is doing the work. THE ANCHOR AXIS IS THE EIGHTH CLOSED ON H-027.
#
# Closed so far: entry filters, timeframe, exit shape, selector objective, clock
# anchor, band shape, account overlay, and now the anchor family.
