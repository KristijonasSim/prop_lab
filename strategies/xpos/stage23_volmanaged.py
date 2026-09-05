"""H-018 - volatility-managed sizing on top of the H-017 book.

MECHANISM, before any result. Momentum and flow strategies lose most of their
drawdown in a small number of high-volatility clusters, and volatility is far
more persistent than return. Scaling exposure by the inverse of RECENT realised
volatility therefore takes size off before the cluster rather than after it.
Moreira-Muir showed this raises Sharpe in equities; the crypto-momentum papers
report the same, from 1.12 to 1.42, and there through higher returns rather
than lower risk. The counterparty is anyone forced to hold constant notional.

Why it should move the number that matters here. `days = 1.625 / K`, and
K = R_per_day / |maxDD_R|. Vol-targeting does not aim at R_per_day at all; it
aims at the denominator, by refusing to be large during the stretch that
produces the worst drawdown. If it works, the same trades pay in fewer days.

THE RULE THAT MUST NOT BE BROKEN. CLAUDE.md forbids a budget-shrinking risk
manager - one that watches the account and sizes down as it nears the cap -
because that manufactures a fake 0% breach rate. The multiplier here is a
function of TRAILING REALISED VOLATILITY OF THE STRATEGY'S OWN DAILY RETURNS
AND NOTHING ELSE. It never reads account equity, drawdown, distance to a
breach, or the phase. It is computed from days strictly before the day it
sizes, so it is knowable in advance, and the exact same multiplier is applied
whether the account is up 7% or down 7%. That is a market-state rule, not a
risk manager.

Everything is chosen inside the fit window and applied blind to the test half,
the same discipline as stage 18: the window, the clip bounds and the target
volatility are picked on the fit half only.

Nulls, because a sizing overlay is exactly where a project fools itself:

  shuffled multiplier   the same multipliers, block-shuffled in time. Same
                        distribution of sizes, same autocorrelation, no
                        relationship to the day it lands on. If this scores as
                        well as the real one, the gain was leverage, not timing.
  constant multiplier   the mean of the real multipliers, applied flat. Isolates
                        "it just traded bigger" from "it traded bigger at the
                        right time".

Output: backtests/xpos/stage23_volmanaged.csv
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from strategies.xpos.stage16_kris_shape import maxdd, pf            # noqa: E402
from strategies.xpos.stage18_nested import (allin, build, gated,    # noqa: E402
                                            rank_legs, to_daily)

OUT = ROOT / "backtests" / "xpos"
ACCOUNT = 10_000.0
LEG_COUNTS = (4, 6, 8, 10, 12, 14, 17, 20, 25)
RISKS = (0.0025, 0.005, 0.0075, 0.01, 0.015)

# the overlay grid, all chosen on the fit window
WINS = (10, 20, 30, 60)          # trailing days of realised vol
CLIP_HI = (1.5, 2.0, 3.0)        # most it may ever scale UP
CLIP_LO = (0.25, 0.5)            # least it may ever scale DOWN


def multiplier(dv: np.ndarray, win: int, lo: float, hi: float,
               target: float | None = None) -> tuple[np.ndarray, float]:
    """Inverse-volatility multiplier, causal.

    `dv` is the book's daily R. The volatility used for day t is the standard
    deviation of days [t-win, t-1] - the shift is what makes it knowable before
    the day trades. Days with no trades count as zeros, because an idle day is
    genuinely a zero-return day for the account and pretending otherwise would
    understate the vol of a lumpy book.
    """
    s = pd.Series(dv)
    vol = s.rolling(win, min_periods=max(win // 2, 5)).std(ddof=0).shift(1)
    if target is None:
        target = float(np.nanmedian(vol.values))
    m = (target / vol.replace(0.0, np.nan)).clip(lo, hi)
    # before the window fills there is no estimate; size at 1.0, never at the
    # clip ceiling, so the warm-up cannot flatter the result
    return m.fillna(1.0).values, target


def report(dv, risk, label, rows, window):
    a = allin(dv, risk)
    if not a or not a.get("allin_days"):
        print(f"  {label:28s} {'no admissible account':>38s}")
        return None
    print(f"  {label:28s} {a['pass_rate']*100:>6.1f}% "
          f"{str(a['median_days']):>10s} {a['allin_days']:>10.1f} "
          f"{a.get('accounts', float('nan')):>8.2f}")
    rows.append({"window": window, "book": label, "risk": risk, **a})
    return a


def main() -> int:
    t = pd.read_parquet(OUT / "stage14_trades.parquet")
    t["entry_ts"] = pd.to_datetime(t.entry_ts, utc=True)
    t["exit_ts"] = pd.to_datetime(t.exit_ts, utc=True)
    t = t[t.topn == 1].sort_values("exit_ts")
    g = gated(t)
    mid = g.exit_ts.quantile(0.5)
    f_lo, f_hi = g.exit_ts.min(), mid
    s_lo, s_hi = mid, g.exit_ts.max()
    first, second = g[g.exit_ts <= mid], g[g.exit_ts > mid]
    print(f"FIT   {f_lo:%Y-%m-%d} -> {f_hi:%Y-%m-%d}")
    print(f"TEST  {s_lo:%Y-%m-%d} -> {s_hi:%Y-%m-%d}\n")

    # ---- the H-017 baseline configuration, rebuilt exactly as stage 18 ----
    order = rank_legs(first)
    best = None
    for n in LEG_COUNTS:
        if n > len(order):
            continue
        _, dv = build(first, order[:n], f_lo, f_hi)
        if dv is None:
            continue
        for risk in RISKS:
            a = allin(dv, risk)
            if a and a.get("allin_days") and (
                    best is None or a["allin_days"] < best["allin_days"]):
                best = {"n": n, "risk": risk, **a}
    keys, risk = order[:best["n"]], best["risk"]
    print(f"baseline config chosen on FIT: {best['n']} legs at "
          f"{risk*100:.2f}% risk\n")

    _, dv_fit = build(first, keys, f_lo, f_hi)

    # ---- choose the overlay on the FIT window only ----
    print("choosing the overlay on the FIT window only")
    pick, rows = None, []
    for win in WINS:
        for lo in CLIP_LO:
            for hi in CLIP_HI:
                m, target = multiplier(dv_fit, win, lo, hi)
                a = allin(dv_fit * m, risk)
                if a and a.get("allin_days") and (
                        pick is None or a["allin_days"] < pick["allin_days"]):
                    pick = {"win": win, "lo": lo, "hi": hi,
                            "target": target, **a}
    if pick is None:
        print("no admissible overlay in the fit window")
        return 1
    print(f"  -> win {pick['win']}d, clip [{pick['lo']}, {pick['hi']}], "
          f"target vol {pick['target']:.4f} R/day "
          f"(fit all-in {pick['allin_days']}d)\n")

    # ---- apply blind to the TEST window ----
    s, dv_test = build(second, keys, s_lo, s_hi)
    span = max((s_hi - s_lo).days, 1)
    m_test, _ = multiplier(dv_test, pick["win"], pick["lo"], pick["hi"],
                           target=pick["target"])

    print("APPLIED BLIND TO THE TEST WINDOW")
    print(f"  {'book':28s} {'pass':>7s} {'median d':>10s} "
          f"{'all-in d':>10s} {'accts':>8s}")
    base = report(dv_test, risk, "H-017 baseline", rows, "test")
    real = report(dv_test * m_test, risk, "H-018 vol-managed", rows, "test")

    # ---- nulls ----
    sh_days = []
    for seed in range(8):
        rng = np.random.default_rng(seed + 91)
        blocks = np.array_split(m_test, max(len(m_test) // 30, 2))
        rng.shuffle(blocks)
        a = allin(dv_test * np.concatenate(blocks), risk)
        if a and a.get("allin_days"):
            sh_days.append(a["allin_days"])
    if sh_days:
        print(f"  {'NULL shuffled multiplier':28s} {'-':>7s} {'-':>10s} "
              f"{np.mean(sh_days):>10.1f} {'-':>8s}   "
              f"(best seed {min(sh_days):.1f})")
        rows.append({"window": "test", "book": "null shuffled multiplier",
                     "allin_days": round(float(np.mean(sh_days)), 1),
                     "best_seed": round(float(min(sh_days)), 1)})
    report(dv_test * float(np.mean(m_test)), risk,
           "NULL constant multiplier", rows, "test")

    # ---- the mandatory fields, on the trades the book actually took ----
    r = s.r_2x.values
    print(f"\n  trades {len(s)}  t/day {len(s)/span:.2f}  "
          f"PF@2x {pf(r):.3f}  avgR {r.mean():.4f}  "
          f"maxDD {maxdd(r):.1f}R  "
          f"mult mean {m_test.mean():.2f} min {m_test.min():.2f} "
          f"max {m_test.max():.2f}")

    if base and real:
        d = (base["allin_days"] - real["allin_days"]) / base["allin_days"]
        print(f"\n  VERDICT: {base['allin_days']:.1f} -> "
              f"{real['allin_days']:.1f} all-in days ({d*100:+.1f}%)")

    pd.DataFrame(rows).to_csv(OUT / "stage23_volmanaged.csv", index=False)
    print(f"\nwrote {OUT / 'stage23_volmanaged.csv'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
