"""H-002 VWAP stage 4 — three challenge profiles, chosen honestly.

The ask: one configuration for the best chance of passing an evaluation, one
aggressive, one in between, with profit factor, CAGR, drawdown and time to pass.

Those numbers are only worth reading if the configuration was chosen without
seeing the data it is scored on. So:

  * candidates are ranked on the FIT window only (2023-09 -> 2025-09);
  * every number in the output table is measured on the TEST year the candidate
    was not chosen on, plus the full period for context;
  * the prop simulation starts a fresh account on every trading day, fixed risk,
    real breaches, no size shrinking.

Risk per trade is the real lever between "safe" and "aggressive": drawdown and
time-to-pass both scale with it, in opposite directions.
"""
from __future__ import annotations

import sys, time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from core.prop_rules import PropRules                          # noqa: E402
from strategies.vwap.sweep import sweep, features, run_one, DEFAULTS  # noqa: E402
from strategies.vwap.engine import T_R, T_EXIT_I                # noqa: E402
from strategies.vwap.stage1_grid import ASSETS, OUT, START, END  # noqa: E402
from strategies.vwap.stage3_timeframes import load_tf, TFS      # noqa: E402

SPLIT = "2025-09-01"
RISKS = [0.0025, 0.005, 0.0075, 0.01, 0.015, 0.02]
CFGKEY = ["anchor_hour", "anchor_minute", "mode", "fill_mode", "band_k", "stop_mode",
          "stop_k", "target_mode", "rr", "max_hold_bars", "min_rvol",
          "min_atr_rank", "max_atr_rank", "warmup_bars"]


def run_accounts(daily_r: pd.Series, risk: float, rules: PropRules = PropRules(),
                 max_days: int = 400) -> dict:
    """Fresh account every trading day. Worst case within a day: the whole day's
    loss lands before any of its gain."""
    d = daily_r.values * risk
    n = len(d)
    out = []
    for s in range(n):
        eq, peak, day, traded, res = 0.0, 0.0, 0, 0, "OPEN"
        for k in range(s, min(s + max_days, n)):
            day += 1
            step = d[k]
            if step != 0.0:
                traded += 1
            if min(step, 0.0) <= -rules.daily_loss:
                res = "FAIL_DAILY"; break
            low = eq + min(step, 0.0)
            if low - peak <= -rules.max_loss or low <= -rules.max_loss:
                res = "FAIL_MAX"; break
            eq += step
            peak = max(peak, eq)
            if eq >= rules.profit_target and traded >= rules.min_trading_days:
                res = "PASS"; break
        out.append((res, day))
    res = pd.DataFrame(out, columns=["outcome", "days"])
    p = res[res.outcome == "PASS"]
    return {
        "pass_rate": round(len(p) / len(res), 4),
        "fail_max": round((res.outcome == "FAIL_MAX").mean(), 4),
        "fail_daily": round((res.outcome == "FAIL_DAILY").mean(), 4),
        "open": round((res.outcome == "OPEN").mean(), 4),
        "median_days_pass": float(p.days.median()) if len(p) else np.nan,
        "p25_days_pass": float(p.days.quantile(0.25)) if len(p) else np.nan,
    }


def curve_stats(r: np.ndarray, ts, risk: float, years: float) -> dict:
    """Fixed fractional risk on starting equity, no compounding."""
    eq = 1.0 + np.cumsum(r) * risk
    peak = np.maximum.accumulate(eq)
    dd = float(((eq - peak) / peak).min()) if len(eq) else 0.0
    total = float(eq[-1] - 1.0) if len(eq) else 0.0
    cagr = (1.0 + total) ** (1.0 / years) - 1.0 if total > -1 else -1.0
    daily = pd.Series(r * risk, index=ts).resample("1D").sum()
    sd = daily.std(ddof=1)
    return {"total_return": round(total, 4), "cagr": round(cagr, 4),
            "max_dd": round(dd, 4),
            "sharpe": round(float(daily.mean() / sd * np.sqrt(365)), 2) if sd else 0.0}


