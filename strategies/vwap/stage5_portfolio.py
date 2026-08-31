"""H-002 VWAP stage 5 — does combining assets actually speed up a challenge?

The idea is sound: independent strategies add trades without adding proportional
drawdown, so the same risk budget resolves faster. Whether it works here depends
entirely on the correlation between the daily P&L series, which is measured, not
assumed.

Two targets are simulated because prop firms use both: 8% (typical phase one)
and 5% (typical phase two). Daily loss 4%, max loss 8%, fresh account every
trading day, fixed risk, real breaches.

Each leg is the best configuration for its market and timeframe as ranked on the
FIT window only, so the legs were not chosen using the period they are scored on.
Note the compounding selection problem: a book of N best-of-market legs carries
N times the selection bias of one leg, and combining them cannot remove it.
"""
from __future__ import annotations

import itertools
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from numba import njit

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from core.prop_rules import PropRules                          # noqa: E402
from strategies.vwap.sweep import features, run_one, DEFAULTS   # noqa: E402
from strategies.vwap.engine import T_R, T_EXIT_I                # noqa: E402
from strategies.vwap.stage1_grid import ASSETS, OUT             # noqa: E402
from strategies.vwap.stage3_timeframes import load_tf           # noqa: E402
from strategies.vwap.stage4_profiles import CFGKEY, SPLIT       # noqa: E402

RISKS = [0.005, 0.0075, 0.01, 0.015, 0.02, 0.03]
TARGETS = {"8%": 0.08, "5%": 0.05}
MAX_LEGS = 4


def leg_daily(sym: str, tf: str, cfg: dict) -> pd.Series | None:
    """Daily R for one leg over the full period."""
    try:
        df = load_tf(sym, tf)
    except Exception:
        return None
    if len(df) < 3000:
        return None
    fee, slip, _ = ASSETS[sym]
    tr = run_one(df, features(df), {}, cfg, fee, slip)
    if len(tr) < 100:
        return None
    ts = df.index[tr[:, T_EXIT_I].astype(int)]
    return pd.Series(tr[:, T_R], index=ts).resample("1D").sum()


@njit(cache=True)
def _accounts(d, target, daily_loss, max_loss, min_days, max_days):
    """One challenge account per start day. Codes: 0 PASS, 1 FAIL_DAILY,
    2 FAIL_MAX, 3 still open at the day limit."""
    n = d.shape[0]
    out = np.empty(n, dtype=np.int64)
    days = np.empty(n, dtype=np.int64)
    for s in range(n):
        eq = 0.0
        peak = 0.0
        day = 0
        traded = 0
        code = 3
        end = s + max_days
        if end > n:
            end = n
        for k in range(s, end):
            day += 1
            step = d[k]
            if step != 0.0:
                traded += 1
            neg = step if step < 0.0 else 0.0
            if neg <= -daily_loss:
                code = 1
                break
            low = eq + neg
            if low - peak <= -max_loss or low <= -max_loss:
                code = 2
                break
            eq += step
            if eq > peak:
                peak = eq
            if eq >= target and traded >= min_days:
                code = 0
                break
        out[s] = code
        days[s] = day
    return out, days


def simulate(daily: pd.Series, risk: float, target: float, max_days: int = 400) -> dict:
    rules = PropRules(profit_target=target)
    code, days = _accounts(np.ascontiguousarray(daily.values * risk), target,
                           rules.daily_loss, rules.max_loss,
                           rules.min_trading_days, max_days)
    n = len(code)
    passed = code == 0
    pdays = days[passed]
    return {
        "pass_rate": round(float(passed.mean()), 4),
        "fail_max": round(float((code == 2).mean()), 4),
        "fail_daily": round(float((code == 1).mean()), 4),
        "median_days": float(np.median(pdays)) if pdays.size else np.nan,
        "p25_days": float(np.percentile(pdays, 25)) if pdays.size else np.nan,
        "pass_within_7": round(float((pdays <= 7).sum() / n), 4) if pdays.size else 0.0,
        "pass_within_14": round(float((pdays <= 14).sum() / n), 4) if pdays.size else 0.0,
        "pass_within_30": round(float((pdays <= 30).sum() / n), 4) if pdays.size else 0.0,
    }


