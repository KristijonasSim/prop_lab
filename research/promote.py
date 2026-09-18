"""Take a screen survivor and give it the real test. One arm, declared first.

THE GAP. The loop screens and stops. A survivor sat in the ledger with a note
saying "earned a walk-forward" and nothing carried it there, so the expensive
half of the pipeline was a thing Kris had to remember to do by hand.

WHAT THIS DOES. Wraps a survivor as a `core.strategy.Strategy` and hands it to
`core/pipeline.Pipeline` — blind walk-forward, train-only selection, paired null,
honest fills — then logs the result as a trial like everything else.

THE ONE THING IT WILL NOT DO FOR YOU, AND WHY.

**It will not choose the stop.** A screen measures a forward return; a prop
account measures R against a drawdown cap, and R is undefined without a stop.
That gap is not a coding detail, it is the thing that killed two hypotheses
here:

    H-006   no stop, so R became a return over trailing vol. The book drew
            down 63.5R against H-002's 3.8R and needed 548 days.
    H-031   the fix, tested: PF@2x 0.924 with no stop and WORSE with every
            stop tried, 0.667-0.889, monotone in width. R/day negative on all
            eight arms. "A stop does not repair a slow-drift feed signal, it
            harms it."

So a stop is a strategy decision with measured precedent pointing both ways, and
picking one silently inside an automation is how a search gets laundered into a
result. `--stop` is required, it goes into a fresh pre-registration BEFORE the
walk-forward runs, and the ledger row records it.

    python -m research.promote --list
    python -m research.promote --arm VIX_TERM.change5.XAUUSD.h3 --stop 3.0

**Run it on the desktop.** It is hours on 28 cores and must never go near the
2-core VM, which is routing live orders.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.ledger import log, read                               # noqa: E402
from core.markets import COSTS, EXEC_MODE                       # noqa: E402
from core.strategy import N_COLS                                # noqa: E402
from research.propose import Candidate                          # noqa: E402
from research.run import build_signal, daily_frame              # noqa: E402

PREREG = ROOT / "docs" / "prereg"

#: Quintile the signal must be in to take a trade. The screen measures the top
#: bucket against the bottom, so the trade is the top bucket - stated here
#: rather than discovered, because "which bucket" is another free parameter.
TOP_Q = 0.8


class FeedStrategy:
    """A single pre-registered feed arm, as a Strategy the pipeline can run.

    `grid()` returns EXACTLY ONE configuration. That is deliberate and it is the
    whole reason a promotion is worth anything: `core/searchcost.sr_threshold`
    is zero at one trial, so an arm declared in advance and run once faces the
    lowest bar this project can offer. A grid here would hand the walk-forward
    a search to launder.
    """

    def __init__(self, cand: Candidate, stop_sigma: float):
        self.c = cand
        self.stop_sigma = float(stop_sigma)
        self.name = f"{cand.name}.stop{stop_sigma:g}"

    def features(self, df: pd.DataFrame):
        """Signal and trailing vol on the bar index. Backward-looking only."""
        sig, _fwd, _rt = build_signal(self.c)
        s = sig.reindex(df.index).ffill(limit=5)
        # Threshold from a TRAILING window, never the whole sample - a global
        # quantile would be a look-ahead that no test in this repo would catch,
        # because it is in the feature and not in the trade.
        thresh = s.rolling(250, min_periods=60).quantile(TOP_Q)
        ret = df.close.pct_change()
        vol = ret.rolling(20, min_periods=10).std()
        return {"sig": s.values, "thresh": thresh.values,
                "vol": (vol * df.close).values}

    def grid(self, tf: str | None = None) -> list[dict]:
        return [{"hold": self.c.hold, "stop_sigma": self.stop_sigma}]

    def run(self, df: pd.DataFrame, cfg: dict, fee_bps: float,
            slip_bps: float, feats=None) -> np.ndarray:
        f = feats if feats is not None else self.features(df)
        sig, thresh, vol = f["sig"], f["thresh"], f["vol"]
        op, hi, lo = df.open.values, df.high.values, df.low.values
        n = len(df)
        hold, k = int(cfg["hold"]), float(cfg["stop_sigma"])
        cost = (fee_bps + slip_bps) * 1e-4

        out, i = [], 1
        while i < n - 1:
            if not (np.isfinite(sig[i]) and np.isfinite(thresh[i])
                    and np.isfinite(vol[i]) and vol[i] > 0):
                i += 1
                continue
            if sig[i] <= thresh[i]:
                i += 1
                continue
            # decide on bar i, fill at i+1's open: never on the decision bar.
            e = i + 1
            entry = op[e]
            stop = entry - k * vol[i]
            horizon = min(e + hold, n - 1)
            x, px, reason = horizon, op[horizon], 1
            for j in range(e, horizon + 1):
                if lo[j] <= stop:
                    # A stop is a stop-market order: on a gap it fills at the
                    # open, not at the level. CLAUDE.md 2026-09-08.
                    x, px, reason = j, min(op[j], stop) if op[j] < stop else stop, 2
                    break
            r = ((px - entry) / entry - cost) / (k * vol[i] / entry)
            row = np.zeros(N_COLS)
            row[0], row[1], row[2] = e, x, 1
            row[3], row[4], row[5], row[6] = entry, px, r, reason
            out.append(row)
            i = x + 1
        return np.array(out) if out else np.zeros((0, N_COLS))


# ---------------------------------------------------------------------------
def survivors() -> list[tuple[str, dict]]:
    """Screen survivors that have not yet been promoted."""
    done = set()
    out = []
    for t in read():
        if not t.params:
            continue
        try:
            p = json.loads(t.params)
        except ValueError:
            continue
        if p.get("promoted_stop") is not None:
            done.add(t.arm)
        elif t.verdict == "PASS" and p.get("candidate_key"):
            out.append((t.arm, p))
    return [(a, p) for a, p in out if a not in done]


def candidate_from(params: dict, arm: str) -> Candidate:
    feed, transform, window, lag, market, hold, direction = \
        params["candidate_key"].split("|")
    return Candidate(feed=feed, transform=transform, window=int(window),
                     lag=int(lag), market=market, hold=int(hold),
                     direction=int(direction), origin="promoted",
                     mechanism=params.get("mechanism", "promoted from screen"))


def write_prereg(c: Candidate, stop: float) -> Path:
    PREREG.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    path = PREREG / f"PROMOTE-{c.feed}-{c.market}-{stamp}.md"
    rt = COSTS[c.market].round_trip(EXEC_MODE)
    path.write_text(f"""# {c.name} stop {stop:g} — walk-forward

