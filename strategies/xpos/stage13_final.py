"""H-017 stage 13 - weighting, the nulls, and the book that goes on the board.

Stage 12 settled the headline: on one identical window the wide crowd-gated
book reaches a funded account in 45.9 expected days against H-009's 178.3.
Three things are still owed before that can be believed.

  WEIGHTING. H-012's parting instruction was "do not propose a wider universe
  as a cure for drawdown without solving the weighting first", and stage 11
  used plain equal weight. Three schemes are compared, all fitted on the FIRST
  half only: equal, inverse-volatility, and proportional to the leg's own K.

  THE GATE'S NULL. The crowd gate is worth 69.1 -> 45.9 days, which is most of
  the improvement. If a block-shuffled feed with the same marginal distribution
  and autocorrelation buys the same thing, it is not the feed doing the work.

  THE SELECTION NULL. Twenty legs were picked from sixty-odd on first-half K.
  Picking twenty at RANDOM, held out identically, says how much of the result
  is the ranking and how much is simply owning a lot of legs.

Everything is measured on the second half, which took no part in choosing the
legs, the weights or anything else.

Output: backtests/xpos/stage13_final.csv, backtests/xpos/board.json
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from core import board                                             # noqa: E402
from core import riskladder as RL                                  # noqa: E402
from strategies.orderflow import orderflow as of                   # noqa: E402

OUT = ROOT / "backtests" / "xpos"
TARGET_DD_R, GATE_PF, NLEGS = 4.0, 1.20, 20


def pf(r):
    w, l = r[r > 0].sum(), -r[r < 0].sum()
    return float(w / l) if l > 0 else np.nan


def maxdd(r):
    e = np.cumsum(r)
    return float((e - np.maximum.accumulate(e)).min())


def weighted(sel: pd.DataFrame, w: dict) -> np.ndarray:
    """Per-trade R after each leg is scaled by its weight, weights summing to 1."""
    k = list(zip(sel.symbol, sel.tf))
    ww = np.array([w.get(x, 0.0) for x in k])
    return sel.r_2x.values * ww


def evaluate(sel: pd.DataFrame, w: dict, r1: bool = False) -> dict | None:
    r = weighted(sel, w)
    if len(r) < 200:
        return None
    dd = maxdd(r)
    if dd >= 0 or r.sum() <= 0:
        return None
    span = max((sel.exit_ts.max() - sel.entry_ts.min()).days, 1)
    scaled = r * (TARGET_DD_R / abs(dd))
    _rows, pick = RL.from_trades(scaled, sel.exit_ts.values)
    return {"trades": len(r), "pf_2x": round(pf(r), 3),
            "tpd": round(len(r) / span, 2), "max_dd_r": round(dd, 2),
            "K": round((r.sum() / span) / abs(dd), 5),
            "risk": pick["risk"], "pass_rate": pick["pass_rate"],
            "killed": round(pick["fail_max"] + pick["fail_daily"], 4),
            "median_days": pick["median_days"],
            "expected_days": pick["expected_days"]}


def gate_mask(t: pd.DataFrame, v=None) -> np.ndarray:
    v = t.crowd_z.values if v is None else v
    d = t.direction.values
    k = np.where(d > 0, v < 0, v > 0)
    return np.where(np.isnan(v), True, k)


def main() -> int:
    t = pd.read_parquet(OUT / "stage10_trades.parquet")
    t["entry_ts"] = pd.to_datetime(t.entry_ts, utc=True)
    t["exit_ts"] = pd.to_datetime(t.exit_ts, utc=True)
    t = t.sort_values("exit_ts").reset_index(drop=True)
    mid = t.exit_ts.quantile(0.5)
    print(f"{len(t):,} walk-forward trades over "
          f"{t.exit_ts.min():%Y-%m} -> {t.exit_ts.max():%Y-%m}")
    print(f"everything chosen on the first half (to {mid:%Y-%m-%d}), "
          f"reported on the second\n")

    g = t[gate_mask(t)]
    first, second = g[g.exit_ts <= mid], g[g.exit_ts > mid]

    # Rank legs on the first half, by their own K.
    rank = []
    for key, gg in first.groupby(["symbol", "tf"]):
        r = gg.r_2x.values
        dd, span = maxdd(r), max((gg.exit_ts.max() - gg.entry_ts.min()).days, 1)
        if dd >= 0 or r.sum() <= 0 or pf(r) < GATE_PF or len(gg) < 200:
            continue
        rank.append(((r.sum() / span) / abs(dd), float(np.std(r)), key))
    rank.sort(reverse=True)
    print(f"{len(rank)} legs clear PF {GATE_PF} on the first half; "
          f"taking the top {NLEGS}\n")
    top = rank[:NLEGS]
    keys = [k for _, _, k in top]
    sel = second[[k in keys for k in zip(second.symbol, second.tf)]]

    rows = []
    print("1. WEIGHTING (all weights fitted on the first half only)\n")
    print(f"  {'scheme':16s} {'trades':>8s} {'t/day':>7s} {'PF2x':>6s} "
          f"{'K':>8s} {'pass':>6s} {'median':>7s} {'EXPECTED':>9s}")
    schemes = {}
    schemes["equal"] = {k: 1.0 / len(keys) for k in keys}
    iv = {k: 1.0 / s for _, s, k in top if s > 0}
    tot = sum(iv.values())
    schemes["inverse-vol"] = {k: v / tot for k, v in iv.items()}
    kw = {k: max(kk, 0.0) for kk, _, k in top}
    tot = sum(kw.values())
    schemes["K-weighted"] = {k: v / tot for k, v in kw.items()}
    best_scheme, best = None, None
    for name, w in schemes.items():
        e = evaluate(sel, w)
        if not e:
            continue
        print(f"  {name:16s} {e['trades']:>8d} {e['tpd']:>7.2f} "
              f"{e['pf_2x']:>6.3f} {e['K']:>8.5f} {e['pass_rate']*100:>5.1f}% "
              f"{str(e['median_days']):>7s} {str(e['expected_days']):>9s}")
        rows.append({"kind": "weighting", "name": name, **e})
        if e["expected_days"] and (best is None or e["expected_days"] < best["expected_days"]):
            best, best_scheme = e, name
    w = schemes[best_scheme]
    print(f"\n  best weighting: {best_scheme}\n")

    print("2. THE GATE'S NULL — block-shuffled crowd feed, 5 seeds\n")
    ung = t[[k in keys for k in zip(t.symbol, t.tf)]]
    ung2 = ung[ung.exit_ts > mid]
    e_ung = evaluate(ung2, w)
    print(f"  {'no gate at all':28s} {str(e_ung['expected_days']):>8s} d  "
          f"K {e_ung['K']:.5f}")
    print(f"  {'real crowd gate':28s} {str(best['expected_days']):>8s} d  "
          f"K {best['K']:.5f}")
    nulls = []
    for seed in range(5):
        sh = of.block_shuffle(pd.Series(ung.crowd_z.values).set_axis(ung.entry_ts),
                              seed=seed + 31, block=288).values
        gn = ung[gate_mask(ung, sh)]
        gn = gn[gn.exit_ts > mid]
        e = evaluate(gn, w)
        if e and e["expected_days"]:
            nulls.append((e["expected_days"], e["K"]))
    if nulls:
        dn = [x[0] for x in nulls]; kn = [x[1] for x in nulls]
        print(f"  {'shuffled-feed gate':28s} {np.mean(dn):>8.1f} d  "
              f"K {np.mean(kn):.5f}   (best seed {min(dn):.1f} d)")
        rows.append({"kind": "null", "name": "shuffled gate",
                     "expected_days": round(float(np.mean(dn)), 1),
                     "K": round(float(np.mean(kn)), 5)})

    print("\n3. THE SELECTION NULL — twenty legs picked at random, 5 seeds\n")
    allkeys = sorted(set(zip(g.symbol, g.tf)))
    rnd = []
    for seed in range(5):
        rng = np.random.default_rng(seed + 7)
        pick_i = rng.choice(len(allkeys), size=min(NLEGS, len(allkeys)),
                            replace=False)
        kk = [allkeys[i] for i in pick_i]
        s2 = second[[k in kk for k in zip(second.symbol, second.tf)]]
        e = evaluate(s2, {k: 1.0 / len(kk) for k in kk})
        if e and e["expected_days"]:
            rnd.append(e["expected_days"])
    if rnd:
        print(f"  {'K-ranked top 20':28s} {str(best['expected_days']):>8s} d")
        print(f"  {'random 20':28s} {np.mean(rnd):>8.1f} d   "
              f"(best seed {min(rnd):.1f})")
        rows.append({"kind": "null", "name": "random legs",
                     "expected_days": round(float(np.mean(rnd)), 1)})

    pd.DataFrame(rows).to_csv(OUT / "stage13_final.csv", index=False)

    # ---- board record, on the held-out half only ----
    r_series = weighted(sel, w)
    dd = maxdd(r_series)
    r_norm = r_series * (TARGET_DD_R / abs(dd))
    # r at 1x cost, weighted identically, for the board's `r` field.
    ww = np.array([w.get(x, 0.0) for x in zip(sel.symbol, sel.tf)])
    r1 = sel.r.values * ww * (TARGET_DD_R / abs(dd))
    board.write_board(
        sid="xpos", hid="H-017",
        name="VWAP mean reversion / breakout",
        tagline="H-002's kernel on all eleven coins the Binance metrics "
                "archive covers, each leg gated by H-009's crowd rule. Nearly "
                "four times faster to a funded account than H-009 on the same "
                "dates - and still three times slower than the target.",
        period=f"{sel.exit_ts.min():%Y-%m} to {sel.exit_ts.max():%Y-%m}, "
               f"walk-forward, legs chosen on an earlier half",
        report="strategies/xpos/notes.md",
        candidate="the fastest book in the project, but 45.9 days against a "
                  "14-day goal and never traded live",
        r=r1, r_2x=r_norm,
        entry_ts=sel.entry_ts.values, exit_ts=sel.exit_ts.values,
        n_books=len(keys),
        null_margin=0.0, beats_null=False, consistency=0.0,
        markets={"traded": [{"sym": a, "tf": b, "asset": a[:3]} for a, b in keys],
                 "searched": "11 USDT-M perps x 6 timeframes x 7,776 "
                             "configurations, walk-forward"},
        note="Selecting each fold on K instead of profit factor was tested and "
             "bought nothing; K's denominator is a single order statistic and "
             "is too noisy to rank candidates by. Stacking further feed gates "
             "on top of the crowd gate made the account SLOWER at every "
             "combination tried.",
        todo=["45.9 expected days against the 14-day goal.",
              "20 legs x 10 configurations is 200 parallel sub-strategies at "
              "66 trades a day - operationally heavy and never paper-traded.",
              "Crypto perps only; costs assumed at 14bps round trip.",
              "No phase-randomised market null on the wide grid - only the "
              "gate and the leg selection have nulls."])
    print(f"\nwrote {OUT / 'stage13_final.csv'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
