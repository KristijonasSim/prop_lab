"""H-017 stage 8 - what Sharpe does a 14-day pass actually require?

Six stages have now failed to find anything approaching Kris's target, so the
question worth answering is no longer "which strategy" but "what would ANY
strategy have to be". That is answerable exactly, and it should have been the
first thing computed.

Method: generate synthetic daily return streams at a known annualised Sharpe
and trade density, size each one so its worst drawdown exactly fills the 8%
cap - the same normalisation every book here gets - and run it through the
project's REAL two-step evaluation. No strategy, no signal, no fitting: just
the arithmetic of the prop rules, mapped over the only two parameters that
matter.

Then drop the project's actual books onto that map, so the gap between what
exists and what is needed is a distance rather than an argument.

The synthetic returns are drawn Student-t with 4 degrees of freedom, not
Gaussian. Real trading returns have fat tails, and a Gaussian simulation would
understate how often an account breaches and so overstate how fast a given
Sharpe gets funded.

Output: backtests/xpos/stage8_feasibility.csv
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from core import riskladder as RL                                   # noqa: E402
from numba import njit                                              # noqa: E402

from core.prop_rules import TWO_STEP                                # noqa: E402

# The pure-Python account loop is O(days^2) - every calendar day opens an
# account that runs forward up to 400 days - and at twelve years x ninety
# parameter cells that is over a billion iterations. Identical rules to
# `riskladder.run_accounts_two_step`, compiled.
_PH = np.array([[p_.profit_target, p_.max_loss, p_.daily_loss,
                 float(p_.min_trading_days)] for p_ in TWO_STEP],
               dtype=np.float64)


@njit(cache=True)
def _two_step(d, phases, max_days):
    n = d.shape[0]
    n_pass = 0
    days_out = np.empty(n, dtype=np.float64)
    n_days = 0
    for s0 in range(n):
        k = s0
        total = 0
        passed = False
        for pi in range(phases.shape[0]):
            target = phases[pi, 0]
            max_loss = phases[pi, 1]
            daily_loss = phases[pi, 2]
            min_td = phases[pi, 3]
            eq = 0.0
            peak = 0.0
            day = 0
            traded = 0
            passed = False
            while k < n and total + day < max_days:
                day += 1
                step = d[k]
                k += 1
                if step != 0.0:
                    traded += 1
                lo = step if step < 0.0 else 0.0
                if lo <= -daily_loss:
                    break
                low = eq + lo
                if low - peak <= -max_loss or low <= -max_loss:
                    break
                eq += step
                if eq > peak:
                    peak = eq
                if eq >= target and traded >= min_td:
                    passed = True
                    break
            total += day
            if not passed:
                break
        if passed:
            days_out[n_days] = total
            n_days += 1
            n_pass += 1
    return n_pass / n, days_out[:n_days]


OUT = ROOT / "backtests" / "xpos"
BT = ROOT / "backtests"
YEARS, DF_T = 12, 4
SHARPES = (0.5, 1.0, 1.5, 2.0, 3.0, 4.0, 5.0, 7.0, 10.0, 15.0)
TRADE_DAYS = (0.3, 1.0, 3.0)          # fraction of calendar days that trade


def synth(sharpe: float, active: float, seed: int) -> pd.Series:
    """Daily R for a strategy with this annualised Sharpe.

    `active` is the share of calendar days on which it trades; idle days are
    exact zeros, which is what makes a low-frequency book slow in calendar time
    even when its Sharpe is high.
    """
    rng = np.random.default_rng(seed)
    n = int(365 * YEARS)
    idx = pd.date_range("2014-01-01", periods=n, freq="1D", tz="UTC")
    on = rng.random(n) < min(active, 1.0)
    k = max(int(on.sum()), 10)
    # Student-t standardised to unit variance, then given the drift that
    # produces the requested annualised Sharpe on CALENDAR days.
    z = rng.standard_t(DF_T, k) / np.sqrt(DF_T / (DF_T - 2))
    mu = sharpe / np.sqrt(365.0)
    r = np.zeros(n)
    r[on] = z / np.sqrt(on.mean()) + mu / on.mean()
    return pd.Series(r, index=idx)


def evaluate(daily: pd.Series) -> dict:
    """Size so the worst drawdown fills the 8% cap, then run the real sim."""
    eq = np.concatenate(([0.0], np.cumsum(daily.values)))
    dd = float((eq - np.maximum.accumulate(eq)).min())
    if dd >= 0:
        return {}
    scaled = daily.values * (4.0 / abs(dd))
    # Risk 2.00% is exactly the level at which this scaling fills the 8% cap,
    # which is the level `riskladder.pick` would choose for it.
    pr, days = _two_step(scaled * 0.02, _PH, RL.MAX_DAYS)
    if pr <= 0 or days.size == 0:
        return {"risk": 0.02, "pass_rate": 0.0, "median_days": None,
                "expected_days": None}
    med = float(np.median(days))
    return {"risk": 0.02, "pass_rate": round(pr, 4),
            "median_days": round(med, 1),
            "expected_days": round(med / pr, 1),
            "K": round(float(scaled.sum()) / len(scaled) / 4.0, 5)}


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    rows = []
    print("MEDIAN DAYS TO A FUNDED ACCOUNT, by annualised Sharpe\n")
    print("  Synthetic daily returns, Student-t(4) tails, sized so the worst")
    print("  drawdown exactly fills the 8% cap, run through the real two-step")
    print("  evaluation. Median over 3 seeds.\n")
    print(f"  {'Sharpe':>7s} " +
          " ".join(f"{'trades/day ' + str(a):>16s}" for a in TRADE_DAYS))
    for sh in SHARPES:
        cells = []
        for act in TRADE_DAYS:
            meds, exps = [], []
            for seed in range(3):
                e = evaluate(synth(sh, act, seed + int(sh * 100) + int(act * 10)))
                if e.get("median_days"):
                    meds.append(e["median_days"])
                    exps.append(e["expected_days"])
                    rows.append({"sharpe": sh, "trades_per_day": act,
                                 "seed": seed, **e})
            cells.append((np.median(meds) if meds else None,
                          np.median(exps) if exps else None))
        def fmt(c):
            if c[0] is None:
                return f"{'-':>16s}"
            return f"{c[0]:5.0f} med /{c[1]:6.0f} exp"
        print(f"  {sh:>7.1f} " + " ".join(fmt(c) for c in cells))

    print("\n\nWHERE THIS PROJECT'S BOOKS SIT\n")
    print(f"  {'id':7s} {'name':32s} {'Sharpe':>7s} {'trades/day':>11s} "
          f"{'expected days':>14s}")
    for p in sorted(BT.glob("*/board.json")):
        b = json.loads(p.read_text())
        f = b["fields"]
        print(f"  {b['hid']:7s} {b['name'][:32]:32s} {f.get('sharpe', 0):>7.2f} "
              f"{f['trades_per_day']:>11.3f} "
              f"{str(b['pick'].get('expected_days')):>14s}")
        rows.append({"sharpe": f.get("sharpe"), "trades_per_day": f["trades_per_day"],
                     "book": b["hid"], "expected_days": b["pick"].get("expected_days")})

    df = pd.DataFrame(rows)
    df.to_csv(OUT / "stage8_feasibility.csv", index=False)

    s = df[df.book.isna()] if "book" in df else df
    hit = s[(s.median_days <= 14)] if "median_days" in s else pd.DataFrame()
    if len(hit):
        print(f"\n  Lowest Sharpe reaching a 14-day MEDIAN: "
              f"{hit.sharpe.min():.1f}")
    hit7 = s[(s.median_days <= 7)] if "median_days" in s else pd.DataFrame()
    if len(hit7):
        print(f"  Lowest Sharpe reaching a 7-day MEDIAN:  {hit7.sharpe.min():.1f}")
    print(f"\nwrote {OUT / 'stage8_feasibility.csv'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