def curve(daily: pd.Series, risk: float) -> dict:
    eq = 1.0 + np.cumsum(daily.values) * risk
    peak = np.maximum.accumulate(eq)
    dd = float(((eq - peak) / peak).min())
    yrs = (daily.index[-1] - daily.index[0]).days / 365.25
    total = float(eq[-1] - 1.0)
    sd = (daily * risk).std(ddof=1)
    return {"cagr": round((1 + total) ** (1 / yrs) - 1 if total > -1 else -1.0, 4),
            "max_dd": round(dd, 4),
            "sharpe": round(float((daily * risk).mean() / sd * np.sqrt(365)), 2) if sd else 0.0}


def main():
    prof = pd.read_csv(OUT / "stage4_profiles.csv")
    # one leg per market x timeframe: the one that ranked best on the fit window
    # One leg per MARKET, not per market x timeframe. 39 legs makes 92,170
    # portfolios and most are the same asset wearing two hats.
    legs = {}
    seen = prof.sort_values("fit_pf", ascending=False).drop_duplicates(["symbol"])
    for _, r in seen.iterrows():
        cfg = dict(DEFAULTS)
        cfg.update({k: r[k] for k in CFGKEY})
        cfg["min_risk_bps"] = ASSETS[r.symbol][2]
        s = leg_daily(r.symbol, r.tf, cfg)
        if s is not None and s.abs().sum() > 0:
            legs[f"{r.symbol} {r.tf}"] = s
            print(f"leg {r.symbol} {r.tf}: {len(s)} days, total {s.sum():.1f}R", flush=True)
    print(f"{len(legs)} legs", flush=True)

    idx = None
    for s in legs.values():
        idx = s.index if idx is None else idx.union(s.index)
    L = pd.DataFrame({k: v.reindex(idx).fillna(0.0) for k, v in legs.items()})
    L.to_csv(OUT / "stage5_legs.csv")

    corr = L[L.abs().sum(axis=1) > 0].corr()
    corr.to_csv(OUT / "stage5_corr.csv")
    print("\nmean pairwise correlation of daily R: %.3f" %
          corr.values[np.triu_indices_from(corr.values, 1)].mean(), flush=True)

    rows = []
    names = list(L.columns)
    combos = []
    for k in range(1, MAX_LEGS + 1):
        combos += list(itertools.combinations(names, k))
    print(f"{len(combos)} portfolios", flush=True)

    for combo in combos:
        # equal risk per leg; the book's daily R is the sum
        daily = L[list(combo)].sum(axis=1)
        if daily.abs().sum() == 0:
            continue
        sub = corr.loc[list(combo), list(combo)].values
        mc = (sub[np.triu_indices_from(sub, 1)].mean() if len(combo) > 1 else 0.0)
        tpd = float((L[list(combo)] != 0).sum().sum()) / max((idx[-1] - idx[0]).days, 1)
        for risk in RISKS:
            c = curve(daily, risk)
            if c["max_dd"] <= -0.60:
                continue
            for tname, tgt in TARGETS.items():
                s = simulate(daily, risk, tgt)
                rows.append({"legs": " + ".join(combo), "n_legs": len(combo),
                             "target": tname, "risk": risk, "mean_corr": round(float(mc), 3),
                             "active_days_per_day": round(tpd, 3), **c, **s})

    out = pd.DataFrame(rows)
    out.to_csv(OUT / "stage5_portfolio.csv", index=False)
    print("saved stage5_portfolio.csv", len(out), "rows", flush=True)


if __name__ == "__main__":
    main()
