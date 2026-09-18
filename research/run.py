"""ENGINE 2's front door — one candidate, screened, pre-registered, charged.

THE SHAPE. A candidate arrives from `research/propose.py` as enum choices. This
file is the only thing that turns those choices into a signal, and it is the
only thing that writes a trial to the ledger. Both facts matter:

  * **The candidate never builds its own signal**, so the lag is applied here,
    once, from the feed's declared floor. A proposal cannot shift a series
    forward because it never touches the series.
  * **One entry point means the trial count is complete by construction**, which
    is the only way `core/searchcost.py`'s bar can be trusted. A ledger anything
    can bypass undercounts exactly the trials somebody wished had not happened.

THE ORDER IS THE POINT. `core/screen.py` already argues it: counting is free,
costing is free, the median is free, and a study is expensive. So a candidate
must survive events -> cost -> skew -> monotonicity -> its own shuffle before
anything heavier runs. Five of six hypotheses on 2026-09-17 died to checks that
each took under a minute, after the whole study had been built.

THE PRE-REGISTRATION IS WRITTEN BEFORE THE SCREEN, NOT AFTER. `docs/prereg/` gets
the file first, with the arm, the null, the cost bar and the kill criterion, and
the ledger row points at it. Measured on this project's own data: the same H-027
series scores a deflated Sharpe of 0.996 declared in advance and 0.000 found by
searching. Kris was right that it does not take a Monday - here it takes no
human time at all, because every field is derivable at proposal time.
"""
from __future__ import annotations

import json
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core import screen as SC                                   # noqa: E402
from core.ledger import log                                     # noqa: E402
from core.markets import COSTS, EXEC_MODE, load                 # noqa: E402
from research import vocab                                      # noqa: E402
from research.propose import Candidate                          # noqa: E402

PREREG = ROOT / "docs" / "prereg"

#: The market's own daily bars are the axis everything is aligned to. Feeds here
#: are daily, so the study is daily: one decision a day, held `hold` days.
BASE_TF = "1h"


@dataclass
class Result:
    candidate: Candidate
    screen: SC.Screen
    prereg_path: str
    round_trip_bps: float
    events: int
    verdict: str

    def as_row(self) -> dict:
        c = self.candidate
        return dict(
            hypothesis=f"FEED-{c.feed}",
            arm=c.name,
            market=c.market,
            tf="1d",
            n_trades=self.events,
            pf=float("nan"),
            sharpe=float("nan"),
            verdict=self.verdict,
            prereg=self.prereg_path,
            note="; ".join(self.screen.notes)[:200],
            candidate_key=c.key,
            origin=c.origin,
            effect_bps=round(self.screen.effect, 3),
            median_bps=round(self.screen.median_effect, 3),
            rho=round(self.screen.rho, 3),
            cost_bar_bps=round(self.round_trip_bps * SC.COST_MULT, 3),
            p_null=self.screen.p_null,
            direction=c.direction,
            lag=c.lag,
            hold=c.hold,
        )


# ---------------------------------------------------------------------------
# Building the signal — the ONLY place a feed is aligned to a market
# ---------------------------------------------------------------------------
def daily_frame(market: str) -> pd.DataFrame:
    """Market daily bars, closed only, indexed UTC midnight."""
    df = load(market, BASE_TF)
    d = pd.DataFrame({
        "open": df.open.resample("1D").first(),
        "close": df.close.resample("1D").last(),
        "volume": df.volume.resample("1D").sum(),
    }).dropna(subset=["close"])
    return d[d.volume > 0] if "volume" in d else d


def build_signal(c: Candidate) -> tuple[pd.Series, pd.Series, float]:
    """Return (signal, forward return in bps, round-trip bps).

    THE LAG IS APPLIED HERE AND NOWHERE ELSE. `shift(lag)` on the transformed
    series, after the transform's own rolling window has closed. A value dated
    d is therefore used to decide on d+lag, entered at d+lag's open and held
    `hold` days - the earliest a reader of that feed could have acted.

    THE FORWARD RETURN IS OPEN-TO-OPEN. Close-to-close would credit the decision
    bar's own move, which is the classic one-bar look-ahead and the reason
    `CLAUDE.md` carries three separate entries about it.
    """
    spec = vocab.FEEDS[c.feed]
    raw = spec.load()
    fn, needs_window = vocab.TRANSFORMS[c.transform]
    sig_raw = fn(raw, c.window if needs_window else 0)

    mkt = daily_frame(c.market)
    # normalise both to date-only UTC so a settlement stamp and a bar stamp meet
    sig_raw.index = pd.to_datetime(sig_raw.index, utc=True).normalize()
    mkt.index = pd.to_datetime(mkt.index, utc=True).normalize()

    sig = sig_raw[~sig_raw.index.duplicated(keep="last")]
    sig = sig.reindex(mkt.index).ffill(limit=5)
    sig = sig.shift(c.lag) * c.direction

    fwd = (mkt.open.shift(-c.hold) / mkt.open - 1.0) * 1e4
    both = pd.concat([sig.rename("s"), fwd.rename("f")], axis=1).dropna()

    rt = COSTS[c.market].round_trip(EXEC_MODE)
    return both.s, both.f, rt


