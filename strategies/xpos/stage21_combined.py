"""H-017 stage 21 - crypto plus non-crypto, everything chosen blind.

Stage 20 ran the same kernel on gold, silver, oil, the three US indices and six
FX majors: **only 4 of 52 top-1 legs clear PF 1.20**, and the median leg has a
NEGATIVE average R. As a universe it is far weaker than the crypto perps.

But H-012's dilution result and HANDOFF's 0.023 leg correlation pull in
opposite directions here, and neither settles it by argument. Four weak legs
that are genuinely uncorrelated with eleven coins may still raise K, because K
is R_per_day over DRAWDOWN and an uncorrelated leg cuts the denominator even
when it adds little to the numerator. Or they may drag it, exactly as H-012
found. The fit window decides, not me.

So the whole configuration is chosen inside the fit window and nothing is
touched afterwards:

    ranking criterion   K, or daily Sharpe, or total R - three candidates,
                        because stage 18's random-leg null came within 1.3 days
                        of the real book, which says K-ranking is barely
                        better than chance and is the weakest joint here
    universe            crypto only, or crypto + non-crypto
    leg count           4 to 30
    risk per trade      0.25% to 1.50%

Four choices, all made on 2021-04 to 2023-11, then one configuration run blind
on 2023-11 to 2026-06 against the same two nulls as stage 18.

Output: backtests/xpos/stage21_combined.csv
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from strategies.orderflow import orderflow as of                    # noqa: E402
from strategies.xpos.stage16_kris_shape import maxdd, pf            # noqa: E402
from strategies.xpos.stage18_nested import allin, gated, to_daily   # noqa: E402

OUT = ROOT / "backtests" / "xpos"
ACCOUNT, GATE_PF = 10_000.0, 1.20
LEG_COUNTS = (4, 6, 8, 10, 12, 14, 17, 20, 25, 30)
RISKS = (0.0025, 0.005, 0.0075, 0.01, 0.015)
CRITERIA = ("K", "sharpe", "total_r")


def leg_scores(first: pd.DataFrame) -> pd.DataFrame:
    """Every candidate leg scored three ways on the fit window."""
    rows = []
    for key, g in first.groupby(["symbol", "tf"]):
        r = g.r_2x.values
        if len(g) < 60 or pf(r) < GATE_PF:
            continue
        dd = maxdd(r)
        span = max((g.exit_ts.max() - g.entry_ts.min()).days, 1)
        d = pd.Series(r, index=pd.DatetimeIndex(g.exit_ts)).resample("1D").sum()
        sd = d.std(ddof=1)
        rows.append({
            "symbol": key[0], "tf": key[1],
            "K": (r.sum() / span) / abs(dd) if dd < 0 and r.sum() > 0 else np.nan,
            # Daily Sharpe is K's stable twin: maxDD ~ c.sigma.sqrt(T), so
            # Sharpe is proportional to K in expectation but estimated from
            # every day rather than from one order statistic.
            "sharpe": float(d.mean() / sd * np.sqrt(365)) if sd else np.nan,
            "total_r": float(r.sum()),
        })
    return pd.DataFrame(rows)


def book(src: pd.DataFrame, keys, lo, hi):
    s = src[[k in keys for k in zip(src.symbol, src.tf)]].sort_values("exit_ts")
    if len(s) < 100:
        return s, None
    return s, to_daily(s, lo, hi)


def main() -> int:
    cr = pd.read_parquet(OUT / "stage14_trades.parquet")
    cr = cr[cr.topn == 1]
    nc = pd.read_parquet(OUT / "stage20_trades.parquet")
    nc = nc[nc.topn == 1]
    for d in (cr, nc):
        d["entry_ts"] = pd.to_datetime(d.entry_ts, utc=True)
        d["exit_ts"] = pd.to_datetime(d.exit_ts, utc=True)
    # Crypto legs carry H-009's crowd gate; the non-crypto ones have no
    # positioning feed and are taken ungated.
    cr = gated(cr)
    both = pd.concat([cr, nc], ignore_index=True).sort_values("exit_ts")

    mid = cr.exit_ts.quantile(0.5)
    universes = {"crypto only": cr, "crypto + non-crypto": both}
    print(f"FIT   -> {mid:%Y-%m-%d}\nTEST  {mid:%Y-%m-%d} ->\n")

    best, rows = None, []
    for uname, u in universes.items():
        first, second = u[u.exit_ts <= mid], u[u.exit_ts > mid]
        f_lo, f_hi = first.exit_ts.min(), mid
        sc = leg_scores(first)
        n_nc = int((~sc.symbol.str.endswith("USDT")).sum())
        print(f"{uname}: {len(sc)} legs clear PF {GATE_PF} in the fit window "
              f"({n_nc} non-crypto)")
        for crit in CRITERIA:
            ranked = sc.dropna(subset=[crit]).sort_values(crit, ascending=False)
            order = list(zip(ranked.symbol, ranked.tf))
            for n in LEG_COUNTS:
                if n > len(order):
                    continue
                _, dv = book(first, order[:n], f_lo, f_hi)
                if dv is None:
                    continue
                for risk in RISKS:
                    a = allin(dv, risk)
                    if not a or not a.get("allin_days"):
                        continue
                    rows.append({"stage": "fit", "universe": uname,
                                 "criterion": crit, "n_legs": n,
                                 "risk_pct": round(risk * 100, 2), **a})
                    if best is None or a["allin_days"] < best["allin_days"]:
                        best = {"universe": uname, "criterion": crit,
                                "n_legs": n, "risk": risk, "order": order, **a}
    print()
    if best is None:
        print("nothing admissible")
        return 1
    print(f"CHOSEN ON THE FIT WINDOW: {best['universe']}, ranked by "
          f"{best['criterion']}, {best['n_legs']} legs at "
          f"{best['risk']*100:.2f}%  (fit all-in {best['allin_days']} d, "
          f"pass {best['pass_rate']*100:.1f}%)\n")

    u = universes[best["universe"]]
    second = u[u.exit_ts > mid]
    s_lo, s_hi = mid, u.exit_ts.max()
    keys = best["order"][:best["n_legs"]]
    nc_keys = [k for k in keys if not k[0].endswith("USDT")]
    print(f"  {len(nc_keys)} of {len(keys)} chosen legs are non-crypto"
          + (f": {', '.join(a + ' ' + b for a, b in nc_keys)}" if nc_keys else ""))

    s, dv = book(second, keys, s_lo, s_hi)
    a = allin(dv, best["risk"])
    span = max((s_hi - s_lo).days, 1)
    print(f"\nBLIND ON THE TEST WINDOW\n")
    print(f"  {'book':24s} {'trades':>7s} {'t/day':>6s} {'PF2x':>6s} "
          f"{'$/trade':>8s} {'pass':>6s} {'median d':>9s} {'all-in d':>9s}")
    print(f"  {'H-017 combined':24s} {len(s):>7d} {len(s)/span:>6.2f} "
          f"{pf(s.r_2x.values):>6.3f} "
          f"{s.r_2x.mean()*best['risk']*ACCOUNT:>7.2f}$ "
          f"{a['pass_rate']*100:>5.1f}% {str(a['median_days']):>9s} "
          f"{str(a['allin_days']):>9s}")
    rows.append({"stage": "test", "book": "real", "universe": best["universe"],
                 "criterion": best["criterion"], "n_legs": best["n_legs"],
                 "risk_pct": round(best["risk"] * 100, 2),
                 "trades": len(s), "tpd": round(len(s)/span, 2),
                 "pf_2x": round(pf(s.r_2x.values), 3), **a})

    # null: same count and risk, legs drawn at random from the same universe
    allk = sorted(set(zip(second.symbol, second.tf)))
    nr = []
    for seed in range(8):
        rng = np.random.default_rng(seed + 101)
        kk = [allk[i] for i in rng.choice(len(allk),
                                          size=min(best["n_legs"], len(allk)),
                                          replace=False)]
        s3, dv3 = book(second, kk, s_lo, s_hi)
        if dv3 is None:
            continue
        a3 = allin(dv3, best["risk"])
        if a3.get("allin_days"):
            nr.append(a3["allin_days"])
    if nr:
        print(f"  {'NULL random legs':24s} {'-':>7s} {'-':>6s} {'-':>6s} "
              f"{'-':>8s} {'-':>6s} {'-':>9s} {np.mean(nr):>9.1f}   "
              f"(best of 8 seeds {min(nr):.1f})")
        rows.append({"stage": "test", "book": "null random legs",
                     "allin_days": round(float(np.mean(nr)), 1),
                     "best_seed": round(float(min(nr)), 1)})

    # null: the crowd gate driven by a block-shuffled feed
    ng = []
    for seed in range(5):
        sh = of.block_shuffle(pd.Series(cr.crowd_z.values).set_axis(cr.entry_ts),
                              seed=seed + 61, block=288).values
        gt = gated(cr, sh)
        u2 = pd.concat([gt, nc], ignore_index=True) if "non" in best["universe"] else gt
        s4, dv4 = book(u2[u2.exit_ts > mid], keys, s_lo, s_hi)
        if dv4 is None:
            continue
        a4 = allin(dv4, best["risk"])
        if a4.get("allin_days"):
            ng.append(a4["allin_days"])
    if ng:
        print(f"  {'NULL shuffled gate':24s} {'-':>7s} {'-':>6s} {'-':>6s} "
              f"{'-':>8s} {'-':>6s} {'-':>9s} {np.mean(ng):>9.1f}   "
              f"(best of 5 seeds {min(ng):.1f})")
        rows.append({"stage": "test", "book": "null shuffled gate",
                     "allin_days": round(float(np.mean(ng)), 1),
                     "best_seed": round(float(min(ng)), 1)})

    print(f"\n  H-017 crypto-only, blind: 30.3 days all-in / 19.5 median")
    print(f"  H-009 incumbent: 48.7 expected.  Target: 7-14.")
    pd.DataFrame(rows).to_csv(OUT / "stage21_combined.csv", index=False)
    print(f"\nwrote {OUT / 'stage21_combined.csv'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
