"""ONE FIXED CONFIGURATION, TEN MARKETS - market effect separated from selection.

`why.py` measured the mechanism with no strategy at all and found something that
does not line up with the board: silver has the STRONGEST raw follow-through of
any market here (+35.8bps over a fortnight against gold's +24.6) and yet loses to
its own null in the walk-forward, while ETH 1h has NEGATIVE raw follow-through
(-5.7bps) and is the second-best cell on the board.

So the mean forward move is not what this strategy harvests. It has no target and
a wide stop, so its payoff is a TRUNCATED one: losers are cut at k sigma, winners
run to the horizon. What it needs is not drift, it is asymmetry - the chance of a
long run in the break direction relative to the chance of an early k-sigma
adverse move.

WHAT THIS FILE ADDS. The walk-forward result mixes three things: the market, the
grid, and the quarterly selector that picks one cell out of 1,800 per fold. This
runs ONE configuration, unchanged, on every market - no grid, no selection - so
whatever differs between markets is the market.

    thr 1.0, stop 8 sigma, hold 384 hours, no session filter, no rvol filter

That is the middle of the traded threshold grid and the stop the selector most
often lands on. Two more configurations are run beside it (a tight stop and a
short hold) so the answer does not rest on one point of the grid.

REPORTED PER CELL: trades, win rate, average R, profit factor at 1x and 2x cost,
the share of gross profit made by the best five trades, R-skew, the mix of exit
reasons, and - the diagnostic that matters for the payoff shape - the median R of
winners against the median R of losers.

Nothing here is walk-forwarded and nothing here is selected, so no number in this
file is a result. It is a diagnosis of where the payoff comes from.

Run: .venv/bin/python strategies/vwapbreak/research/fixed.py
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
from core.strategy import T_DIR, T_ENTRY_I, T_EXIT_I, T_R, T_REASON  # noqa: E402
from strategies.vwapbreak.strategy import STRATEGY                 # noqa: E402
from strategies.vwapbreak.research.exits import UNIVERSE           # noqa: E402

TFS = ("1h", "4h")
ARMS = {
    "traded":     {"thr": 1.0, "stop_sig": 8.0,  "hold_h": 384},
    "tight stop": {"thr": 1.0, "stop_sig": 2.0,  "hold_h": 384},
    "short hold": {"thr": 1.0, "stop_sig": 8.0,  "hold_h": 96},
    "big break":  {"thr": 2.0, "stop_sig": 8.0,  "hold_h": 384},
}


def pf_band(r2: np.ndarray, draws: int = 2000, seed: int = 20260910) -> tuple:
    """10-90% band on profit factor at 2x cost, by resampling the trades.

    With 100-150 trades and a 28% win rate the point estimate of a profit factor
    is nearly meaningless on its own - one trade moves it. This is the same
    argument `core/noiseband.py` makes for the board, applied to a fixed
    configuration's trade list rather than to a daily series.
    """
    rng = np.random.default_rng(seed)
    n = len(r2)
    if n < 20:
        return None, None
    out = []
    for _ in range(draws):
        s = r2[rng.integers(0, n, n)]
        up, dn = s[s > 0].sum(), -s[s <= 0].sum()
        if dn > 0:
            out.append(up / dn)
    if not out:
        return None, None
    return round(float(np.quantile(out, 0.10)), 3), round(float(np.quantile(out, 0.90)), 3)


def stats(tr: np.ndarray, sym: str, tf: str, arm: str, r2: np.ndarray) -> dict:
    r = tr[:, T_R]
    if len(r) < 20:
        return {"sym": sym, "tf": tf, "arm": arm, "trades": int(len(r))}
    win, loss = r[r > 0], r[r <= 0]
    gross_win, gross_loss = float(win.sum()), float(-loss.sum())
    top5 = float(np.sort(win)[-5:].sum() / gross_win) if len(win) >= 5 else None
    reason = tr[:, T_REASON]
    return {
        "sym": sym, "tf": tf, "arm": arm,
        "trades": int(len(r)),
        "win_pct": round(float((r > 0).mean()) * 100, 1),
        "avg_r": round(float(r.mean()), 4),
        "pf": round(gross_win / gross_loss, 3) if gross_loss > 0 else None,
        "pf_2x": (round(float(r2[r2 > 0].sum() / -r2[r2 <= 0].sum()), 3)
                  if (r2 <= 0).any() and (r2 > 0).any() else None),
        "total_r": round(float(r.sum()), 1),
        # payoff SHAPE: what a winner is worth against what a loser costs
        "median_win_r": round(float(np.median(win)), 3) if len(win) else None,
        "median_loss_r": round(float(np.median(loss)), 3) if len(loss) else None,
        "max_r": round(float(r.max()), 2),
        "skew": round(float(pd.Series(r).skew()), 2),
        "top5_share_of_wins": round(top5, 3) if top5 else None,
        # how trades end: 0 = stop, 1 = horizon
        "stopped_pct": round(float((reason == 0).mean()) * 100, 1),
        "hold_bars_median": float(np.median(tr[:, T_EXIT_I] - tr[:, T_ENTRY_I])),
        "long_pct": round(float((tr[:, T_DIR] > 0).mean()) * 100, 1),
        "pf_2x_band": pf_band(r2),
    }


def main() -> int:
    syms = [s for v in UNIVERSE.values() for s in v]
    span = window(syms, list(TFS))
    rows = []
    print(f"{'market':9}{'tf':4}{'arm':12}{'trades':>7}{'win%':>7}{'avgR':>8}"
          f"{'PF':>7}{'PF2x':>7}{'medWin':>8}{'medLoss':>8}{'stop%':>7}{'top5':>7}")
    for group in UNIVERSE.values():
        for sym in group:
            df = None
            for tf in TFS:
                df = load(sym, tf)
                df = df[(df.index >= span[0]) & (df.index <= span[1])]
                feats = STRATEGY.features(df)
                fee, slip = COSTS[sym].per_side(EXEC_MODE)
                bph = TF_BPH[tf]
                for arm, a in ARMS.items():
                    cfg = {"thr": a["thr"], "stop_sig": a["stop_sig"],
                           "max_hold": max(2, int(round(a["hold_h"] * bph))),
                           "hour_lo": 0, "hour_hi": 0, "min_rvol": 0.0,
                           "min_risk_bps": COSTS[sym].min_risk_bps}
                    tr = STRATEGY.run(df, cfg, fee, slip, feats=feats)
                    tr2 = STRATEGY.run(df, cfg, fee * 2, slip * 2, feats=feats)
                    r = stats(tr, sym, tf, arm, tr2[:, T_R])
                    rows.append(r)
                    if r.get("pf") is None:
                        continue
                    print(f"{sym:9}{tf:4}{arm:12}{r['trades']:7}{r['win_pct']:7.1f}"
                          f"{r['avg_r']:8.3f}{r['pf']:7.2f}"
                          f"{(r['pf_2x'] or 0):7.2f}{r['median_win_r']:8.2f}"
                          f"{r['median_loss_r']:8.2f}{r['stopped_pct']:7.1f}"
                          f"{(r['top5_share_of_wins'] or 0):7.2f}"
                          f"   band {r['pf_2x_band'][0]}-{r['pf_2x_band'][1]}", flush=True)

    dest = ROOT / "backtests" / "vwapbreak" / "fixed.json"
    dest.write_text(json.dumps({"arms": ARMS, "rows": rows}, indent=1, default=str))
    print(f"\nwrote {dest.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
