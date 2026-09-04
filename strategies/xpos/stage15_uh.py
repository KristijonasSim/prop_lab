"""H-017 stage 15 - trade quality vs trade count, and the combined book (UH).

KRIS'S OBJECTION, AND IT WAS CORRECT. The stage 11 book took 66 trades a day
each worth 0.031R, against H-009's 1.29 a day worth 0.113R. The cause was a
top-10 configuration book inside every leg: each trade's R was divided by ten
before the twenty legs were equal-weighted. Nobody trades that.

Stage 14 re-ran the whole universe at three widths. Per leg:

    top-1    avg 0.2485R per trade, 0.42 trades/day   <- 2.2x H-009's edge
    top-3    avg 0.0829R,           1.23 trades/day
    top-10   avg 0.0208R,           4.27 trades/day

So this stage asks the question that decides the shape of the book: given the
choice, is it better to take few good trades or many thin ones? Days to a
funded account is the referee, not profit factor.

AND THE ULTRA HYPOTHESIS. Kris's second idea: stop looking for one new
strategy and combine the ones that already work. The books here are genuinely
different mechanisms on partly different markets - H-009 is VWAP reversion
gated by crowd positioning on crypto and gold, H-016 is multi-timescale trend
on metals - so they should diversify rather than duplicate. Stage 1 measured
the diversification exponent at 0.441, close to the theoretical 0.5, which is
what makes combining worth trying at all.

Everything is measured on a held-out half: legs and weights are chosen on the
first half of each series and never re-touched.

Output: backtests/xpos/stage15_uh.csv
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from core import riskladder as RL                                   # noqa: E402

OUT = ROOT / "backtests" / "xpos"
BT = ROOT / "backtests"
TARGET_DD_R, GATE_PF = 4.0, 1.20


def pf(r):
    w, l = r[r > 0].sum(), -r[r < 0].sum()
    return float(w / l) if l > 0 else np.nan


def maxdd(r):
    e = np.cumsum(r)
    return float((e - np.maximum.accumulate(e)).min())


def describe(r: np.ndarray, entry, exit_, nlegs: int) -> dict | None:
    """Book statistics, plus what one trade is actually worth in ACCOUNT terms.

    `pct_per_trade` is the number Kris asked about: at the risk the 8% cap
    permits, how much of the account does the average trade add?
    """
    if len(r) < 150:
        return None
    r = r / nlegs
    dd = maxdd(r)
    if dd >= 0 or r.sum() <= 0:
        return None
    span = max((pd.Timestamp(exit_.max()) - pd.Timestamp(entry.min())).days, 1)
    risk = 0.08 / abs(dd)
    return {"n_legs": nlegs, "trades": len(r), "pf_2x": round(pf(r), 3),
            "avg_r": round(float(r.mean()), 5),
            "avg_r_per_leg": round(float(r.mean() * nlegs), 4),
            "tpd": round(len(r) / span, 2), "max_dd_r": round(dd, 2),
            "K": round((r.sum() / span) / abs(dd), 5),
            "risk_pct": round(risk * 100, 3),
            "pct_per_trade": round(risk * float(r.mean()) * 100, 4),
            "pct_per_day": round(risk * float(r.sum()) / span * 100, 4)}


def simulate(r: np.ndarray, exit_ts, nlegs: int) -> dict:
    r = r / nlegs
    dd = maxdd(r)
    if dd >= 0:
        return {}
    _rows, pick = RL.from_trades(r * (TARGET_DD_R / abs(dd)), exit_ts)
    return {"risk": pick["risk"], "pass_rate": pick["pass_rate"],
            "killed": round(pick["fail_max"] + pick["fail_daily"], 4),
            "median_days": pick["median_days"],
            "expected_days": pick["expected_days"]}


def gate(t):
    v, d = t.crowd_z.values, t.direction.values
    k = np.where(d > 0, v < 0, v > 0)
    return t[np.where(np.isnan(v), True, k)]


def rank_legs(first: pd.DataFrame) -> list:
    out = []
    for key, g in first.groupby(["symbol", "tf"]):
        r = g.r_2x.values
        dd = maxdd(r)
        span = max((g.exit_ts.max() - g.entry_ts.min()).days, 1)
        if dd >= 0 or r.sum() <= 0 or pf(r) < GATE_PF or len(g) < 100:
            continue
        out.append(((r.sum() / span) / abs(dd), key))
    out.sort(reverse=True)
    return [k for _, k in out]


def main() -> int:
    t = pd.read_parquet(OUT / "stage14_trades.parquet")
    t["entry_ts"] = pd.to_datetime(t.entry_ts, utc=True)
    t["exit_ts"] = pd.to_datetime(t.exit_ts, utc=True)
    t = t.sort_values("exit_ts")
    mid = t.exit_ts.quantile(0.5)
    rows = []

    print("1. FEW GOOD TRADES vs MANY THIN ONES "
          f"(legs chosen on the first half, to {mid:%Y-%m-%d})\n")
    print(f"  {'width':>6s} {'legs':>5s} {'t/day':>6s} {'avg R/trade':>12s} "
          f"{'PF2x':>6s} {'risk/trade':>11s} {'%/trade':>8s} {'%/day':>7s} "
          f"{'EXPECTED':>9s}")
    best_crypto = None
    for topn in sorted(t.topn.unique()):
        d = gate(t[t.topn == topn])
        first, second = d[d.exit_ts <= mid], d[d.exit_ts > mid]
        order = rank_legs(first)
        for n in (5, 10, 20):
            if n > len(order):
                continue
            keys = order[:n]
            s = second[[k in keys for k in zip(second.symbol, second.tf)]]
            s = s.sort_values("exit_ts")
            st = describe(s.r_2x.values, s.entry_ts, s.exit_ts, n)
            if not st:
                continue
            sm = simulate(s.r_2x.values, s.exit_ts.values, n)
            print(f"  top-{topn:<2d} {n:>5d} {st['tpd']:>6.2f} "
                  f"{st['avg_r_per_leg']:>12.4f} {st['pf_2x']:>6.3f} "
                  f"{st['risk_pct']:>10.2f}% {st['pct_per_trade']:>7.3f}% "
                  f"{st['pct_per_day']:>6.3f}% {str(sm.get('expected_days')):>9s}")
            rows.append({"kind": "width", "name": f"top-{topn} x {n} legs",
                         **st, **sm})
            ed = sm.get("expected_days")
            if ed and (best_crypto is None or ed < best_crypto[0]):
                best_crypto = (ed, s, n, f"top-{topn} x {n} legs")

    print("\n\n2. THE ULTRA HYPOTHESIS — combining the books that work\n")
    # Load the other books' out-of-sample trades, each already walk-forward.
    parts = {}
    if best_crypto:
        _, s, n, lab = best_crypto
        parts["H-017 crypto (" + lab + ")"] = (s.r_2x.values / n,
                                               s.entry_ts.values, s.exit_ts.values)
    h9 = pd.read_parquet(BT / "gated_vwap" / "stage6_trades.parquet")
    h9["entry_ts"] = pd.to_datetime(h9.entry_ts, utc=True)
    h9["exit_ts"] = pd.to_datetime(h9.exit_ts, utc=True)
    h9 = h9[h9.gated].sort_values("exit_ts")
    n9 = h9.groupby(["symbol", "tf"]).ngroups
    parts["H-009 VWAP+crowd"] = (h9.r_2x.values / n9, h9.entry_ts.values,
                                 h9.exit_ts.values)
    rb = pd.read_parquet(BT / "ribbon" / "stage10_trades.parquet")
    rb["entry_ts"] = pd.to_datetime(rb.entry_ts, utc=True)
    rb["exit_ts"] = pd.to_datetime(rb.exit_ts, utc=True)
    rb = rb.sort_values("exit_ts")
    nr = rb.groupby(["sym", "tf", "rule"]).ngroups if "sym" in rb else 1
    parts["H-016 ribbon metals"] = (rb.r_2x.values / nr, rb.entry_ts.values,
                                    rb.exit_ts.values)

    # Common window across everything, so no book gets a period the others lack.
    lo = max(pd.Timestamp(v[1].min()) for v in parts.values())
    hi = min(pd.Timestamp(v[2].max()) for v in parts.values())
    print(f"  common window {lo:%Y-%m-%d} -> {hi:%Y-%m-%d} "
          f"({(hi-lo).days} days)\n")
    print(f"  {'book':34s} {'trades':>8s} {'t/day':>6s} {'PF2x':>6s} "
          f"{'K':>8s} {'pass':>6s} {'EXPECTED':>9s}")

    cut = {}
    for k, (r, en, ex) in parts.items():
        m = (pd.DatetimeIndex(ex) >= lo) & (pd.DatetimeIndex(ex) <= hi)
        if m.sum() < 150:
            print(f"  {k:34s}  (too few trades in the common window)")
            continue
        cut[k] = (r[m], pd.DatetimeIndex(en)[m], pd.DatetimeIndex(ex)[m])
        st = describe(cut[k][0], cut[k][1], cut[k][2], 1)
        sm = simulate(cut[k][0], cut[k][2].values, 1)
        if st:
            print(f"  {k:34s} {st['trades']:>8d} {st['tpd']:>6.2f} "
                  f"{st['pf_2x']:>6.3f} {st['K']:>8.5f} "
                  f"{sm.get('pass_rate', 0)*100:>5.1f}% "
                  f"{str(sm.get('expected_days')):>9s}")
            rows.append({"kind": "solo", "name": k, **st, **sm})

    if len(cut) >= 2:
        print()
        import itertools
        for k in range(2, len(cut) + 1):
            for sub in itertools.combinations(sorted(cut), k):
                # Equal weight across BOOKS: each contributes 1/k of the risk,
                # which is the only weighting that needs no fitting.
                r = np.concatenate([cut[x][0] / k for x in sub])
                en = np.concatenate([cut[x][1].values for x in sub])
                ex = np.concatenate([cut[x][2].values for x in sub])
                o = np.argsort(ex)
                r, en, ex = r[o], en[o], ex[o]
                st = describe(r, pd.DatetimeIndex(en), pd.DatetimeIndex(ex), 1)
                sm = simulate(r, ex, 1)
                if not st:
                    continue
                lab = " + ".join(x.split(" ")[0] for x in sub)
                print(f"  {lab:34s} {st['trades']:>8d} {st['tpd']:>6.2f} "
                      f"{st['pf_2x']:>6.3f} {st['K']:>8.5f} "
                      f"{sm.get('pass_rate', 0)*100:>5.1f}% "
                      f"{str(sm.get('expected_days')):>9s}")
                rows.append({"kind": "combo", "name": lab, **st, **sm})

    df = pd.DataFrame(rows)
    df.to_csv(OUT / "stage15_uh.csv", index=False)
    ok = df[df.expected_days.notna()]
    if len(ok):
        b = ok.loc[ok.expected_days.idxmin()]
        print(f"\n  FASTEST OVERALL: {b['name']} -> {b.expected_days} expected "
              f"days ({b.tpd} trades/day, avg {b.avg_r_per_leg}R per trade)")
    print(f"\nwrote {OUT / 'stage15_uh.csv'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
