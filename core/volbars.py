"""Bars sampled on the VOLUME clock instead of the time clock.

Tier 1 item 2 of `VWAP_BACKLOG.md`. The pre-registration, including the kill
criterion and the caveats, is in `strategies/vwapbreak/research/VOLBARS.md` and
was written before the first run.

WHY THIS EXISTS. A standard-deviation band assumes observations that are close
to IID and homoscedastic. A time-sampled series of a market that trades in
bursts is neither: the Asian session and the NY open are one hour each and carry
very different amounts of information. Sampling every N units of volume is the
standard correction, and it is the one input every previous H-027 variant left
alone — they all changed what the BAND is, none changed what a BAR is.

HOW THE THRESHOLD IS SET, and it is the whole point. V is calibrated so the arm
produces the SAME NUMBER OF BARS as the timeframe it is compared against. Sub-hour
died because more bars did not mean more trades; matching the bar count removes
that confound by construction, so any difference is the clock itself.

WEEKEND PADDING IS DROPPED BEFORE ACCUMULATING. Dukascopy pads the closed FX
weekend with synthetic zero-volume bars at the last traded price — 21.5% of the
XAUUSD series. They add nothing to a volume accumulator but would otherwise sit
inside buckets as dead minutes and drag a bar's open/high/low around. The repo's
standing rule is never to decide or fill on one; here they are removed a step
earlier, at construction.

Build:  .venv/bin/python -c "from core.volbars import build; build('XAUUSD','vol1h')"
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.fx_data import AGG, DATA_DIR, RAW_DIR, _decode          # noqa: E402

#: label -> (kind, bars per hour it is calibrated to). `dollar` accumulates
#: notional (volume x price) rather than raw volume, which keeps the threshold
#: economically constant while gold runs from $1,800 to $3,500.
SPECS = {
    "vol1h": ("volume", 1.0),
    "dol1h": ("dollar", 1.0),
}


def minute_frame(sym: str, start: str = "2023-09-01",
                 end: str = "2026-09-01") -> pd.DataFrame:
    """Every cached 1-minute candle for one symbol, concatenated and deduped.

    Same assembly `core.fx_data.build_tf` uses, lifted so the volume clock reads
    the identical bytes the time bars are built from. No downloads: the raw cache
    is already in the repo.
    """
    t0 = datetime.fromisoformat(start).replace(tzinfo=timezone.utc)
    t1 = datetime.fromisoformat(end).replace(tzinfo=timezone.utc)
    frames, t = [], t0
    while t < t1:
        cache = RAW_DIR / sym / f"{t:%Y%m%d}.bi5"
        if cache.exists():
            d = _decode(cache.read_bytes(), sym, t)
            if d is not None:
                frames.append(d)
        t += timedelta(days=1)
    if not frames:
        raise FileNotFoundError(f"no cached raw files for {sym}")
    m1 = pd.concat(frames).sort_index()
    return m1[~m1.index.duplicated(keep="last")]


def bucket_bars(m1: pd.DataFrame, threshold: float,
                dollar: bool = False) -> pd.DataFrame:
    """Group 1-minute bars into buckets of roughly `threshold` units.

    The bucket index is `floor(cumulative / threshold)`, so a bucket closes on
    the minute that carries the accumulator past a multiple of the threshold.
    A single minute larger than the threshold produces one bar and skips indices,
    which is correct: it is one burst, not several.

    The emitted bar is labelled at its FIRST minute, matching the `label="left"`
    convention every resample in this repo uses. The label is the bar's OPEN, so
    a decision taken on the bar's close is taken strictly after every minute in
    it — there is no look-ahead in the labelling.
    """
    if threshold <= 0:
        raise ValueError("threshold must be positive")
    live = m1[m1.volume.values > 0]              # weekend padding, dropped first
    if not len(live):
        raise ValueError("no live minutes")
    unit = live.volume.values * live.close.values if dollar else live.volume.values
    bucket = np.floor(np.cumsum(unit) / threshold).astype(np.int64)

    g = live.groupby(bucket)
    out = g.agg(AGG)
    out.index = g.apply(lambda x: x.index[0])
    out.index.name = None
    # The final bucket is almost never full. Dropping it keeps every bar in the
    # series the same size, which is the property the whole exercise is for.
    return out.iloc[:-1] if len(out) > 1 else out


def calibrate(m1: pd.DataFrame, bars_per_hour: float,
              dollar: bool = False) -> float:
    """The threshold that yields `bars_per_hour` bars per LIVE hour.

    Live hours, not wall-clock hours: the weekend is closed and padding has
    already been removed, so counting it would set the threshold too low and
    produce more bars than the control.
    """
    live = m1[m1.volume.values > 0]
    unit = live.volume.values * live.close.values if dollar else live.volume.values
    hours = len(live) / 60.0                     # one row is one minute
    return float(unit.sum() / max(hours * bars_per_hour, 1.0))


def build(sym: str, label: str = "vol1h", start: str = "2023-09-01",
          end: str = "2026-09-01", force: bool = False) -> pd.DataFrame:
    """Build and cache one volume-clock series, named so `core.markets.load` finds it."""
    if label not in SPECS:
        raise KeyError(f"unknown volume-bar label {label!r}; known: {list(SPECS)}")
    kind, bph = SPECS[label]
    path = DATA_DIR / f"{sym}_dukascopy_{label}.parquet"
    if path.exists() and not force:
        return pd.read_parquet(path).sort_index()

    m1 = minute_frame(sym, start, end)
    dollar = kind == "dollar"
    thr = calibrate(m1, bph, dollar=dollar)
    df = bucket_bars(m1, thr, dollar=dollar)
    df.to_parquet(path)
    span_h = (df.index[-1] - df.index[0]).total_seconds() / 3600.0
    print(f"{sym} {label}: {len(df)} bars, threshold {thr:,.2f} "
          f"({kind}), {len(df) / max(span_h, 1):.3f} bars/wall-clock hour")
    return df
