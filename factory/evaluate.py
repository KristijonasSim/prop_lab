"""STEP 7 — RUN THE EVALUATION. Two numbers, and the one the board never priced.

    docs/WORKFLOW.drawio   the picture
    docs/STEP7.md          the design and what each column means

THE SCORE, SETTLED WITH KRIS 2026-09-21: **pass % and days to pass.** Not
profit factor - it is highest for a tight stop that wins one time in twenty and
pays huge, which is the worst thing to carry into a 3% daily cap. Not trades
per day - more trades only ever looked faster because a blown account was free.

**A CANDIDATE HAS A CURVE, NOT A SCORE.** Risk per trade trades one number
against the other: bigger size is fewer days AND a lower pass rate. So this
prints the whole ladder and refuses to pick a rung. Re-simulating a fixed trade
series at another position size selects nothing and searches nothing - it is
arithmetic - which is why the ladder is the one thing in this repo not subject
to the noise floor.

**ACCOUNTS CONSUMED IS REPORTED HERE AND IT IS OWED.** `core/scorecard.py`
computes `expected_days = median_days / pass_rate`, which treats a blown
account as free. On 2026-09-17 that was the mechanism behind the fastest number
this project ever produced, and the number was withdrawn: on BTCUSDT every cell
LOST money and the wide configuration still "resolved" an evaluation in 14.5
days against 28.2, purely by trading more often. `1 / pass_rate` is how many
evaluations are bought per funded seat, at EUR 40-100 each, and it belongs
beside every days figure rather than in a footnote.

**EVERY NUMBER CARRIES ITS BAND** (`core/noiseband.py`), because the floor
measured on 2026-09-08 governs: six information-free gates scored between 13.3
and 26.5 expected days, so a days figure quoted without its band is not
evidence. Rungs whose bands overlap are not ordered.

**THE SPEC IS THE HOUSE SPEC** - 8% target, 3% daily, 6% max (`core.prop_rules.
HOUSE`), deliberately harsher than anything we would buy, so the numbers read
as a floor rather than a best case.

**WHAT THIS IS NOT.** It is a prop simulation on one cell's trade series, not a
walk-forward. Nothing here is fitted, because every idea the factory makes has
a fixed stop, target and hold - what protects the number is step 5's null and
step 6's holdout, both upstream of it.

    python -m factory.evaluate
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core import noiseband, prop_rules, riskladder                   # noqa: E402
from factory import build, cells, check                              # noqa: E402
from factory.spec import Strategy                                    # noqa: E402

#: Kris's pace target, 2026-09-07. Anything past this is not a plan.
PACE_TARGET_DAYS = (5.0, 14.0)
#: `core.scorecard` flags past this. Kept so step 7 says the same thing.
TOO_SLOW_DAYS = 50.0
#: Resamples behind each band. 200 is `core.noiseband.RESAMPLES`; the default
#: here is lower because step 7 prints a whole ladder and the bands are read
#: for overlap, not quoted to a decimal.
BAND_RESAMPLES = 100


@dataclass
class Rung:
    """One risk per trade, and both numbers that matter at it."""
    risk: float
    pass_pct: float
    median_days: float | None
    expected_days: float | None
    accounts: float | None          # 1 / pass_rate - evaluations per funded seat
    max_dd: float
    fail_daily: float
    fail_max: float
    band: dict | None = None

    def __str__(self) -> str:
        b = self.band or {}
        span = (f"{b['days_lo']:.0f}-{b['days_hi']:.0f}"
                if b.get("days_lo") is not None else "-")
        ed = f"{self.expected_days:.1f}" if self.expected_days else "-"
        md = f"{self.median_days:.0f}" if self.median_days else "-"
        ac = f"{self.accounts:.1f}" if self.accounts else "-"
        return (f"{self.risk * 100:>7.2f}%{self.pass_pct:>9.1f}{md:>8}"
                f"{ed:>10}{span:>10}{ac:>11}{self.max_dd * 100:>9.1f}"
                f"{self.fail_daily * 100:>8.1f}{self.fail_max * 100:>7.1f}")


@dataclass
class Evaluation:
    """Step 7 on one candidate: the whole risk curve, plus what it means."""
    idea: str
    market: str
    tf: str
    n_trades: int = 0
    trades_per_day: float = 0.0
    span: str = ""
    rungs: list[Rung] = field(default_factory=list)
    note: str = ""

    @property
    def cell(self) -> str:
        return f"{self.market} {self.tf}"

    def fastest(self) -> Rung | None:
        """The rung with the fewest expected days, among those allowed.

        `core.riskladder.pick` is the one that decides, and it applies the
        project's own constraints - both breach rates under 5%, peak drawdown
        inside the cap at the risk used. This is only for the headline line.
        """
        ok = [r for r in self.rungs if r.expected_days]
        return min(ok, key=lambda r: r.expected_days) if ok else None

    def table(self) -> str:
        head = (f"{'risk':>8}{'pass %':>9}{'median':>8}{'expected':>10}"
                f"{'band':>10}{'accounts':>11}{'maxDD %':>9}{'dayDD':>8}"
                f"{'maxDD':>7}")
        lines = [head, "-" * len(head)] + [str(r) for r in self.rungs]
        return "\n".join(lines)


def _rung(row: dict, daily: pd.Series, resamples: int) -> Rung:
    rate = row["pass_rate"]
    band = (noiseband.band(daily, row["risk"], resamples=resamples)
            if rate else None)
    return Rung(
        risk=row["risk"],
        pass_pct=round(rate * 100, 1),
        median_days=row["median_days"],
        expected_days=row["expected_days"],
        accounts=(1.0 / rate) if rate else None,
        max_dd=row["max_dd"],
        fail_daily=row["fail_daily"],
        fail_max=row["fail_max"],
        band=band,
    )


def evaluate(strategy: Strategy, market: str, tf: str, *,
             frame: pd.DataFrame | None = None,
             resamples: int = BAND_RESAMPLES) -> Evaluation:
    """The prop simulation on one candidate's trades, at every risk level.

    `frame` defaults to the step-3 window. Pass the five-year frame to score a
    candidate on everything it has been tested on - which is what `_main` does
    once step 6 has cleared it, because a pass rate is a count of simulated
    accounts and more history is more accounts.
    """
    df = cells.load(market, tf) if frame is None else frame
    ev = Evaluation(idea=strategy.label(), market=market, tf=tf)
    if not len(df):
        ev.note = "no data"
        return ev
    ev.span = f"{df.index[0]:%Y-%m-%d}..{df.index[-1]:%Y-%m-%d}"

    trades = build.run(strategy, df.reset_index(drop=True),
                       cost_bps=cells.cost_bps(market))
    ev.n_trades = len(trades)
    days = check.trading_days(df)
    ev.trades_per_day = ev.n_trades / days if days else 0.0
    if not trades:
        ev.note = "no trades"
        return ev

    r = np.array([t.r for t in trades], dtype=float)
    exit_ts = df.index[[t.exit_bar for t in trades]]
    daily = pd.Series(r, index=pd.DatetimeIndex(exit_ts)).resample("1D").sum()
    ev.rungs = [_rung(row, daily, resamples) for row in riskladder.ladder(daily, r)]

    f = ev.fastest()
    if f is None:
        ev.note = "funds no account at any risk level"
    elif f.expected_days > TOO_SLOW_DAYS:
        ev.note = f"TOO SLOW - {f.expected_days:.0f} days against a {TOO_SLOW_DAYS:.0f} flag"
    elif PACE_TARGET_DAYS[0] <= f.expected_days <= PACE_TARGET_DAYS[1]:
        ev.note = "inside the 5-14 day pace target at its fastest rung"
    else:
        ev.note = (f"outside the 5-14 day pace target "
                   f"({f.expected_days:.1f} at its fastest rung)")
    return ev


def five_year_frame(market: str, tf: str) -> pd.DataFrame:
    """Holdout and step-3 window stitched, for scoring everything at once."""
    parts = [p for p in (cells.holdout(market, tf), cells.load(market, tf)) if len(p)]
    if not parts:
        return pd.DataFrame()
    df = pd.concat(parts)
    return df[~df.index.duplicated(keep="last")].sort_index()


def _main(argv=None) -> int:
    """Step 7 on the survivors of steps 3+4, scored over all the history they
    have been tested on."""
    import argparse

    from factory import check as _check, queue

    ap = argparse.ArgumentParser(description=_main.__doc__)
    ap.add_argument("-n", "--count", type=int, default=20)
    ap.add_argument("--market", action="append")
    ap.add_argument("--tf", action="append")
    ap.add_argument("--three-year", action="store_true",
                    help="score on the step-3 window only, not the five years")
    ap.add_argument("--resamples", type=int, default=BAND_RESAMPLES)
    a = ap.parse_args(argv)

    ideas = [s for s in (queue.take() for _ in range(a.count)) if s is not None]
    cell_list = cells.all_cells(a.market, tuple(a.tf) if a.tf else None)
    found = []
    for s in ideas:
        for c in _check.check_all(s, cell_list):
            if c.verdict == "PASS":
                found.append((s, c.market, c.tf))
    if not found:
        print(f"{len(ideas)} ideas, none reached step 7")
        return 0

    print(f"HOUSE spec: {prop_rules.HOUSE.profit_target:.0%} target, "
          f"{prop_rules.HOUSE.daily_loss:.0%} daily, "
          f"{prop_rules.HOUSE.max_loss:.0%} max\n")
    for s, m, tf in found:
        frame = None if a.three_year else five_year_frame(m, tf)
        ev = evaluate(s, m, tf, frame=frame, resamples=a.resamples)
        print(f"{ev.idea}   [{ev.cell}]   {ev.span}")
        print(f"{ev.n_trades} trades, {ev.trades_per_day:.2f}/day")
        print(ev.table())
        print(f"-> {ev.note}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
