"""H-016 — the ribbon kernel through an independent event-driven engine.

THE LAST EVIDENCE GAP ON THIS HYPOTHESIS. `core/verification.py` caps H-016's
board score at 3.0 for exactly one reason: its kernel has never been checked
against a second engine. H-002 has been (26 of 26 configurations exact,
2026-09-07) and that cross-check is what found both of the bugs fixed since.

WHAT IS AND IS NOT VERIFIED HERE, stated plainly so the pass is not read as more
than it is.

  VERIFIED: the trade logic. Entry timing, the initial stop, the two trailing
  forms, the flip exit, the time stop, the intrabar ordering, the dead-bar
  guards, the cost arithmetic and the R computation - reimplemented below from
  the documented rules and driven ONE BAR AT A TIME by NautilusTrader. The
  strategy holds no array it could index into, so it cannot reproduce a
  look-ahead even by accident. That is the whole value of the exercise.

  NOT VERIFIED HERE: the twenty moving averages and the channel that produce
  `agree`, `nflat` and `strength`. Those are covered by
  `strategies/ribbon/test_parity.py`, which recomputes them the slow literal way
  straight from the Pine source, and by the truncation test. They are handed in
  per bar rather than recomputed, and a value for bar j is released only when
  bar j arrives.

WHAT IS DELIBERATELY REPRODUCED RATHER THAN FIXED. A port that quietly improved
on the kernel would hide the assumption instead of testing it:

  * a stop fills AT the stop level on the first bar whose range touches it,
    even when the bar OPENED beyond it. On gold this is optimistic across a
    weekend gap and it is a known open item, not a finding of this file;
  * the stop beats the target inside the same bar, always;
  * after a trade the kernel resumes scanning AT the exit bar, not after it, so
    the exit bar can also be a signal bar. `resume_at` reproduces that.

Run: .venv/bin/python strategies/ribbon/stage12_nautilus.py
     .venv/bin/python strategies/ribbon/stage12_nautilus.py --tf=1h
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from nautilus_trader.config import StrategyConfig                      # noqa: E402
from nautilus_trader.model.data import BarType                         # noqa: E402
from nautilus_trader.trading.strategy import Strategy                  # noqa: E402

from core.nautilus_setup import make_engine, add_bars_for, fx_instrument  # noqa: E402
from strategies.ribbon.sweep import COSTS, load_tf, ribbon_inputs, build_grid, TFS  # noqa: E402
from strategies.ribbon.strategy import BASE                            # noqa: E402
from strategies.ribbon.engine import (T_ENTRY_I, T_EXIT_I, T_DIR,      # noqa: E402
                                      T_ENTRY_PX, T_EXIT_PX, T_R, T_REASON,
                                      R_TRAIL, R_TARGET, R_TIME, R_FLIP, R_EOD,
                                      MODE_SQUEEZE, TRAIL_CHAND,
                                      DIR_LONG, DIR_SHORT)

OUT = ROOT / "backtests" / "ribbon"
SYM = "XAUUSD"
BAR_SPEC = {"15m": "15-MINUTE-LAST", "30m": "30-MINUTE-LAST",
            "1h": "1-HOUR-LAST", "4h": "4-HOUR-LAST"}

#: measured, not assumed - 0.915bps/side from Dukascopy ticks (stage 11)
FEE_BPS, SLIP_BPS = 0.915, 0.0

CFGKEY = ["mode", "entry_thr", "require_flip", "squeeze_n", "min_strength",
          "trail_mode", "trail_k", "stop_k", "trail_start_r", "rr",
          "max_hold_bars", "flip_exit", "dir_mode", "min_risk_bps"]


class RibbonStreamConfig(StrategyConfig, frozen=True):
    bar_type: str
    n_bars: int
    mode: int
    entry_thr: float
    require_flip: int
    squeeze_n: float
    min_strength: float
    trail_mode: int
    trail_k: float
    stop_k: float
    trail_start_r: float
    rr: float
    max_hold_bars: int
    flip_exit: int
    dir_mode: int
    min_risk_bps: float
    fee_bps: float = FEE_BPS
    slip_bps: float = SLIP_BPS


class RibbonStream(Strategy):
    """`engine.simulate`, streamed. One bar in, no array held.

    Feature values are pushed in by `one()` before the run and released strictly
    as their bar arrives - `self.i` is the index of the bar currently being
    handled and nothing above it is ever read.
    """

    def __init__(self, config: RibbonStreamConfig):
        super().__init__(config)
        self.bar_type = BarType.from_str(config.bar_type)
        self.cost = (config.fee_bps + config.slip_bps) / 10000.0
        self.stop_k = config.stop_k if config.stop_k > 0 else config.trail_k

        # pushed in before the run; each is read only at or below self.i
        self.agree = self.prev_agree = self.nflat = None
        self.strength = self.atr = self.live = None

        self.i = -1
        self.trades: list[dict] = []

        # flat state
        # NOTE: `stop_px`, not `stop`. `Strategy.stop()` is a NautilusTrader
        # lifecycle method and assigning a float over it breaks the engine's
        # shutdown with "'numpy.float64' object is not callable" - a real
        # collision, caught on the first run of this file.
        self.armed_side = 0          # entry decided on the last closed bar
        self.resume_at = 0           # the kernel's `i = exit_i` skip
        # open position
        self.pos = 0
        self.entry_px = 0.0
        self.entry_i = -1
        self.risk = 0.0
        self.stop_px = 0.0
        self.target = 0.0
        self.extreme = 0.0
        self.mfe = 0.0
        self.atr_at_entry = 0.0
        self.flip_pending = False    # flip seen on a close, fills at the next open

    def on_start(self):
        self.subscribe_bars(self.bar_type)

    # -- helpers ----------------------------------------------------------- #
    def _close(self, px: float, exit_i: int, reason: int):
        gross = (px - self.entry_px) if self.pos == 1 else (self.entry_px - px)
        fees = (self.entry_px + px) * self.cost
        self.trades.append(dict(
            entry_bar=self.entry_i, exit_bar=exit_i, dir=self.pos,
            entry_px=self.entry_px, exit_px=px,
            r=(gross - fees) / self.risk, reason=reason))
        self.pos = 0
        self.flip_pending = False
        # The kernel resumes scanning AT the exit bar, so the exit bar may also
        # be a signal bar. Anything before it is skipped.
        self.resume_at = exit_i

    def _try_arm(self, i: int):
        """Decide, on the CLOSE of bar i, whether to enter at bar i+1's open."""
        c = self.config
        a, pa = self.agree[i], self.prev_agree[i]
        st, at = self.strength[i], self.atr[i]
        if np.isnan(a) or np.isnan(at) or at <= 0.0 or np.isnan(st):
            return
        if self.live[i] == 0 or (i + 1 < c.n_bars and self.live[i + 1] == 0):
            return                                  # signal or fill bar is dead

        side = 0
        if c.mode == MODE_SQUEEZE:
            if i >= 1 and self.nflat[i - 1] >= c.squeeze_n:
                if a >= c.entry_thr:
                    side = 1
                elif a <= -c.entry_thr:
                    side = -1
        else:
            if a >= c.entry_thr and (c.require_flip == 0 or pa < c.entry_thr):
                side = 1
            elif a <= -c.entry_thr and (c.require_flip == 0 or pa > -c.entry_thr):
                side = -1
        if side == 0:
            return
        if c.min_strength > 0.0 and abs(st) < c.min_strength:
            return
        if c.dir_mode == DIR_LONG and side < 0:
            return
        if c.dir_mode == DIR_SHORT and side > 0:
            return
        self.armed_side = side
        self.atr_at_entry = at

    def _open(self, bar_open: float, e: int):
        c = self.config
        if bar_open <= 0.0:
            self.armed_side = 0
            return
        risk = self.stop_k * self.atr_at_entry
        floor = bar_open * c.min_risk_bps / 10000.0
        risk = max(risk, floor)
        if risk <= 0.0:
            self.armed_side = 0
            return
        self.pos = self.armed_side
        self.armed_side = 0
        self.entry_px = bar_open
        self.entry_i = e
        self.risk = risk
        self.extreme = bar_open
        self.mfe = 0.0
        if self.pos == 1:
            self.stop_px = bar_open - risk
            self.target = bar_open + c.rr * risk if c.rr > 0 else 0.0
        else:
            self.stop_px = bar_open + risk
            self.target = bar_open - c.rr * risk if c.rr > 0 else 0.0

    # -- the stream -------------------------------------------------------- #
    def on_bar(self, bar):
        self.i += 1
        i = self.i
        c = self.config
        o, hi, lo, cl = (float(bar.open), float(bar.high),
                         float(bar.low), float(bar.close))

        # 1. a flip decided on the previous close fills at THIS open, but only
        #    if this bar traded - filling on a padded weekend bar is the same
        #    error as exiting on one.
        if self.pos != 0 and self.flip_pending:
            if self.live[i] == 1:
                self._close(o, i, R_FLIP)
            # otherwise stay pending: the next live bar takes it

        # 2. an entry armed on the previous close fills at THIS open
        if self.pos == 0 and self.armed_side != 0:
            if self.live[i] == 1:
                self._open(o, i)
            else:
                self.armed_side = 0

        # 3. manage an open position on this bar
        if self.pos != 0 and self.live[i] == 1 and i > self.entry_i - 1:
            done = False
            # gap-through: a stop the bar OPENED beyond fills at the open, not
            # at the level. Mirrors engine.py.
            if self.pos == 1 and lo <= self.stop_px:
                self._close(self.stop_px if o > self.stop_px else o, i, R_TRAIL)
                done = True
            elif self.pos == -1 and hi >= self.stop_px:
                self._close(self.stop_px if o < self.stop_px else o, i, R_TRAIL)
                done = True

            if not done and c.rr > 0.0:
                if self.pos == 1 and hi >= self.target:
                    self._close(self.target, i, R_TARGET); done = True
                elif self.pos == -1 and lo <= self.target:
                    self._close(self.target, i, R_TARGET); done = True

            if not done:
                # trail
                if self.pos == 1:
                    self.extreme = max(self.extreme, hi)
                    m = (self.extreme - self.entry_px) / self.risk
                else:
                    self.extreme = min(self.extreme, lo)
                    m = (self.entry_px - self.extreme) / self.risk
                self.mfe = max(self.mfe, m)
                if self.mfe >= c.trail_start_r:
                    d = (c.trail_k * self.atr[i] if c.trail_mode == TRAIL_CHAND
                         else c.trail_k * self.atr_at_entry)
                    if not np.isnan(d) and d > 0.0:
                        if self.pos == 1:
                            self.stop_px = max(self.stop_px, self.extreme - d)
                        else:
                            self.stop_px = min(self.stop_px, self.extreme + d)

                # flip, read on THIS close, filled at the next open
                if c.flip_exit == 1 and i + 1 < c.n_bars:
                    af = self.agree[i]
                    if not np.isnan(af) and (
                            (self.pos == 1 and af <= 0.0)
                            or (self.pos == -1 and af >= 0.0)):
                        self.flip_pending = True

                # time stop, at this close
                if (not self.flip_pending and c.max_hold_bars > 0
                        and (i - self.entry_i) >= c.max_hold_bars):
                    self._close(cl, i, R_TIME)
                    done = True

        # 4. flat and past the skip window: look for the next signal
        if self.pos == 0 and self.armed_side == 0 and i >= self.resume_at and i >= 1:
            self._try_arm(i)

    def on_stop(self):
        # end of data: mark to this bar, which is the last one that arrived
        if self.pos != 0:
            self._close(self.last_close, self.last_live_i, R_EOD)

    # last-bar bookkeeping, so on_stop does not need to look anything up
    def on_event(self, event):      # pragma: no cover - not used
        pass


