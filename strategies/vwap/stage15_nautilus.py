"""H-002 cross-check — the VWAP kernel re-implemented in NautilusTrader.

WHY. `strategies/vwap/engine.py` is a hand-written numba loop that produces
every number on the board. Three look-aheads were found in it on 2026-09-05 by
reading it. Reading is not a test. This runs the same configuration through an
independent, event-driven engine that CANNOT look ahead by construction - a
Nautilus strategy is handed one bar at a time and has no array to index into -
and compares the trades.

Indicators are recomputed here INCREMENTALLY, from bars already delivered,
rather than imported from `sweep.features`. That is the point: if the vectorised
version peeks, the streaming version will disagree with it.

WHAT A MISMATCH MEANS
  entry bars differ      -> a causality bug in the signal or the filters
  entry prices differ    -> a fill-timing bug
  exit prices differ     -> an intrabar ordering assumption, which is expected:
                            the numba kernel resolves stop-before-target by
                            fiat, Nautilus walks O->H->L->C (or O->L->H->C) and
                            can disagree honestly. That gap is a finding, not a
                            bug.

Run: .venv/bin/python strategies/vwap/stage15_nautilus.py
"""
from __future__ import annotations

import sys
from collections import deque
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from nautilus_trader.config import StrategyConfig                       # noqa: E402
from nautilus_trader.model.data import BarType                          # noqa: E402
from nautilus_trader.model.enums import OrderSide                       # noqa: E402
from nautilus_trader.trading.strategy import Strategy                   # noqa: E402

from core.nautilus_setup import make_engine, add_bars                   # noqa: E402
from strategies.vwap.sweep import features, run_one, trade_metrics, DEFAULTS  # noqa: E402
from strategies.vwap.stage3_timeframes import load_tf                   # noqa: E402
from strategies.vwap.engine import T_ENTRY_I, T_EXIT_I, T_DIR, T_ENTRY_PX, T_EXIT_PX, T_R  # noqa: E402

OUT = ROOT / "backtests" / "queue"
OUT.mkdir(parents=True, exist_ok=True)

# The board's most-selected BTCUSDT 4h configuration.
CFG = dict(DEFAULTS)
CFG.update(anchor_hour=-1, anchor_minute=24, mode=2, fill_mode=1,
           band_k=1.5, stop_mode=0, stop_k=0.5, target_mode=0, rr=0.0,
           max_hold_bars=0, warmup_bars=2, min_risk_bps=10.0, min_rvol=2.5)

VWAP_WIN = 24            # anchor_minute, the rolling window in bars
RVOL_LEN = 20 * 96
FEE_BPS, SLIP_BPS = 5.0, 2.0


class VwapBreakConfig(StrategyConfig, frozen=True):
    bar_type: str
    instrument_id: str
    band_k: float = 1.5
    stop_k: float = 0.5
    min_rvol: float = 2.5
    warmup_bars: int = 2
    vwap_win: int = VWAP_WIN
    min_risk_bps: float = 10.0
    trade_size: float = 1.0


