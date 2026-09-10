"""SECOND ENGINE for the two candidates: the partial exit, and the Asian range.

Neither can be traded without this. The current pick matched 14 of 14
configurations bar for bar (`nautilus_check.py`); these two arms have never been
near an independent engine, and the bug class this catches - a look-ahead - has
already taken a whole crypto book off this board.

WHY AN EVENT ENGINE CATCHES IT. NautilusTrader hands the strategy one bar at a
time and it holds no array it could index into, so it *cannot* reproduce a
look-ahead even by accident. If the vectorised kernel is reading the future, the
two disagree on an entry bar.

WHAT IS CHECKED

  partial 2R    `research/exitshape.ShapedExit(partial_r=2.0)` - the arm that
                takes the win rate from 20.3% to 41.9%. Half the position is
                booked at +2R and the rest runs to the stop or the horizon, so
                the streaming side has to carry a half-filled position and two
                fills for one trade.
  asian range   `research/volume.VolumeVariant("asia")` - the 00:00-07:00 UTC
                range as the level, traded during the European and US day. The
                streaming side has to build the range as the night goes and
                freeze it at 07:00, which is exactly the kind of state a
                vectorised implementation can get wrong in the forward direction.

WHAT COUNTS AS A FAILURE. An entry-bar disagreement is a causality finding and
fails the check. An exit-bar or price disagreement is a finding about intrabar
ordering, reported and judged on its mechanism - the 2026-09-09 lesson is that
one of those was an ill-posed rule and one was a bookkeeping convention at the
end of the series, and neither was a look-ahead.

THE STREAMING SIDE IS WRITTEN FROM THE RULE, not translated from the kernel's
array code, which is the only way the check means anything.

Run: .venv/bin/python strategies/vwapbreak/nautilus_check2.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from nautilus_trader.config import StrategyConfig                       # noqa: E402
from nautilus_trader.model.data import BarType                          # noqa: E402
from nautilus_trader.trading.strategy import Strategy                   # noqa: E402

from core.chosen import SETTINGS                                        # noqa: E402
from core.markets import COSTS, EXEC_MODE, load                         # noqa: E402
from core.nautilus_setup import add_bars_for, fx_instrument, make_engine  # noqa: E402
from core.strategy import (T_DIR, T_ENTRY_I, T_ENTRY_PX, T_EXIT_I,      # noqa: E402
                           T_EXIT_PX, T_R, T_REASON)
from strategies.vwapbreak.strategy import grid_for                      # noqa: E402
from strategies.vwapbreak.research.exitshape import ShapedExit          # noqa: E402
from strategies.vwapbreak.research.volume import VolumeVariant          # noqa: E402

SYM, TF, BAR_SPEC = "XAUUSD", "1h", "1-HOUR-LAST"
RVOL_LEN, RVOL_MIN = 20 * 24, 120


class Cfg(StrategyConfig, frozen=True):
    bar_type: str
    n_bars: int
    thr: float
    stop_sig: float
    max_hold: int
    hour_lo: int
    hour_hi: int
    min_rvol: float
    min_risk_bps: float
    fee_bps: float
    slip_bps: float
    partial_r: float = 0.0
    asia: bool = False


class Streamed(Strategy):
    """H-027 as a streaming strategy, with either exit shape. No arrays."""

    def __init__(self, config: Cfg):
        super().__init__(config)
        self.bar_type = BarType.from_str(config.bar_type)
        self.n = 0
        # daily VWAP accumulators
        self.pv = self.vv = self.p2v = 0.0
        self.last_v = 0.0
        self.day = None
        # the Asian range, built through the night and frozen at 07:00
        self.a_hi = -np.inf
        self.a_lo = np.inf
        # rvol over prior bars only
        self.vols: list[float] = []
        self.vsum = 0.0
        # position state
        self.side = 0
        self.entry_px = self.stop_px = self.risk = 0.0
        self.entry_bar = self.last_bar = -1
        self.part_done = False
        self.part_r = 0.0
        self.pending = 0
        self.pending_sd = 0.0
        self.live_i, self.live_close = -1, float("nan")
        self.blocked_until = -1
        self.trades: list[dict] = []

    def on_start(self):
        self.subscribe_bars(self.bar_type)

    def on_bar(self, bar):
        c = self.config
        o, hi, lo, cl = (float(bar.open), float(bar.high),
                         float(bar.low), float(bar.close))
        vol = float(bar.volume)
        i = self.n
        ts = pd.Timestamp(bar.ts_event, unit="ns", tz="UTC")
        live = vol > 0.0

        # 1. fill what the previous bar queued, at this bar's open
        if self.pending != 0 and self.side == 0:
            if live:
                risk = c.stop_sig * self.pending_sd
                floor = o * c.min_risk_bps / 1e4
                if np.isfinite(risk) and o > 0:
                    risk = max(risk, floor)
                    self.side, self.entry_px, self.risk = self.pending, o, risk
                    self.stop_px = o - self.side * risk
                    self.entry_bar = i
                    self.last_bar = min(i + c.max_hold, c.n_bars - 1)
                    self.part_done, self.part_r = False, 0.0
            self.pending = 0

        # 2. manage the position. Stop first: it wins every tie, and a bar that
        #    gapped through it fills at the open because it is a market order.
        if self.side != 0 and live:
            hit = (lo <= self.stop_px) if self.side == 1 else (hi >= self.stop_px)
            if hit:
                gapped = (o < self.stop_px) if self.side == 1 else (o > self.stop_px)
                self._close(o if gapped else self.stop_px, i, 0)
            elif c.partial_r > 0.0 and not self.part_done:
                lvl = self.entry_px + self.side * c.partial_r * self.risk
                reached = (hi >= lvl) if self.side == 1 else (lo <= lvl)
                if reached:
                    fees = (self.entry_px + lvl) * (c.fee_bps + c.slip_bps) / 1e4 / 2
                    self.part_r = ((lvl - self.entry_px) * self.side - fees) / self.risk
                    self.part_done = True
        if self.side != 0 and i >= self.last_bar:
            if live:
                self._close(cl, i, 1)
            elif self.live_i >= self.entry_bar and self.live_i >= 0:
                self._close(self.live_close, self.live_i, 1)

        # 3. indicators from bars already closed
        base = (self.vsum / len(self.vols)
                if len(self.vols) >= RVOL_MIN else float("nan"))
        rvol = vol / base if base == base and base > 0 else 0.0
        self.vols.append(vol)
        self.vsum += vol
        if len(self.vols) > RVOL_LEN:
            self.vsum -= self.vols.pop(0)

        day = ts.floor("D")
        if self.day is None or day != self.day:
            self.pv = self.vv = self.p2v = 0.0
            self.a_hi, self.a_lo = -np.inf, np.inf
            self.day = day
        tp = (hi + lo + cl) / 3.0
        w = vol if vol > 0 else (self.last_v if self.last_v > 0 else 1.0)
        if vol > 0:
            self.last_v = vol
        self.pv += tp * w
        self.vv += w
        self.p2v += tp * tp * w
        vwap = self.pv / self.vv if self.vv > 0 else float("nan")
        var = (self.p2v / self.vv - vwap * vwap) if self.vv > 0 else float("nan")
        vwsd = float(np.sqrt(max(var, 0.0))) if var == var else float("nan")

        if c.asia:
            # the overnight range grows until 07:00 and is then fixed for the day
            if ts.hour < 7:
                self.a_hi = max(self.a_hi, hi)
                self.a_lo = min(self.a_lo, lo)
                z, sd = float("nan"), float("nan")
            elif np.isfinite(self.a_hi) and self.a_hi > -np.inf:
                mid = (self.a_hi + self.a_lo) / 2.0
                sd = (self.a_hi - self.a_lo) / 2.0
                z = ((cl - mid) / sd) if sd > abs(mid) * 1e-6 else float("nan")
            else:
                z, sd = float("nan"), float("nan")
        else:
            sd = vwsd
            z = ((cl - vwap) / sd) if (sd == sd and sd > vwap * 1e-6) else float("nan")

        if live:
            self.live_i, self.live_close = i, cl
        self.n += 1

        # 4. decide on this closed bar
        if self.side != 0 or not live or i <= self.blocked_until:
            return
        if i + 1 >= c.n_bars - 1 or i < 1:
            return
        if not np.isfinite(z):
            return
        want = 1 if z >= c.thr else (-1 if z <= -c.thr else 0)
        if want == 0:
            return
        if c.hour_lo != c.hour_hi:
            h = ts.hour
            inside = (c.hour_lo <= h < c.hour_hi) if c.hour_lo < c.hour_hi \
                else (h >= c.hour_lo or h < c.hour_hi)
            if not inside:
                return
        if c.min_rvol > 0.0 and rvol < c.min_rvol:
            return
        self.pending, self.pending_sd = want, sd

    def on_stop(self):
        self.side = 0

    def _close(self, px: float, exit_i: int, reason: int):
        c = self.config
        gross = (px - self.entry_px) * self.side
        fees = (self.entry_px + px) * (c.fee_bps + c.slip_bps) / 1e4 / 2
        r_rest = (gross - fees) / self.risk
        r = (self.part_r * 0.5 + r_rest * 0.5) if self.part_done else r_rest
        self.trades.append({"entry_bar": self.entry_bar, "exit_bar": exit_i,
                            "dir": self.side, "entry_px": self.entry_px,
                            "exit_px": px, "r": r, "reason": reason})
        self.side = 0
        self.blocked_until = exit_i - 1


def kernel_trades(strat, df, feats, cfg, fee, slip) -> pd.DataFrame:
    tr = strat.run(df, cfg, fee, slip, feats=feats)
    return pd.DataFrame({
        "entry_bar": tr[:, T_ENTRY_I].astype(int),
        "exit_bar": tr[:, T_EXIT_I].astype(int),
        "dir": tr[:, T_DIR].astype(int),
        "entry_px": tr[:, T_ENTRY_PX], "exit_px": tr[:, T_EXIT_PX],
        "r": tr[:, T_R], "reason": tr[:, T_REASON].astype(int)})


def one(arm: str, strat, df, feats, cfg, fee, slip) -> dict:
    ref = kernel_trades(strat, df, feats, cfg, fee, slip)
    engine = make_engine()
    instrument = fx_instrument(SYM)
    _, bar_type = add_bars_for(engine, df, instrument, bar_spec=BAR_SPEC)
    s = Streamed(Cfg(
        bar_type=str(bar_type), n_bars=len(df),
        thr=float(cfg["thr"]), stop_sig=float(cfg["stop_sig"]),
        max_hold=int(cfg["max_hold"]), hour_lo=int(cfg["hour_lo"]),
        hour_hi=int(cfg["hour_hi"]), min_rvol=float(cfg["min_rvol"]),
        min_risk_bps=float(cfg["min_risk_bps"]),
        fee_bps=float(fee), slip_bps=float(slip),
        partial_r=2.0 if arm == "partial 2R" else 0.0,
        asia=(arm == "asian range")))
    engine.add_strategy(s)
    engine.run()
    engine.dispose()
    nau = pd.DataFrame(s.trades)

    row = {"arm": arm, **{k: cfg[k] for k in ("thr", "stop_sig", "max_hold",
                                              "hour_lo", "hour_hi", "min_rvol")},
           "kernel": len(ref), "stream": len(nau)}
    if len(ref) and len(nau):
        j = ref.merge(nau, on="entry_bar", how="outer", suffixes=("_k", "_s"),
                      indicator=True)
        both = j[j._merge == "both"]
        row |= {"matched": len(both),
                "kernel_only": int((j._merge == "left_only").sum()),
                "stream_only": int((j._merge == "right_only").sum()),
                "entry_match": round(len(both) / max(len(ref), 1), 4),
                "exit_bar_match": round(float((both.exit_bar_k == both.exit_bar_s).mean()), 4),
                "max_r_diff": float((both.r_k - both.r_s).abs().max())}
    else:
        row |= {"matched": 0, "entry_match": 0.0, "kernel_only": len(ref),
                "stream_only": len(nau)}
    return row


def configs() -> list[dict]:
    out = [dict(s, min_risk_bps=3.0) for s in SETTINGS]
    for cfg in grid_for(24)[::211]:
        if len(out) >= 10:
            break
        out.append(dict(cfg))
    return out


def main() -> int:
    df = load(SYM, TF)
    c = COSTS[SYM]
    fee, slip = c.per_side(EXEC_MODE)
    cfgs = configs()
    arms = [("partial 2R", ShapedExit("p2", partial_r=2.0)),
            ("asian range", VolumeVariant("asia", "asia"))]
    print(f"{SYM} {TF}: {len(df):,} bars, {len(cfgs)} configurations per arm "
          f"(first 5 are the traded settings)\n")
    rows = []
    for arm, strat in arms:
        feats = strat.features(df)
        print(f"=== {arm} " + "=" * 48)
        print(f"{'thr':>5}{'stop':>6}{'hold':>6}{'rvol':>6}{'kernel':>8}"
              f"{'stream':>8}{'entry':>8}{'exit bar':>9}{'max dR':>10}")
        for k, cfg in enumerate(cfgs):
            r = one(arm, strat, df, feats, cfg, fee, slip)
            rows.append(r)
            print(f"{cfg['thr']:5.2f}{cfg['stop_sig']:6.1f}{cfg['max_hold']:6d}"
                  f"{cfg['min_rvol']:6.1f}{r['kernel']:8d}{r['stream']:8d}"
                  f"{r['entry_match']:8.4f}{r.get('exit_bar_match', 0):9.4f}"
                  f"{r.get('max_r_diff', float('nan')):10.2e}"
                  + ("   <- TRADED" if k < 5 else ""), flush=True)

    out = pd.DataFrame(rows)
    dest = ROOT / "backtests" / "vwapbreak" / "nautilus_check2.csv"
    out.to_csv(dest, index=False)
    bad = out[out.entry_match < 0.9999]
    print(f"\n{len(out) - len(bad)} of {len(out)} arm-configurations match every "
          f"entry bar.")
    if len(bad):
        print("DISAGREEMENTS - an entry-bar difference is a causality finding:")
        print(bad.to_string(index=False))
    print(f"max |dR| across all matched trades: {out.max_r_diff.max():.3e}")
    print(f"wrote {dest.relative_to(ROOT)}")
    return 0 if not len(bad) else 1


if __name__ == "__main__":
    raise SystemExit(main())