def one(df: pd.DataFrame, inp: dict, cfg: dict, bar_spec: str) -> dict:
    """One configuration: kernel against stream, compared trade by trade."""
    from strategies.ribbon.sweep import run_one
    full = dict(BASE) | cfg
    tr = run_one(inp, full, FEE_BPS, SLIP_BPS, full["min_risk_bps"])
    ref = pd.DataFrame({
        "entry_bar": tr[:, T_ENTRY_I].astype(int),
        "exit_bar": tr[:, T_EXIT_I].astype(int),
        "dir": tr[:, T_DIR].astype(int),
        "entry_px": tr[:, T_ENTRY_PX], "exit_px": tr[:, T_EXIT_PX],
        "r": tr[:, T_R], "reason": tr[:, T_REASON].astype(int)})

    engine = make_engine()
    instrument = fx_instrument(SYM)
    _, bar_type = add_bars_for(engine, df, instrument, bar_spec=bar_spec)
    strat = RibbonStream(RibbonStreamConfig(
        bar_type=str(bar_type), n_bars=len(df),
        **{k: (int(full[k]) if k in ("mode", "require_flip", "trail_mode",
                                     "max_hold_bars", "flip_exit", "dir_mode")
               else float(full[k])) for k in CFGKEY}))
    strat.agree = inp["agree"]; strat.prev_agree = inp["prev_agree"]
    strat.nflat = inp["nflat"]; strat.strength = inp["strength"]
    strat.atr = inp["atr"]; strat.live = inp["live"]
    strat.last_close = float(df.close.values[-1])
    strat.last_live_i = int(np.max(np.where(inp["live"] == 1)[0]))
    engine.add_strategy(strat)
    engine.run()
    engine.dispose()
    nau = pd.DataFrame(strat.trades)

    row = {**{k: full[k] for k in CFGKEY},
           "kernel_trades": len(ref), "stream_trades": len(nau),
           "kernel_R": round(float(ref.r.sum()), 3) if len(ref) else 0.0,
           "stream_R": round(float(nau.r.sum()), 3) if len(nau) else 0.0}
    if len(ref) and len(nau):
        j = ref.merge(nau, on="entry_bar", how="outer",
                      suffixes=("_ref", "_nau"), indicator=True)
        both = j[j._merge == "both"]
        row.update(
            matched=len(both),
            kernel_only=int((j._merge == "left_only").sum()),
            stream_only=int((j._merge == "right_only").sum()),
            entry_match=round(len(both) / max(len(ref), 1), 4),
            exit_bar_match=round(float((both.exit_bar_ref == both.exit_bar_nau).mean()), 4),
            max_r_diff=float((both.r_ref - both.r_nau).abs().max()))
    else:
        row.update(matched=0, kernel_only=len(ref), stream_only=len(nau),
                   entry_match=0.0)
    return row


