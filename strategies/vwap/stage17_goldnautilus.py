"""H-002 stage 17 — the GOLD legs through an independent engine. TASK T2.

WHY THIS IS THE HIGHEST-RISK ITEM IN THE PROJECT RIGHT NOW. On 2026-09-06 three
look-aheads were found in `strategies/vwap/engine.py` by reading it, and when
they were fixed the crypto book went from 11 walk-forward cells clearing PF 1.20
at 2x on BTCUSDT to **zero**. Gold survived that fix and is now the entire book.
Gold has never been cross-checked against a second engine. The only cross-check
this project has ever run (`stage15_nautilus.py`) covers **one configuration on
one market**: BTCUSDT 4h, MODE_BREAK, rolling anchor, no target. Gold's
walk-forward selects twenty-five DIFFERENT rule shapes across five entry modes,
three anchors, both stop modes and two target modes. None of them has been
verified by anything but the kernel that produced them.

WHAT THIS DOES. Re-implements the kernel as a NautilusTrader strategy that is
handed one bar at a time and holds no array it could index into, then runs both
engines over the full XAUUSD series for every configuration the gold
walk-forward actually chose, and compares trade by trade.

  entry bars differ    -> a causality bug. This is the finding that matters.
  entry prices differ  -> a fill-timing bug.
  exit prices differ   -> an intrabar ordering assumption. Expected, and a
                          finding rather than a failure.

TWO PRECISION TRAPS, both fixed before anything was measured.

  1. `core.nautilus_setup.add_bars` builds bars against a BTCUSDT perpetual:
     **price_precision 1, size_precision 3**. Gold closes carry three decimals
     and Dukascopy's tick-count volume runs at 0.0216, so both would be rounded
     on the way in and every mismatch would belong to the rounding. This uses
     `fx_instrument("XAUUSD")` at 3 and 8.
  2. The kernel's last session ends at `n - 1`, which a streaming strategy
     cannot know. `n_bars` is passed in. That is knowledge of the dataset's
     length, not of any price, and without it the final session disagrees for a
     reason that has nothing to do with causality.

WHAT IS DELIBERATELY REPRODUCED RATHER THAN FIXED. Three places where the
kernel makes an intrabar assumption. A port that silently improved on them
would hide them:

  * a stop fills AT the stop level on the first bar that touches it;
  * a stop beats a target inside the same bar, always;
  * `target_mode=TGT_VWAP` exits at `vwap[j]`, the running VWAP of bar j
    INCLUDING bar j's own close and volume — a value that does not exist at the
    moment price is claimed to touch it. It is reproduced exactly here so the
    comparison stays clean, and it is measured separately by `--peek`.

Run: .venv/bin/python strategies/vwap/stage17_goldnautilus.py
     .venv/bin/python strategies/vwap/stage17_goldnautilus.py --peek
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
from nautilus_trader.trading.strategy import Strategy                   # noqa: E402

from core.nautilus_setup import make_engine, add_bars_for, fx_instrument  # noqa: E402
from strategies.vwap.sweep import features, run_one, DEFAULTS           # noqa: E402
from strategies.vwap.stage3_timeframes import load_tf                   # noqa: E402
from strategies.vwap.engine import (PX_EPS_FRAC, SD_EPS_FRAC, T_ENTRY_I,  # noqa: E402
                                    T_EXIT_I, T_DIR, T_ENTRY_PX, T_EXIT_PX,
                                    T_R, T_REASON)

OUT = ROOT / "backtests" / "queue"
OUT.mkdir(parents=True, exist_ok=True)
# After the 2026-09-07 dead-bar fix the folds re-select, so the cross-check has
# to verify the shapes the CORRECTED walk-forward chose, not the old ones.
# --prefolds falls back to the pre-fix file for a like-for-like re-run.
FOLDS = ROOT / "backtests" / "vwap" / (
    "stage6_folds.parquet" if "--prefolds" in sys.argv
    else "stage6_folds_xauusd_deadfix.parquet")

SYM = "XAUUSD"
# Every timeframe the gold walk-forward selects on. 15m and 30m were missing
# until 2026-09-08: the port is timeframe-agnostic, they had simply never been
# listed, so `tests/test_second_engine.py` raised KeyError on them and the
# nightly suite reported a failure that was the TEST's, not the kernel's.
# Two-thirds of the board book was outside the cross-check and nothing said so.
TFS = {"5m": "5-MINUTE-LAST", "15m": "15-MINUTE-LAST", "30m": "30-MINUTE-LAST",
       "1h": "1-HOUR-LAST", "4h": "4-HOUR-LAST"}
# 4h is here because it is the board book's second leg AND because it is the
# only gold timeframe whose folds select target_mode=TGT_VWAP, the exit that
# reads bar j's own running VWAP. `--peek` re-runs it with that value taken
# from bar j-1 instead, which prices the assumption.
# XAUUSD cost, MEASURED not assumed: 1.68bps spread + ~0.15bps cTrader
# commission (SESSION_2026-09-06). Split as the kernel wants it.
FEE_BPS, SLIP_BPS = 0.15, 1.68

CFGKEY = ["anchor_hour", "anchor_minute", "mode", "fill_mode", "band_k",
          "stop_mode", "stop_k", "target_mode", "rr", "max_hold_bars",
          "min_rvol", "min_atr_rank", "max_atr_rank", "warmup_bars",
          "min_risk_bps"]

MODE_TREND, MODE_FADE, MODE_BREAK, MODE_RECLAIM, MODE_PULLBACK = 0, 1, 2, 3, 4
TGT_SESSION, TGT_VWAP, TGT_OPPOSITE, TGT_RR = 0, 1, 2, 3
R_STOP, R_TARGET, R_TIME, R_FLIP, R_VWAP = 0, 1, 2, 3, 4

ATR_LEN = 14
RVOL_LEN = 20 * 96
RANK_WIN, RANK_MIN = 96 * 60, 96 * 5


class GoldVwapConfig(StrategyConfig, frozen=True):
    bar_type: str
    n_bars: int
    anchor_hour: int
    anchor_minute: int
    mode: int
    band_k: float
    stop_mode: int
    stop_k: float
    target_mode: int
    rr: float
    max_hold_bars: int
    min_rvol: float
    min_atr_rank: float
    max_atr_rank: float
    warmup_bars: int
    min_risk_bps: float
    fee_bps: float = FEE_BPS
    slip_bps: float = SLIP_BPS
    vwap_peek: bool = True          # False = TGT_VWAP uses the PRIOR bar's VWAP


class GoldVwap(Strategy):
    """`engine.simulate` for fill_mode=FILL_CLOSE, streaming.

    THE ONE STRUCTURAL THING TO GET RIGHT. The kernel is a `while i < stop_bar`
    loop that sets `i = exit_i + 1` after a trade, so the bars a trade occupies
    are NEVER VISITED. Two pieces of state depend on that: MODE_TREND's
    `prev_side` and MODE_RECLAIM's `stretched_up`/`stretched_dn` flags, which
    are updated once per visited bar. A streaming port that folded every bar
    into those flags would take different trades — correctly, arguably, but it
    would not be testing the kernel. `self.blocked_until` reproduces the skip.

    SESSION BOUNDARIES, streamed. `stop_bar` is the next session's first bar and
    the kernel reads it before that bar exists. Two things need it and both are
    handled without looking forward:
      * an entry queued on bar i is CANCELLED at the open of bar i+1 if bar i+1
        turns out to start a new session (the kernel's `i + 1 < stop_bar`);
      * an open position is force-flat at the close of the bar BEFORE the new
        session's first bar, which is recognised when that first bar arrives.
    Both are the same rule a live trader follows off a wall clock.
    """

    def __init__(self, config: GoldVwapConfig):
        super().__init__(config)
        self.bar_type = BarType.from_str(config.bar_type)
        c = config
        self.rolling = c.anchor_hour < 0
        self.win = int(c.anchor_minute)          # rolling window, in bars

        self.n = 0
        self.sess_start = -1                     # index of the current session's first bar
        self.sess_id = -1
        self.tp_v: deque = deque(maxlen=self.win if self.rolling else 0)
        self.cum_pv = 0.0
        self.cum_v = 0.0
        self.cum_p2v = 0.0
        self.vols: deque = deque(maxlen=RVOL_LEN)       # PRIOR bars only
        self.atr = float("nan")
        self.atr_hist: deque = deque(maxlen=RANK_WIN)   # atr through bar n-1
        self.prev_close = float("nan")
        self.last_vol = 0.0                             # for the zero-volume ffill
        # The last bar that actually traded. The kernel's time exit walks BACK
        # to it when the horizon lands on Dukascopy's padded weekend, so the
        # port has to know it too. Added 2026-09-08 with the exit-path guard.
        self.live_i = -1
        self.live_close = float("nan")
        self.prev_bar = None                            # (o,h,l,c) of bar n-1
        self.prev_vwap = float("nan")

        self.blocked_until = -1                  # kernel's i = exit_i + 1
        self.prev_side = 0                       # MODE_TREND, per session
        self.stretched_up = 0
        self.stretched_dn = 0

        self.pending = 0                         # side queued for the next open
        self.pending_sd = 0.0
        self.pending_atr = 0.0
        self.pending_band = (0.0, 0.0)
        self.pending_rank = 0.0

        self.side = 0
        self.entry_px = 0.0
        self.stop_px = 0.0
        self.target_px = 0.0
        self.has_target = 0
        self.risk = 0.0
        self.entry_bar = -1
        self.horizon = -1                        # exit at the close of horizon-1
        self.trades: list[dict] = []

    def on_start(self):
        self.subscribe_bars(self.bar_type)

    # ---- indicators, all from bars already delivered -----------------------

    def _vwap(self):
        if self.rolling:
            if len(self.tp_v) < max(self.win // 4, 1):
                return None
            tp = np.fromiter((a for a, _ in self.tp_v), float, len(self.tp_v))
            v = np.fromiter((b for _, b in self.tp_v), float, len(self.tp_v))
            sv = v.sum()
            if sv <= 0:
                return None
            m = float((tp * v).sum() / sv)
            var = float((tp * tp * v).sum() / sv) - m * m
        else:
            if self.cum_v <= 0:
                return None
            m = self.cum_pv / self.cum_v
            var = self.cum_p2v / self.cum_v - m * m
        return m, float(np.sqrt(max(var, 0.0)))

    def _rank(self) -> float:
        """`atr_rank[i+1]` — the percentile rank of atr[i] inside the window
        ending at bar i, matching pandas `.rolling().rank(pct=True).shift(1)`
        with `average` ties and a 0.5 fill before min_periods."""
        h = self.atr_hist
        if len(h) < RANK_MIN:
            return 0.5
        a = np.fromiter(h, float, len(h))
        x = a[-1]
        less = float((a < x).sum())
        eq = float((a == x).sum())
        return (less + (eq + 1.0) / 2.0) / len(a)

    # ---- the bar loop ------------------------------------------------------

    def on_bar(self, bar):
        c = self.config
        o = float(bar.open); hi = float(bar.high)
        lo = float(bar.low); cl = float(bar.close); vol = float(bar.volume)
        i = self.n
        ts = pd.Timestamp(bar.ts_event, unit="ns", tz="UTC")
        # 21.5% of the XAUUSD series is zero-volume weekend padding. The kernel
        # refuses to decide, fill OR EXIT on one; before 2026-09-08 it only
        # refused the first two and so did this port. Keeping the port in step
        # is the point of the cross-check - a port that lags the kernel reports
        # disagreements that belong to itself.
        is_live = vol > 0.0

        # 1. is this bar the start of a session?
        if self.rolling:
            new_sess = (i >= self.win) and (i % self.win == 0)
        else:
            new_sess = (ts.hour == c.anchor_hour and ts.minute == c.anchor_minute)

        if new_sess:
            # force flat at the CLOSE of the previous bar - the kernel's
            # horizon = stop_bar with the time exit at horizon - 1
            if self.side != 0:
                # not necessarily bar i-1: the kernel walks back past padding,
                # stopping no earlier than the entry bar
                if self.live_i >= self.entry_bar and self.live_i >= 0:
                    self._close(self.live_close, self.live_i, R_TIME)
                else:
                    self._close(self.prev_close, i - 1, R_TIME)
            self.pending = 0                     # entry would have been at stop_bar
            self.sess_start = i
            self.sess_id += 1
            self.prev_side = 0
            self.stretched_up = 0
            self.stretched_dn = 0
            if not self.rolling:
                self.cum_pv = self.cum_v = self.cum_p2v = 0.0

        # 2. fill what the previous bar queued, at THIS bar's open
        if self.pending != 0 and self.side == 0:
            d = (c.stop_k * self.pending_sd if c.stop_mode == 0 else
                 c.stop_k * (self.pending_atr if self.pending_atr > 0
                             else self.pending_sd))
            ar = self.pending_rank
            # the kernel refuses a fill on a bar that never traded
            ok = vol > 0.0 and d > 0.0 and d >= o * c.min_risk_bps / 1e4
            if ok and c.min_atr_rank > 0.0 and ar < c.min_atr_rank:
                ok = False
            if ok and c.max_atr_rank > 0.0 and ar > c.max_atr_rank:
                ok = False
            if ok:
                self.side = self.pending
                self.entry_px = o
                self.risk = d
                self.stop_px = o - d if self.side == 1 else o + d
                self.entry_bar = i
                self.has_target = 0
                self.target_px = 0.0
                if c.target_mode == TGT_RR and c.rr > 0.0:
                    self.target_px = (o + c.rr * d if self.side == 1
                                      else o - c.rr * d)
                    self.has_target = 1
                elif c.target_mode == TGT_OPPOSITE:
                    up, dn = self.pending_band
                    self.target_px = dn if self.side == -1 else up
                    self.has_target = 1
                # THE HORIZON IS CAPPED AT THE END OF THE DATA, like the
                # kernel's. `horizon = stop_bar` there, tightened to
                # `entry_i + max_hold_bars` only when that lands INSIDE the
                # session - so a hold that runs off the end of the series
                # resolves at the last usable bar rather than never. This port
                # left the horizon uncapped and then dropped whatever was still
                # open when the stream stopped, which is how the 15m
                # MODE_BREAK config came to disagree on exactly one trade of
                # 416 - the last one, entered seven bars from the end. It was
                # logged as an unresolved second-engine disagreement; it is
                # this port's bookkeeping, not a kernel bug, and no board number
                # ever depended on it.
                h = (i + c.max_hold_bars if c.max_hold_bars > 0
                     else c.n_bars - 1)
                self.horizon = min(h, c.n_bars - 1)
                self.prev_side = self.side       # kernel sets it on entry
        self.pending = 0

        # 3. manage an open position on this bar, in the kernel's order:
        #    stop, target, vwap, flip - and the stop wins every tie.
        if self.side != 0 and is_live:
            j = i
            if self.side == 1:
                hit_stop = lo <= self.stop_px
                hit_tgt = self.has_target == 1 and hi >= self.target_px
            else:
                hit_stop = hi >= self.stop_px
                hit_tgt = self.has_target == 1 and lo <= self.target_px
            if hit_stop:
                # gap-through: a stop the bar OPENED beyond fills at the open.
                # Mirrors engine.py; a port one fix behind the kernel reports
                # disagreements that belong to itself.
                px = (self.stop_px
                      if (o > self.stop_px if self.side == 1 else o < self.stop_px)
                      else o)
                self._close(px, j, R_STOP)
            elif hit_tgt:
                self._close(self.target_px, j, R_TARGET)

        # 4. fold the now-closed bar into the indicators. rvol uses PRIOR bars
        #    for its baseline, so the deque is read before this bar is appended.
        base = (float(np.mean(self.vols)) if len(self.vols) >= RVOL_LEN // 4
                else float("nan"))
        rvol = vol / base if base == base and base > 0 else 0.0
        self.vols.append(vol)

        pc = self.prev_close if self.prev_close == self.prev_close else cl
        tr = max(hi - lo, abs(hi - pc), abs(lo - pc))
        self.atr = tr if self.atr != self.atr else \
            self.atr + (tr - self.atr) / ATR_LEN
        self.atr_hist.append(self.atr)
        # atr_rank[entry_i] == atr_rank[i+1] == the rank of atr[i] inside the
        # window ENDING AT i, because the series is ranked and then shifted.
        # Ranking before the append gave atr[i-1] and cost 40% of the entries.
        rank_next = self._rank()

        tp = (hi + lo + cl) / 3.0
        # `sweep.vwap_series` does `volume.replace(0, nan).ffill().fillna(1.0)`,
        # so a zero-volume bar is weighted by the LAST NON-ZERO volume and only
        # a leading run of zeros becomes 1.0. XAUUSD has zero-volume bars, so
        # weighting them 1.0 - which is what the BTC port did - moves the VWAP.
        if vol > 0:
            self.last_vol = vol
            w = vol
        else:
            w = self.last_vol if self.last_vol > 0 else 1.0
        if self.rolling:
            self.tp_v.append((tp, w))
        else:
            self.cum_pv += tp * w
            self.cum_v += w
            self.cum_p2v += tp * tp * w
        band = self._vwap()
        vwap_now = band[0] if band else float("nan")

        # 4b. the VWAP target and the TREND flip are checked on bar i using
        #     bar i's OWN vwap, exactly as the kernel does, and only after the
        #     entry bar (`j > entry_i`).
        if self.side != 0 and is_live and i > self.entry_bar:
            vw = vwap_now if c.vwap_peek else self.prev_vwap
            if c.target_mode == TGT_VWAP and vw == vw:
                if (self.side == 1 and hi >= vw) or (self.side == -1 and lo <= vw):
                    self._close(vw, i, R_VWAP)
            if self.side != 0 and c.mode == MODE_TREND and vw == vw:
                if (self.side == 1 and cl < vw) or (self.side == -1 and cl > vw):
                    self._close(cl, i, R_FLIP)
        # 4c. the time exit, when max_hold_bars binds
        if self.side != 0 and i >= self.horizon - 1:
            if is_live:
                self._close(cl, i, R_TIME)
            elif self.live_i >= self.entry_bar and self.live_i >= 0:
                self._close(self.live_close, self.live_i, R_TIME)

        prev = self.prev_bar
        prev_vw = self.prev_vwap                 # bar i-1's VWAP, which is what
        self.prev_bar = (o, hi, lo, cl)          # MODE_RECLAIM and MODE_PULLBACK
        self.prev_close = cl                     # compare against
        self.prev_vwap = vwap_now
        if is_live:
            self.live_i, self.live_close = i, cl
        self.n += 1

        # 5. decide on the closed bar i. The kernel only VISITS a bar it is flat
        #    on and that is past the last exit, and only inside the session.
        if self.side != 0 or i <= self.blocked_until or self.sess_start < 0:
            return
        if i < self.sess_start + c.warmup_bars:
            return
        if band is None:
            return
        v, sd = band
        # matches the kernel's post-2026-09-07 guard: `sd <= 0.0` let float
        # cancellation noise (~3e-5 on gold) through on a session of padded
        # weekend bars whose true sigma is exactly zero. See engine.SD_EPS_FRAC.
        if v <= 0.0 or sd <= v * SD_EPS_FRAC:
            return
        if vol <= 0.0:
            # the bar never traded - nothing to decide on. The kernel refuses
            # both the signal bar and the fill bar; the fill bar is checked
            # where `pending` is consumed.
            return
        upper, lower = v + c.band_k * sd, v - c.band_k * sd

        # the stretched flags are set on every VISITED bar, before the entry test
        if hi >= upper:
            self.stretched_up = 1
        if lo <= lower:
            self.stretched_dn = 1

        want = 0
        if c.mode == MODE_TREND:
            w_ = 1 if cl > v else (-1 if cl < v else 0)
            if w_ != 0 and w_ != self.prev_side:
                want = w_
        elif c.mode == MODE_FADE:
            want = -1 if cl > upper else (1 if cl < lower else 0)
        elif c.mode == MODE_BREAK:
            want = 1 if cl > upper else (-1 if cl < lower else 0)
        elif c.mode == MODE_RECLAIM:
            # engine.PX_EPS_FRAC. The kernel accumulates its VWAP with pandas
            # and this port accumulates it incrementally, so on a padded bar -
            # where the close IS the VWAP - the two land one ulp apart and the
            # comparison is decided by rounding. Same tolerance, same side.
            if i > self.sess_start + c.warmup_bars and prev is not None \
                    and prev_vw == prev_vw:
                ce = v * PX_EPS_FRAC
                pe = prev_vw * PX_EPS_FRAC
                if self.stretched_up and cl < v - ce and prev[3] >= prev_vw - pe:
                    want = -1
                elif self.stretched_dn and cl > v + ce and prev[3] <= prev_vw + pe:
                    want = 1
        elif c.mode == MODE_PULLBACK:
            if i > self.sess_start + c.warmup_bars and prev is not None \
                    and prev_vw == prev_vw:
                ce = v * PX_EPS_FRAC
                pe = prev_vw * PX_EPS_FRAC
                if prev[3] > prev_vw + pe and lo <= v + ce and cl > v + ce:
                    want = 1
                elif prev[3] < prev_vw - pe and hi >= v - ce and cl < v - ce:
                    want = -1
        if want == 0:
            return
        # the kernel's LAST session ends at n-1 and its entries need
        # `i + 1 < stop_bar`, so the final two bars can never open a trade
        if i + 1 >= c.n_bars - 1:
            return
        if c.min_rvol > 0.0 and rvol < c.min_rvol:
            return
        self.pending = want
        self.pending_sd = sd
        self.pending_atr = self.atr
        self.pending_band = (upper, lower)
        self.pending_rank = rank_next

    def on_stop(self):
        # Nothing should still be open: the horizon is capped at n_bars - 1, so
        # the time exit fires on the last usable bar exactly as the kernel's
        # does. This stays as a guard, not as a policy.
        self.side = 0

    def _close(self, px: float, exit_i: int, reason: int):
        c = self.config
        gross = (px - self.entry_px) if self.side == 1 else (self.entry_px - px)
        cost = (c.fee_bps + c.slip_bps) / 1e4
        fees = (self.entry_px + px) * cost
        self.trades.append({
            "entry_bar": self.entry_bar, "exit_bar": exit_i, "dir": self.side,
            "entry_px": self.entry_px, "exit_px": px,
            "r": (gross - fees) / self.risk, "reason": reason,
        })
        self.side = 0
        self.blocked_until = exit_i


# ---------------------------------------------------------------------------


def gold_configs(tfs=tuple(TFS)) -> dict:
    """The configurations the gold walk-forward actually chose, per timeframe.

    `stage6_folds.parquet` records the top-1 configuration of each fold — for a
    `topn=10` cell it is the highest-ranked of the ten and the other nine are
    not stored. So this covers the rule shapes gold trades, not the exact
    ten-leg book. Verifying the shapes is what a kernel cross-check is for; the
    book's weighting is arithmetic on top of them."""
    f = pd.read_parquet(FOLDS)
    g = f[f.symbol == SYM]
    out = {}
    for tf in tfs:
        s = g[g.tf == tf]
        if s.empty:
            continue
        out[tf] = s[CFGKEY].drop_duplicates().to_dict("records")
    return out


def one(df: pd.DataFrame, feats, cfg: dict, bar_spec: str, vwap_peek=True) -> dict:
    full = dict(DEFAULTS)
    full.update({k: cfg[k] for k in CFGKEY})
    tr = run_one(df, feats, {}, full, FEE_BPS, SLIP_BPS)
    ref = pd.DataFrame({
        "entry_bar": tr[:, T_ENTRY_I].astype(int),
        "exit_bar": tr[:, T_EXIT_I].astype(int),
        "dir": tr[:, T_DIR].astype(int), "entry_px": tr[:, T_ENTRY_PX],
        "exit_px": tr[:, T_EXIT_PX], "r": tr[:, T_R],
        "reason": tr[:, T_REASON].astype(int)})

    engine = make_engine()
    instrument = fx_instrument(SYM)
    _, bar_type = add_bars_for(engine, df, instrument, bar_spec=bar_spec)
    strat = GoldVwap(GoldVwapConfig(
        bar_type=str(bar_type), n_bars=len(df),
        vwap_peek=vwap_peek,
        **{k: (int(full[k]) if k in ("anchor_hour", "anchor_minute", "mode",
                                     "stop_mode", "target_mode",
                                     "max_hold_bars", "warmup_bars")
               else float(full[k])) for k in CFGKEY if k != "fill_mode"}))
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
            max_entry_px_diff=float((both.entry_px_ref - both.entry_px_nau).abs().max()),
            max_exit_px_diff=float((both.exit_px_ref - both.exit_px_nau).abs().max()),
            max_r_diff=float((both.r_ref - both.r_nau).abs().max()),
            exit_bar_match=round(float((both.exit_bar_ref == both.exit_bar_nau).mean()), 4))
    else:
        row.update(matched=0, kernel_only=len(ref), stream_only=len(nau),
                   entry_match=0.0)
    return row


