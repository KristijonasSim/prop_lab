"""H-016 sweep driver - data loading, the config grid and the metric block.

One place so stage 2 (real), stage 3 (null) and stage 5 (walk-forward) cannot
drift apart. Costs come from H-002's per-asset table, so an H-016 number is
directly comparable with an H-002 one.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from core import fx_data                                             # noqa: E402
from strategies.ribbon import engine as E                            # noqa: E402
from strategies.ribbon.ribbon import RibbonParams, features          # noqa: E402
from strategies.vwap.stage1_grid import ASSETS                       # noqa: E402
from strategies.vwap.stage3_timeframes import (                      # noqa: E402
    null_seed, shuffle_market_paired)

OUT = ROOT / "backtests" / "ribbon"

#: (fee_bps, slip_bps, min_risk_bps) per side. H-002's table, extended.
COSTS = dict(ASSETS)
COSTS.update({"ETHUSDT": (5.0, 2.0, 10.0), "SOLUSDT": (5.0, 3.0, 12.0)})
# Index CFDs are charged GOLD's cost, not their own. Their real quoted spreads
# are tighter in bps (US30 ~2pts on 53,000 is 0.38bps against gold's 1.00), so
# this is deliberately pessimistic: an index result that clears here would
# clear on its own costs too, and cannot be accused of a flattering fee.
COSTS.update({"SPX500": (1.00, 0.50, 3.0), "US30": (1.00, 0.50, 3.0),
              "NAS100": (1.00, 0.50, 3.0)})

CRYPTO = ("BTCUSDT", "ETHUSDT", "SOLUSDT")
INDICES = ("SPX500", "US30", "NAS100")
FX = ("XAUUSD", "XAGUSD", "EURUSD", "GBPUSD", "USDJPY",
      "AUDUSD", "USDCAD", "USDCHF", "NZDUSD") + INDICES

#: rule -> (pandas resample rule, bars per 24h)
TFS = {"5m": ("5min", 288), "15m": ("15min", 96), "30m": ("30min", 48),
       "1h": ("1h", 24), "4h": ("4h", 6)}
AGG = {"open": "first", "high": "max", "low": "min", "close": "last",
       "volume": "sum"}


def load_tf(sym: str, tf: str) -> pd.DataFrame:
    """Bars for one market and timeframe, from the caches already in the repo."""
    rule = TFS[tf][0]
    if sym in CRYPTO:
        if tf == "5m":
            return pd.DataFrame()                 # crypto cache is 15m-based
        base = pd.read_parquet(ROOT / "data" / f"{sym}_spot_15m.parquet")
        if tf != "15m":
            base = base.resample(rule, label="left", closed="left").agg(
                AGG).dropna(subset=["open"])
        return base
    try:
        return fx_data.load(sym, rule)
    except Exception:
        return pd.DataFrame()


# --------------------------------------------------------------------------
# The grid
# --------------------------------------------------------------------------

def build_grid(bars_per_day: int) -> list[dict]:
    """Exit and entry variations around the rule Kris actually traded.

    His rule is the `entry_thr=1.0, require_flip=1, rr=0` corner: enter the bar
    the ribbon FIRST goes fully green, exit only on the trailing stop. The rest
    of the grid exists to say whether that corner is special or whether it is
    one draw from a cloud - which is the only way to tell a rule from a fit.
    """
    cfgs = []
    # A time stop of about a week on each timeframe, so a trade cannot hold
    # forever and quietly turn the book into buy-and-hold.
    week = int(bars_per_day * 7)
    # `trail_k` runs to 8 ATR deliberately: an earlier, narrower grid put its
    # optimum at the widest value it contained, and an optimum on the boundary
    # means the grid, not the market, chose the answer.
    for thr in (1.0, 0.8, 0.6):
        for flip in (1, 0):
            for tmode in (E.TRAIL_FIXED, E.TRAIL_CHAND):
                for tk in (1.0, 1.5, 2.0, 3.0, 4.0, 6.0, 8.0, 12.0, 16.0):
                    for rr in (0.0, 2.0):
                        for start in (0.0, 1.0, 2.0):
                            cfgs.append(dict(
                                mode=E.MODE_AGREE, entry_thr=thr,
                                require_flip=flip, squeeze_n=0,
                                min_strength=0.0, trail_mode=tmode,
                                trail_k=tk, stop_k=tk, trail_start_r=start,
                                rr=rr, max_hold_bars=week, flip_exit=0,
                                dir_mode=E.DIR_BOTH))
    # Variation C - the squeeze. The ribbon was compressed, then fanned out.
    for sq in (10, 14):
        for tmode in (E.TRAIL_FIXED, E.TRAIL_CHAND):
            for tk in (1.5, 2.0, 3.0):
                cfgs.append(dict(
                    mode=E.MODE_SQUEEZE, entry_thr=0.8, require_flip=0,
                    squeeze_n=sq, min_strength=0.0, trail_mode=tmode,
                    trail_k=tk, stop_k=tk, trail_start_r=0.0, rr=0.0,
                    max_hold_bars=week, flip_exit=0, dir_mode=E.DIR_BOTH))
    for i, c in enumerate(cfgs):
        c["cfg"] = i
    return cfgs


def ribbon_inputs(df: pd.DataFrame, p: RibbonParams | None = None) -> dict:
    """Everything the kernel needs that does not depend on the config."""
    f = features(df, p)
    agree = f["agree"].to_numpy(float)
    prev = np.concatenate(([np.nan], agree[:-1]))
    return dict(
        o=df["open"].to_numpy(float), h=df["high"].to_numpy(float),
        l=df["low"].to_numpy(float), c=df["close"].to_numpy(float),
        atr=E.atr_wilder(df["high"], df["low"], df["close"], 14),
        agree=agree, prev_agree=prev,
        nflat=f["n_flat"].to_numpy(float),
        strength=f["strength"].to_numpy(float),
    )


def run_one(inp: dict, cfg: dict, fee, slip, minrisk, gate=None,
            side_override=None) -> np.ndarray:
    g = gate if gate is not None else np.zeros_like(inp["agree"])
    so = (side_override if side_override is not None
          else np.zeros_like(inp["agree"]))
    return E.simulate(
        inp["o"], inp["h"], inp["l"], inp["c"], inp["atr"],
        inp["agree"], inp["prev_agree"], inp["nflat"], inp["strength"], g,
        int(cfg["mode"]), float(cfg["entry_thr"]), int(cfg["require_flip"]),
        float(cfg["squeeze_n"]), float(cfg["min_strength"]),
        int(cfg["trail_mode"]), float(cfg["trail_k"]), float(cfg["stop_k"]),
        float(cfg["trail_start_r"]), float(cfg["rr"]), int(cfg["max_hold_bars"]), int(cfg["flip_exit"]),
        int(cfg["dir_mode"]), so, 1 if side_override is not None else 0,
        1 if gate is not None else 0,
        float(fee), float(slip), float(minrisk))


# --------------------------------------------------------------------------
# Metrics - every field CLAUDE.md marks mandatory
# --------------------------------------------------------------------------

def _pf(r: np.ndarray) -> float:
    w, l = r[r > 0].sum(), -r[r < 0].sum()
    return float(w / l) if l > 0 else (np.inf if w > 0 else np.nan)


def metrics(tr: np.ndarray, index: pd.DatetimeIndex, fee, slip,
            entry_px_col=E.T_ENTRY_PX) -> dict:
    """PF at 1x/2x/3x, trades/day, hold, drawdown, Sharpe, days to +8%.

    2x and 3x are recomputed by charging the extra cost against the same
    trades, in R units, rather than re-running the kernel: re-running would
    also move every stop, which conflates "costs doubled" with "a different
    strategy". The repo's other engines do the same.
    """
    if tr.shape[0] == 0:
        return dict(trades=0, pf=np.nan, pf_2x=np.nan, pf_3x=np.nan)
    r = tr[:, E.T_R]
    ei = tr[:, E.T_ENTRY_I].astype(int)
    xi = tr[:, E.T_EXIT_I].astype(int)
    entry_ts = index[ei]
    exit_ts = index[xi]
    span = max((index[-1] - index[0]).total_seconds() / 86400.0, 1e-9)

    # Cost per trade in R: the round trip is (fee+slip) on each side, applied
    # to notional and divided by the risk that produced the R.
    px = tr[:, E.T_ENTRY_PX] + tr[:, E.T_EXIT_PX]
    with np.errstate(divide="ignore", invalid="ignore"):
        risk = np.where(r != 0, np.abs(
            (tr[:, E.T_EXIT_PX] - tr[:, E.T_ENTRY_PX])
            * np.where(tr[:, E.T_DIR] > 0, 1.0, -1.0)
            - px * (fee + slip) / 1e4) / np.abs(np.where(r == 0, np.nan, r)),
            np.nan)
    extra = np.where(np.isfinite(risk) & (risk > 0),
                     px * (fee + slip) / 1e4 / risk, 0.0)

    eq = np.concatenate(([0.0], np.cumsum(r)))
    dd = float((eq - np.maximum.accumulate(eq)).min())
    hold_h = (exit_ts.values - entry_ts.values).astype(
        "timedelta64[s]").astype(float).mean() / 3600.0
    daily = pd.Series(r, index=exit_ts).resample("1D").sum()
    sd = daily.std(ddof=1)
    r_per_day = float(r.sum()) / span

    return dict(
        trades=int(len(r)),
        pf=round(_pf(r), 4),
        pf_2x=round(_pf(r - extra), 4),
        pf_3x=round(_pf(r - 2 * extra), 4),
        trades_per_day=round(len(r) / span, 3),
        trades_per_week=round(7 * len(r) / span, 2),
        avg_hold_h=round(float(hold_h), 2),
        win_rate=round(float((r > 0).mean()), 4),
        avg_r=round(float(r.mean()), 4),
        total_r=round(float(r.sum()), 2),
        max_dd_r=round(dd, 2),
        sharpe=round(float(daily.mean() / sd * np.sqrt(365)), 3) if sd else 0.0,
        r_per_day=round(r_per_day, 4),
        # The phase gate. days = maxDD_in_R / R_per_day x (target / cap), the
        # formula HANDOFF.md fixes: risk is set so the book's drawdown exactly
        # fills the 8% cap, then time to +8% follows.
        days_to_target=(round(abs(dd) / r_per_day, 1)
                        if r_per_day > 0 and dd < 0 else np.nan),
        long_share=round(float((tr[:, E.T_DIR] > 0).mean()), 3),
        # The direction split is not cosmetic here. Gold and crypto both trend
        # up hard over these windows, so a wide-stop long-biased trend rule can
        # score well by being a slow buy-and-hold. If PF lives entirely on the
        # long side, that is the explanation to rule out before anything else.
        pf_long=round(_pf(r[tr[:, E.T_DIR] > 0]), 4),
        pf_short=round(_pf(r[tr[:, E.T_DIR] < 0]), 4),
        n_long=int((tr[:, E.T_DIR] > 0).sum()),
        n_short=int((tr[:, E.T_DIR] < 0).sum()),
    )


def sweep(df: pd.DataFrame, cfgs: list[dict], sym: str, tf: str,
          gate: np.ndarray | None = None,
          p: RibbonParams | None = None) -> pd.DataFrame:
    fee, slip, minrisk = COSTS[sym]
    inp = ribbon_inputs(df, p)
    rows = []
    for cfg in cfgs:
        c = dict(cfg); c["min_risk_bps"] = minrisk
        tr = run_one(inp, c, fee, slip, minrisk, gate=gate)
        m = metrics(tr, df.index, fee, slip)
        m.update(symbol=sym, tf=tf, cfg=cfg["cfg"], mode=cfg["mode"],
                 entry_thr=cfg["entry_thr"], require_flip=cfg["require_flip"],
                 trail_mode=cfg["trail_mode"], trail_k=cfg["trail_k"],
                 trail_start_r=cfg["trail_start_r"], rr=cfg["rr"],
                 squeeze_n=cfg["squeeze_n"])
        rows.append(m)
    return pd.DataFrame(rows)


def shuffled(df: pd.DataFrame, sym: str, tf: str, tag: str, seed_i: int
             ) -> pd.DataFrame:
    """The paired null. Each bar keeps its own volume; only sequence dies."""
    return shuffle_market_paired(df, seed=null_seed(sym, tf, tag, str(seed_i)))
