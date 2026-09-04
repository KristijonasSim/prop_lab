"""H-017 stage 17 - buying several accounts, and what a funded seat costs.

Stage 16 settled the argument. At Kris's sizing - one configuration per leg,
17 legs, 5.5 trades a day, a flat $50 risk per trade on $10k - the book reaches
the profit target in a **median of 15 days**, which is the goal. It also kills
**56% of accounts** getting there, which is why `riskladder.pick` had refused
that risk level: it insists the whole six-year equity curve fit inside the 8%
cap, and at 0.50% that curve draws down 54.9%.

`CLAUDE.md` is explicit that this is the wrong test to hide behind - "clean
PASS/FAIL with fixed risk per trade and real breaches; if it fails, it fails;
accounts are cheap." A 56% kill rate is not a disqualification, it is a price.
This stage puts the price in dollars and days.

For each risk level: how many evaluations must be bought, what they cost, and
how long until the first one is funded when several run at once. Evaluation fee
is taken from the prop-firm page - Velotrade at $32 is the cheapest that
permits a bot at all.

Accounts bought together on the SAME strategy are correlated - they see the
same trades - so buying five does NOT give five independent tries. They are
staggered a week apart here, which is what decorrelates them, and the
correlation is measured rather than assumed.

Output: backtests/xpos/stage17_economics.csv
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
from strategies.xpos.stage8_feasibility import _PH, _two_step       # noqa: E402
from strategies.xpos.stage16_kris_shape import gate, maxdd, pf      # noqa: E402

OUT = ROOT / "backtests" / "xpos"
ACCOUNT, FEE = 10_000.0, 32.0
STAGGER = 7            # accounts opened a week apart
GATE_PF = 1.20


def account_runs(daily: np.ndarray, risk: float, starts):
    """(passed, days) for an account opened on each start day."""
    d = daily * risk
    out = []
    for s0 in starts:
        pr, days = _two_step(d[s0:], _PH, MAX_DAYS)
        # _two_step scans every start inside the slice; the first entry is the
        # account opened on day s0 itself, which is the one being bought.
        got = _first_account(d[s0:])
        out.append(got)
    return out


def _first_account(d: np.ndarray):
    """One account opened on day 0 of `d`. Same rules, single path."""
    k, total = 0, 0
    n = len(d)
    for rules in TWO_STEP:
        eq = peak = 0.0
        day = traded = 0
        passed = False
        while k < n and total + day < MAX_DAYS:
            day += 1
            step = d[k]; k += 1
            if step != 0.0:
                traded += 1
            if min(step, 0.0) <= -rules.daily_loss:
                break
            low = eq + min(step, 0.0)
            if low - peak <= -rules.max_loss or low <= -rules.max_loss:
                break
            eq += step
            peak = max(peak, eq)
            if eq >= rules.profit_target and traded >= rules.min_trading_days:
                passed = True
                break
        total += day
        if not passed:
            return False, total
    return True, total


def main() -> int:
    t = pd.read_parquet(OUT / "stage14_trades.parquet")
    t["entry_ts"] = pd.to_datetime(t.entry_ts, utc=True)
    t["exit_ts"] = pd.to_datetime(t.exit_ts, utc=True)
    t = gate(t[t.topn == 1]).sort_values("exit_ts")
    mid = t.exit_ts.quantile(0.5)
    first, second = t[t.exit_ts <= mid], t[t.exit_ts > mid]

    rank = []
    for key, g in first.groupby(["symbol", "tf"]):
        r = g.r_2x.values
        dd = maxdd(r)
        span = max((g.exit_ts.max() - g.entry_ts.min()).days, 1)
        if dd >= 0 or r.sum() <= 0 or pf(r) < GATE_PF or len(g) < 60:
            continue
        rank.append(((r.sum() / span) / abs(dd), key))
    rank.sort(reverse=True)
    keys = [k for _, k in rank[:17]]
    s = second[[k in keys for k in zip(second.symbol, second.tf)]].sort_values("exit_ts")
    daily = pd.Series(s.r_2x.values,
                      index=pd.DatetimeIndex(s.exit_ts)).resample("1D").sum()
    idx = pd.date_range(daily.index[0], daily.index[-1], freq="1D", tz="UTC")
    dv = daily.reindex(idx).fillna(0.0).values
    span = len(idx)
    print(f"17 legs, one config each: {len(s)} trades over {span} days "
          f"= {len(s)/span:.2f}/day, PF@2x {pf(s.r_2x.values):.3f}, "
          f"avg {s.r_2x.mean():.4f}R\n")

    rows = []
    print("ONE ACCOUNT AT A TIME\n")
    print(f"  {'risk':>7s} {'$/trade':>8s} {'pass':>6s} {'median days':>12s} "
          f"{'accounts bought':>16s} {'fee cost':>9s} {'days to funded':>15s}")
    horizon = span - MAX_DAYS
    starts = list(range(0, max(horizon, 1), 7))
    best = None
    for risk in (0.0025, 0.005, 0.0075, 0.01, 0.015, 0.02):
        res = [_first_account(dv[s0:] * risk) for s0 in starts]
        ok = [d for p, d in res if p]
        pr = len(ok) / len(res)
        if not ok:
            continue
        med = float(np.median(ok))
        n_bought = 1.0 / pr
        # Sequential retries: buy, fail, buy again. Failures end early, so the
        # wasted days are the failed accounts' own lifetimes, not a full cycle.
        fail_days = [d for p, d in res if not p]
        wasted = float(np.mean(fail_days)) if fail_days else 0.0
        seq_days = med + (n_bought - 1) * wasted
        print(f"  {risk*100:>6.2f}% {s.r_2x.mean()*risk*ACCOUNT:>7.2f}$ "
              f"{pr*100:>5.1f}% {med:>12.0f} {n_bought:>16.1f} "
              f"{n_bought*FEE:>8.0f}$ {seq_days:>15.0f}")
        rows.append({"mode": "sequential", "risk_pct": round(risk*100, 2),
                     "usd_per_trade": round(float(s.r_2x.mean())*risk*ACCOUNT, 2),
                     "pass_rate": round(pr, 4), "median_days": med,
                     "accounts_bought": round(n_bought, 2),
                     "fee_cost_usd": round(n_bought*FEE, 0),
                     "days_to_funded": round(seq_days, 0)})

    # NOTE the survivor bias this table would have without the hit rate: the
    # median is taken over start points where SOMETHING passed, so a column
    # with a higher hit rate includes harder periods the lower one skipped.
    # Read the pair, never the median alone.
    print("\n\nSEVERAL AT ONCE, opened a week apart "
          "(median days until the FIRST is funded / share of start dates "
          "where any passed)\n")
    print(f"  {'risk':>7s} " + " ".join(f"{'N='+str(n):>11s}"
                                        for n in (1, 3, 5, 10)))
    for risk in (0.0025, 0.005, 0.0075, 0.01, 0.015, 0.02):
        cells = []
        for nacc in (1, 3, 5, 10):
            outs = []
            for s0 in starts:
                done = []
                for i in range(nacc):
                    p, d = _first_account(dv[s0 + i*STAGGER:] * risk)
                    if p:
                        done.append(i*STAGGER + d)
                outs.append(min(done) if done else np.nan)
            outs = np.array(outs, float)
            v = float(np.median(outs[np.isfinite(outs)])) if np.isfinite(outs).any() else None
            cells.append((v, float(np.isfinite(outs).mean())))
            rows.append({"mode": "parallel", "risk_pct": round(risk*100, 2),
                         "n_accounts": nacc, "median_days_first": v,
                         "hit_rate": round(float(np.isfinite(outs).mean()), 3)})
        print(f"  {risk*100:>6.2f}% " + " ".join(
            f"{('%3.0f d /%3.0f%%' % (c[0], c[1]*100)) if c[0] else '-':>11s}"
            for c in cells))

    pd.DataFrame(rows).to_csv(OUT / "stage17_economics.csv", index=False)
    print(f"\nwrote {OUT / 'stage17_economics.csv'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