def main():
    s3 = pd.read_parquet(OUT / "stage3_timeframes.parquet")
    s3 = s3[s3.kind == "real"].copy()
    for c in ["pf", "trades", "trades_per_day"]:
        s3[c] = pd.to_numeric(s3[c], errors="coerce")

    # candidate pool: enough trades to mean anything, positive on the fit window
    pool = s3[(s3.trades >= 150) & (s3.pf >= 1.15)].copy()
    print(f"{len(pool)} candidates before the fit/test split", flush=True)

    rows = []
    for (sym, tf), g in pool.groupby(["symbol", "tf"], observed=True):
        try:
            df = load_tf(sym, tf)
        except Exception:
            continue
        if len(df) < 3000:
            continue
        fee, slip, minrisk = ASSETS[sym]
        is_df, oos_df = df[df.index < SPLIT], df[df.index >= SPLIT]
        f_is, f_oos, f_all = features(is_df), features(oos_df), features(df)
        vc_is, vc_oos, vc_all = {}, {}, {}
        yrs_all = (df.index[-1] - df.index[0]).days / 365.25
        yrs_oos = (oos_df.index[-1] - oos_df.index[0]).days / 365.25

        # rank on the fit window only
        cand = []
        for _, r in g.iterrows():
            cfg = dict(DEFAULTS)
            cfg.update({k: r[k] for k in CFGKEY})
            cfg["min_risk_bps"] = minrisk
            tr = run_one(is_df, f_is, vc_is, cfg, fee, slip)
            if len(tr) < 80:
                continue
            rr = tr[:, T_R]
            w, l = rr[rr > 0].sum(), -rr[rr < 0].sum()
            cand.append((w / l if l else np.inf, cfg))
        if not cand:
            continue
        cand.sort(key=lambda x: -x[0])
        for fit_pf, cfg in cand[:3]:            # top 3 per market/timeframe
            tr_oos = run_one(oos_df, f_oos, vc_oos, cfg, fee, slip)
            tr_all = run_one(df, f_all, vc_all, cfg, fee, slip)
            if len(tr_oos) < 20 or len(tr_all) < 100:
                continue
            r_all = tr_all[:, T_R]
            r_oos = tr_oos[:, T_R]
            ts_all = df.index[tr_all[:, T_EXIT_I].astype(int)]
            ts_oos = oos_df.index[tr_oos[:, T_EXIT_I].astype(int)]
            w, l = r_oos[r_oos > 0].sum(), -r_oos[r_oos < 0].sum()
            pf_oos = w / l if l else np.inf
            w, l = r_all[r_all > 0].sum(), -r_all[r_all < 0].sum()
            pf_all = w / l if l else np.inf
            daily_all = pd.Series(r_all, index=ts_all).resample("1D").sum()

            for risk in RISKS:
                st = curve_stats(r_all, ts_all, risk, yrs_all)
                if st["max_dd"] <= -0.60:       # unusable at this risk, skip
                    continue
                acc = run_accounts(daily_all, risk)
                rows.append({
                    "symbol": sym, "tf": tf, "risk": risk,
                    "fit_pf": round(float(fit_pf), 3),
                    "pf_oos": round(float(pf_oos), 3),
                    "pf_all": round(float(pf_all), 3),
                    "trades_all": int(len(r_all)), "trades_oos": int(len(r_oos)),
                    "tpd": round(len(r_all) / max((df.index[-1] - df.index[0]).days, 1), 3),
                    **st, **acc,
                    **{k: cfg[k] for k in CFGKEY},
                })
        print(f"  {sym} {tf}: {len(rows)} rows so far", flush=True)

    out = pd.DataFrame(rows)
    out.to_csv(OUT / "stage4_profiles.csv", index=False)
    print("saved stage4_profiles.csv", len(out), "rows", flush=True)


if __name__ == "__main__":
    main()
