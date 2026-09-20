"""THE GATES KRIS ACTUALLY CARES ABOUT. Set by him 2026-09-17, in his words.

This replaces the old pass/fail habit of killing anything whose noise band
overlapped the baseline's. That bar demanded an edge large enough to be
unmistakable, and it killed three effects that were real and beat their own
nulls - H-011, H-024 and H-045. Kris: *"loosen those rules a bit"*.

WHAT DID NOT CHANGE, and must not. The claim standard is untouched: a paired
null, costs at 1x/2x/3x, and the noise band still travel with every number that
gets quoted. These gates decide what is worth WORKING ON. They do not decide
what is true, and passing them is not evidence of an edge.

    PF          > 1.0, and higher is better. The only hard floor.
    days        <= 21 is the target. 21-50 is NOT dead - "if edge is good but
                projected days to complete is 30 we shouldnt just drop it maybe
                we can improve it". Over 50 is slow, and still not auto-dead.
    trades/day  >= 0.3. A hard floor: below it nothing resolves in time and the
                sample is too thin to learn from.
    drawdown    tracked, generously capped. "DD is kinda important but also
                loosen up on it a little bit".
    consistency best single trade <= 50% of total profit. His rule, and the
                reason is that a book carried by one trade has not been tested.

VERDICTS. Three, not two, and the middle one is the point:

    DEAD    PF <= 1, or under 0.3 trades a day, or one trade is more than half
            the profit. Nothing here is salvageable by more work.
    WORK    clears the floors, misses the 21-day target, or the drawdown is
            ugly. This is where an idea goes to be improved instead of binned.
    READY   clears everything. Still needs a null before it is believed.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

#: Kris's numbers, 2026-09-17.
PF_FLOOR = 1.0
DAYS_TARGET = 21.0
DAYS_WORKABLE = 50.0
TPD_FLOOR = 0.3
#: Loosened deliberately. The house spec's own max loss is 6%; a study that runs
#: hotter than this is not disqualified, it is flagged.
MAX_DD_R = 40.0
#: "1 trade wont exceed 50% of our profits"
BEST_TRADE_SHARE = 0.50


@dataclass
class Verdict:
    verdict: str          # DEAD | WORK | READY
    pf: float
    days: float | None
    tpd: float
    max_dd_r: float
    best_share: float | None
    reasons: list[str]

    def __str__(self) -> str:
        d = f"{self.days:.1f}" if self.days else "n/a"
        b = f"{self.best_share:.0%}" if self.best_share is not None else "n/a"
        return (f"{self.verdict:5}  PF {self.pf:.3f}  days {d:>6}  "
                f"tpd {self.tpd:.2f}  maxDD {self.max_dd_r:.1f}R  "
                f"best-trade {b}   {'; '.join(self.reasons) or 'clears everything'}")


def profit_factor(r: np.ndarray) -> float:
    w, l = r[r > 0].sum(), -r[r < 0].sum()
    if l <= 0:
        return float("inf") if w > 0 else float("nan")
    return float(w / l)


def best_trade_share(r: np.ndarray) -> float | None:
    """Largest single winner as a share of NET profit.

    Net, not gross: a book whose biggest trade is most of what it actually kept
    is the thing Kris is guarding against. If the book loses money the share is
    meaningless and None is returned rather than a misleading number.
    """
    net = r.sum()
    if net <= 0:
        return None
    wins = r[r > 0]
    return float(wins.max() / net) if len(wins) else None


def max_dd_r(r: np.ndarray) -> float:
    eq = np.cumsum(r)
    return float(np.max(np.maximum.accumulate(eq) - eq)) if len(eq) else 0.0


def judge(trades: pd.DataFrame, days: float | None = None,
          r_col: str = "r", ts_col: str = "exit_ts") -> Verdict:
    """Score a trade list against Kris's gates.

    `days` is expected days to pass an evaluation, from the risk ladder. Pass
    None when the study is a screen rather than a prop simulation - the day gate
    is then skipped instead of being faked.
    """
    r = np.asarray(trades[r_col].values, dtype=float)
    r = r[np.isfinite(r)]
    if not len(r):
        return Verdict("DEAD", float("nan"), days, 0.0, 0.0, None,
                       ["no trades"])

    pf = profit_factor(r)
    dd = max_dd_r(r)
    share = best_trade_share(r)

    ts = pd.DatetimeIndex(trades[ts_col])
    span = max(1.0, (ts.max() - ts.min()).total_seconds() / 86400)
    tpd = len(r) / span

    reasons: list[str] = []
    dead = False

    if not np.isfinite(pf) or pf <= PF_FLOOR:
        dead = True
        reasons.append(f"PF {pf:.3f} at or below {PF_FLOOR}")
    if tpd < TPD_FLOOR:
        dead = True
        reasons.append(f"{tpd:.2f} trades/day below the {TPD_FLOOR} floor")
    if share is not None and share > BEST_TRADE_SHARE:
        dead = True
        reasons.append(f"one trade is {share:.0%} of profit, over "
                       f"{BEST_TRADE_SHARE:.0%}")
    if dead:
        return Verdict("DEAD", pf, days, tpd, dd, share, reasons)

    if days is not None and days > DAYS_WORKABLE:
        reasons.append(f"{days:.0f} days, over {DAYS_WORKABLE:.0f} - slow, not dead")
    elif days is not None and days > DAYS_TARGET:
        reasons.append(f"{days:.0f} days, over the {DAYS_TARGET:.0f} target")
    if dd > MAX_DD_R:
        reasons.append(f"drawdown {dd:.0f}R over {MAX_DD_R:.0f}R")

    return Verdict("WORK" if reasons else "READY", pf, days, tpd, dd, share,
                   reasons)
