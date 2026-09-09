"""TASK 1 — H-027's kernel against an INDEPENDENT engine, bar by bar.

WHY THIS IS FIRST. Every other number in this project rests on the kernel being
right, and this check is the only one that can catch the bug class that has
already killed a result here: a look-ahead. An event-driven engine is handed one
bar at a time and holds no array it could index into, so it *cannot* reproduce a
look-ahead even by accident. The same check on the older `vwap` kernel found
three real bugs, one of which took the entire crypto book off the board.

H-027 has never been through it. It is now the strategy Kris trades.

WHAT IS COMPARED. The five configurations in `core/chosen.py` plus a spread of
others from the grid, on the full XAUUSD 1h series:

    entry bars differ    -> a causality bug. The finding that matters.
    entry prices differ  -> a fill-timing bug.
    exit bars/prices differ -> an intrabar ordering assumption. A finding, not
                            necessarily a failure.

WHAT IS DELIBERATELY REPRODUCED RATHER THAN IMPROVED. Three kernel assumptions,
copied exactly so the comparison stays clean:

  * a stop the bar GAPPED past fills at the open, not at the level;
  * the horizon exit walks BACK to the last bar that actually traded, because
    Dukascopy pads the closed weekend with zero-volume bars;
  * `min_risk_bps` floors the stop distance, which on a quiet bar makes the stop
    wider than `stop_sig * sigma`.

Two facts the streaming side is allowed to know, neither of them a price: the
length of the series (the kernel's last usable bar is `n - 1`), and the
instrument's precision.

Run: .venv/bin/python strategies/vwapbreak/nautilus_check.py
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
from strategies.vwapbreak.strategy import STRATEGY, grid_for            # noqa: E402

SYM = "XAUUSD"
TF = "1h"
BAR_SPEC = "1-HOUR-LAST"
RVOL_LEN = 20 * 24
RVOL_MIN = 120


class BreakConfig(StrategyConfig, frozen=True):
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


class VwapBreak(Strategy):
    """The H-027 rule as a streaming strategy. No arrays, no future."""

    def __init__(self, config: BreakConfig):
        super().__init__(config)
        self.bar_type = BarType.from_str(config.bar_type)
        self.n = 0

        # anchored VWAP accumulators, reset at the UTC day
        self.pv = self.vv = self.p2v = 0.0
        self.last_v = 0.0
        self.day = None

        # relative volume: a trailing mean of PRIOR bars only
        self.vols: list[float] = []
        self.vsum = 0.0

        # one position at a time, exactly as the kernel scans
        self.side = 0
        self.entry_px = 0.0
        self.stop_px = 0.0
        self.risk = 0.0
        self.entry_bar = -1
        self.last_bar = -1                 # kernel's `last` = min(e+mh, n-1)
        self.pending = 0
        self.pending_sd = 0.0
        # the kernel walks a time exit back to the last bar that traded
        self.live_i = -1
        self.live_close = float("nan")
        self.blocked_until = -1

        self.trades: list[dict] = []

    def on_start(self):
        self.subscribe_bars(self.bar_type)

    # -- the bar loop ------------------------------------------------------ #
    def on_bar(self, bar):
        c = self.config
        o, hi, lo, cl = (float(bar.open), float(bar.high),
                         float(bar.low), float(bar.close))
        vol = float(bar.volume)
        i = self.n
        ts = pd.Timestamp(bar.ts_event, unit="ns", tz="UTC")
        live = vol > 0.0

        # 1. fill what the previous bar queued, at THIS bar's open
        if self.pending != 0 and self.side == 0:
            if live:                       # the kernel refuses a dead fill bar
                risk = c.stop_sig * self.pending_sd
                floor = o * c.min_risk_bps / 1e4
                if np.isfinite(risk) and o > 0:
                    risk = max(risk, floor)
                    self.side = self.pending
                    self.entry_px = o
                    self.risk = risk
                    self.stop_px = o - self.side * risk
                    self.entry_bar = i
                    self.last_bar = min(i + c.max_hold, c.n_bars - 1)
            self.pending = 0

        # 2. manage the open position on this bar
        if self.side != 0 and live:
            hit = (lo <= self.stop_px) if self.side == 1 else (hi >= self.stop_px)
            if hit:
                # gap-through fills at the open, mirroring the kernel
                gapped = (o < self.stop_px) if self.side == 1 else (o > self.stop_px)
                self._close(o if gapped else self.stop_px, i, 0)
        if self.side != 0 and i >= self.last_bar:
            # horizon: the kernel walks back to the last bar that traded
            if live:
                self._close(cl, i, 1)
            elif self.live_i >= self.entry_bar and self.live_i >= 0:
                self._close(self.live_close, self.live_i, 1)

        # 3. indicators, from bars already closed. rvol reads PRIOR bars only,
        #    so the baseline is taken before this bar is appended.
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
            self.day = day
        tp = (hi + lo + cl) / 3.0
        # sweep.vwap_series forward-fills a zero volume with the last non-zero
        w = vol if vol > 0 else (self.last_v if self.last_v > 0 else 1.0)
        if vol > 0:
            self.last_v = vol
        self.pv += tp * w
        self.vv += w
        self.p2v += tp * tp * w
        vwap = self.pv / self.vv if self.vv > 0 else float("nan")
        var = (self.p2v / self.vv - vwap * vwap) if self.vv > 0 else float("nan")
        sd = float(np.sqrt(max(var, 0.0))) if var == var else float("nan")
        z = ((cl - vwap) / sd) if (sd == sd and sd > vwap * 1e-6) else float("nan")

        if live:
            self.live_i, self.live_close = i, cl
        self.n += 1

        # 4. decide on the closed bar. The kernel only looks at a bar it is flat
        #    on, that is live, whose NEXT bar is live too - and it never starts a
        #    trade on the last bar of the series.
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
        self.pending = want
        self.pending_sd = sd

    def on_stop(self):
        # The kernel's scan ends at n-1 and books whatever is open at `last`,
        # which the horizon branch above has already handled.
        self.side = 0

    def _close(self, px: float, exit_i: int, reason: int):
        c = self.config
        gross = (px - self.entry_px) * self.side
        fees = (self.entry_px + px) * (c.fee_bps + c.slip_bps) / 1e4 / 2
        self.trades.append({
            "entry_bar": self.entry_bar, "exit_bar": exit_i, "dir": self.side,
            "entry_px": self.entry_px, "exit_px": px,
            "r": (gross - fees) / self.risk, "reason": reason})
        self.side = 0
        # The kernel resumes its scan AT the exit bar (`i = exit_i`), so a trade
        # that opens and stops inside the same bar leaves that bar available for
        # a fresh decision. Blocking it here - which the first version did for
        # same-bar exits - pushed every subsequent entry one bar late and made
        # the whole comparison look like a causality disagreement when it was
        # this port's bookkeeping.
        self.blocked_until = exit_i - 1


def kernel_trades(df, feats, cfg, fee, slip) -> pd.DataFrame:
    tr = STRATEGY.run(df, cfg, fee, slip, feats=feats)
    return pd.DataFrame({
        "entry_bar": tr[:, T_ENTRY_I].astype(int),
        "exit_bar": tr[:, T_EXIT_I].astype(int),
        "dir": tr[:, T_DIR].astype(int),
        "entry_px": tr[:, T_ENTRY_PX], "exit_px": tr[:, T_EXIT_PX],
        "r": tr[:, T_R], "reason": tr[:, T_REASON].astype(int)})


def one(df, feats, cfg, fee, slip) -> dict:
    ref = kernel_trades(df, feats, cfg, fee, slip)

    engine = make_engine()
    instrument = fx_instrument(SYM)
    _, bar_type = add_bars_for(engine, df, instrument, bar_spec=BAR_SPEC)
    strat = VwapBreak(BreakConfig(
        bar_type=str(bar_type), n_bars=len(df),
        thr=float(cfg["thr"]), stop_sig=float(cfg["stop_sig"]),
        max_hold=int(cfg["max_hold"]), hour_lo=int(cfg["hour_lo"]),
        hour_hi=int(cfg["hour_hi"]), min_rvol=float(cfg["min_rvol"]),
        min_risk_bps=float(cfg["min_risk_bps"]),
        fee_bps=float(fee), slip_bps=float(slip)))
    engine.add_strategy(strat)
    engine.run()
    engine.dispose()
    nau = pd.DataFrame(strat.trades)

    row = {k: cfg[k] for k in ("thr", "stop_sig", "max_hold", "hour_lo",
                               "hour_hi", "min_rvol")}
    row |= {"kernel": len(ref), "stream": len(nau)}
    if len(ref) and len(nau):
        j = ref.merge(nau, on="entry_bar", how="outer", suffixes=("_k", "_s"),
                      indicator=True)
        both = j[j._merge == "both"]
        row |= {
            "matched": len(both),
            "kernel_only": int((j._merge == "left_only").sum()),
            "stream_only": int((j._merge == "right_only").sum()),
            "entry_match": round(len(both) / max(len(ref), 1), 4),
            "exit_bar_match": round(float((both.exit_bar_k == both.exit_bar_s).mean()), 4),
            "max_entry_px_diff": float((both.entry_px_k - both.entry_px_s).abs().max()),
            "max_exit_px_diff": float((both.exit_px_k - both.exit_px_s).abs().max()),
            "max_r_diff": float((both.r_k - both.r_s).abs().max()),
        }
    else:
        row |= {"matched": 0, "entry_match": 0.0, "kernel_only": len(ref),
                "stream_only": len(nau)}
    return row


def configs() -> list[dict]:
    """The five traded settings, plus a spread of others from the real grid so
    the check is not limited to the shapes that happen to be in production."""
    out = [dict(s, min_risk_bps=3.0) for s in SETTINGS]
    grid = grid_for(24)                       # 1h -> 24 bars per hour-unit
    for cfg in grid[::137]:                   # a deterministic spread
        if len(out) >= 14:
            break
        out.append(dict(cfg))
    return out


def main() -> int:
    df = load(SYM, TF)
    feats = STRATEGY.features(df)
    c = COSTS[SYM]
    fee, slip = c.per_side(EXEC_MODE)
    cfgs = configs()
    print(f"{SYM} {TF}: {len(df):,} bars {df.index[0].date()} -> {df.index[-1].date()}, "
          f"{len(cfgs)} configurations (first 5 are the traded ones)\n")
    print(f"{'thr':>5}{'stop':>6}{'hold':>6}{'sess':>8}{'rvol':>6}"
          f"{'kernel':>8}{'stream':>8}{'entry':>8}{'exit bar':>9}{'max dR':>10}")
    rows = []
    for k, cfg in enumerate(cfgs):
        r = one(df, feats, cfg, fee, slip)
        rows.append(r)
        sess = (f"{cfg['hour_lo']:02d}-{cfg['hour_hi']:02d}"
                if cfg["hour_lo"] != cfg["hour_hi"] else "all")
        print(f"{cfg['thr']:5.2f}{cfg['stop_sig']:6.1f}{cfg['max_hold']:6d}{sess:>8}"
              f"{cfg['min_rvol']:6.1f}{r['kernel']:8d}{r['stream']:8d}"
              f"{r['entry_match']:8.4f}{r.get('exit_bar_match', 0):9.4f}"
              f"{r.get('max_r_diff', float('nan')):10.2e}"
              + ("   <- TRADED" if k < 5 else ""), flush=True)

    out = pd.DataFrame(rows)
    dest = ROOT / "backtests" / "vwapbreak" / "nautilus_check.csv"
    out.to_csv(dest, index=False)
    bad = out[out.entry_match < 0.9999]
    print(f"\n{len(out) - len(bad)} of {len(out)} configurations match every entry bar.")
    if len(bad):
        print("DISAGREEMENTS — an entry-bar difference is a causality finding:")
        print(bad.to_string(index=False))
    print(f"max |dR| across all matched trades: {out.max_r_diff.max():.3e}")
    print(f"wrote {dest.relative_to(ROOT)}")
    return 0 if not len(bad) else 1


if __name__ == "__main__":
    raise SystemExit(main())