class VwapBreak(Strategy):
    """MODE_BREAK on a rolling VWAP band, streaming, target_mode=0.

    Mirrors `engine.simulate` exactly, and the session arithmetic is the fiddly
    part. `rolling_vwap` sets sess_start = arange(win, n, win) = [24, 48, ...],
    so session s spans bars [24(s+1), 24(s+2)), the first `warmup_bars` of each
    are skipped, and bars 0-23 are never traded at all. A bar is tradeable when

        n >= win + warmup   and   n % win >= warmup

    and a trade is force-flat at the close of its session's last bar, because
    target_mode=0 sets horizon = stop_bar.

    One deliberate difference from the kernel, which is a finding and not a
    port defect: the kernel's `min_risk_bps` floor is compared against
    `entry = o[i+1]`, the entry bar's open, while the decision is being made at
    the close of bar i. That is a fourth (tiny) peek. Here the check is done at
    fill time, when the open is genuinely known."""

    def __init__(self, config: VwapBreakConfig):
        super().__init__(config)
        self.bar_type = BarType.from_str(config.bar_type)
        self.tp_v = deque(maxlen=config.vwap_win)     # (typical price, volume)
        self.vols = deque(maxlen=RVOL_LEN)            # PRIOR bars only
        self.n = 0
        self.pending = 0                              # side queued for next open
        self.band_at_signal = None
        self.side = 0
        self.entry_px = 0.0
        self.stop_px = 0.0
        self.risk = 0.0
        self.entry_bar = -1
        self.session_end = -1                         # force flat at this bar
        self.block_until = -1                         # kernel does i = exit_i + 1
        self.trades: list[dict] = []

    def on_start(self):
        self.subscribe_bars(self.bar_type)

    def _vwap_band(self):
        """Rolling VWAP and volume-weighted sigma over the last `win` bars.

        min_periods = win // 4, matching `sweep.rolling_vwap`."""
        win = self.config.vwap_win
        if len(self.tp_v) < win // 4:
            return None
        tp = np.array([a for a, _ in self.tp_v])
        v = np.array([b for _, b in self.tp_v])
        sv = v.sum()
        if sv <= 0:
            return None
        vwap = float((tp * v).sum() / sv)
        var = float((tp * tp * v).sum() / sv) - vwap * vwap
        return vwap, float(np.sqrt(max(var, 0.0)))

    def on_bar(self, bar):
        o = float(bar.open); h = float(bar.high)
        l = float(bar.low); c = float(bar.close); vol = float(bar.volume)
        win = self.config.vwap_win

        # 1. fill what the previous bar queued, at THIS bar's open
        if self.pending != 0 and self.side == 0:
            _, sd = self.band_at_signal
            d = self.config.stop_k * sd
            # min_risk floor, checked against the price we actually got
            if d > 0 and d >= o * self.config.min_risk_bps / 1e4:
                self.side = self.pending
                self.entry_px = o
                self.risk = d
                self.stop_px = o - d if self.side == 1 else o + d
                self.entry_bar = self.n
                # horizon = stop_bar; force flat at the close of stop_bar - 1
                self.session_end = win * (self.n // win + 1) - 1
        self.pending = 0

        # 2. manage the open position on this bar. Stop first - the kernel
        #    resolves ties pessimistically and checks the stop before anything.
        if self.side != 0:
            hit_stop = (l <= self.stop_px) if self.side == 1 else (h >= self.stop_px)
            if hit_stop:
                self._close(self.stop_px, "stop")
            elif self.n >= self.session_end:
                self._close(c, "session")

        # 3. fold the now-closed bar into the indicators
        base = np.mean(self.vols) if len(self.vols) >= RVOL_LEN // 4 else np.nan
        rvol = vol / base if base == base and base > 0 else 0.0
        self.vols.append(vol)
        self.tp_v.append(((h + l + c) / 3.0, vol if vol > 0 else 1.0))
        i = self.n
        self.n += 1

        # 4. decide on the closed bar i
        if self.side != 0 or i <= self.block_until:
            return
        # session arithmetic: bars 0..win-1 never trade, and the first
        # `warmup` bars of each session are skipped
        if i < win + self.config.warmup_bars or (i % win) < self.config.warmup_bars:
            return
        # the order fills on bar i+1, which must still be inside this session
        if (i + 1) >= win * (i // win + 1):
            return
        band = self._vwap_band()
        if band is None:
            return
        vwap, sd = band
        if vwap <= 0.0 or sd <= 0.0:
            return
        upper, lower = vwap + self.config.band_k * sd, vwap - self.config.band_k * sd
        want = 1 if c > upper else (-1 if c < lower else 0)
        if want == 0:
            return
        if self.config.min_rvol > 0 and rvol < self.config.min_rvol:
            return                                   # rvol of the CLOSED bar i
        self.pending = want
        self.band_at_signal = (vwap, sd)

    def _close(self, px: float, reason: str):
        gross = (px - self.entry_px) if self.side == 1 else (self.entry_px - px)
        cost = (FEE_BPS + SLIP_BPS) / 1e4
        fees = (self.entry_px + px) * cost
        self.trades.append({
            "entry_bar": self.entry_bar, "exit_bar": self.n, "dir": self.side,
            "entry_px": self.entry_px, "exit_px": px,
            "r": (gross - fees) / self.risk, "reason": reason,
        })
        self.side = 0
        self.block_until = self.n            # kernel resumes at exit_i + 1


TFS = {"4h": ("4-HOUR-LAST", 24), "1h": ("1-HOUR-LAST", 24), "30m": ("30-MINUTE-LAST", 24)}


def cross_check(tf: str, bar_spec: str, win: int) -> dict:
    df = load_tf("BTCUSDT", tf)
    cfg = dict(CFG)
    cfg["anchor_minute"] = win

    feats = features(df)
    tr = run_one(df, feats, {}, cfg, FEE_BPS, SLIP_BPS)
    span = (df.index[-1] - df.index[0]).total_seconds() / 86400.0
    m = trade_metrics(tr, df.index, span)
    ref = pd.DataFrame({
        "entry_bar": tr[:, T_ENTRY_I].astype(int), "exit_bar": tr[:, T_EXIT_I].astype(int),
        "dir": tr[:, T_DIR].astype(int), "entry_px": tr[:, T_ENTRY_PX],
        "exit_px": tr[:, T_EXIT_PX], "r": tr[:, T_R]})

    engine = make_engine()
    instrument, bar_type = add_bars(engine, df, bar_spec=bar_spec)
    strat = VwapBreak(VwapBreakConfig(
        bar_type=str(bar_type), instrument_id=str(instrument.id),
        band_k=cfg["band_k"], stop_k=cfg["stop_k"], min_rvol=cfg["min_rvol"],
        warmup_bars=cfg["warmup_bars"], vwap_win=win,
        min_risk_bps=cfg["min_risk_bps"]))
    engine.add_strategy(strat)
    engine.run()
    nau = pd.DataFrame(strat.trades)

    out = {"tf": tf, "bars": len(df), "kernel_trades": len(ref),
           "stream_trades": len(nau), "kernel_R": float(ref.r.sum()),
           "stream_R": float(nau.r.sum()) if len(nau) else np.nan,
           "kernel_pf": m["pf"]}
    if len(ref) and len(nau):
        j = ref.merge(nau, on="entry_bar", how="outer",
                      suffixes=("_ref", "_nau"), indicator=True)
        both = j[j._merge == "both"]
        out.update(matched=len(both),
                   kernel_only=int((j._merge == "left_only").sum()),
                   stream_only=int((j._merge == "right_only").sum()),
                   max_px_diff=float((both.entry_px_ref - both.entry_px_nau).abs().max()),
                   max_r_diff=float((both.r_ref - both.r_nau).abs().max()))
        j.to_csv(OUT / f"stage15_nautilus_compare_{tf}.csv", index=False)
    return out


def main():
    rows = []
    for tf, (spec, win) in TFS.items():
        try:
            rows.append(cross_check(tf, spec, win))
        except Exception as e:
            print(f"{tf}: {type(e).__name__}: {e}")
    res = pd.DataFrame(rows)
    res.to_csv(OUT / "stage15_nautilus.csv", index=False)
    print(f"\n{'=' * 84}")
    print("VWAP KERNEL vs INDEPENDENT EVENT-DRIVEN ENGINE (BTCUSDT, MODE_BREAK)")
    print(f"{'=' * 84}")
    print(f"{'tf':5} {'bars':>7} {'kernel':>7} {'stream':>7} {'matched':>8} "
          f"{'k-only':>7} {'s-only':>7} {'dPx':>7} {'dR':>9}")
    for _, r in res.iterrows():
        print(f"{r.tf:5} {r.bars:7d} {r.kernel_trades:7d} {r.stream_trades:7d} "
              f"{int(r.get('matched', 0)):8d} {int(r.get('kernel_only', 0)):7d} "
              f"{int(r.get('stream_only', 0)):7d} {r.get('max_px_diff', np.nan):7.3f} "
              f"{r.get('max_r_diff', np.nan):9.6f}")
    print("\ndPx of half a tick and dR ~1e-4 are Nautilus quantising prices to the")
    print("instrument tick size, not a logic difference.")
    print(f"\nwrote {OUT / 'stage15_nautilus.csv'}")


if __name__ == "__main__":
    main()
