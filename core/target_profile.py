"""What a strategy must LOOK LIKE to pass the firm inside the pace target.

The board scores strategies after they exist. This asks the question the other
way round, before anything is built: given the firm's rules, which combinations
of win rate, reward:risk and trades per day actually resolve in 5-14 days?

It exists because the project kept building mechanisms and then discovering they
were 10x too slow. Screening on this table costs seconds and kills a candidate
before a kernel is written.

THE FIRM (Thunderbolt, chosen 2026-09-08): 6% target, 3% daily drawdown, 6% max
drawdown, one step, unlimited time. `core/prop_rules.THUNDERBOLT`.

KRIS'S DESIGN CONSTRAINT (2026-09-08): 1-2 trades per day is healthy, 4 is the
ceiling. Holds under 24h preferred. Entries by limit order.

READ IT AS A FLOOR, NOT A TARGET. Every trade here is independent by
construction. Real losing streaks cluster in bad regimes, so a real strategy with
these statistics draws down more than this simulation and resolves slower.

Run: .venv/bin/python core/target_profile.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.riskladder import from_trades                       # noqa: E402

WIN_RATES = (0.35, 0.40, 0.45, 0.50, 0.55, 0.60)
REWARDS = (1.5, 2.0, 3.0)
TRADES_PER_DAY = (1, 2, 4)
YEARS = 3


def profile(win: float, rr: float, tpd: float, years: int = YEARS) -> dict:
    """One synthetic strategy: fixed win rate, fixed reward:risk, IID trades."""
    n = int(365 * years * tpd)
    rng = np.random.default_rng(int(win * 100) * 1000 + int(rr * 10) * 10 + int(tpd))
    r = np.where(rng.random(n) < win, rr, -1.0)
    ts = pd.date_range("2023-01-01", periods=n,
                       freq=f"{int(24 * 60 / tpd)}min", tz="UTC")
    _, pick = from_trades(r, ts)
    return {"win": win, "rr": rr, "tpd": tpd, "avg_r": round(float(r.mean()), 3),
            "risk": pick["risk"], "max_dd_pct": round(pick["max_dd"] * 100, 2),
            "pass_pct": round(pick["pass_rate"] * 100, 1),
            "days": pick["expected_days"]}


def table() -> pd.DataFrame:
    rows = [profile(w, rr, t)
            for w in WIN_RATES for rr in REWARDS for t in TRADES_PER_DAY]
    d = pd.DataFrame(rows)
    d["verdict"] = np.where(
        d.days.isna(), "never",
        np.where(d.days <= 14, "PASSES",
                 np.where(d.days <= 30, "close", "too slow")))
    return d


def main() -> int:
    d = table()
    print(__doc__.splitlines()[0])
    print()
    print(d.to_string(index=False))
    ok = d[(d.verdict == "PASSES") & (d.tpd <= 2)]
    print(f"\n{'=' * 78}")
    print("WHAT PASSES AT 1-2 TRADES/DAY - the shape a candidate has to have")
    print("=" * 78)
    if len(ok):
        print(ok[["win", "rr", "tpd", "avg_r", "risk", "max_dd_pct", "days"]]
              .to_string(index=False))
        print(f"\nthe easiest qualifying profile is "
              f"{ok.win.min() * 100:.0f}% wins at "
              f"{ok[ok.win == ok.win.min()].rr.min():.0f}:1")
    else:
        print("nothing at 1-2 trades/day clears 14 days")
    print("\nFor comparison, what the board actually has:")
    print("  H-002  avg R +0.035 at 4.41 trades/day")
    print("  H-016  avg R +0.065 at 0.53 trades/day")
    print("\nThe gap is not a tuning problem. It is a different KIND of trade:")
    print("  the board wins small and often; this needs asymmetry.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