# ---------------------------------------------------------------------------
# Pre-registration, written before the screen runs
# ---------------------------------------------------------------------------
def write_prereg(c: Candidate, round_trip: float, n_events: int) -> Path:
    PREREG.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    path = PREREG / f"FEED-{c.feed}-{c.market}-{stamp}.md"
    spec = vocab.FEEDS[c.feed]
    bar = round_trip * SC.COST_MULT
    path.write_text(f"""# {c.name} — feed screen

Written {datetime.now(timezone.utc).isoformat(timespec='seconds')} by
`research/run.py`, BEFORE the screen ran. Auto-generated: every field below is
derivable at proposal time, which is why this costs no human minutes.

## Mechanism

{c.mechanism}

Source: {spec.source}. {spec.desc}.

## The single arm

| | |
|---|---|
| feed | `{c.feed}` |
| transform | `{c.transform}` window {c.window or '-'} |
| lag | {c.lag} ({spec.lag_reason}) |
| market | {c.market} |
| hold | {c.hold} trading days, open to open |
| direction | {c.direction:+d} |

**This is ONE arm.** No grid, no sweep, no best-of. The trial count charged to
`backtests/ledger.csv` is 1, which is the whole reason this file exists —
`core/searchcost.sr_threshold` is exactly zero at N=1.

## Null

Block shuffle of the signal at block {SC.BLOCK}, {SC.NULL_SEEDS} seeds
(`core/screen.py`). Beating it means p < 0.05 on the bucket-response effect.

## Cost bar

{c.market} round trip {round_trip:.2f} bps at `{EXEC_MODE}` execution. The effect
must clear **{bar:.2f} bps** ({SC.COST_MULT}x) between the top and bottom bucket.

## Kill criterion — fixed before the number is known

Any one of: fewer than {SC.MIN_EVENTS} independent events; effect under
{bar:.2f} bps; mean and median disagreeing in sign; |rho| under {SC.MIN_RHO};
p >= 0.05 against the shuffle. **First failure ends it — no second look, no
tuning of the window, no other market rescuing it.**

## Expected events

{n_events} independent, from `core.screen.independent_events`.

## What would make this WRONG

The feed being real but unreadable at the stated lag, or the effect existing
only in the market whose cost bar is lowest. Both are checked by re-running the
identical arm on the rest of `core/universe.STANDARD`, never by widening this
one.
""")
    return path


# ---------------------------------------------------------------------------
# The run
# ---------------------------------------------------------------------------
def run_candidate(c: Candidate, dry: bool = False) -> Result:
    sig, fwd, rt = build_signal(c)
    events = SC.independent_events(sig, c.hold)
    prereg = write_prereg(c, rt, events) if not dry else Path("(dry run)")

    s = SC.screen(c.name, sig, fwd, rt, hold=c.hold, run_null=True)
    verdict = "PASS" if s.verdict == "WORK" else "FAIL"

    res = Result(candidate=c, screen=s, prereg_path=(
        str(prereg.relative_to(ROOT)) if not dry else ""),
        round_trip_bps=rt, events=s.events or events, verdict=verdict)
    if not dry:
        log(**res.as_row())
    return res


def run_batch(cands: list[Candidate], dry: bool = False) -> list[Result]:
    out = []
    print(SC.HEADER)
    for c in cands:
        try:
            r = run_candidate(c, dry=dry)
        except Exception as exc:                       # noqa: BLE001
            print(f"{c.name:22}ERROR  {type(exc).__name__}: {exc}")
            continue
        print(r.screen)
        out.append(r)
    if out:
        print()
        print(SC.price_the_search([r.screen for r in out]))
    return out


def main(argv: list[str] | None = None) -> int:
    import argparse
    from research.propose import propose
    ap = argparse.ArgumentParser(description="screen the next candidates")
    ap.add_argument("-n", type=int, default=5)
    ap.add_argument("--mode", choices=("library", "llm"), default="library")
    ap.add_argument("--dry-run", action="store_true",
                    help="no pre-registration, no ledger row")
    a = ap.parse_args(argv)
    run_batch(propose(a.n, a.mode), dry=a.dry_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