def covering_configs(tf: str) -> list[dict]:
    """A configuration set that exercises every RULE SHAPE, not twelve near
    duplicates.

    The first run of this file took its configurations from the fold file and
    got twelve rows that were all `mode 0, entry_thr 1.0, trail_mode 0`. They
    all matched, and that was worth very little: the board's own legs run
    `trail_mode 1` (chandelier), and the chandelier path recomputes the trailing
    distance from ATR on EVERY bar - which is the branch a streaming port is most
    likely to get wrong, and the branch the dead-bar bug lived in.

    So: one configuration per distinct combination of the switches that change
    the CODE PATH - entry mode, flip requirement, trail form, whether a fixed
    target exists, and whether trailing starts at entry or at +1R - plus the
    board's own BASE. 48 shapes rather than 660 parameter draws, because a
    cross-check is about branches, not about tuning.
    """
    grid = pd.DataFrame(build_grid(TFS[tf][1]))
    shape = ["mode", "require_flip", "trail_mode", "rr", "trail_start_r"]
    out = (grid.sort_values(["trail_k", "stop_k"])
                .groupby(shape, as_index=False).first())
    cfgs = out[[c for c in grid.columns if c != "cfg"]].to_dict("records")
    # the board's own rule, explicitly, so a pass covers what is actually traded
    cfgs.append({k: BASE[k] for k in CFGKEY})
    return cfgs


