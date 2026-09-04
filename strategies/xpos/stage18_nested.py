"""H-017 stage 18 - the nested holdout. Does the 15-day figure survive?

Stage 16/17 ranked the LEGS on a held-out first half, which is right, but then
chose the leg COUNT (17) and the RISK LEVEL (0.50%) by reading the second-half
table. Those are two more parameters fitted on the data they are reported on,
and a selected maximum is not a forecast. HANDOFF's rule - "rank candidates on
the fit window only, then report every number on the window they were not
chosen on" - was half-applied.

This applies it fully. Everything is chosen inside the first half:

    legs ranked by their own K       (already done)
    leg COUNT chosen on the first half account simulation
    RISK LEVEL chosen on the first half account simulation

and then that one configuration - a number of legs and a percentage - is run
blind on the second half. Whatever it produces is the honest figure.

Two nulls beside it, because a 50% pass rate on a searched configuration is
exactly where a project talks itself into a result:

  shuffled gate    the same book with a block-shuffled crowd feed driving the
                   gate, so the gate keeps the same share of trades and the
                   same autocorrelation but knows nothing
  random legs      the same count and risk, legs drawn at random instead of
                   K-ranked

Output: backtests/xpos/stage18_nested.csv
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
from strategies.xpos.stage17_economics import _first_account        # noqa: E402

OUT = ROOT / "backtests" / "xpos"
ACCOUNT, FEE, GATE_PF = 10_000.0, 32.0, 1.20
LEG_COUNTS = (4, 6, 8, 10, 12, 14, 17, 20, 25)
RISKS = (0.0025, 0.005, 0.0075, 0.01, 0.015)


def gated(t: pd.DataFrame, v=None) -> pd.DataFrame:
    v = t.crowd_z.values if v is None else v
    d = t.direction.values
    k = np.where(d > 0, v < 0, v > 0)
    return t[np.where(np.isnan(v), True, k)]


def to_daily(s: pd.DataFrame, lo, hi):
    """Daily R on a complete calendar, idle days as exact zeros.

    `lo`/`hi` are trade timestamps and carry a time of day; `resample("1D")`
    emits midnights. Without normalising, the reindex matches nothing and the
    whole series silently comes back as zeros - which reads as "no account ever
    passed" rather than as a bug.
    """
    d = pd.Series(s.r_2x.values,
                  index=pd.DatetimeIndex(s.exit_ts)).resample("1D").sum()
    idx = pd.date_range(pd.Timestamp(lo).normalize(),
                        pd.Timestamp(hi).normalize(), freq="1D", tz="UTC")
    return d.reindex(idx).fillna(0.0).values


def allin(dv: np.ndarray, risk: float) -> dict:
    """Pass rate, median days, and days-to-funded including sequential retries."""
    starts = list(range(0, max(len(dv) - 400, 1), 7))
    if len(starts) < 10:
        return {}
    res = [_first_account(dv[s0:] * risk) for s0 in starts]
    ok = [d for p, d in res if p]
    bad = [d for p, d in res if not p]
    if not ok:
        return {"pass_rate": 0.0, "median_days": None, "allin_days": None}
    pr = len(ok) / len(res)
    med = float(np.median(ok))
    wasted = float(np.mean(bad)) if bad else 0.0
    return {"pass_rate": round(pr, 4), "median_days": med,
            "allin_days": round(med + (1 / pr - 1) * wasted, 1),
            "accounts": round(1 / pr, 2), "fee_usd": round(FEE / pr, 0)}


def rank_legs(first: pd.DataFrame) -> list:
    out = []
    for key, g in first.groupby(["symbol", "tf"]):
        r = g.r_2x.values
        dd = maxdd(r)
        span = max((g.exit_ts.max() - g.entry_ts.min()).days, 1)
        if dd >= 0 or r.sum() <= 0 or pf(r) < GATE_PF or len(g) < 60:
            continue
        out.append(((r.sum() / span) / abs(dd), key))
    out.sort(reverse=True)
    return [k for _, k in out]


def build(src: pd.DataFrame, keys, lo, hi):
    s = src[[k in keys for k in zip(src.symbol, src.tf)]].sort_values("exit_ts")
    return (s, to_daily(s, lo, hi)) if len(s) >= 100 else (s, None)


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
    print(f"FIT   {f_lo:%Y-%m-%d} -> {f_hi:%Y-%m-%d}   "
          f"({(f_hi-f_lo).days} days)")
    print(f"TEST  {s_lo:%Y-%m-%d} -> {s_hi:%Y-%m-%d}   "
          f"({(s_hi-s_lo).days} days)\n")

    order = rank_legs(first)
    print(f"{len(order)} legs clear PF {GATE_PF} in the fit window\n")

    # ---- choose leg count and risk INSIDE the fit window ----
    print("choosing leg count and risk on the FIT window only")
    best = None
    grid = []
    for n in LEG_COUNTS:
        if n > len(order):
            continue
        _, dv = build(first, order[:n], f_lo, f_hi)
        if dv is None:
            continue
        for risk in RISKS:
            a = allin(dv, risk)
            if not a or not a.get("allin_days"):
                continue
            grid.append({"n": n, "risk": risk, **a})
            if best is None or a["allin_days"] < best["allin_days"]:
                best = {"n": n, "risk": risk, **a}
    if best is None:
        print("nothing admissible in the fit window")
        return 1
    print(f"  -> chose {best['n']} legs at {best['risk']*100:.2f}% risk "
          f"(fit-window all-in {best['allin_days']} days, "
          f"pass {best['pass_rate']*100:.1f}%)\n")

    keys = order[:best["n"]]
    risk = best["risk"]
    rows = [{"window": "fit (chosen here)", **best}]

    print("APPLIED BLIND TO THE TEST WINDOW\n")
    print(f"  {'book':26s} {'trades':>7s} {'t/day':>6s} {'PF2x':>6s} "
          f"{'$/trade':>8s} {'pass':>6s} {'median d':>9s} {'all-in d':>9s}")

    s, dv = build(second, keys, s_lo, s_hi)
    a = allin(dv, risk)
    span = max((s_hi - s_lo).days, 1)
    print(f"  {'H-017 real':26s} {len(s):>7d} {len(s)/span:>6.2f} "
          f"{pf(s.r_2x.values):>6.3f} "
          f"{s.r_2x.mean()*risk*ACCOUNT:>7.2f}$ "
          f"{a['pass_rate']*100:>5.1f}% {str(a['median_days']):>9s} "
          f"{str(a['allin_days']):>9s}")
    rows.append({"window": "test", "book": "real", "n": best["n"], "risk": risk,
                 "trades": len(s), "tpd": round(len(s)/span, 2),
                 "pf_2x": round(pf(s.r_2x.values), 3), **a})

    # ---- null 1: the gate driven by a block-shuffled feed ----
    ng = []
    for seed in range(5):
        sh = of.block_shuffle(pd.Series(t.crowd_z.values).set_axis(t.entry_ts),
                              seed=seed + 41, block=288).values
        gt = gated(t, sh)
        s2, dv2 = build(gt[gt.exit_ts > mid], keys, s_lo, s_hi)
        if dv2 is None:
            continue
        a2 = allin(dv2, risk)
        if a2.get("allin_days"):
            ng.append((a2["allin_days"], a2["pass_rate"], a2["median_days"]))
    if ng:
        d_, p_, m_ = (np.mean([x[i] for x in ng]) for i in range(3))
        print(f"  {'NULL shuffled gate':26s} {'-':>7s} {'-':>6s} {'-':>6s} "
              f"{'-':>8s} {p_*100:>5.1f}% {m_:>9.0f} {d_:>9.1f}   "
              f"(best seed {min(x[0] for x in ng):.1f})")
        rows.append({"window": "test", "book": "null shuffled gate",
                     "pass_rate": round(float(p_), 4),
                     "median_days": round(float(m_), 1),
                     "allin_days": round(float(d_), 1)})

    # ---- null 2: the same count and risk, legs drawn at random ----
    allk = sorted(set(zip(second.symbol, second.tf)))
    nr = []
    for seed in range(5):
        rng = np.random.default_rng(seed + 11)
        kk = [allk[i] for i in rng.choice(len(allk), size=min(best["n"], len(allk)),
                                          replace=False)]
        s3, dv3 = build(second, kk, s_lo, s_hi)
        if dv3 is None:
            continue
        a3 = allin(dv3, risk)
        if a3.get("allin_days"):
            nr.append((a3["allin_days"], a3["pass_rate"], a3["median_days"]))
    if nr:
        d_, p_, m_ = (np.mean([x[i] for x in nr]) for i in range(3))
        print(f"  {'NULL random legs':26s} {'-':>7s} {'-':>6s} {'-':>6s} "
              f"{'-':>8s} {p_*100:>5.1f}% {m_:>9.0f} {d_:>9.1f}   "
              f"(best seed {min(x[0] for x in nr):.1f})")
        rows.append({"window": "test", "book": "null random legs",
                     "pass_rate": round(float(p_), 4),
                     "median_days": round(float(m_), 1),
                     "allin_days": round(float(d_), 1)})

    print("\nfor reference, the whole test-window surface "
          "(NOT how the configuration was chosen):")
    print(f"  {'legs':>5s} " + " ".join(f"{r*100:>10.2f}%" for r in RISKS))
    for n in LEG_COUNTS:
        if n > len(order):
            continue
        _, dv4 = build(second, order[:n], s_lo, s_hi)
        if dv4 is None:
            continue
        cells = []
        for r in RISKS:
            a4 = allin(dv4, r)
            cells.append(a4.get("allin_days"))
        mark = " <-- chosen" if n == best["n"] else ""
        print(f"  {n:>5d} " + " ".join(
            f"{('%.0f' % c) if c else '-':>11s}" for c in cells) + mark)

    pd.DataFrame(rows).to_csv(OUT / "stage18_nested.csv", index=False)
    print(f"\nwrote {OUT / 'stage18_nested.csv'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
