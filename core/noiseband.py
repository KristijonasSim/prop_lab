"""How much of a headline number is the strategy, and how much is the draw.

WHY THIS FILE EXISTS. On 2026-09-08 six gates carrying **no information by
construction** were run through the full blind walk-forward on gold. They scored
between **13.3 and 26.5 expected days** and between **PF@2x 1.485 and 2.295**,
and the best-scoring arm of that whole day's work was one of the shuffled gates.
Every real candidate measured that day - 14.1, 16.1, 16.6, 17.2 expected days -
landed inside that spread. So did the 62.6%-pass headline of the day before,
which evaporated the moment the grid was widened.

The lesson is not "that experiment failed". It is that **a point estimate of
expected days carries an uncertainty this project has never quoted**, and that
the uncertainty is larger than every difference it has ever reported. CLAUDE.md
now states the rule outright: quote a per-cell number with its band or do not
quote it.

WHAT THE BAND HERE IS, precisely. It is the sampling band of ONE cell's headline:
resample this cell's own daily returns with a stationary block bootstrap, re-run
the same prop simulation on each resample, and report the spread of the answer.
It says *if the same strategy met a differently-shuffled draw of the same
two years, the headline would have landed in here*.

WHAT IT IS NOT. It is not the selection band. Choosing the best of ten markets,
or the best of four selection rules, adds uncertainty this cannot see - the
paired null in `core/pipeline.py` is what measures that, and it stays the primary
gate. It is also not the measured noise floor: that number (`FLOOR_DAYS` below)
came from running information-free gates through the whole machine, and it is
carried here as a reference line rather than recomputed per cell.

WHY A BLOCK BOOTSTRAP AND NOT A PLAIN ONE. Daily returns of a strategy holding
positions for up to four days are autocorrelated, and an i.i.d. resample would
break exactly the runs that decide whether an account breaches. The stationary
bootstrap (Politis-Romano) resamples geometric-length blocks, so a bad fortnight
survives resampling as a bad fortnight. `MEAN_BLOCK` is the mean block length in
trading days.

THE ONE THING NOT SUBJECT TO ANY OF THIS: the risk ladder. Re-simulating a fixed
trade series at a different position size selects nothing and searches nothing.
Gold 1h needing 38.0 expected days at 0.25% risk and 16.6 at 2% is arithmetic on
one series, and the difference is real in a way no filter result was.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.prop_rules import ONE_STEP, PropRules                # noqa: E402
from core.riskladder import MAX_DAYS                           # noqa: E402

#: Resamples per band. 200 puts the 10th/90th percentile inside about +-3% of
#: its own Monte Carlo error, which is far finer than the band it is measuring.
RESAMPLES = 200

#: Mean block length in trading days. H-027 holds for up to four days and the
#: drawdown that kills an account builds over a week or two, so the block has to
#: be long enough to carry a bad fortnight through the resample.
MEAN_BLOCK = 10

#: The percentiles reported. Deliberately 10/90 rather than 2.5/97.5: the point
#: is to stop two numbers being read as different when they are not, and a 95%
#: interval on 200 resamples is itself noisy at the tails.
LO_PCT, HI_PCT = 10.0, 90.0

#: THE MEASURED NOISE FLOOR, 2026-09-08. Six information-free gates (the MA200
#: slope sign, block-shuffled at its own median run length) taken through the
#: full blind walk-forward on gold at 2% risk. Not recomputed here - it is the
#: output of a day of running, kept as the reference line every per-cell band is
#: read against. See CLAUDE.md and RESEARCH_LOG.md 2026-09-08.
FLOOR_DAYS = (13.3, 26.5)
FLOOR_PF_2X = (1.485, 2.295)
FLOOR_NOTE = ("six information-free gates on gold, 2% risk, full blind "
              "walk-forward")


def _states(d: np.ndarray, rules: PropRules, max_days: int) -> tuple:
    """Run a fresh account from every day of every row of `d`.

    `d` is (B, n) of DAILY returns already multiplied by risk per trade. Returns
    `(outcome, days)`, both (B, n) - one account per (row, start day).

    This is `core.riskladder.run_accounts` with the account loop vectorised
    across every account at once: iteration `k` advances every still-open
    account by one day. The rules are applied in the same order and with the
    same worst-case convention (the whole day's loss lands before any of its
    gain), because a band computed under different rules from the point estimate
    it brackets would be worse than no band at all. `test_noiseband.py` pins the
    two against each other on real numbers.

    Outcome codes: 0 open (ran out of data), 1 pass, 2 max-loss, 3 daily-loss.
    """
    B, n = d.shape
    flat = d.reshape(-1)
    start = np.tile(np.arange(n), B)
    row0 = np.repeat(np.arange(B) * n, n)          # offset of each row in `flat`

    eq = np.zeros(B * n)
    peak = np.zeros(B * n)
    day = np.zeros(B * n, dtype=np.int32)
    traded = np.zeros(B * n, dtype=np.int32)
    out = np.zeros(B * n, dtype=np.int8)
    open_ = np.ones(B * n, dtype=bool)

    for k in range(max_days):
        idx = start + k
        have = open_ & (idx < n)
        if not have.any():
            break
        j = np.flatnonzero(have)
        step = flat[row0[j] + idx[j]]

        day[j] += 1
        traded[j] += (step != 0.0)
        down = np.minimum(step, 0.0)

        # 1. daily cap, on the day's loss alone
        hit_daily = down <= -rules.daily_loss
        # 2. max-loss cap, on the worst point inside the day
        low = eq[j] + down
        hit_max = np.zeros(len(j), dtype=bool)
        if rules.trailing:
            hit_max |= (low - peak[j]) <= -rules.max_loss
        if rules.static:
            hit_max |= low <= -rules.max_loss
        hit_max &= ~hit_daily

        # 3. survivors bank the day and may hit the target
        alive = ~(hit_daily | hit_max)
        ja = j[alive]
        eq[ja] += step[alive]
        peak[ja] = np.maximum(peak[ja], eq[ja])
        passed = (eq[ja] >= rules.profit_target) & (traded[ja] >= rules.min_trading_days)

        out[j[hit_daily]] = 3
        out[j[hit_max]] = 2
        out[ja[passed]] = 1
        open_[j[hit_daily | hit_max]] = False
        open_[ja[passed]] = False

    return out.reshape(B, n), day.reshape(B, n)


def _per_row(out: np.ndarray, day: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """(pass rate, median days of the passers) for each row of accounts."""
    passed = out == 1
    rate = passed.mean(axis=1)
    med = np.full(len(out), np.nan)
    for i in range(len(out)):
        if passed[i].any():
            med[i] = float(np.median(day[i][passed[i]]))
    return rate, med


def _resample_index(n: int, b: int, rng: np.random.Generator,
                    mean_block: int) -> np.ndarray:
    """Stationary-bootstrap index matrix, (b, n).

    Each step continues the current block with probability 1 - 1/mean_block and
    otherwise jumps to a fresh uniform position, wrapping at the end. Block
    lengths are therefore geometric with the requested mean, and every day of
    the original series is equally likely to appear - which is what makes it
    *stationary* and what stops the ends of the series being under-sampled.
    """
    p = 1.0 / max(mean_block, 1)
    idx = np.empty((b, n), dtype=np.int64)
    idx[:, 0] = rng.integers(0, n, b)
    jump = rng.random((b, n)) < p
    fresh = rng.integers(0, n, (b, n))
    for t in range(1, n):
        idx[:, t] = np.where(jump[:, t], fresh[:, t], (idx[:, t - 1] + 1) % n)
    return idx


def band(daily_r, risk: float, *, resamples: int = RESAMPLES,
         mean_block: int = MEAN_BLOCK, seed: int = 0,
         rules: PropRules = ONE_STEP[0], max_days: int = MAX_DAYS) -> dict | None:
    """The sampling band of one cell's headline, at one risk per trade.

    `daily_r` is the stitched walk-forward series resampled to calendar days -
    the same object `core.riskladder.from_trades` builds. `risk` is the fraction
    of equity risked per trade at the rung being quoted.

    Returns None when the series is too short to say anything (under 60 days),
    because a band computed from a handful of days would invite exactly the
    false confidence this file exists to prevent.

    Keys: `days_lo`/`days_hi`/`days_med` for expected days per funded account,
    `pass_lo`/`pass_hi`/`pass_med` in percent, `never_pct` for the share of
    resamples that never funded an account at all (an unfundable resample has no
    finite expected days, so it cannot enter the percentiles and has to be
    reported separately or it silently flatters the band).
    """
    r = np.asarray(pd.Series(daily_r).values, dtype=float)
    n = len(r)
    if n < 60:
        return None
    rng = np.random.default_rng(seed)
    idx = _resample_index(n, resamples, rng, mean_block)
    out, day = _states(r[idx] * risk, rules, max_days)
    rate, med = _per_row(out, day)

    ok = np.isfinite(med) & (rate > 0)
    days = med[ok] / rate[ok]
    never = float((~ok).mean()) * 100.0
    if not len(days):
        return {"days_lo": None, "days_hi": None, "days_med": None,
                "pass_lo": round(float(np.percentile(rate, LO_PCT) * 100), 1),
                "pass_hi": round(float(np.percentile(rate, HI_PCT) * 100), 1),
                "pass_med": round(float(np.median(rate) * 100), 1),
                "never_pct": round(never, 1), "resamples": int(resamples),
                "mean_block": int(mean_block)}
    return {
        "days_lo": round(float(np.percentile(days, LO_PCT)), 1),
        "days_hi": round(float(np.percentile(days, HI_PCT)), 1),
        "days_med": round(float(np.median(days)), 1),
        "pass_lo": round(float(np.percentile(rate, LO_PCT) * 100), 1),
        "pass_hi": round(float(np.percentile(rate, HI_PCT) * 100), 1),
        "pass_med": round(float(np.median(rate) * 100), 1),
        "never_pct": round(never, 1),
        "resamples": int(resamples), "mean_block": int(mean_block),
    }


def from_trades(r: np.ndarray, exit_ts, risk: float, **kw) -> dict | None:
    """Band straight from a trade series, matching `riskladder.from_trades`."""
    daily = pd.Series(np.asarray(r),
                      index=pd.DatetimeIndex(exit_ts)).resample("1D").sum()
    return band(daily, risk, **kw)


def overlap(a: dict | None, b: dict | None, key: str = "days") -> bool:
    """Do two bands overlap? Missing band means UNKNOWN, and unknown counts as
    overlapping - refusing to separate two numbers is the safe direction, and it
    is the direction that costs a project nothing but a ranking it should not
    have trusted."""
    if not a or not b:
        return True
    lo_a, hi_a = a.get(f"{key}_lo"), a.get(f"{key}_hi")
    lo_b, hi_b = b.get(f"{key}_lo"), b.get(f"{key}_hi")
    if None in (lo_a, hi_a, lo_b, hi_b):
        return True
    return not (hi_a < lo_b or hi_b < lo_a)


def inside_floor(days: float | None) -> bool:
    """Is a headline inside the measured noise floor? A cell here has not been
    shown to differ from a gate that knows nothing."""
    return days is not None and FLOOR_DAYS[0] <= days <= FLOOR_DAYS[1]
