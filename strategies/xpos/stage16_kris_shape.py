"""H-017 stage 16 - Kris's configuration, run literally.

THE DISAGREEMENT, STATED PRECISELY.

Kris: 4 trades a day, $50 risk each on a $10k account, RR 1:2 or 1:3. 73
trades a day is nonsense, and his own N5 book ran 17 legs at 5-7 trades/day.

He is right about the shape, and his N5 figure matches this data exactly: the
top-1 legs here average 0.42 trades a day, so 17 of them is 7 a day. The stage
15 book only reached 73 because each leg carried a TOP-10 configuration book -
200 parallel sub-strategies, each trade 1/200 of the risk budget, roughly
$1.56 of risk, not $50.

The other AI's arithmetic is correct for the question it was asked and does not
apply here: it assumes 73 trades each risking a full $50, which is $3,650 of
risk per day on a $10k account - 36.5%, breaching the 4% daily loss limit
several times over before lunch. Its own conclusion says so: an edge producing
50% a week cannot exist, so an input is wrong. The wrong input is the sizing.

So this stage stops arguing and runs Kris's configuration exactly:

  * top-1 configurations only - one config per leg, the best in the fold
  * enough legs to land near 4 trades a day
  * **fixed $50 risk per trade on a $10k account** - 0.50%, NOT rescaled to
    fill the cap, NOT divided by the leg count
  * the project's real two-step evaluation, which is free to kill the account

Then the same book across a risk sweep, so the level that actually survives is
measured rather than assumed. If $50 a trade passes in eight days, the earlier
sizing rule was too conservative and Kris is right. If it kills most accounts,
that is the answer and the number says by how much.

Output: backtests/xpos/stage16_kris_shape.csv
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
ACCOUNT = 10_000.0
GATE_PF = 1.20


def pf(r):
    w, l = r[r > 0].sum(), -r[r < 0].sum()
    return float(w / l) if l > 0 else np.nan


def maxdd(r):
    e = np.cumsum(r)
    return float((e - np.maximum.accumulate(e)).min())


def gate(t):
    v, d = t.crowd_z.values, t.direction.values
    k = np.where(d > 0, v < 0, v > 0)
    return t[np.where(np.isnan(v), True, k)]


def main() -> int:
    t = pd.read_parquet(OUT / "stage14_trades.parquet")
    t["entry_ts"] = pd.to_datetime(t.entry_ts, utc=True)
    t["exit_ts"] = pd.to_datetime(t.exit_ts, utc=True)
    t = gate(t[t.topn == 1]).sort_values("exit_ts")
    mid = t.exit_ts.quantile(0.5)
    first, second = t[t.exit_ts <= mid], t[t.exit_ts > mid]

    # Rank legs on the first half only, exactly as before.
    rank = []
    for key, g in first.groupby(["symbol", "tf"]):
        r = g.r_2x.values
        dd = maxdd(r)
        span = max((g.exit_ts.max() - g.entry_ts.min()).days, 1)
        if dd >= 0 or r.sum() <= 0 or pf(r) < GATE_PF or len(g) < 60:
            continue
        rank.append(((r.sum() / span) / abs(dd), key))
    rank.sort(reverse=True)
    print(f"{len(rank)} top-1 legs clear PF {GATE_PF} on the first half\n")

    rows = []
    print("KRIS'S SHAPE: one config per leg, FIXED $50 risk per trade on $10k")
    print("(no rescaling, no dividing by leg count - each trade is a full "
          "0.50% position)\n")
    print(f"  {'legs':>5s} {'t/day':>6s} {'PF2x':>6s} {'avg R':>7s} "
          f"{'$/trade':>8s} {'$/day':>8s} {'curve DD':>9s} "
          f"{'pass':>6s} {'killed':>7s} {'median d':>9s} {'EXPECTED':>9s}")

    for n in (4, 6, 8, 10, 12, 17, 20):
        if n > len(rank):
            continue
        keys = [k for _, k in rank[:n]]
        s = second[[k in keys for k in zip(second.symbol, second.tf)]]
        s = s.sort_values("exit_ts")
        if len(s) < 100:
            continue
        r = s.r_2x.values                    # per-trade R at FULL size
        span = max((s.exit_ts.max() - s.entry_ts.min()).days, 1)
        tpd = len(r) / span
        risk = 0.005                         # $50 on $10k
        dd_pct = maxdd(r) * risk
        _rows, _pick = RL.from_trades(r * risk, s.exit_ts.values)
        at = next((x for x in _rows if abs(x["risk"] - risk) < 1e-9), None)
        if at is None:
            continue
        print(f"  {n:>5d} {tpd:>6.2f} {pf(r):>6.3f} {r.mean():>7.4f} "
              f"{r.mean()*risk*ACCOUNT:>7.2f}$ {r.mean()*risk*ACCOUNT*tpd:>7.2f}$ "
              f"{dd_pct*100:>8.1f}% {at['pass_rate']*100:>5.1f}% "
              f"{(at['fail_max']+at['fail_daily'])*100:>6.1f}% "
              f"{str(at['median_days']):>9s} {str(at['expected_days']):>9s}")
        rows.append({"legs": n, "tpd": round(tpd, 2), "pf_2x": round(pf(r), 3),
                     "avg_r": round(float(r.mean()), 4),
                     "usd_per_trade": round(float(r.mean()) * risk * ACCOUNT, 2),
                     "usd_per_day": round(float(r.mean()) * risk * ACCOUNT * tpd, 2),
                     "curve_dd_pct": round(dd_pct * 100, 2),
                     "risk_pct": 0.5, **at})

    # The risk sweep on the shape Kris named: 17 legs, ~7 trades a day.
    n = min(17, len(rank))
    keys = [k for _, k in rank[:n]]
    s = second[[k in keys for k in zip(second.symbol, second.tf)]].sort_values("exit_ts")
    r = s.r_2x.values
    span = max((s.exit_ts.max() - s.entry_ts.min()).days, 1)
    print(f"\n\nRISK SWEEP on {n} legs ({len(r)/span:.2f} trades/day, "
          f"PF@2x {pf(r):.3f}, avg {r.mean():.4f}R)\n")
    print(f"  {'risk':>7s} {'$/trade':>8s} {'$/day':>8s} {'curve DD':>9s} "
          f"{'pass':>6s} {'killed':>7s} {'median d':>9s} {'EXPECTED':>9s}")
    _rows, _ = RL.from_trades(r, s.exit_ts.values)
    for x in _rows:
        risk = x["risk"]
        dd_pct = maxdd(r) * risk
        print(f"  {risk*100:>6.2f}% {r.mean()*risk*ACCOUNT:>7.2f}$ "
              f"{r.mean()*risk*ACCOUNT*len(r)/span:>7.2f}$ {dd_pct*100:>8.1f}% "
              f"{x['pass_rate']*100:>5.1f}% "
              f"{(x['fail_max']+x['fail_daily'])*100:>6.1f}% "
              f"{str(x['median_days']):>9s} {str(x['expected_days']):>9s}")
        rows.append({"legs": n, "sweep": True, "risk_pct": round(risk * 100, 2),
                    "usd_per_trade": round(float(r.mean()) * risk * ACCOUNT, 2),
                    "curve_dd_pct": round(dd_pct * 100, 2), **x})

    pd.DataFrame(rows).to_csv(OUT / "stage16_kris_shape.csv", index=False)
    print(f"\nwrote {OUT / 'stage16_kris_shape.csv'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
