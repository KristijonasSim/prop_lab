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
    """MODE_BREAK with a rolling VWAP band, streaming.

    Mirrors the kernel: signal on the closed bar, market order that fills at the
    next bar's open, stop at `stop_k` volume-weighted sigmas, flat at the
    rolling session boundary every `vwap_win` bars."""

    def __init__(self, config: VwapBreakConfig):
        super().__init__(config)
        self.bar_type = BarType.from_str(config.bar_type)
        self.tp_v = deque(maxlen=config.vwap_win)     # (typical price, volume)
        self.vols = deque(maxlen=RVOL_LEN)            # PRIOR bars only
        self.n = 0
        self.pending = 0                              # side queued for next open
        self.entry_px = 0.0
        self.stop_px = 0.0
        self.side = 0
        self.entry_bar = -1
        self.trades: list[dict] = []

    def on_start(self):
        self.subscribe_bars(self.bar_type)

    # -- streaming indicators, from delivered bars only --------------------
    def _vwap_band(self):
        if len(self.tp_v) < self.config.vwap_win // 4:
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

        # 1. fill anything queued by the PREVIOUS bar, at THIS bar's open
        if self.pending != 0 and self.side == 0:
            self.side = self.pending
            self.entry_px = o
            band = self._band_at_signal
            d = self.config.stop_k * band[1]
            self.stop_px = o - d if self.side == 1 else o + d
            self.entry_bar = self.n
            self._risk = d
        self.pending = 0

        # 2. manage an open position on this bar
        if self.side != 0:
            hit_stop = (l <= self.stop_px) if self.side == 1 else (h >= self.stop_px)
            boundary = (self.n % self.config.vwap_win) == 0 and self.n > self.entry_bar
            if hit_stop:
                self._close(self.stop_px, "stop")
            elif boundary:
                self._close(c, "session")

        # 3. update indicators with the now-closed bar
        base = np.mean(self.vols) if len(self.vols) >= RVOL_LEN // 4 else np.nan
        rvol = vol / base if base and base == base and base > 0 else 0.0
        self.vols.append(vol)
        self.tp_v.append(((h + l + c) / 3.0, vol if vol > 0 else 1.0))
        self.n += 1

        # 4. decide on the closed bar
        band = self._vwap_band()
        if band is None or self.side != 0 or self.n <= self.config.warmup_bars:
            return
        vwap, sd = band
        upper, lower = vwap + self.config.band_k * sd, vwap - self.config.band_k * sd
        if sd <= 0:
            return
        want = 1 if c > upper else (-1 if c < lower else 0)
        if want == 0:
            return
        if self.config.min_rvol > 0 and rvol < self.config.min_rvol:
            return                                   # rvol of the CLOSED bar
        if self.config.stop_k * sd < c * self.config.min_risk_bps / 1e4:
            return
        self.pending = want
        self._band_at_signal = (vwap, sd)

    def _close(self, px: float, reason: str):
        gross = (px - self.entry_px) if self.side == 1 else (self.entry_px - px)
        cost = (FEE_BPS + SLIP_BPS) / 1e4
        fees = (self.entry_px + px) * cost
        self.trades.append({
            "entry_bar": self.entry_bar, "exit_bar": self.n, "dir": self.side,
            "entry_px": self.entry_px, "exit_px": px,
            "r": (gross - fees) / self._risk, "reason": reason,
        })
        self.side = 0


def main():
    df = load_tf("BTCUSDT", "4h")
    print(f"BTCUSDT 4h: {len(df):,} bars {df.index[0]:%Y-%m-%d} -> {df.index[-1]:%Y-%m-%d}")

    # ---- reference: the repo's numba kernel, on the FIXED engine ----
    feats = features(df)
    tr = run_one(df, feats, {}, CFG, FEE_BPS, SLIP_BPS)
    span = (df.index[-1] - df.index[0]).total_seconds() / 86400.0
    m = trade_metrics(tr, df.index, span)
    ref = pd.DataFrame({
        "entry_bar": tr[:, T_ENTRY_I].astype(int), "exit_bar": tr[:, T_EXIT_I].astype(int),
        "dir": tr[:, T_DIR].astype(int), "entry_px": tr[:, T_ENTRY_PX],
        "exit_px": tr[:, T_EXIT_PX], "r": tr[:, T_R]})
    print(f"numba kernel : {len(ref)} trades, PF {m['pf']:.3f}, total R {m['total_r']:.1f}")

    # ---- independent: streaming, event-driven ----
    engine = make_engine()
    instrument, bar_type = add_bars(engine, df, bar_spec="4-HOUR-LAST")
    strat = VwapBreak(VwapBreakConfig(
        bar_type=str(bar_type), instrument_id=str(instrument.id),
        band_k=CFG["band_k"], stop_k=CFG["stop_k"], min_rvol=CFG["min_rvol"],
        warmup_bars=CFG["warmup_bars"], min_risk_bps=CFG["min_risk_bps"]))
    engine.add_strategy(strat)
    engine.run()
    nau = pd.DataFrame(strat.trades)
    print(f"streaming    : {len(nau)} trades"
          + (f", total R {nau.r.sum():.1f}" if len(nau) else ""))

    if len(nau) == 0 or len(ref) == 0:
        print("\nno overlap to compare")
        return
    j = ref.merge(nau, on="entry_bar", how="outer", suffixes=("_ref", "_nau"),
                  indicator=True)
    both = j[j._merge == "both"]
    print(f"\nentry bars: {len(both)} matched, "
          f"{int((j._merge == 'left_only').sum())} kernel-only, "
          f"{int((j._merge == 'right_only').sum())} streaming-only")
    if len(both):
        dpx = (both.entry_px_ref - both.entry_px_nau).abs()
        dr = (both.r_ref - both.r_nau).abs()
        print(f"entry price: max diff {dpx.max():.6f}")
        print(f"R multiple : max diff {dr.max():.6f}, "
              f"{int((dr > 1e-6).sum())} of {len(both)} differ")
    j.to_csv(OUT / "stage15_nautilus_compare.csv", index=False)
    print(f"\nwrote {OUT / 'stage15_nautilus_compare.csv'}")


if __name__ == "__main__":
    main()
