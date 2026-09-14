"""GATE 2 of the mechanism pipeline — does an event actually move forward returns?

This is the fast kill. It answers one question and refuses to answer any other:

    around this event, is the forward return different from baseline,
    by more than the same test finds on shuffled dates?

WHAT IT DELIBERATELY DOES NOT DO. No stops, no targets, no position sizing, no
parameter grid. Those belong to gate 3 and cost days. Seven hypotheses in this
repo have a `stage1_response.py` doing this job for a FEED and they died in a day;
the twelve price hypotheses skipped it, built a full kernel with 60k
configurations first, and took a week each to reach the same verdict. This module
is that pattern generalised so a calendar or event idea can be killed in an hour.

THE NULL IS THE POINT. An event that fires ~250 times a year will produce a
non-zero mean forward return by chance alone, and with enough horizons and
instruments something always looks good. So every reported edge is scored against
the identical statistic computed on RANDOMLY SHIFTED event dates: same number of
events, same market, same forward-return distribution, alignment destroyed. The
number that matters is not the edge, it is the percentile of the edge in its own
null.

READ THE OUTPUT AS A HURDLE COMPARISON, NOT A PROFIT. `edge_bps` is a gross
forward return with no execution in it. Compare it to the round-trip cost of the
instrument: EURUSD 0.274bps measured, XAUUSD 1.83, crypto ~14. An edge below its
own hurdle is dead no matter how significant it is.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

# Measured round-trip costs in bps. Anything not here is a guess and is flagged.
COST_RT = {
    "EURUSD": 0.274, "XAUUSD": 1.83, "XAGUSD": 9.11,
    "BTCUSDT": 14.0, "ETHUSDT": 14.0, "SOLUSDT": 14.0,
}
GUESSED_RT = {           # from strategies/vwap/stage1_grid.ASSETS, never measured
    "GBPUSD": 1.60, "USDJPY": 1.50, "AUDUSD": 1.90,
    "USDCAD": 2.00, "USDCHF": 2.10, "NZDUSD": 2.60,
}


def forward_bps(df: pd.DataFrame, h: int) -> np.ndarray:
    """Return from the NEXT bar's open to the open h bars later, in bps.

    Next-bar open on both ends, never a close: the decision is made on the bar
    that just closed, so the earliest fill is the next open. Using the signal
    bar's own close as an entry is the look-ahead that killed every crypto
    result in this project on 2026-09-05.
    """
    o = df.open.values
    entry = np.roll(o, -1)
    exit_ = np.roll(o, -(1 + h))
    out = (exit_ - entry) / entry * 1e4
    out[-(1 + h):] = np.nan
    return out


def _stat(fwd: np.ndarray, mask: np.ndarray) -> float:
    v = fwd[mask & np.isfinite(fwd)]
    return float(np.mean(v)) if v.size else np.nan


def live_mask(df: pd.DataFrame) -> np.ndarray:
    """Bars that actually traded, AND whose next bar (the entry) traded too.

    THIS IS NOT OPTIONAL AND IT COST US A FALSE POSITIVE ON DAY ONE. The first
    run of this module promoted "FX weekly open" on EURUSD and GBPUSD at 100th
    percentile of its null — and 76.5% of those events were Dukascopy's padded
    weekend bars: zero volume, last price repeated. The "edge" was the synthetic
    Friday-to-Monday price step, which nobody can trade. Same defect that was
    removed from both strategy kernels on 2026-09-07, reappearing immediately in
    a brand-new tool because the tool did not carry the rule.
    """
    v = df.volume.values > 0
    nxt = np.roll(v, -1)
    nxt[-1] = False
    return v & nxt


def hour_matched_shifts(index, idx: np.ndarray) -> np.ndarray:
    """Circular shifts that land every event on the SAME time of day.

    WHY THIS EXISTS. The null used to shift events by any offset at all. An
    event that always fires at 00:00 UTC was therefore compared against a
    population drawn from every hour of the day - and gold's hours are not
    interchangeable. Forward returns from the 00:00 bar are not the forward
    returns of the NY open, so the null was drawing from a different population
    than the real events and was easier to beat than it should have been. It was
    worth roughly 5bps to a short-side daily arm, found 2026-09-13, and every
    screen that used this module before 2026-09-14 is affected.

    A shift of a whole number of DAYS preserves the time of day on a regular
    grid, so the candidates are the multiples of one day's bars - but the wrap
    at the end of the series can break the phase and a padded cache can carry a
    gap, so each candidate is CHECKED against the real minute-of-day rather than
    assumed. Returns the shifts that pass, empty if the grid cannot support it.
    """
    d = pd.DatetimeIndex(index)
    n = len(d)
    if n < 3 or not len(idx):
        return np.empty(0, dtype=np.int64)
    step = pd.Series(d).diff().dropna().mode()
    if not len(step) or step.iloc[0] <= pd.Timedelta(0):
        return np.empty(0, dtype=np.int64)
    step = step.iloc[0]
    if pd.Timedelta("1D") % step != pd.Timedelta(0):
        return np.empty(0, dtype=np.int64)          # bars do not divide a day
    bpd = int(pd.Timedelta("1D") // step)
    mod = (d.hour * 60 + d.minute).values
    want = mod[idx]
    return np.array([s for s in range(bpd, n, bpd)
                     if np.array_equal(mod[(idx + s) % n], want)], dtype=np.int64)


def probe(df: pd.DataFrame, events: np.ndarray, horizons: list[int],
          sym: str, label: str, side: np.ndarray | None = None,
          n_null: int = 400, seed: int = 0) -> pd.DataFrame:
    """One row per horizon.

    `events`  boolean per bar — the bar the event is KNOWN on. Entry is the next
              bar's open, so the event bar itself is never traded.
    `side`    optional +1/-1 per bar giving the mechanism's own direction rule.
              Without it the probe tests an unconditional drift, which is the
              right first question for a flow that always pushes one way.
    """
    rng = np.random.default_rng(seed)
    live = live_mask(df)
    ev = np.asarray(events, bool) & live      # never probe a bar that never traded
    n = len(df)
    n_dead = int(np.asarray(events, bool).sum() - ev.sum())
    rows = []
    hurdle = COST_RT.get(sym, GUESSED_RT.get(sym, np.nan))
    measured = sym in COST_RT

    for h in horizons:
        fwd = forward_bps(df, h)
        if side is not None:
            fwd = fwd * np.where(np.asarray(side) == 0, np.nan, side)

        real = _stat(fwd, ev)
        base = _stat(fwd, ~ev)

        # NULL: same events, shifted to random offsets. Preserves the event
        # count and the market's own return distribution; destroys only the
        # alignment between the two. A circular roll keeps the clustering
        # structure of the event dates, which an independent resample would not.
        #
        # THE SHIFT IS A WHOLE NUMBER OF DAYS (2026-09-14). See
        # `hour_matched_shifts`: a free shift compares a 00:00 event against
        # every hour of the day and hands the real events an edge they did not
        # earn. When the grid cannot support it the old behaviour stands and
        # `null_hour_matched` in the output says so.
        idx = np.flatnonzero(ev)
        shifts = hour_matched_shifts(df.index, idx)
        null = np.empty(n_null)
        for i in range(n_null):
            shifted = np.zeros(n, bool)
            s_ = (int(rng.choice(shifts)) if len(shifts)
                  else int(rng.integers(1, n)))
            shifted[(idx + s_) % n] = True
            # the null must live under the same constraint as the real events,
            # or it is drawing from a different population and is easier to beat
            null[i] = _stat(fwd, shifted & live)
        null = null[np.isfinite(null)]

        pct = float((null < real).mean() * 100) if null.size and np.isfinite(real) else np.nan
        rows.append({
            "mechanism": label, "sym": sym, "h_bars": h,
            "events": int(ev.sum()), "dead_dropped": n_dead,
            "edge_bps": round(real, 3) if np.isfinite(real) else np.nan,
            "baseline_bps": round(base, 3) if np.isfinite(base) else np.nan,
            "null_mean": round(float(null.mean()), 3) if null.size else np.nan,
            "null_p95": round(float(np.percentile(null, 95)), 3) if null.size else np.nan,
            "pctile": round(pct, 1) if np.isfinite(pct) else np.nan,
            "hurdle_bps": hurdle, "cost_measured": measured,
            "null_hour_matched": bool(len(shifts)),
            "null_shifts": int(len(shifts)),
            "beats_hurdle": bool(np.isfinite(real) and real > hurdle),
        })
    return pd.DataFrame(rows)


def by_year(df: pd.DataFrame, events: np.ndarray, h: int,
            side: np.ndarray | None = None) -> pd.Series:
    """Same edge, split by calendar year. A mechanism that only worked in one
    year is a story about that year, and this project has been fooled by exactly
    that before — BTC 30m and 1h both cleared thirty quarters and lost money
    from 2024 on."""
    fwd = forward_bps(df, h)
    if side is not None:
        fwd = fwd * np.where(np.asarray(side) == 0, np.nan, side)
    s = pd.Series(fwd, index=df.index)
    m = pd.Series(np.asarray(events, bool), index=df.index)
    return s[m].groupby(s[m].index.year).mean().round(2)
