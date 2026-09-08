"""H-027 — VWAP band BREAKOUT, trend-shaped. The candidate the deep dive found.

WHAT IT IS, and why it is a separate hypothesis rather than a tuning of H-002:

  * DIRECTION IS FOLLOW, NOT FADE. `research/tails.py` compared both on the same
    bars, thresholds and holds - follow won 79 of 100 paired cells, and 25 of 25
    on ETH 4h and XAUUSD 1h. H-002's own blind walk-forward already agreed: it
    picks MODE_BREAK in 100 of 140 folds. The name "mean reversion" was wrong
    about what was being traded.
  * THERE IS NO TARGET. `research/shape.py` swept reward:risk from 1 to 8 and
    average R rose monotonically to the edge of the grid every time. Removing the
    target entirely moved XAUUSD 1h from 0.155 to 0.684 average R. The payoff is
    trend-shaped - roughly one winner in nine, carried a long way - and a target
    is the thing that was destroying it.
  * THE HORIZON IS LONG. 96 bars, four days on 1h. H-002 exits at the session
    close, which cuts the same trade off after hours.

Everything else follows the kernel contract: signal on a closed bar, fill at the
next open, stop wins every tie, a stop the bar gapped past fills at the open, no
decision or fill or exit on a bar that never traded, costs charged both sides.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from core.strategy import N_COLS, T_DIR, T_ENTRY_I, T_ENTRY_PX      # noqa: E402
from core.strategy import T_EXIT_I, T_EXIT_PX, T_R, T_REASON        # noqa: E402
from strategies.vwap.sweep import vwap_series                       # noqa: E402

R_STOP, R_HORIZON = 0, 1

#: The grid. Threshold and stop in sigma, horizon in bars. No target axis: the
#: whole finding is that a target destroys this payoff, so leaving one in the
#: grid would only give the fold selector a way to rediscover that.
THRESHOLDS = (0.5, 0.75, 1.0, 1.25, 1.5)
STOPS = (0.75, 1.0, 1.25, 1.5, 2.0)
HOLD_HOURS = (48, 96, 192)

#: SESSION WINDOWS, in UTC hours [lo, hi). (0, 0) means no window at all and is
#: always in the grid, so the fold selector can decline the filter entirely -
#: which is the only way to tell a filter that helps from one that is merely
#: being fitted.
#:
#: H-001 established on this repo's own data that the NY cash open (13:30 UTC) is
#: the ONLY session anchor carrying anything on FX and metals, and that Asia is
#: the worst region. These windows are chosen around that finding rather than
#: swept blindly:
#:   (7, 16)   London session
#:   (13, 21)  New York
#:   (13, 17)  the London/NY overlap, the deepest liquidity of the day
#:   (0, 7)    Asia - included precisely BECAUSE it is expected to be worst. A
#:             filter set containing only the windows you believe in cannot fail.
SESSIONS = ((0, 0), (7, 16), (13, 21), (13, 17), (0, 7))

#: Minimum relative volume on the SIGNAL bar. 0 disables. rvol was the only
#: filter family that ever lifted anything in this project (H-001, +0.063 paired
#: on the strongest cut), so it is the one worth spending grid on.
MIN_RVOL = (0.0, 1.0, 1.5)


def grid_for(bars_per_hour: float) -> list[dict]:
    """Horizons in HOURS, converted per timeframe so they mean the same thing on
    1h and 4h."""
    out = []
    for thr in THRESHOLDS:
        for stop in STOPS:
            for hrs in HOLD_HOURS:
                for lo, hi in SESSIONS:
                    for mrv in MIN_RVOL:
                        out.append({"thr": thr, "stop_sig": stop,
                                    "max_hold": max(2, int(round(hrs * bars_per_hour))),
                                    "hour_lo": lo, "hour_hi": hi,
                                    "min_rvol": mrv, "min_risk_bps": 3.0})
    return out


class VwapBreakStrategy:
    """Follow the VWAP band break; stop in sigma; no target; long horizon."""

    name = "vwapbreak"
    extra_column = "z"

    def features(self, df: pd.DataFrame):
        vwap, vwstd, _ = vwap_series(df, 0, 0)          # UTC-day anchor
        c = df.close.values
        with np.errstate(invalid="ignore", divide="ignore"):
            z = (c - vwap) / np.where(vwstd > vwap * 1e-6, vwstd, np.nan)
        # rvol against a trailing baseline, SHIFTED so a bar is never judged on
        # its own completed volume - the exact mistake that inflated H-002's
        # profit factor from 0.627 to 2.765 in 2026-09-05.
        v = pd.Series(df.volume.values, index=df.index)
        base = v.rolling(20 * 24, min_periods=120).mean().shift(1)
        rvol = (v / base).fillna(0.0).values
        return {"z": z, "sd": vwstd, "rvol": rvol,
                "hour": df.index.hour.values.astype(np.int64),
                "live": (df.volume.values > 0).astype(np.uint8)}

    def grid(self, tf: str) -> list[dict]:
        from core.markets import TF_BPH
        return grid_for(TF_BPH[tf])

    def run(self, df: pd.DataFrame, cfg: dict, fee_bps: float, slip_bps: float,
            feats=None, **kw) -> np.ndarray:
        f = feats if feats is not None else self.features(df)
        z, sd, live = f["z"], f["sd"], f["live"]
        rvol, hour = f["rvol"], f["hour"]
        h_lo, h_hi = int(cfg.get("hour_lo", 0)), int(cfg.get("hour_hi", 0))
        min_rvol = float(cfg.get("min_rvol", 0.0))
        o, h, l, c = (df.open.values, df.high.values,
                      df.low.values, df.close.values)
        n = len(c)
        cost = (fee_bps + slip_bps) / 1e4
        thr, ssig = float(cfg["thr"]), float(cfg["stop_sig"])
        mh, minr = int(cfg["max_hold"]), float(cfg.get("min_risk_bps", 3.0))

        out = np.zeros((n, N_COLS))
        k, i = 0, 1
        while i < n - 1:
            if not (np.isfinite(z[i]) and live[i] and live[i + 1]):
                i += 1
                continue
            side = 1 if z[i] >= thr else (-1 if z[i] <= -thr else 0)
            if side == 0:
                i += 1
                continue
            # FILTERS, read on the SIGNAL bar i and never on the fill bar i+1.
            # A filter that reads the entry bar asks for volume and range that do
            # not exist when the order is placed.
            if h_lo != h_hi:
                hh = hour[i]
                inside = (h_lo <= hh < h_hi) if h_lo < h_hi else (hh >= h_lo or hh < h_hi)
                if not inside:
                    i += 1
                    continue
            if min_rvol > 0.0 and rvol[i] < min_rvol:
                i += 1
                continue
            e = i + 1
            entry = o[e]
            risk = ssig * sd[i]
            floor = entry * minr / 1e4
            if not np.isfinite(risk) or entry <= 0:
                i += 1
                continue
            risk = max(risk, floor)
            stop = entry - side * risk
            last = min(e + mh, n - 1)
            exit_px, exit_i, reason = c[last], last, R_HORIZON
            j = e
            while j <= last:
                if live[j]:
                    if side == 1 and l[j] <= stop:
                        exit_px = stop if o[j] > stop else o[j]
                        exit_i, reason = j, R_STOP
                        break
                    if side == -1 and h[j] >= stop:
                        exit_px = stop if o[j] < stop else o[j]
                        exit_i, reason = j, R_STOP
                        break
                j += 1
            if reason == R_HORIZON:
                while exit_i > e and not live[exit_i]:
                    exit_i -= 1
                exit_px = c[exit_i]
            gross = (exit_px - entry) * side
            fees = (entry + exit_px) * cost / 2
            out[k, T_ENTRY_I] = e
            out[k, T_EXIT_I] = exit_i
            out[k, T_DIR] = side
            out[k, T_ENTRY_PX] = entry
            out[k, T_EXIT_PX] = exit_px
            out[k, T_R] = (gross - fees) / risk
            out[k, T_REASON] = reason
            out[k, 7] = z[i]
            k += 1
            i = exit_i if exit_i > i else i + 1
        return out[:k]


STRATEGY = VwapBreakStrategy()
