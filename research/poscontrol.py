"""POSITIVE CONTROL — can this pipeline see an edge that is definitely there?

WHY THIS EXISTS. Every control in this repo is a NEGATIVE one: paired nulls,
block shuffles, noise bands. All of them answer "could noise have done this?"
Nothing answered the other question - **"could we detect a real edge if one
were there?"** - and after 457 charged trials with no survivor those two
hypotheses are observationally identical:

    the market has no edge at this size   OR   the pipeline cannot see one

The idea is borrowed from arXiv 2605.04004, a systematic falsification of 14
OHLCV intraday signal families on MNQ futures. None passed - and what makes
those 14 failures MEAN anything is that the study planted two positive controls
which scored T=3.11 and T=4.30. Without them the paper says nothing.

WHAT IT DOES. Plants an edge of known size in real gold 1h returns and hands it
to `core.screen` unmodified. The smallest size that is reliably found is the
DETECTION FLOOR. Below that floor, a DEAD verdict from this screen is a
statement about the screen, not about the market.

WHAT IT FOUND, 2026-09-21 - AND IT IS A DEFECT, NOT A REASSURANCE.

  * On a CONTINUOUS signal the screen is fine. Floor is ~2bps of predictive
    strength, an implied IC of ~0.09 - roughly H-027's own 0.077.

  * On an INTERMITTENT signal - one that only carries information on a small
    fraction of bars - **the screen is close to blind at any strength.**
    `bucket_response` buckets EVERY row, so a signal live 5% of the time has
    its effect diluted about 20x before the cost gate ever sees it.

        20 planted edges, all real and all tradeable, gold 1h, 3 years
          screened as the loop screens today  ->   7 of 20 found
          screened on their own event rows    ->  18 of 20 found

        fires 5% of bars:   0 of 5 found today, 4 of 5 found on events
        fires 1% of bars:   0 of 5 found today, 4 of 5 found on events

    At 1% firing a 40bps edge - 228 events in three years, each paying twelve
    times the round trip - is rejected for "effect 0.4 under the 3.3 bar".

    **THE SCREEN IS ASKING THE WRONG QUESTION.** It asks whether the signal
    predicts the AVERAGE BAR. Nobody trades the average bar. The question is
    whether it predicts the bars it fires on.

  * The two ways it dies are `effect under the bar` and `mean and median
    disagree in sign`, which are exactly the recorded causes of death for
    H-046 (footprint, COST) and H-046c (long holds, SKEW). **Those two should
    be re-run on their events before they stay dead.**

  * SECOND DEFECT, same root. `research/vocab.py` has four transforms and all
    four are continuous - `level`, `change`, `zscore`, `pctile`. There is no
    threshold or event transform, so **the loop cannot express an intermittent
    signal in the first place** - including the shape of H-027 itself, which is
    a rare breakout past a band.

NEITHER IS FIXED HERE. Proposing, not choosing. Run this before believing the
next DEAD.

    PYTHONPATH=. .venv/bin/python -m research.poscontrol
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from core.screen import COST_MULT, MIN_EVENTS, MIN_RHO, screen

#: Measured round trip on gold from this repo's own tick cache.
GOLD_RT_BPS = 1.64
SERIES = "data/XAUUSD_dukascopy_1h.parquet"
YEARS = 3


def gold_forward_returns(path: str = SERIES, years: int = YEARS) -> pd.Series:
    """Next-bar log return in bps. The honest noise to plant an edge into."""
    px = pd.read_parquet(path)
    r = (np.log(px["close"]).diff().shift(-1) * 1e4).dropna()
    return r.iloc[-years * 365 * 24:]


def plant(rng, r: pd.Series, k: float, fires: float = 1.0):
    """A signal, and a forward return it genuinely predicts.

    `k` is bps of return per sigma of signal. `fires` is the fraction of bars on
    which the signal carries any information at all; the rest are pure noise,
    which is what an event feed looks like.
    """
    s = pd.Series(rng.standard_normal(len(r)), index=r.index)
    live = pd.Series(rng.random(len(r)) < fires, index=r.index)
    return s, r + k * s * live, live


def run(seeds: int = 5) -> None:
    r = gold_forward_returns()
    print(f"gold 1h  {len(r):,} bars  sd {r.std():.1f} bps  "
          f"cost bar {GOLD_RT_BPS * COST_MULT:.2f} bps")
    print(f"gates: events>={MIN_EVENTS}  effect>={COST_MULT}x round trip  "
          f"rho>={MIN_RHO}  sign(mean)==sign(median)  null\n")
    print(f"{'fires':>7}{'k bps':>7}{'IC':>7}   "
          f"{'SCREENED AS TODAY (all bars)':<40}{'SCREENED ON ITS EVENTS':<26}")
    print("-" * 88)
    for fires in (1.0, 0.20, 0.05, 0.01):
        for k in (2, 5, 10, 20, 40):
            a_ok = b_ok = 0
            a = b = ic = None
            for seed in range(seeds):
                g = np.random.default_rng(1000 + seed)
                s, fwd, live = plant(g, r, k, fires)
                ic = float(s.corr(fwd))
                a = screen("all", s, fwd, GOLD_RT_BPS, hold=1)
                b = screen("evt", s[live], fwd[live], GOLD_RT_BPS, hold=1)
                a_ok += a.verdict == "WORK"
                b_ok += b.verdict == "WORK"
            why = ("; ".join(a.notes) or "earned a real study")[:26]
            print(f"{fires:>6.0%}{k:>7}{ic:>7.3f}   "
                  f"{a.verdict + ' ' + why:<32}{a_ok}/{seeds}      "
                  f"{b.verdict:<6}{b_ok}/{seeds}")
        print()


if __name__ == "__main__":
    run()
