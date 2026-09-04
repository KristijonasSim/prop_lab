"""H-017 stage 7 - the lever nobody here has modelled: parallel accounts.

Every days-to-funded figure in this project answers "how long does ONE account
take, including the ones that die and are replaced". That is `expected_days =
median_days / pass_rate`. It is the right number for cost per funded account.
It is NOT the number Kris asked for. He asked how long until he IS funded, and
`CLAUDE.md` already says accounts are cheap and the plan is 10-20 of them.

Those are different questions with different answers. Buying several
evaluations at once and taking the first to pass is a minimum over draws, not a
mean, and minima are much faster than means.

THE CATCH, AND IT IS THE WHOLE PROBLEM. N accounts all running the same book
from the same day are the SAME draw - they pass or die together, and
parallelism buys nothing. Independence has to come from somewhere, and there
are exactly two honest sources:

  stagger   start the accounts on different days. They then see different
            stretches of the same series, which decorrelates them without
            changing the strategy at all. Free.
  split     give each account its own LEG. HANDOFF records the legs' mean
            daily-R correlation at 0.023 - effectively independent - so eight
            accounts on eight legs are eight real draws. The cost is that each
            account runs one leg, and stage 1 measured per-leg K far below the
            pooled book's.

Both are simulated here against the pooled book, at every risk level, on the
project's real two-step rules. Nothing about the strategy changes; only how it
is deployed.

Output: backtests/xpos/stage7_parallel.csv
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from core.prop_rules import TWO_STEP                                # noqa: E402
from core.riskladder import MAX_DAYS                                # noqa: E402
from strategies.xpos.stage5_gatestack import TRADES, maxdd          # noqa: E402

OUT = ROOT / "backtests" / "xpos"
TARGET_DD_R = 4.0
RISKS = (0.005, 0.01, 0.015, 0.02, 0.03, 0.04)
N_ACCOUNTS = (1, 3, 5, 10, 20)
STAGGER_DAYS = 3          # accounts opened three days apart


def account_path(d: np.ndarray, s0: int, phases=TWO_STEP,
                 max_days: int = MAX_DAYS) -> tuple[str, int]:
    """One account started on day `s0`. Identical rules to riskladder."""
    k, total = s0, 0
    res = "OPEN"
    n = len(d)
    for rules in phases:
        eq = peak = 0.0
        day = traded = 0
        res = "OPEN"
        while k < n and total + day < max_days:
            day += 1
            step = d[k]
            k += 1
            if step != 0.0:
                traded += 1
            if min(step, 0.0) <= -rules.daily_loss:
                res = "FAIL_DAILY"
                break
            low = eq + min(step, 0.0)
            if low - peak <= -rules.max_loss or low <= -rules.max_loss:
                res = "FAIL_MAX"
                break
            eq += step
            peak = max(peak, eq)
            if eq >= rules.profit_target and traded >= rules.min_trading_days:
                res = "PASS"
                break
        total += day
        if res != "PASS":
            break
    return res, total


def daily_series(df: pd.DataFrame, scale: float) -> pd.Series:
    r = df.r_2x.values * scale
    return pd.Series(r, index=pd.DatetimeIndex(df.exit_ts)).resample("1D").sum()


def first_k_pass(cols: list[np.ndarray], risk: float, k_needed: int,
                 stagger: int, n_acc: int) -> float | None:
    """Days from opening the first account until `k_needed` are funded.

    Each account is a column (a leg, or the pooled book) and is opened
    `stagger` days after the previous one. Both sources of independence are
    therefore live at once, which is how anyone would actually deploy this.
    Averaged over every possible calendar start so the answer is not one lucky
    fortnight.
    """
    n = min(len(c) for c in cols)
    outs = []
    horizon = n - MAX_DAYS - stagger * n_acc
    if horizon <= 50:
        return None
    for start in range(0, horizon, 7):          # weekly starts, for speed
        done = []
        for i in range(n_acc):
            col = cols[i % len(cols)]
            s0 = start + i * stagger
            res, days = account_path(col * risk, s0)
            if res == "PASS":
                done.append(i * stagger + days)
        done.sort()
        outs.append(done[k_needed - 1] if len(done) >= k_needed else np.nan)
    outs = np.array(outs, dtype=float)
    ok = np.isfinite(outs)
    if ok.sum() < 10:
        return None
    return float(np.median(outs[ok]))


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    t = pd.read_parquet(TRADES)
    t["entry_ts"] = pd.to_datetime(t.entry_ts, utc=True)
    t["exit_ts"] = pd.to_datetime(t.exit_ts, utc=True)
    t = t[t.gated]                                       # H-009 as it stands

    legs = sorted(set(zip(t.symbol, t.tf)))
    pooled_df = t.sort_values("exit_ts")
    dd = maxdd(pooled_df.r_2x.values)
    pooled = daily_series(pooled_df, TARGET_DD_R / abs(dd))

    # Each leg scaled the same way - to fill the cap on its OWN drawdown - so a
    # single-leg account is sized as a trader would size it, not at the pooled
    # book's leverage.
    leg_series = []
    for a, b in legs:
        g = t[(t.symbol == a) & (t.tf == b)].sort_values("exit_ts")
        d = maxdd(g.r_2x.values)
        if d >= 0 or len(g) < 100:
            continue
        leg_series.append(daily_series(g, TARGET_DD_R / abs(d)))

    idx = pd.date_range(min(pooled.index[0], *[s.index[0] for s in leg_series]),
                        max(pooled.index[-1], *[s.index[-1] for s in leg_series]),
                        freq="1D", tz="UTC")
    pooled = pooled.reindex(idx).fillna(0.0).values
    leg_cols = [s.reindex(idx).fillna(0.0).values for s in leg_series]
    print(f"H-009: {len(t):,} trades, {len(leg_cols)} legs, "
          f"{len(idx)} calendar days\n")

    rows = []
    print("MEDIAN DAYS UNTIL THE FIRST ACCOUNT IS FUNDED")
    print("  (accounts opened 3 days apart; 'split' gives each its own leg)\n")
    print(f"  {'risk':>6s} {'deploy':>8s} " +
          " ".join(f"{'N=' + str(n):>8s}" for n in N_ACCOUNTS))
    for risk in RISKS:
        for label, cols in (("pooled", [pooled]), ("split", leg_cols)):
            out = []
            for n in N_ACCOUNTS:
                v = first_k_pass(cols, risk, 1, STAGGER_DAYS, n)
                out.append(v)
                rows.append({"risk": risk, "deploy": label, "n_accounts": n,
                             "k_needed": 1, "median_days": v})
            print(f"  {risk*100:>5.2f}% {label:>8s} " +
                  " ".join(f"{('%.0f' % v) if v else '-':>8s}" for v in out))

    print("\n\nMEDIAN DAYS UNTIL THREE ACCOUNTS ARE FUNDED\n")
    print(f"  {'risk':>6s} {'deploy':>8s} " +
          " ".join(f"{'N=' + str(n):>8s}" for n in N_ACCOUNTS))
    for risk in RISKS:
        for label, cols in (("pooled", [pooled]), ("split", leg_cols)):
            out = []
            for n in N_ACCOUNTS:
                v = first_k_pass(cols, risk, 3, STAGGER_DAYS, n) if n >= 3 else None
                out.append(v)
                rows.append({"risk": risk, "deploy": label, "n_accounts": n,
                             "k_needed": 3, "median_days": v})
            print(f"  {risk*100:>5.2f}% {label:>8s} " +
                  " ".join(f"{('%.0f' % v) if v else '-':>8s}" for v in out))

    df = pd.DataFrame(rows)
    df.to_csv(OUT / "stage7_parallel.csv", index=False)
    ok = df[(df.k_needed == 1) & df.median_days.notna()]
    if len(ok):
        b = ok.loc[ok.median_days.idxmin()]
        print(f"\nFASTEST TO ONE FUNDED ACCOUNT: {b.median_days:.0f} days at "
              f"{b.risk*100:.2f}% risk, {b.deploy}, N={b.n_accounts}")
    print(f"\nwrote {OUT / 'stage7_parallel.csv'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
