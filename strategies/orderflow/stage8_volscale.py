"""H-009 with vol-managed sizing — an idea lifted from the n5 book's `volmom`.

THE IDEA. Moreira & Muir's vol-managed portfolios, and the `volmom` leg in the
other repo's N5 book, both scale exposure by inverse realised volatility: risk
less when the market is moving a lot, more when it is quiet. H-009's binding
constraint is not profit factor, it is DRAWDOWN -

    days = maxDD_in_R / R_per_day

so anything that cuts drawdown by more than it cuts return makes the account
faster. If H-009's bad stretches cluster in high-volatility regimes, scaling
down into them is exactly the right trade.

WHAT THIS IS NOT, and the distinction matters here more than anywhere.
`CLAUDE.md` forbids "a budget-shrinking risk manager that sizes down to avoid
ever breaching - that produces a fake 0% fail rate". That rule is about sizing
off ACCOUNT STATE: equity, drawdown, recent P&L. This scales off MARKET
VOLATILITY only, measured before the trade is taken, and it never looks at the
account or at the strategy's own returns. A quiet market gets more size whether
the book is up or down.

POINT IN TIME. Realised volatility is a trailing window, shifted one day, and
the reference level it is divided by is an EXPANDING median of everything before
today - never a full-sample constant, which would be hindsight about the
distribution.

HELD OUT. The X experiment showed how easily a book-level tweak fits the window
it was measured on, so every number is reported twice: the full window, and only
the period after SPLIT that no choice here has seen.

Run: .venv/bin/python strategies/orderflow/stage8_volscale.py
"""
from __future__ import annotations

import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from core import riskladder as RL                              # noqa: E402
from strategies.vwap.stage10_universe import load_tf           # noqa: E402

GV = ROOT / "backtests" / "gated_vwap"
OUT = ROOT / "backtests" / "volscale"
OUT.mkdir(parents=True, exist_ok=True)

LEGS = [("BTCUSDT", "4h"), ("ETHUSDT", "1h"), ("ETHUSDT", "30m"),
        ("SOLUSDT", "4h"), ("XAUUSD", "5m")]
COMMON, SPLIT = "2024-09-01", "2025-10-01"
VOL_WIN = 20            # days of realised volatility
MIN_REF = 120           # days before the expanding reference is trusted
CLIPS = [(0.5, 2.0), (0.5, 1.5), (0.33, 3.0)]


def daily_vol(sym: str, tf: str) -> pd.Series:
    """Trailing realised volatility of the market, shifted one day."""
    df = load_tf(sym, tf)
    d = np.log(df.close).diff()
    v = d.groupby(df.index.floor("D")).std().rolling(VOL_WIN, min_periods=VOL_WIN // 2).mean()
    return v.shift(1)


def weights(vol: pd.Series, lo: float, hi: float) -> pd.Series:
    """Inverse-vol weight against an EXPANDING median of past volatility.

    The reference has to come from the past. Dividing by the full-sample mean
    would quietly tell every trade in 2024 what 2026 looked like."""
    ref = vol.expanding(MIN_REF).median().shift(1)
    return (ref / vol).clip(lo, hi)


def stats(r: np.ndarray, ts: pd.Series) -> dict:
    eq = np.concatenate(([0.0], np.cumsum(r)))
    dd = abs(float((eq - np.maximum.accumulate(eq)).min()))
    span = max((ts.iloc[-1] - ts.iloc[0]).days, 1)
    rpd = r.sum() / span
    w, l = r[r > 0].sum(), -r[r < 0].sum()
    return {"trades": len(r), "pf": w / l if l > 0 else np.nan,
            "total_r": float(r.sum()), "maxdd_r": -dd,
            "ret_dd": r.sum() / dd if dd > 0 else np.nan,
            "r_per_day": rpd, "days": dd / rpd if rpd > 0 else np.nan}


def prop(r: np.ndarray, ts: pd.Series) -> dict:
    daily = pd.Series(r, index=pd.DatetimeIndex(ts)).resample("1D").sum()
    rows = RL.ladder(daily, r)
    return RL.pick(rows)


def show(name, s, p=None):
    line = (f"  {name:34s} PF {s['pf']:.3f}  maxDD {s['maxdd_r']:6.2f}R  "
            f"ret/DD {s['ret_dd']:6.2f}  R/day {s['r_per_day']:+.4f}  "
            f"days {s['days']:6.1f}")
    if p:
        line += (f"  |  two-step: risk {p['risk']*100:.2f}% "
                 f"pass {p['pass_rate']*100:4.1f}% exp "
                 f"{p['expected_days'] if p['expected_days'] else 'never'}")
    print(line)


def main():
    tr = pd.read_parquet(GV / "stage6_trades.parquet")
    tr["entry_ts"] = pd.to_datetime(tr.entry_ts, utc=True)
    tr["exit_ts"] = pd.to_datetime(tr.exit_ts, utc=True)
    tr = tr[tr.gated & [(a, b) in LEGS for a, b in zip(tr.symbol, tr.tf)]]
    tr = tr[tr.exit_ts >= COMMON].sort_values("exit_ts").reset_index(drop=True)
    n = len(LEGS)
    print(f"H-009's book: {len(tr)} gated trades, {n} legs\n")

    # per-leg market volatility, and BTC's as a single common regime driver
    vols = {}
    for sym, tf in LEGS:
        try:
            vols[(sym, tf)] = daily_vol(sym, tf)
        except Exception as e:
            print(f"  no vol for {sym} {tf}: {e}")
    btc = vols[("BTCUSDT", "4h")]

    day = tr.entry_ts.dt.floor("D")
    base_r = tr.r.values / n
    base_r2 = tr.r_2x.values / n

    variants = {"unscaled (H-009 as it stands)": np.ones(len(tr))}
    for lo, hi in CLIPS:
        w_btc = weights(btc, lo, hi)
        variants[f"BTC vol, clip {lo}-{hi}"] = day.map(w_btc).fillna(1.0).values
        wl = np.ones(len(tr))
        for (sym, tf), v in vols.items():
            m = (tr.symbol == sym) & (tr.tf == tf)
            wl[m.values] = day[m].map(weights(v, lo, hi)).fillna(1.0).values
        variants[f"per-leg vol, clip {lo}-{hi}"] = wl

    for label, win, lo_ts, hi_ts in [("FULL WINDOW", None, COMMON, None),
                                     (f"HELD OUT (after {SPLIT})", None, SPLIT, None)]:
        m = (tr.exit_ts >= lo_ts)
        sub = tr[m]
        print("=" * 116)
        print(label)
        print("=" * 116)
        for name, w in variants.items():
            ww = w[m.values]
            # keep average exposure at 1 so this is a RESHAPING of risk, not
            # more of it - otherwise a variant could win by simply betting more
            ww = ww / ww.mean()
            r = base_r[m.values] * ww
            r2 = base_r2[m.values] * ww
            s = stats(r, sub.exit_ts)
            s["pf"] = stats(r2, sub.exit_ts)["pf"]      # report PF at 2x cost
            p = prop(r, sub.exit_ts) if lo_ts == COMMON else None
            show(name, s, p)
        print()


if __name__ == "__main__":
    main()
