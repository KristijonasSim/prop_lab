"""H-051 — the gold/silver ratio, and the one test that killed H-008.

THE FAMILY WARNING, STATED BEFORE THE RUN. Two things in `CLAIM.md`'s dead list
apply here and pretending otherwise would be dishonest:

  * *"Fading an extreme, as a family"* has failed twice, on a rolling high/low
    (H-005) and on the previous day/week high/low (H-011).
  * **H-008**, beta-residual reversion, stripped BTC's beta out of alts and faded
    the residual. Dead, and the decisive number was the **z-response being FLAT**:
    profit factor before costs ran 1.000 / 0.997 / 1.006 / 1.013 as entry moved
    from 1.5 to 3.0 sigma. *"The size of a deviation says nothing about what
    follows. There is no mechanism here to repair."*

WHAT IS GENUINELY DIFFERENT, and it is not nothing. H-008 stripped a STATISTICAL
beta out of assets with no reason to converge. Gold and silver are two
substitutable precious metals with a centuries-old relative price and a real
economic tether - industrial demand pulls them apart, monetary demand pulls them
back. And the cost bar is different in kind: the pair costs **1.06 + 4.70 =
5.76 bps** round trip against crypto's 14, and today's work showed cost is what
kills, not direction.

THE TEST, and it runs before anything else is built. Bucket the ratio's z-score
and measure the forward return of the SPREAD - long the cheap metal, short the
rich one, dollar-neutral. **If the response is flat in z, this is H-008 again and
it dies here in twenty minutes rather than after a day of building.** A real
mean-reversion effect must be MONOTONE in the size of the deviation: the further
from fair, the stronger the pull back.

Holds are long by design - today closed four scalping ideas and the shipped bot
survives a 21 bps spread only because it holds for weeks.

Run: .venv/bin/python strategies/ratio/zresponse.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from core.markets import COSTS, EXEC_MODE, load                    # noqa: E402

RT = COSTS["XAUUSD"].round_trip(EXEC_MODE) + COSTS["XAGUSD"].round_trip(EXEC_MODE)
LOOKBACKS = (60, 120, 250)          # trading days for the z-score
HOLDS = (5, 10, 20, 40, 60)         # trading days held
BUCKETS = 5


def spread_frame(lb: int) -> pd.DataFrame:
    au = load("XAUUSD", "1h").close.resample("1D").last().dropna()
    ag = load("XAGUSD", "1h").close.resample("1D").last().dropna()
    idx = au.index.intersection(ag.index)
    au, ag = au.reindex(idx), ag.reindex(idx)
    ratio = au / ag
    m = ratio.rolling(lb, min_periods=lb).mean()
    s = ratio.rolling(lb, min_periods=lb).std()
    z = ((ratio - m) / s).shift(1)              # decided on the CLOSED day
    return pd.DataFrame({"au": au, "ag": ag, "ratio": ratio, "z": z}).dropna()


def fwd_spread(d: pd.DataFrame, hold: int) -> pd.Series:
    """Dollar-neutral convergence trade, in bps.

    z > 0 means gold is rich against silver, so the convergence trade is short
    gold and long silver. The return is silver's move minus gold's, which is
    what a dollar-neutral pair actually earns.
    """
    rau = (d.au.shift(-hold) / d.au - 1.0) * 1e4
    rag = (d.ag.shift(-hold) / d.ag - 1.0) * 1e4
    return (rag - rau) * np.sign(d.z)


def main() -> int:
    print("H-051 — gold/silver ratio. THE Z-RESPONSE TEST FIRST.")
    print(f"Pair round trip = {RT:.2f} bps (gold {COSTS['XAUUSD'].round_trip(EXEC_MODE):.2f}"
          f" + silver {COSTS['XAGUSD'].round_trip(EXEC_MODE):.2f}).")
    print("H-008 died because this response was FLAT. A real effect is MONOTONE "
          "in |z|.\n")
    for lb in LOOKBACKS:
        d = spread_frame(lb)
        d = d[d.index >= "2023-08-01"]
        if len(d) < 300:
            print(f"lookback {lb}: only {len(d)} days, skipped")
            continue
        print(f"=== z-score lookback {lb}d   {len(d)} days   "
              f"{d.index[0].date()} -> {d.index[-1].date()} " + "=" * 12)
        print(f"{'hold':>6}{'|z| bucket mean fwd bps (low -> high)':>46}"
              f"{'rho':>8}{'top-bot':>9}  vs {RT:.1f}")
        print("-" * 78)
        az = d.z.abs()
        for hold in HOLDS:
            f = fwd_spread(d, hold)
            x = pd.DataFrame({"az": az, "f": f}).replace(
                [np.inf, -np.inf], np.nan).dropna()
            if len(x) < 200:
                continue
            try:
                x["b"] = pd.qcut(x.az, BUCKETS, labels=False, duplicates="drop")
            except ValueError:
                continue
            m = x.groupby("b").f.mean()
            if len(m) < 3:
                continue
            rho = float(pd.Series(m.values).corr(
                pd.Series(range(len(m))), method="spearman"))
            spread = float(m.iloc[-1] - m.iloc[0])
            cells = "  ".join(f"{v:7.1f}" for v in m.values)
            flag = ""
            if rho >= 0.8 and m.iloc[-1] > RT:
                flag = "  <- MONOTONE and pays"
            print(f"{hold:>5}d  {cells:>44}{rho:>8.2f}{spread:>9.1f}{flag}",
                  flush=True)
        print()
    print("READ IT LIKE H-008: if the buckets do not rise with |z|, the size of")
    print("the deviation says nothing and there is no mechanism to repair.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
