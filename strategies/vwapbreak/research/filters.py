"""H-027 filter screen — does ANY entry filter lift gold, measured as a paired lift.

WHY THIS IS A SCREEN AND NOT A SEARCH. On 2026-09-08 the H-027 grid was widened
(topn 1/3/5/10, hold 96/192/384) and gold 1h's blind pass rate FELL from 70.5%
to 54.8%. Nothing about the market changed; only the number of configurations the
selector could pick from. Adding filter axes straight into that grid would repeat
the mistake at larger scale, so nothing here touches the grid.

THE METHOD, from README.md 3.3: "Score a filter as a paired lift on the MEDIAN,
never by whether it produced a new best. A filter that only raises the maximum
has shrunk the sample."

So: fix a reference slice of the grid (every threshold x stop x hold, with the
session and rvol filters OFF), run it, and for each candidate filter compare the
SAME configuration with and without it. The statistic is the median change across
configurations, plus how many trades the filter throws away - a filter that keeps
a fifth of the trades and lifts profit factor has not found anything.

THE ONE APPROXIMATION, stated up front. The kernel is non-overlapping: after a
trade it resumes at the exit bar. Masking a trade out afterwards therefore is NOT
identical to refusing it inside the kernel, because refusing it would have freed
the bars it occupied and let a different trade happen. This is a screen. Anything
that survives it gets re-run inside the kernel before a single number is quoted.

NOT TESTED HERE, AND WHY: order flow. Every feed in data/feeds/ is a Binance
crypto symbol, and data/dukascopy_raw/XAUUSD holds one-minute BID CANDLES, not
ticks - there is no bid/ask volume for gold on disk. Gold trades naked. That is
backlog item H-030 and it needs a download, not a script.

Run: .venv/bin/python strategies/vwapbreak/research/filters.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from core.markets import COSTS, TF_BPH, load                       # noqa: E402
from core.run_hypothesis import window                             # noqa: E402
from core.strategy import T_DIR, T_ENTRY_I, T_R                    # noqa: E402
from strategies.vwapbreak.strategy import STRATEGY, THRESHOLDS, STOPS, HOLD_HOURS  # noqa: E402

SYM = "XAUUSD"
#: The same universe H-027 was run on, so `window` snaps to the identical common
#: end date. A screen measured over a different span is not comparable to the
#: board, and the whole point of this file is to be comparable to the board.
UNIVERSE = {"FX": ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD"],
            "Metals/Energy": ["XAUUSD", "XAGUSD", "WTI"],
            "Crypto": ["BTCUSDT", "ETHUSDT", "SOLUSDT"]}
TFS = ("1h", "4h")
#: The 2x-cost gate is what the pipeline selects on, so the screen uses it too.
COST_MULT = 2.0


def reference_grid(tf: str) -> list[dict]:
    """Every threshold x stop x hold, session and rvol filters OFF.

    Deliberately the part of the grid that carries no filter of its own, so a
    candidate filter is measured against a clean baseline rather than against
    whatever the session filter was already doing.
    """
    bph = TF_BPH[tf]
    return [{"thr": t, "stop_sig": s,
             "max_hold": max(2, int(round(h * bph))),
             "hour_lo": 0, "hour_hi": 0, "min_rvol": 0.0, "min_risk_bps": 3.0}
            for t in THRESHOLDS for s in STOPS for h in HOLD_HOURS]


def pf(r: np.ndarray) -> float:
    w, l = r[r > 0].sum(), -r[r < 0].sum()
    return float(w / l) if l > 0 else np.nan


def max_dd_R(r: np.ndarray) -> float:
    """Peak-to-trough of the cumulative R curve, in R. Positive number."""
    eq = np.concatenate(([0.0], np.cumsum(r)))
    return float(-(eq - np.maximum.accumulate(eq)).min())


def pace(r: np.ndarray, span_days: float) -> float:
    """The project's governing identity, up to the constant (target / cap).

        days = maxDD_in_R / R_per_day x (target / cap)

    Lower is better. Returns inf for a book that loses, because a losing book
    never reaches the target however long it runs. THIS, not profit factor, is
    what decides whether a filter helps: README.md - "Not profit factor. Not
    Sharpe. Expected days to a funded account."
    """
    rpd = r.sum() / span_days
    if rpd <= 0:
        return np.inf
    dd = max_dd_R(r)
    return float(dd / rpd) if dd > 0 else 0.0


def sma(x: np.ndarray, n: int) -> np.ndarray:
    return pd.Series(x).rolling(n, min_periods=n).mean().values


def candidates(df: pd.DataFrame, feats: dict) -> dict[str, np.ndarray]:
    """Every filter, as a per-bar mask that may depend on the trade's side.

    Returns {name: mask} where mask is (n, 2): column 0 is the verdict for a
    LONG signalled on that bar, column 1 for a SHORT. Everything is computed
    from bars up to and including the signal bar and never beyond it.
    """
    c = df.close.values
    hour = feats["hour"]
    n = len(c)
    out: dict[str, np.ndarray] = {}

    def both(mask: np.ndarray) -> np.ndarray:
        """A side-independent filter."""
        return np.column_stack([mask, mask])

    # --- moving averages: does the break want the higher-timeframe trend? -----
    for p in (50, 100, 200):
        m = sma(c, p)
        up = c > m
        out[f"MA{p} aligned"] = np.column_stack([up, ~up])
        out[f"MA{p} counter"] = np.column_stack([~up, up])
        # slope, which is a different question from position
        rising = np.r_[False, np.diff(m) > 0]
        out[f"MA{p} slope aligned"] = np.column_stack([rising, ~rising])

    # --- fibonacci: where in the recent swing is the break happening? --------
    # Range over a trailing window, SHIFTED so the signal bar's own high/low
    # cannot define the swing it is being judged against.
    for w in (100, 200):
        hi = pd.Series(df.high.values).rolling(w, min_periods=w).max().shift(1).values
        lo = pd.Series(df.low.values).rolling(w, min_periods=w).min().shift(1).values
        rng = hi - lo
        with np.errstate(invalid="ignore", divide="ignore"):
            pos = np.where(rng > 0, (c - lo) / rng, np.nan)
        # breaking out beyond the 61.8% line, in the direction of the break
        out[f"fib{w} beyond .618"] = np.column_stack([pos > 0.618, pos < 0.382])
        # the classic retracement pocket
        pocket = (pos >= 0.382) & (pos <= 0.618)
        out[f"fib{w} .382-.618 pocket"] = both(pocket)
        # the opposite: only take breaks from the far end of the range
        out[f"fib{w} outside .236/.764"] = both((pos < 0.236) | (pos > 0.764))

    # --- sessions, as a paired lift rather than as a grid axis ---------------
    for name, (lo_h, hi_h) in {"London 07-16": (7, 16), "NY 13-21": (13, 21),
                               "overlap 13-17": (13, 17), "Asia 00-07": (0, 7),
                               "London open 07-09": (7, 9),
                               "NY open 13-15": (13, 15)}.items():
        out[f"session {name}"] = both((hour >= lo_h) & (hour < hi_h))

    # --- volatility regime ---------------------------------------------------
    sd = feats["sd"]
    med = pd.Series(sd).rolling(500, min_periods=200).median().shift(1).values
    with np.errstate(invalid="ignore"):
        hi_vol = sd > med
    out["vol above trailing median"] = both(hi_vol)
    out["vol below trailing median"] = both(~hi_vol & np.isfinite(med))

    # --- calendar ------------------------------------------------------------
    dow = df.index.dayofweek.values
    out["skip Monday"] = both(dow != 0)
    out["skip Friday"] = both(dow != 4)

    for k, v in out.items():
        assert v.shape == (n, 2), (k, v.shape)
    return out


def main() -> int:
    syms = [s for v in UNIVERSE.values() for s in v]
    start, end = window(syms, ["1h", "4h"])
    print(f"window {start.date()} -> {end.date()}   cost {COST_MULT:.0f}x   "
          f"paired lift on the median configuration\n")

    rows = []
    for tf in TFS:
        df = load(SYM, tf)
        df = df[(df.index >= start) & (df.index < end)]
        feats = STRATEGY.features(df)
        # `mixed` is the pipeline's default: a resting limit entry and a market
        # exit, because a stop cannot be a limit order.
        f0, s0 = COSTS[SYM].per_side("mixed")
        fee, slip = f0 * COST_MULT, s0 * COST_MULT
        cands = candidates(df, feats)
        grid = reference_grid(tf)

        base = []
        span_days = (df.index[-1] - df.index[0]).days
        for cfg in grid:
            t = STRATEGY.run(df, cfg, fee, slip, feats=feats)
            base.append(t)
        n_base = np.array([len(t) for t in base])
        print(f"{SYM} {tf}: {len(grid)} reference configs, "
              f"{n_base.sum():,} trades, median {int(np.median(n_base))} per config, "
              f"median PF {np.nanmedian([pf(t[:, T_R]) for t in base]):.3f}")

        for name, mask in cands.items():
            d_pf, d_rpd, keep, d_pace, faster = [], [], [], [], []
            for t in base:
                if len(t) < 20:
                    continue
                r = t[:, T_R]
                sig = t[:, T_ENTRY_I].astype(int) - 1          # the SIGNAL bar
                col = np.where(t[:, T_DIR] > 0, 0, 1)
                ok = mask[sig, col]
                ok = np.where(np.isnan(ok.astype(float)), False, ok).astype(bool)
                if ok.sum() < 20:
                    continue
                p0, p1 = pf(r), pf(r[ok])
                if not (np.isfinite(p0) and np.isfinite(p1)):
                    continue
                d_pf.append(p1 - p0)
                d_rpd.append((r[ok].sum() - r.sum()) / span_days)
                keep.append(ok.mean())
                # the metric that actually decides it
                q0, q1 = pace(r, span_days), pace(r[ok], span_days)
                if np.isfinite(q0) and np.isfinite(q1):
                    d_pace.append(q1 - q0)
                    faster.append(q1 < q0)
                elif np.isfinite(q0) and not np.isfinite(q1):
                    # the filter turned a book that pays into one that does not
                    faster.append(False)
            if len(d_pf) < 10:
                rows.append({"tf": tf, "filter": name, "n_cfg": len(d_pf),
                             "d_pf": np.nan, "win": np.nan, "d_rpd": np.nan,
                             "keep": np.nan, "d_pace": np.nan,
                             "faster": np.nan})
                continue
            rows.append({"tf": tf, "filter": name, "n_cfg": len(d_pf),
                         "d_pf": float(np.median(d_pf)),
                         "win": float(np.mean(np.array(d_pf) > 0)),
                         "d_rpd": float(np.median(d_rpd)),
                         "keep": float(np.median(keep)),
                         "d_pace": float(np.median(d_pace)) if d_pace else np.nan,
                         "faster": float(np.mean(faster)) if faster else np.nan})

    out = pd.DataFrame(rows)
    dest = ROOT / "backtests" / "vwapbreak" / "filter_screen.csv"
    dest.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(dest, index=False)

    for tf in TFS:
        sub = out[out.tf == tf].sort_values("d_pace")
        print(f"\n=== {SYM} {tf} — paired lift per configuration, median. "
              f"SORTED BY PACE ===")
        print(f"{'filter':28s} {'dDAYS':>8s} {'fast%':>6s} {'dPF':>7s} "
              f"{'win%':>6s} {'dR/day':>8s} {'keep%':>6s}")
        for _, r in sub.iterrows():
            if not np.isfinite(r.d_pf):
                print(f"{r['filter']:28s}       —  (too few configs kept enough trades)")
                continue
            dp = f"{r.d_pace:+8.1f}" if np.isfinite(r.d_pace) else "     n/a"
            print(f"{r['filter']:28s} {dp} {r.faster*100:6.0f} {r.d_pf:+7.3f} "
                  f"{r.win*100:6.0f} {r.d_rpd:+8.4f} {r.keep*100:6.0f}")
    print(f"\nwrote {dest.relative_to(ROOT)}")
    print("\nREAD IT THIS WAY. dDAYS is the median change in maxDD_R / R_per_day, "
          "the\nproject's governing identity for time to a funded account - "
          "NEGATIVE IS BETTER\nAND IT IS THE ONLY COLUMN THAT DECIDES ANYTHING. "
          "fast% is how many configurations\nit sped up. dPF is the median "
          "change in profit factor at 2x cost and win% how many\nconfigurations "
          "it improved - both are diagnostics, not the goal. keep% is the share "
          "of\ntrades let through; a high dPF on a low keep% is a smaller "
          "sample, not an edge.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