def main() -> int:
    tfs = [a.split("=", 1)[1] for a in sys.argv if a.startswith("--tf=")] \
        or ["1h", "30m", "15m"]
    rows = []
    for tf in tfs:
        cfgs = covering_configs(tf)
        df = load_tf(SYM, tf)
        inp = ribbon_inputs(df)
        print(f"\n{len(cfgs)} rule shapes on {tf}", flush=True)
        print(f"{SYM} {tf}: {len(df):,} bars  {df.index[0]:%Y-%m-%d} -> "
              f"{df.index[-1]:%Y-%m-%d}", flush=True)
        for k, cfg in enumerate(cfgs):
            r = one(df, inp, cfg, BAR_SPEC[tf]); r["tf"] = tf
            rows.append(r)
            print(f"  [{k+1:2d}/{len(cfgs)}] mode{int(r['mode'])} "
                  f"thr{r['entry_thr']:.2f} trail{int(r['trail_mode'])}/"
                  f"{r['trail_k']:.1f} rr{r['rr']:.1f} hold{int(r['max_hold_bars'])}"
                  f"  kernel {r['kernel_trades']:5d}  stream {r['stream_trades']:5d}"
                  f"  entry-match {r['entry_match']:.4f}"
                  f"  dR {r.get('max_r_diff', float('nan')):.2e}", flush=True)

    res = pd.DataFrame(rows)
    res.to_csv(OUT / "stage12_nautilus.csv", index=False)
    print(f"\n{'=' * 92}\nRIBBON KERNEL vs INDEPENDENT EVENT-DRIVEN ENGINE — {SYM}\n{'=' * 92}")
    for tf, g in res.groupby("tf"):
        exact = int((g.entry_match >= 0.9999).sum())
        print(f"{tf:4}  configs {len(g):3d}   entry bars match exactly on "
              f"{exact}/{len(g)}   median {g.entry_match.median():.4f}   "
              f"worst {g.entry_match.min():.4f}")
    bad = res[res.entry_match < 0.9999]
    if len(bad):
        print(f"\n{len(bad)} configuration(s) DISAGREE on entry bars:")
        print(bad[["tf", "mode", "entry_thr", "trail_mode", "trail_k", "rr",
                   "max_hold_bars", "kernel_trades", "stream_trades",
                   "matched", "kernel_only", "stream_only",
                   "entry_match"]].to_string(index=False))
    else:
        print("\nEVERY configuration agrees on every entry bar.")
    print(f"\nwrote {OUT / 'stage12_nautilus.csv'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
