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


def grid_for(bars_per_hour: float) -> list[dict]:
    """Horizons in HOURS, converted per timeframe so they mean the same thing on
    1h and 4h."""
    out = []
    for thr in THRESHOLDS:
        for stop in STOPS:
            for hrs in HOLD_HOURS:
                out.append({"thr": thr, "stop_sig": stop,
                            "max_hold": max(2, int(round(hrs * bars_per_hour))),
                            "min_risk_bps": 3.0})
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
        return {"z": z, "sd": vwstd,
                "live": (df.volume.values > 0).astype(np.uint8)}

    def grid(self, tf: str) -> list[dict]:
        from core.markets import TF_BPH
        return grid_for(TF_BPH[tf])

    def run(self, df: pd.DataFrame, cfg: dict, fee_bps: float, slip_bps: float,
            feats=None, **kw) -> np.ndarray:
        f = feats if feats is not None else self.features(df)
        z, sd, live = f["z"], f["sd"], f["live"]
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
