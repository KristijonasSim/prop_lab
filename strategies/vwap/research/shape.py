"""Can the payoff be SHAPED to the profile the goal needs?

`core/target_profile.py` says the easiest qualifying profile for 60% pass inside
14 days is about **45% wins at 2:1**, average +0.37R per trade. The board's live
strategy is 36% wins at +0.012R.

`research/tails.py` established the direction: FOLLOW the band break, not fade it
- 79 of 100 paired cells, and 25 of 25 on ETH 4h and XAUUSD 1h. That study had no
stop and no target, so R was unbounded and meaningless as a risk unit.

This adds the two things that MAKE a payoff ratio - a stop and a target - and
sweeps them, asking one question: does any combination reach 45% wins at 2:1?

R is measured against the INITIAL STOP, so an R multiple means the same thing at
every setting, which is the only way these cells are comparable.

Run: .venv/bin/python strategies/vwap/research/shape.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from core.markets import COSTS, EXEC_MODE, load                     # noqa: E402
from core.nulls import null_seed, shuffle_market_paired             # noqa: E402
from core.run_hypothesis import YEARS, window                       # noqa: E402
from strategies.vwap.sweep import vwap_series                       # noqa: E402

ANCHOR = (0, 0)
THRESHOLDS = (1.0, 1.5, 2.0, 2.5)
STOPS = (1.0, 1.5, 2.0, 3.0)          # in sigma
#: TARGETS EXTENDED, and the first grid is why. Average R rose monotonically with
#: reward:risk right up to 4.0, the widest tested, and the tails study liked the
#: longest hold in ITS grid too. Both edges pointed the same way: this is a
#: trend-shaped payoff and the grid was cutting the winners off. `0` means no
#: target at all - ride to the horizon or the stop.
TARGETS = (2.0, 4.0, 6.0, 8.0, 0.0)
#: Likewise the horizon. 24 bars is 4 days on 4h; 96 is a fortnight.
HOLDS = (24, 48, 96)


def trades(df, thr, stop_sig, rr, cost_bps, max_hold=24) -> dict:
    """Follow the break, stop at `stop_sig` sigma, target at `rr` R, hard horizon.

    Stop wins every tie inside a bar, and a stop the bar gapped past fills at the
    open - both the pessimistic reading the kernels use.
    """
    o, h, l, c = (df.open.values, df.high.values, df.low.values, df.close.values)
    live = df.volume.values > 0
    vwap, vwstd, _ = vwap_series(df, *ANCHOR)
    with np.errstate(invalid="ignore", divide="ignore"):
        z = (c - vwap) / np.where(vwstd > vwap * 1e-6, vwstd, np.nan)
    n = len(c)
    cost = cost_bps / 2 / 1e4

    rs, xs, i = [], [], 1
    while i < n - 1:
        if not (np.isfinite(z[i]) and live[i] and live[i + 1]):
            i += 1
            continue
        side = 1 if z[i] >= thr else (-1 if z[i] <= -thr else 0)   # FOLLOW
        if side == 0:
            i += 1
            continue
        e = i + 1
        entry = o[e]
        risk = stop_sig * vwstd[i]
        if not np.isfinite(risk) or risk < entry * 3e-4:      # min risk floor
            i += 1
            continue
        stop = entry - side * risk
        target = entry + side * rr * risk if rr > 0 else None
        exit_px, exit_i = c[min(e + max_hold, n - 1)], min(e + max_hold, n - 1)
        j = e
        while j <= min(e + max_hold, n - 1):
            if live[j]:
                if side == 1 and l[j] <= stop:
                    exit_px, exit_i = (stop if o[j] > stop else o[j]), j
                    break
                if side == -1 and h[j] >= stop:
                    exit_px, exit_i = (stop if o[j] < stop else o[j]), j
                    break
                if target is not None:
                    if side == 1 and h[j] >= target:
                        exit_px, exit_i = target, j
                        break
                    if side == -1 and l[j] <= target:
                        exit_px, exit_i = target, j
                        break
            j += 1
        gross = (exit_px - entry) * side
        fees = (entry + exit_px) * cost
        rs.append((gross - fees) / risk)
        xs.append(exit_i)
        i = exit_i if exit_i > i else i + 1

    r = np.array(rs)
    if len(r) < 60:
        return {"n": len(r)}
    w, lo = r[r > 0].sum(), -r[r < 0].sum()
    return {"n": len(r), "win": round(float((r > 0).mean()) * 100, 1),
            "avg_r": round(float(r.mean()), 4),
            "pf": round(float(w / lo), 3) if lo > 0 else np.inf,
            "r": r, "exit_ts": df.index[np.array(xs)] if xs else None}


def main() -> int:
    markets = [("ETHUSDT", "4h"), ("XAUUSD", "1h"), ("XAUUSD", "4h"),
               ("BTCUSDT", "4h"), ("USDJPY", "1h")]
    lo, hi = window([m for m, _ in markets], ["1h", "4h"], YEARS)
    span = (hi - lo).days
    print(f"window {lo.date()} -> {hi.date()}   FOLLOW the band break, stop in "
          f"sigma, target in R, horizons {HOLDS} bars\n")
    print(f"TARGET PROFILE for 60% pass in 14 days: ~45% wins at 2:1, "
          f"avg R ~ +0.37\n")

    rows = []
    for sym, tf in markets:
        df = load(sym, tf)
        df = df[(df.index >= lo) & (df.index <= hi)]
        rt = COSTS[sym].round_trip(EXEC_MODE)
        nd = shuffle_market_paired(df, null_seed(sym, tf, "shape"))
        for thr in THRESHOLDS:
            for st in STOPS:
                for rr in TARGETS:
                    for mh in HOLDS:
                        a = trades(df, thr, st, rr, rt, max_hold=mh)
                        if a.get("n", 0) < 60:
                            continue
                        b = trades(nd, thr, st, rr, rt, max_hold=mh)
                        rows.append(dict(sym=sym, tf=tf, thr=thr, stop_sig=st,
                                         rr=rr, hold=mh, n=a["n"], win=a["win"],
                                         avg_r=a["avg_r"], pf=a["pf"],
                                         null_pf=b.get("pf"),
                                         tpd=round(a["n"] / span, 2),
                                         r_per_day=round(a["avg_r"] * a["n"] / span, 4)))
        print(f"  {sym} {tf} done")

    d = pd.DataFrame(rows)
    out = ROOT / "backtests" / "vwap" / "research_shape.csv"
    d.to_csv(out, index=False)

    print(f"\n{'=' * 104}\nCELLS THAT REACH THE TARGET PROFILE "
          f"(avg R >= 0.30, PF > 1.20, beats its null, n >= 100)\n{'=' * 104}")
    good = d[(d.avg_r >= 0.30) & (d.pf > 1.20) & (d.n >= 100)
             & (d.null_pf.notna()) & (d.pf > d.null_pf)]
    print(good.sort_values("avg_r", ascending=False).to_string(index=False)
          if len(good) else "  none")

    print(f"\n{'=' * 104}\nBEST 15 BY AVERAGE R, whatever else they do\n{'=' * 104}")
    print(d.sort_values("avg_r", ascending=False).head(12).to_string(index=False))
    print(f"\n{'=' * 104}\nBEST 12 BY R PER DAY - the number that sets days-to-pass"
          f"\n{'=' * 104}")
    print(d.sort_values("r_per_day", ascending=False).head(12).to_string(index=False))
    print("\n  for 14 days at 1% risk you need R/day >= 0.43")
    print(f"\nwrote {out.relative_to(ROOT)}   ({len(d)} cells)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