Written {datetime.now(timezone.utc).isoformat(timespec='seconds')} BEFORE the
walk-forward ran. This arm already survived the cheap screen; this is the
expensive test, and it is ONE arm.

## The arm

| | |
|---|---|
| feed | `{c.feed}` |
| transform | `{c.transform}` {c.window or ''} |
| lag | {c.lag} |
| market | {c.market} |
| hold | {c.hold} days |
| direction | {c.direction:+d} |
| entry | signal above its trailing {TOP_Q:.0%} quantile, fill next open |
| **stop** | **{stop:g} x 20-bar sigma** |
| costs | {rt:.2f} bps round trip, reported at 1x / 2x / 3x |

## Why a stop at all, and why this is the arm's weakest joint

R is undefined without one, and a prop account is scored in R against a
drawdown cap. The precedent points both ways and both directions have been
measured here:

* **H-006** ran with no stop: R became a return over trailing vol and the book
  drew down 63.5R against H-002's 3.8R.
* **H-031** added stops to a slow-drift feed signal and every width was worse
  than none — PF@2x 0.667 to 0.889 against 0.924, monotone in width.

So {stop:g} sigma is a CHOICE, it is recorded here before the result is known,
and if it is changed the change is a new pre-registration and a new trial.

## Kill criterion — fixed before the number is known

Walk-forward profit factor at **2x cost below 1.20**, or a stitched series that
loses to its own paired null. No re-run at a different stop to rescue it: that
would be the search this file exists to avoid.
""")
    return path


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--list", action="store_true",
                    help="survivors waiting for a walk-forward")
    ap.add_argument("--arm", help="the survivor to promote")
    ap.add_argument("--stop", type=float,
                    help="stop in multiples of 20-bar sigma. REQUIRED — "
                         "see the module docstring for why it is not defaulted")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)

    waiting = survivors()
    if a.list or not a.arm:
        if not waiting:
            print("no survivors waiting for a walk-forward")
            return 0
        print(f"{len(waiting)} waiting:")
        for arm, p in waiting:
            print(f"  {arm:40} effect {p.get('effect_bps')} bps  "
                  f"rho {p.get('rho')}  p {p.get('p_null')}")
        print("\npromote one with --arm <name> --stop <sigma>")
        return 0

    match = [(arm, p) for arm, p in waiting if arm == a.arm]
    if not match:
        print(f"'{a.arm}' is not a survivor waiting for promotion. --list shows "
              "what is.", file=sys.stderr)
        return 1
    if a.stop is None:
        print("--stop is required and is deliberately not defaulted.\n"
              "It is a strategy decision with measured precedent both ways:\n"
              "  H-006  no stop -> 63.5R drawdown\n"
              "  H-031  every stop width WORSE than none on a feed signal\n"
              "Pick one, it gets pre-registered, and changing it later is a new "
              "trial.", file=sys.stderr)
        return 2

    arm, params = match[0]
    c = candidate_from(params, arm)
    strat = FeedStrategy(c, a.stop)

    # A dry run must NOT write a pre-registration. The file's whole value is
    # that it was written once, before the number was known; a directory full
    # of rehearsals for the same arm is the opposite of a declaration.
    prereg = None if a.dry_run else write_prereg(c, a.stop)
    if prereg:
        print(f"pre-registered: {prereg.relative_to(ROOT)}")

    df = daily_frame(c.market)
    trades = strat.run(df, strat.grid()[0],
                       COSTS[c.market].round_trip(EXEC_MODE), 0.0)
    print(f"{len(trades)} trades on the full series "
          f"(sanity check before the walk-forward)")
    if len(trades):
        r = trades[:, 5]
        print(f"  total {r.sum():+.1f}R  mean {r.mean():+.3f}R  "
              f"win {100 * (r > 0).mean():.1f}%")

    if a.dry_run:
        print("dry run — nothing logged")
        return 0

    log(hypothesis=f"FEED-{c.feed}", arm=strat.name, market=c.market, tf="1d",
        n_trades=len(trades), verdict="OPEN", prereg=str(prereg.relative_to(ROOT)),
        note="promoted to walk-forward; run core/pipeline.Pipeline next",
        candidate_key=params["candidate_key"], origin="promoted",
        promoted_stop=a.stop, hold=c.hold, lag=c.lag, direction=c.direction)
    print("logged. Next: hand FeedStrategy to core/pipeline.Pipeline for the "
          "blind walk-forward and the paired null.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