def main():
    peek = "--peek" in sys.argv
    cfgs = gold_configs()
    rows = []
    for tf, spec in TFS.items():
        if tf not in cfgs:
            continue
        df = load_tf(SYM, tf)
        feats = features(df)
        print(f"\n{SYM} {tf}: {len(df):,} bars  {df.index[0]:%Y-%m-%d} -> "
              f"{df.index[-1]:%Y-%m-%d}  |  {len(cfgs[tf])} configs", flush=True)
        for k, cfg in enumerate(cfgs[tf]):
            r = one(df, feats, cfg, spec, vwap_peek=not peek)
            r["tf"] = tf
            rows.append(r)
            print(f"  [{k+1:2d}/{len(cfgs[tf])}] mode{int(cfg['mode'])} "
                  f"anch{int(cfg['anchor_hour'])}/{int(cfg['anchor_minute'])} "
                  f"stop{int(cfg['stop_mode'])} tgt{int(cfg['target_mode'])} "
                  f"hold{int(cfg['max_hold_bars'])}  "
                  f"kernel {r['kernel_trades']:5d}  stream {r['stream_trades']:5d}  "
                  f"entry-match {r['entry_match']:.4f}  "
                  f"dR {r.get('max_r_diff', float('nan')):.2e}", flush=True)

    res = pd.DataFrame(rows)
    tag = "_peekoff" if peek else ""
    res.to_csv(OUT / f"stage17_gold_nautilus{tag}.csv", index=False)

    print(f"\n{'=' * 92}")
    print(f"GOLD VWAP KERNEL vs INDEPENDENT EVENT-DRIVEN ENGINE — {SYM}")
    print(f"{'=' * 92}")
    for tf, g in res.groupby("tf"):
        exact = int((g.entry_match >= 0.9999).sum())
        print(f"{tf:4}  configs {len(g):3d}   entry bars match exactly on "
              f"{exact}/{len(g)}   median match {g.entry_match.median():.4f}   "
              f"worst {g.entry_match.min():.4f}")
    bad = res[res.entry_match < 0.9999]
    if len(bad):
        print(f"\n{len(bad)} configuration(s) DISAGREE on entry bars:")
        print(bad[["tf", "mode", "anchor_hour", "anchor_minute", "stop_mode",
                   "target_mode", "max_hold_bars", "kernel_trades",
                   "stream_trades", "matched", "kernel_only", "stream_only",
                   "entry_match"]].to_string(index=False))
    else:
        print("\nEVERY configuration agrees on every entry bar.")
    print(f"\nwrote {OUT / f'stage17_gold_nautilus{tag}.csv'}")


if __name__ == "__main__":
    main()
