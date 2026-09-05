"""H-019 + H-018 - do the two survivors compose?

Stage 24's common-flow gate and stage 23's volatility-managed sizing both beat
their own nulls on the blind half. They act on different things - one decides
WHICH trades the book takes, the other decides HOW BIG it is on a given day -
so there is no mechanical reason they should collide. There is also no reason
they should add: if the flow gate already removes the trades that cluster in
the high-volatility stretches, the vol overlay has nothing left to cut.

Stage 15's lesson applies and is the reason this is run at all rather than
assumed: combining two things that each work is not a result until it is
measured, and stage 22 found H-016 earning weight 0.00 beside H-017.

Both overlays are re-chosen jointly INSIDE the fit window - not carried over
from the runs that chose them alone, which would import a choice made with the
other overlay absent - and the single winning configuration is run blind.

Output: backtests/xpos/stage26_combined.csv
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
from strategies.xpos.stage18_nested import (allin, build, gated,    # noqa: E402
                                            rank_legs)
from strategies.xpos.stage23_volmanaged import multiplier           # noqa: E402
from strategies.xpos.stage24_commonflow import (apply_gate, attach, # noqa: E402
                                                common_factor)

OUT = ROOT / "backtests" / "xpos"
LEG_COUNTS = (4, 6, 8, 10, 12, 14, 17, 20, 25)
RISKS = (0.0025, 0.005, 0.0075, 0.01, 0.015)
WINS, CLIP_HI, CLIP_LO = (10, 20, 30, 60), (1.5, 2.0, 3.0), (0.25, 0.5)
QS = (0.0, 0.2, 0.3, 0.4, 0.5)


def main() -> int:
    t = pd.read_parquet(OUT / "stage14_trades.parquet")
    t["entry_ts"] = pd.to_datetime(t.entry_ts, utc=True)
    t["exit_ts"] = pd.to_datetime(t.exit_ts, utc=True)
    t = t[t.topn == 1].sort_values("exit_ts")
    t = attach(t, common_factor(), "cflow")

    g0 = gated(t)
    mid = g0.exit_ts.quantile(0.5)
    f_lo, f_hi, s_lo, s_hi = g0.exit_ts.min(), mid, mid, g0.exit_ts.max()
    print(f"\nFIT   {f_lo:%Y-%m-%d} -> {f_hi:%Y-%m-%d}")
    print(f"TEST  {s_lo:%Y-%m-%d} -> {s_hi:%Y-%m-%d}\n")

    order = rank_legs(g0[g0.exit_ts <= mid])
    best = None
    for n in LEG_COUNTS:
        if n > len(order):
            continue
        _, dv = build(g0[g0.exit_ts <= mid], order[:n], f_lo, f_hi)
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

    thr_grid = [float(np.nanquantile(np.abs(t.cflow.values), q)) if q else 0.0
                for q in QS]

    print("choosing BOTH overlays jointly on the FIT window only")
    pick = None
    for mode in ("stack", "replace"):
        src = g0 if mode == "stack" else t
        for sign in (+1, -1):
            for q, thr in zip(QS, thr_grid):
                gg = apply_gate(src, "cflow", thr, sign)
                _, dv = build(gg[gg.exit_ts <= mid], keys, f_lo, f_hi)
                if dv is None:
                    continue
                for win in WINS:
                    for lo in CLIP_LO:
                        for hi in CLIP_HI:
                            m, target = multiplier(dv, win, lo, hi)
                            a = allin(dv * m, risk)
                            if a and a.get("allin_days") and (
                                    pick is None
                                    or a["allin_days"] < pick["allin_days"]):
                                pick = {"mode": mode, "sign": sign, "thr": thr,
                                        "q": q, "win": win, "lo": lo, "hi": hi,
                                        "target": target, **a}
    if pick is None:
        print("nothing admissible in the fit window")
        return 1
    lab = "momentum" if pick["sign"] > 0 else "contrarian"
    print(f"  -> gate: {pick['mode']}, {lab}, |z| >= {pick['thr']:.3f}")
    print(f"  -> sizing: win {pick['win']}d, clip [{pick['lo']}, {pick['hi']}], "
          f"target {pick['target']:.4f}")
    print(f"     (fit all-in {pick['allin_days']}d)\n")

    span = max((s_hi - s_lo).days, 1)
    rows = []

    def row(gg, label, mult=None):
        s, dv = build(gg[gg.exit_ts > mid], keys, s_lo, s_hi)
        if dv is None:
            print(f"  {label:32s} {'too few trades':>38s}")
            return None
        d = dv if mult is None else dv * mult(dv)
        a = allin(d, risk)
        if not a or not a.get("allin_days"):
            print(f"  {label:32s} {'no admissible account':>38s}")
            return None
        r = s.r_2x.values
        print(f"  {label:32s} {len(s):>6d} {len(s)/span:>6.2f} "
              f"{pf(r):>6.3f} {a['pass_rate']*100:>6.1f}% "
              f"{str(a['median_days']):>9s} {a['allin_days']:>9.1f}")
        rows.append({"window": "test", "book": label, "trades": len(s),
                     "tpd": round(len(s)/span, 2), "pf_2x": round(pf(r), 3),
                     "avg_r": round(float(r.mean()), 4),
                     "max_dd_r": round(maxdd(r), 2), **a})
        return a

    mm = lambda dv: multiplier(dv, pick["win"], pick["lo"], pick["hi"],
                               target=pick["target"])[0]
    src = g0 if pick["mode"] == "stack" else t
    gated_src = apply_gate(src, "cflow", pick["thr"], pick["sign"])

    print("APPLIED BLIND TO THE TEST WINDOW")
    print(f"  {'book':32s} {'trades':>6s} {'t/day':>6s} {'PF2x':>6s} "
          f"{'pass':>7s} {'median d':>9s} {'all-in d':>9s}")
    base = row(g0, "H-017 baseline")
    row(g0, "  + vol sizing only", mult=mm)
    row(gated_src, "  + flow gate only")
    both = row(gated_src, "H-019+018 both", mult=mm)

    nd = []
    for seed in range(8):
        sh = of.block_shuffle(pd.Series(src.cflow.values).set_axis(src.entry_ts),
                              seed=seed + 31, block=288).values
        s2 = src.copy()
        s2["cflow_sh"] = sh
        gg = apply_gate(s2, "cflow_sh", pick["thr"], pick["sign"])
        _, dv2 = build(gg[gg.exit_ts > mid], keys, s_lo, s_hi)
        if dv2 is None:
            continue
        a2 = allin(dv2 * mm(dv2), risk)
        if a2 and a2.get("allin_days"):
            nd.append(a2["allin_days"])
    if nd:
        print(f"  {'NULL shuffled factor, same sizing':32s} "
              f"{'-':>6s} {'-':>6s} {'-':>6s} {'-':>7s} {'-':>9s} "
              f"{np.mean(nd):>9.1f}   (best seed {min(nd):.1f})")
        rows.append({"window": "test", "book": "null shuffled factor",
                     "allin_days": round(float(np.mean(nd)), 1),
                     "best_seed": round(float(min(nd)), 1)})

    if base and both:
        d = (base["allin_days"] - both["allin_days"]) / base["allin_days"]
        print(f"\n  VERDICT: {base['allin_days']:.1f} -> "
              f"{both['allin_days']:.1f} all-in days ({d*100:+.1f}%)")

    pd.DataFrame(rows).to_csv(OUT / "stage26_combined.csv", index=False)
    print(f"\nwrote {OUT / 'stage26_combined.csv'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
