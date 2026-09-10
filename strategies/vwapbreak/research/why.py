"""WHY does this work on gold and ETH and not on BTC, silver, oil or most FX?

Kris, 2026-09-10: "make investigation why exactly BTC and other major assets like
silver is not performing with this strategy, we need to understand this".

The strategy's own result cannot answer that: it is a walk-forward over a grid,
so a dead cell could be dead because the mechanism is absent, because the costs
eat it, or because the fold selector picked badly. This measures the MECHANISM
directly, with no strategy, no grid and no selection, so each market's answer is
its own.

THE MECHANISM, stated before it is measured. The rule buys a close that is `thr`
sigma above its own session VWAP and sells one that is `thr` below. It has no
target, a wide stop and a horizon of days. So it pays if and only if a market
that has just travelled a long way from its volume-weighted average price KEEPS
GOING - i.e. if displacement predicts continuation rather than reversion. Who is
on the other side: whoever is fading the move (the mean-reversion crowd this
project has already measured, H-010/H-011), plus anyone stopped out of it.

WHAT IS MEASURED PER MARKET AND TIMEFRAME

  follow-through   forward return over H bars, signed by the break direction,
                   entered at the NEXT open exactly as the strategy would, in
                   bps and gross of cost. Bucketed by |z| so monotonicity is
                   visible: a real mechanism gets stronger as the break gets
                   bigger, and H-008 died precisely because that response was
                   flat.
  edge net of cost the same number minus the cell's own round-trip cost. This is
                   what separates "no mechanism" from "mechanism too small for
                   the spread" - two different diagnoses with different cures.
  variance ratio   VR(k) = Var(k-bar return) / (k x Var(1-bar return)). Above 1
                   the market trends at that horizon, below 1 it mean-reverts.
                   A follow-the-break rule needs VR > 1 at its holding horizon.
  band economics   the sigma the stop is measured in, as bps, against the bar
                   range and against cost. A stop of k sigma on a market whose
                   sigma is small relative to its spread is a stop inside the
                   noise, whatever k is.
  break frequency  share of bars beyond the threshold: how much of the series
                   the rule even looks at.

Nothing here is a trading rule and nothing here is walk-forwarded, so no number
from this file may be quoted as a result. It is a diagnosis.

Run: .venv/bin/python strategies/vwapbreak/research/why.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from core.markets import COSTS, EXEC_MODE, TF_BPH, load            # noqa: E402
from core.run_hypothesis import window                             # noqa: E402
from strategies.vwap.sweep import vwap_series                      # noqa: E402
from strategies.vwapbreak.research.exits import UNIVERSE           # noqa: E402

TFS = ("1h", "4h")
#: the horizon the traded rule actually holds for, in HOURS (384 = a fortnight),
#: plus two shorter ones so the answer is not one number's luck
HORIZONS_H = (24, 96, 384)
Z_BUCKETS = (0.5, 1.0, 1.5, 2.0, 3.0)
THR = 1.0                      # the middle of the traded threshold grid


def cost_rt_bps(sym: str) -> float:
    """Round trip in bps, from the same table the kernels charge against."""
    return COSTS[sym].round_trip(EXEC_MODE)


def features(df: pd.DataFrame):
    vwap, vwstd, _ = vwap_series(df, 0, 0)
    c = df.close.values
    with np.errstate(invalid="ignore", divide="ignore"):
        z = (c - vwap) / np.where(vwstd > vwap * 1e-6, vwstd, np.nan)
    return z, vwstd


def variance_ratio(logret: np.ndarray, k: int) -> float:
    r = logret[np.isfinite(logret)]
    if len(r) < k * 20:
        return float("nan")
    v1 = np.var(r, ddof=1)
    agg = np.add.reduceat(r, np.arange(0, len(r) - len(r) % k, k))
    vk = np.var(agg, ddof=1)
    return float(vk / (k * v1)) if v1 > 0 else float("nan")


def row(sym: str, tf: str, span) -> dict:
    df = load(sym, tf)
    df = df[(df.index >= span[0]) & (df.index <= span[1])]
    live = df.volume.values > 0
    o, c = df.open.values, df.close.values
    z, sd = features(df)
    n = len(c)
    bph = TF_BPH[tf]
    logret = np.diff(np.log(np.where(c > 0, c, np.nan)))

    out = {"sym": sym, "tf": tf, "bars": int(n),
           "cost_rt_bps": round(cost_rt_bps(sym), 2),
           "live_pct": round(float(live.mean()) * 100, 1)}

    # --- band economics -------------------------------------------------- #
    rng = (df.high.values - df.low.values) / np.where(c > 0, c, np.nan) * 1e4
    sd_bps = sd / np.where(c > 0, c, np.nan) * 1e4
    ok = np.isfinite(sd_bps) & live
    out["sigma_bps"] = round(float(np.nanmedian(sd_bps[ok])), 1)
    out["bar_range_bps"] = round(float(np.nanmedian(rng[live])), 1)
    out["sigma_over_cost"] = round(out["sigma_bps"] / out["cost_rt_bps"], 1)
    out["break_pct"] = round(float(np.nanmean(np.abs(z[live]) >= THR)) * 100, 1)

    # --- trendiness ------------------------------------------------------- #
    for k in (int(24 * bph), int(96 * bph)):
        out[f"vr_{k}"] = round(variance_ratio(logret, max(2, k)), 3)

    # --- follow-through --------------------------------------------------- #
    # entry at the next open exactly as the strategy fills, exit at the open H
    # bars later. Gross, in bps, signed by the break direction.
    for hrs in HORIZONS_H:
        H = max(1, int(round(hrs * bph)))
        i = np.arange(n - H - 1)
        side = np.where(z[i] >= THR, 1.0, np.where(z[i] <= -THR, -1.0, 0.0))
        valid = (side != 0) & live[i] & live[i + 1] & np.isfinite(z[i])
        if valid.sum() < 30:
            out[f"ft_{hrs}h_bps"] = None
            continue
        e, x = o[i + 1][valid], o[i + 1 + H][valid]
        ret = side[valid] * (x - e) / e * 1e4
        out[f"ft_{hrs}h_bps"] = round(float(np.mean(ret)), 2)
        out[f"ft_{hrs}h_n"] = int(valid.sum())
        out[f"ft_{hrs}h_net_bps"] = round(float(np.mean(ret)) - out["cost_rt_bps"], 2)
        out[f"ft_{hrs}h_hit"] = round(float(np.mean(ret > 0)) * 100, 1)

    # --- monotonicity in z, at the traded horizon ------------------------- #
    H = max(1, int(round(384 * bph)))
    i = np.arange(n - H - 1)
    az = np.abs(z[i])
    side = np.sign(z[i])
    base_ok = live[i] & live[i + 1] & np.isfinite(z[i])
    e, x = o[i + 1], o[i + 1 + H]
    ret = side * (x - e) / e * 1e4
    resp = {}
    for lo, hi in zip(Z_BUCKETS, Z_BUCKETS[1:] + (99.0,)):
        m = base_ok & (az >= lo) & (az < hi)
        resp[f"{lo}"] = (round(float(np.mean(ret[m])), 1), int(m.sum())) if m.sum() >= 30 else None
    out["z_response"] = resp
    return out


def main() -> int:
    syms = [s for v in UNIVERSE.values() for s in v]
    span = window(syms, list(TFS))
    print(f"window {span[0].date()} -> {span[1].date()}\n")
    print(f"{'market':9}{'tf':4}{'cost':>6}{'sigma':>7}{'s/cost':>7}{'brk%':>6}"
          f"{'VR24':>7}{'VR96':>7}{'ft96h':>8}{'ft384h':>8}{'net384':>8}{'hit%':>6}")
    rows = []
    for group in UNIVERSE.values():
        for sym in group:
            for tf in TFS:
                r = row(sym, tf, span)
                rows.append(r)
                bph = TF_BPH[tf]
                print(f"{r['sym']:9}{r['tf']:4}{r['cost_rt_bps']:6.1f}"
                      f"{r['sigma_bps']:7.0f}{r['sigma_over_cost']:7.1f}"
                      f"{r['break_pct']:6.1f}"
                      f"{r.get(f'vr_{int(24*bph)}', float('nan')):7.2f}"
                      f"{r.get(f'vr_{int(96*bph)}', float('nan')):7.2f}"
                      f"{(r.get('ft_96h_bps') or 0):8.1f}"
                      f"{(r.get('ft_384h_bps') or 0):8.1f}"
                      f"{(r.get('ft_384h_net_bps') or 0):8.1f}"
                      f"{(r.get('ft_384h_hit') or 0):6.1f}", flush=True)

    dest = ROOT / "backtests" / "vwapbreak" / "why.json"
    dest.write_text(json.dumps({"thr": THR, "horizons_h": list(HORIZONS_H),
                                "rows": rows}, indent=1, default=str))
    print(f"\nwrote {dest.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
