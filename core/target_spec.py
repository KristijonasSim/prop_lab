"""TASK 4 — what edge is actually big enough? The screening spec.

THE PROBLEM THIS SOLVES. Every hypothesis here has been built first and priced
afterwards, and every one has died at the pricing step. Five feeds in a row have
landed in the 1-9bps band and been discarded one at a time, each after a full
build. That is the wrong order. If the minimum viable edge were known up front,
a diagnostic could be screened against it in one line and most of those builds
would never have started.

So: given Kris's actual constraints, what is the smallest edge worth building?

    ONE-STEP evaluation      8% target, 4% daily loss, 8% max loss
                             (max loss enforced BOTH static and trailing —
                             the stricter reading, per core/prop_rules.py)
    THREE accounts           bought together, and only ONE needs to pass
    SHORT holds              intraday to a few days

THE THREE-ACCOUNT POINT, which changes the answer. Time-to-funded across three
independent accounts is a MINIMUM, not an average, and the probability of at
least one passing is 1 - (1-p)^3. At p = 0.4 per account that is 0.784. This
makes HIGHER risk per trade rational than single-account math suggests: a
setting that busts two accounts and passes one in 12 days beats one that limps
all three to 60. Nobody here has priced that, and every board number so far was
computed for a single account.

WHAT IS SWEPT. A strategy is described by three numbers a diagnostic can
actually report:

    tpd      trades per day
    avg_R    average R per trade (R = the fixed initial stop, so it is
             comparable across markets — the repo's own convention)
    sd_R     per-trade dispersion in R. 1.0 is typical for a fixed-stop system
             with a ~2:1 target; it is swept because it matters more than
             people expect.

Daily R is the sum of that day's trades. The account simulation is the repo's
own `core/riskladder.run_accounts`, unchanged, so these numbers are directly
comparable to every board record — fresh account every trading day, fixed risk,
real breaches, no size-shrinking risk manager.

TRANSLATING TO BPS. avg_R is dimensionless; a diagnostic reports bps. The
bridge is the stop distance:

    edge_bps = avg_R * stop_bps

A 4h crypto trade with a 1% stop has stop_bps = 100, so avg_R 0.05 is a 5bps
edge. The output table is printed in both units at three representative stop
sizes so a response study can be read straight against it.

Run:  .venv/bin/python core/target_spec.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.prop_rules import PropRules                          # noqa: E402
from core.riskladder import run_accounts, RISK_LADDER          # noqa: E402

OUT = ROOT / "backtests" / "propfirms"
OUT.mkdir(parents=True, exist_ok=True)

ONE_STEP = PropRules(profit_target=0.08, daily_loss=0.04, max_loss=0.08)
N_ACCOUNTS = 3
N_DAYS = 4000                 # synthetic history; run_accounts starts one
                              # account per day, so this is 4,000 sampled paths
TPD = (0.5, 1.0, 2.0, 4.0, 8.0)
AVG_R = (0.01, 0.02, 0.03, 0.05, 0.08, 0.12, 0.20)
SD_R = (1.0,)
STOPS_BPS = (50, 100, 200)    # a 0.5%, 1% and 2% stop
SEED = 20260906
#: "good enough": at least one of three accounts funded inside this many days
HORIZON_DAYS = 45


def daily_series(tpd: float, avg_r: float, sd_r: float, rng) -> pd.Series:
    """A synthetic daily R series with the requested per-trade properties.

    Trades per day is Poisson, not fixed: a real strategy does not deliver
    exactly n signals every day, and the lumpiness is part of what breaches a
    daily loss limit."""
    n = rng.poisson(tpd, N_DAYS)
    tot = int(n.sum())
    r = rng.normal(avg_r, sd_r, tot)
    out = np.zeros(N_DAYS)
    i = 0
    for d in range(N_DAYS):
        k = n[d]
        if k:
            out[d] = r[i:i + k].sum()
            i += k
    return pd.Series(out, index=pd.RangeIndex(N_DAYS))


def best_risk(daily: pd.Series) -> dict:
    """The risk setting that minimises expected days for THREE accounts.

    Deliberately not the setting that maximises pass rate. With three tickets
    and one needed, the quantity to minimise is the expected wait until the
    FIRST pass, and that trades pass rate against speed."""
    best = None
    for risk in RISK_LADDER:
        a = run_accounts(daily, risk, ONE_STEP)
        p = a["pass_rate"]
        if p <= 0 or a["median_days"] is None:
            continue
        p_any = 1.0 - (1.0 - p) ** N_ACCOUNTS
        # expected days to the first of three passes, approximated from the
        # median of one account scaled by how much three tickets help
        exp1 = a["median_days"] / p if p > 0 else np.inf
        exp_any = exp1 / N_ACCOUNTS
        row = {"risk": risk, "pass_rate": p, "p_any3": p_any,
               "median_days": a["median_days"], "p25_days": a["p25_days"],
               "fail_daily": a["fail_daily"], "fail_max": a["fail_max"],
               "exp_days_1": exp1, "exp_days_any3": exp_any}
        if best is None or row["exp_days_any3"] < best["exp_days_any3"]:
            best = row
    return best or {}


def main() -> int:
    rng = np.random.default_rng(SEED)
    rows = []
    for tpd in TPD:
        for avg_r in AVG_R:
            for sd_r in SD_R:
                daily = daily_series(tpd, avg_r, sd_r, rng)
                b = best_risk(daily)
                if not b:
                    continue
                rows.append({"tpd": tpd, "avg_R": avg_r, "sd_R": sd_r,
                             "sharpe_ann": avg_r / sd_r * np.sqrt(252 * tpd),
                             **b,
                             **{f"bps_at_stop{s}": avg_r * s for s in STOPS_BPS}})
        print(f"  swept tpd={tpd}", flush=True)

    out = pd.DataFrame(rows)
    out.to_csv(OUT / "target_spec.csv", index=False)

    print(f"\n{'=' * 104}\nONE-STEP, THREE ACCOUNTS — expected days until the "
          f"FIRST account is funded\n{'=' * 104}")
    piv = out.pivot_table(index="avg_R", columns="tpd", values="exp_days_any3")
    print(piv.round(1).to_string())

    print(f"\n-- probability at least one of three passes --")
    print(out.pivot_table(index="avg_R", columns="tpd",
                          values="p_any3").round(3).to_string())

    print(f"\n-- the risk per trade that gets there fastest --")
    print(out.pivot_table(index="avg_R", columns="tpd",
                          values="risk").round(4).to_string())

    # ------------------------------------------------------------------
    # THE NULL FOR THE EVALUATION ITSELF.
    #
    # This repo scores every hypothesis against a null and has caught three
    # different results that way. Nobody has ever done it to the prop challenge.
    # A ZERO-edge strategy is the right null: an 8% target against an 8% max
    # loss is close to a fair coin, so a large share of "passes" are luck and
    # any pass rate has to be read against that share, not against zero.
    # ------------------------------------------------------------------
    print(f"\n{'=' * 104}\nTHE NULL: what a strategy with NO EDGE AT ALL "
          f"achieves on the same rules\n{'=' * 104}")
    null_rows = []
    for tpd in TPD:
        daily = daily_series(tpd, 0.0, 1.0, rng)
        for risk in RISK_LADDER:
            a = run_accounts(daily, risk, ONE_STEP)
            if a["pass_rate"] <= 0:
                continue
            null_rows.append({"tpd": tpd, "risk": risk,
                              "pass_rate": a["pass_rate"],
                              "p_any3": 1 - (1 - a["pass_rate"]) ** N_ACCOUNTS,
                              "median_days": a["median_days"],
                              "fail_daily": a["fail_daily"],
                              "fail_max": a["fail_max"]})
    nulldf = pd.DataFrame(null_rows)
    nulldf.to_csv(OUT / "target_spec_null.csv", index=False)
    print(nulldf.pivot_table(index="risk", columns="tpd",
                             values="p_any3").round(3).to_string())
    peak = nulldf.loc[nulldf.p_any3.idxmax()]
    print(f"\n  A COIN FLIP funds at least one of three accounts "
          f"{peak.p_any3:.1%} of the time\n"
          f"  (tpd {peak.tpd:g}, risk {peak.risk:.2%}, median "
          f"{peak.median_days:.0f} days).")
    print("  So pass rate on its own says almost nothing. What an edge has to\n"
          "  buy is the LIFT over this line — and what actually matters is\n"
          "  keeping the funded account afterwards, which no amount of luck does.")

    print(f"\n{'=' * 104}\nTHE SPEC: lift over the no-edge null, "
          f"at the null's own best risk\n{'=' * 104}")
    base = nulldf.groupby("tpd").p_any3.max().to_dict()
    sp = out.copy()
    sp["null_p_any3"] = sp.tpd.map(base)
    sp["lift"] = sp.p_any3 - sp.null_p_any3
    piv = sp.pivot_table(index="avg_R", columns="tpd", values="lift")
    print(piv.round(3).to_string())
    print("\n  avg_R rows, trades/day columns. A row that is ~0 everywhere is a\n"
          "  strategy indistinguishable from tossing a coin at the same risk.")

    ok = sp[(sp.lift >= 0.15) & (sp.exp_days_any3 <= HORIZON_DAYS)]
    print(f"\n-- what it takes to beat the coin flip by 15 points inside "
          f"{HORIZON_DAYS} days --")
    if len(ok):
        need = ok.groupby("tpd").avg_R.min()
        print(f"{'trades/day':>11} {'min avg_R':>10}   "
              + "  ".join(f"{'edge@' + str(s) + 'bps stop':>18}" for s in STOPS_BPS))
        for tpd, r in need.items():
            print(f"{tpd:11.1f} {r:10.3f}   "
                  + "  ".join(f"{r * s:18.1f}" for s in STOPS_BPS))
        print("\n  Read the right-hand columns as: the NET bps per trade a\n"
              "  diagnostic has to show, after cost, at that stop size.")
    else:
        print("  nothing in the swept range clears it")

    print(f"\n-- for reference, what this project has actually measured --")
    print("  DVOL dvolz@4h        8.9 bps gross, ~0 net of a 14bps taker round trip")
    print("  depth imbz_5@4h      7.9 bps gross, ~0 net")
    print("  absorption@4h        6.55 bps gross, ~0 net")
    print("  size_z@4h           14.6 bps gross on a held-out half — see")
    print("                       strategies/stack/stage2_size.py")
    print(f"\nwrote {OUT / 'target_spec.csv'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
