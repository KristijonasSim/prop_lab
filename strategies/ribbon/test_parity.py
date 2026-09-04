"""H-016 - verify the port against a literal, bar-by-bar reading of the Pine.

The fast implementation in `ribbon.py` uses convolutions and rolling windows.
This file recomputes the same numbers the slow, obvious way - one bar at a
time, straight from the Pine source text - and asserts they agree. If the two
ever disagree, the fast one is wrong, because this one is unreadable but
literal.

Run: .venv/bin/python strategies/ribbon/test_parity.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from strategies.ribbon.ribbon import (           # noqa: E402
    RibbonParams, channel, features, gettrend, linreg, moving_average, ribbon,
)


def slow_ema(x, n):
    out = np.full(x.size, np.nan)
    if x.size < n:
        return out
    a = 2.0 / (n + 1.0)
    out[n - 1] = x[:n].mean()
    for i in range(n, x.size):
        out[i] = a * x[i] + (1 - a) * out[i - 1]
    return out


def slow_rma(x, n):
    out = np.full(x.size, np.nan)
    if x.size < n:
        return out
    a = 1.0 / n
    out[n - 1] = x[:n].mean()
    for i in range(n, x.size):
        out[i] = a * x[i] + (1 - a) * out[i - 1]
    return out


def slow_wma(x, n):
    w = np.arange(1.0, n + 1.0)
    out = np.full(x.size, np.nan)
    for i in range(n - 1, x.size):
        out[i] = np.dot(x[i - n + 1:i + 1], w) / w.sum()
    return out


def slow_linreg(x, n, offset=0):
    """`intercept + slope * (n - 1 - offset)`, fitted bar by bar."""
    out = np.full(x.size, np.nan)
    pos = np.arange(n, dtype=float)
    for i in range(n - 1, x.size):
        y = x[i - n + 1:i + 1]
        if not np.isfinite(y).all():
            continue
        slope, intercept = np.polyfit(pos, y, 1)
        out[i] = intercept + slope * (n - 1 - offset)
    return out


def slow_gettrend(ma, chan, prd):
    out = np.full(ma.size, np.nan)
    for i in range(prd - 1, ma.size):
        win = ma[i - prd + 1:i + 1]
        if not np.isfinite(win).all() or not np.isfinite(chan[i]) or chan[i] <= 0:
            continue
        hh, ll = win.max(), win.min()
        diff = abs(hh - ll)
        if diff > chan[i]:
            trend = 1.0 if ma[i] > ll + chan[i] else (-1.0 if ma[i] < hh - chan[i] else 0.0)
        else:
            trend = 0.0
        out[i] = trend * diff / chan[i]
    return out


def close_enough(a, b, name, tol=1e-8):
    both = np.isfinite(a) & np.isfinite(b)
    only_a = np.isfinite(a) & ~np.isfinite(b)
    only_b = np.isfinite(b) & ~np.isfinite(a)
    assert not only_a.any() and not only_b.any(), (
        f"{name}: NaN masks differ ({only_a.sum()} / {only_b.sum()})")
    err = np.abs(a[both] - b[both]).max() if both.any() else 0.0
    assert err < tol, f"{name}: max abs error {err:.3e}"
    print(f"  ok  {name:28s} n={both.sum():>7,}  max err {err:.2e}")


def main() -> int:
    df = pd.read_parquet(ROOT / "data" / "BTCUSDT_spot_15m.parquet").tail(4000)
    close = df["close"].to_numpy(float)
    vol = df["volume"].to_numpy(float)
    print(f"BTCUSDT 15m, {len(df):,} bars, {df.index[0]} -> {df.index[-1]}\n")

    print("MA types")
    close_enough(moving_average(close, vol, 50, "EMA"), slow_ema(close, 50), "EMA(50)")
    close_enough(moving_average(close, vol, 50, "RMA"), slow_rma(close, 50), "RMA(50)")
    close_enough(moving_average(close, vol, 50, "WMA"), slow_wma(close, 50), "WMA(50)", 1e-7)
    close_enough(moving_average(close, vol, 50, "SMA"),
                 pd.Series(close).rolling(50).mean().to_numpy(), "SMA(50)")
    vwma = (pd.Series(close * vol).rolling(50).sum()
            / pd.Series(vol).rolling(50).sum()).to_numpy()
    close_enough(moving_average(close, vol, 50, "VWMA"), vwma, "VWMA(50)", 1e-6)

    print("\nlinreg")
    close_enough(linreg(close, 10, 0), slow_linreg(close, 10, 0), "linreg(close,10,0)", 1e-6)
    close_enough(linreg(close, 3, 0), slow_linreg(close, 3, 0), "linreg(close,3,0)", 1e-6)

    print("\ngettrend, through the full study path")
    p = RibbonParams()
    chan = channel(df, p).to_numpy(float)
    for n in (5, 45, 100):
        raw = moving_average(close, vol, n, p.matype)
        sm = linreg(raw, p.linprd, 0)
        close_enough(gettrend(sm, chan, p.prd), slow_gettrend(sm, chan, p.prd),
                     f"gettrend(len={n})", 1e-7)

    print("\nno look-ahead: truncating the series cannot change earlier bars")
    _, s_full = ribbon(df, p)
    _, s_cut = ribbon(df.iloc[:-500], p)
    tail = s_full.iloc[:len(s_cut)]
    diff = (tail.to_numpy(float) - s_cut.to_numpy(float))
    both = np.isfinite(diff)
    assert np.nanmax(np.abs(diff[both])) < 1e-9, "future bars leaked backwards"
    print(f"  ok  {len(s_cut):,} bars identical with the last 500 removed")

    print("\naggregates are internally consistent")
    f = features(df, p)
    ok = f.dropna()
    assert (ok[["n_up", "n_dn", "n_flat"]].sum(axis=1) == len(p.lengths)).all()
    assert np.allclose(ok["agree"], (ok["n_up"] - ok["n_dn"]) / len(p.lengths))
    assert ok["agree"].between(-1, 1).all() and ok["stack"].between(0, 1).all()
    print(f"  ok  counts sum to 20, agree == (n_up-n_dn)/20, on {len(ok):,} bars")

    print("\nPARITY OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
