"""H-017 stage 22 - the last stone: H-017 with H-016, sized and chosen blind.

Stage 20/21 closed the non-crypto question: not one gold, silver, oil, index or
FX leg cleared PF 1.20 inside the fit window, so the VWAP kernel earns nothing
outside crypto and the wide book stays as it is.

That leaves one combination untested under a proper holdout. H-016 is a
different mechanism (multi-timescale trend) on a different asset class (gold
and silver) and stage 15 found H-016 + H-017 the fastest pairing there - but
that was measured with both books rescaled to fill the cap and with the mix
chosen on the window it was reported on.

Here the blend weight is chosen inside the fit window like everything else, and
the result is read on the test half. Weights are just the two books at w and
1-w, w on a coarse grid, because a fitted weight vector on two series is a
parameter per observation.

Output: backtests/xpos/stage22_uh_final.csv
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from core import riskladder as RL                                   # noqa: E402
from strategies.xpos.stage16_kris_shape import maxdd, pf            # noqa: E402
from core.prop_rules import TWO_STEP                                 # noqa: E402
from strategies.xpos.stage18_nested import gated, rank_legs         # noqa: E402

OUT = ROOT / "backtests" / "xpos"
BT = ROOT / "backtests"
NLEGS, RISKS = 14, (0.0025, 0.005, 0.0075, 0.01)
WEIGHTS = (0.0, 0.25, 0.5, 0.75, 1.0)      # share given to H-016

#: The H-016 overlap is only 635 days, so halving it leaves less than the
#: simulator's usual 400-day account horizon and every cell came back empty.
#: Capped at 180 days here: H-017's median is about 20, so an account still
#: open after six months is a failure by any reading and nothing real is lost.
MAX_DAYS = 180


def _account(d: np.ndarray) -> tuple[bool, int]:
    """One account opened on day 0. Same rules as riskladder, shorter horizon."""
    k = total = 0
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


def allin(dv: np.ndarray, risk: float) -> dict:
    starts = list(range(0, max(len(dv) - MAX_DAYS, 1), 5))
    if len(starts) < 10:
        return {}
    res = [_account(dv[s0:] * risk) for s0 in starts]
    ok = [d for p, d in res if p]
    bad = [d for p, d in res if not p]
    if not ok:
        return {"pass_rate": 0.0, "median_days": None, "allin_days": None}
    pr = len(ok) / len(res)
    med = float(np.median(ok))
    wasted = float(np.mean(bad)) if bad else 0.0
    return {"pass_rate": round(pr, 4), "median_days": med,
            "allin_days": round(med + (1 / pr - 1) * wasted, 1)}


def daily(s: pd.DataFrame, lo, hi, rcol="r_2x") -> np.ndarray:
    d = pd.Series(s[rcol].values,
                  index=pd.DatetimeIndex(s.exit_ts)).resample("1D").sum()
    idx = pd.date_range(pd.Timestamp(lo).normalize(),
                        pd.Timestamp(hi).normalize(), freq="1D", tz="UTC")
    return d.reindex(idx).fillna(0.0).values


def main() -> int:
    x = pd.read_parquet(OUT / "stage14_trades.parquet")
    x = x[x.topn == 1]
    x["entry_ts"] = pd.to_datetime(x.entry_ts, utc=True)
    x["exit_ts"] = pd.to_datetime(x.exit_ts, utc=True)
    x = gated(x).sort_values("exit_ts")

    rb = pd.read_parquet(BT / "ribbon" / "stage10_trades.parquet")
    rb["entry_ts"] = pd.to_datetime(rb.entry_ts, utc=True)
    rb["exit_ts"] = pd.to_datetime(rb.exit_ts, utc=True)
    rb = rb.rename(columns={"sym": "symbol"}).sort_values("exit_ts")
    nrb = rb.groupby(["symbol", "tf", "rule"]).ngroups

    lo = max(x.exit_ts.min(), rb.exit_ts.min())
    hi = min(x.exit_ts.max(), rb.exit_ts.max())
    mid = lo + (hi - lo) / 2
    print(f"common window {lo:%Y-%m-%d} -> {hi:%Y-%m-%d}")
    print(f"FIT   {lo:%Y-%m-%d} -> {mid:%Y-%m-%d}")
    print(f"TEST  {mid:%Y-%m-%d} -> {hi:%Y-%m-%d}\n")

    xf = x[(x.exit_ts >= lo) & (x.exit_ts <= mid)]
    keys = rank_legs(xf)[:NLEGS]
    if len(keys) < 4:
        print("too few H-017 legs clear in this shorter fit window")
        return 1
    print(f"H-017: {len(keys)} legs chosen in the fit window\n")

    def series(win_lo, win_hi):
        xs = x[[k in keys for k in zip(x.symbol, x.tf)]]
        xs = xs[(xs.exit_ts >= win_lo) & (xs.exit_ts <= win_hi)]
        rs = rb[(rb.exit_ts >= win_lo) & (rb.exit_ts <= win_hi)]
        if len(xs) < 100 or len(rs) < 100:
            return None, None, None
        dx = daily(xs, win_lo, win_hi) / len(keys)
        dr = daily(rs, win_lo, win_hi) / nrb
        # Each book is first normalised to the same drawdown so `w` is a share
        # of RISK, not an accident of how each one happens to be scaled.
        dx = dx * (4.0 / abs(maxdd(dx)))
        dr = dr * (4.0 / abs(maxdd(dr)))
        return dx, dr, (xs, rs)

    fx, fr, _ = series(lo, mid)
    if fx is None:
        print("not enough overlap in the fit window")
        return 1

    rows, best = [], None
    print("choosing blend weight and risk on the FIT window")
    print(f"  {'w(H-016)':>9s} " + " ".join(f"{r*100:>9.2f}%" for r in RISKS))
    for w in WEIGHTS:
        cells = []
        for risk in RISKS:
            a = allin((1 - w) * fx + w * fr, risk)
            cells.append(a.get("allin_days") if a else None)
            if a and a.get("allin_days"):
                rows.append({"stage": "fit", "w_h016": w,
                             "risk_pct": round(risk * 100, 2), **a})
                if best is None or a["allin_days"] < best["allin_days"]:
                    best = {"w": w, "risk": risk, **a}
        print(f"  {w:>9.2f} " + " ".join(
            f"{('%.1f' % c) if c else '-':>10s}" for c in cells))

    if best is None:
        print("nothing admissible")
        return 1
    print(f"\n  -> chose w(H-016) = {best['w']:.2f} at "
          f"{best['risk']*100:.2f}% risk  (fit all-in {best['allin_days']} d)\n")

    tx, tr_, parts = series(mid, hi)
    if tx is None:
        print("not enough overlap in the test window")
        return 1
    print("BLIND ON THE TEST WINDOW\n")
    print(f"  {'book':28s} {'pass':>6s} {'median d':>9s} {'all-in d':>9s}")
    for lab, w in (("H-017 alone", 0.0), ("H-016 alone", 1.0),
                   (f"blend w={best['w']:.2f} (chosen)", best["w"])):
        a = allin((1 - w) * tx + w * tr_, best["risk"])
        if not a or not a.get("allin_days"):
            print(f"  {lab:28s}  (no account passed)")
            continue
        print(f"  {lab:28s} {a['pass_rate']*100:>5.1f}% "
              f"{str(a['median_days']):>9s} {str(a['allin_days']):>9s}")
        rows.append({"stage": "test", "book": lab, "w_h016": w,
                     "risk_pct": round(best["risk"] * 100, 2), **a})

    print(f"\n  H-009 incumbent: 48.7 expected.  Target: 7-14 days.")
    pd.DataFrame(rows).to_csv(OUT / "stage22_uh_final.csv", index=False)
    print(f"\nwrote {OUT / 'stage22_uh_final.csv'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
