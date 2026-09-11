"""H-030 — the CFTC Commitments of Traders feed for COMEX gold, point in time.

Gold trades naked in this repo: every feed on disk is a Binance crypto symbol.
This is the one free positioning feed that exists for gold with a long history:
the CFTC's DISAGGREGATED futures-only report, contract 088691 (COMEX GOLD),
weekly since 2006.

WHO IS IN IT. Managed money is the speculators - CTAs and hedge funds, mostly
trend followers. Producer/merchant is the hedgers (miners, refiners). Swap
dealers are the banks' book. A positioning signal is only worth anything if it
says who is already in the trade and who is left to buy.

WHEN IT IS KNOWN - the whole look-ahead risk is here. Positions are as of
TUESDAY and published FRIDAY at 15:30 ET. Two exceptions move that later:

  * a US federal holiday in the release week pushes it to the next business
    day. Handled by moving every such week to MONDAY 20:30 UTC.
  * the 2025 shutdown stopped publication from 2025-10-01; the backlog was
    released in chronological order and cleared by 2025-12-29 (CFTC press
    releases 9138-25, 9147-25). Every report dated inside it is treated as
    known from 2025-12-30 00:00 UTC. Late, but never early.

20:30 UTC is 15:30 EST. In summer (EDT) the release is at 19:30 UTC, so this is
an hour conservative for half the year. Never early.

Run: .venv/bin/python strategies/goldfeed/cot.py        (downloads and caches)
"""
from __future__ import annotations

import json
import sys
import urllib.parse
import urllib.request
from pathlib import Path

import numpy as np
import pandas as pd
from pandas.tseries.holiday import USFederalHolidayCalendar

ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / "data" / "feeds" / "GOLD_cot_disagg.parquet"
API = "https://publicreporting.cftc.gov/resource/72hh-3qpy.json"
CODE = "088691"

COLS = {
    "open_interest_all": "oi",
    "m_money_positions_long_all": "mm_long",
    "m_money_positions_short_all": "mm_short",
    "prod_merc_positions_long": "pm_long",
    "prod_merc_positions_short": "pm_short",
    "swap_positions_long_all": "sd_long",
    "swap__positions_short_all": "sd_short",
    "nonrept_positions_long_all": "nr_long",
    "nonrept_positions_short_all": "nr_short",
}
SHUTDOWN = (pd.Timestamp("2025-09-30"), pd.Timestamp("2025-12-23"))
SHUTDOWN_KNOWN = pd.Timestamp("2025-12-30", tz="UTC")


def download() -> pd.DataFrame:
    rows, off = [], 0
    while True:
        q = urllib.parse.urlencode({
            "cftc_contract_market_code": CODE, "$limit": 5000, "$offset": off,
            "$order": "report_date_as_yyyy_mm_dd"})
        with urllib.request.urlopen(f"{API}?{q}", timeout=60) as r:
            got = json.load(r)
        rows += got
        if len(got) < 5000:
            break
        off += 5000
    df = pd.DataFrame(rows)
    df["report_date"] = pd.to_datetime(df.report_date_as_yyyy_mm_dd).dt.normalize()
    df = df.set_index("report_date")[list(COLS)].rename(columns=COLS).astype(float)
    return df[~df.index.duplicated(keep="last")].sort_index()


def released(report_dates: pd.DatetimeIndex) -> pd.DatetimeIndex:
    """When each Tuesday report became public. See the module docstring."""
    hol = USFederalHolidayCalendar().holidays(report_dates.min() - pd.Timedelta(days=7),
                                              report_dates.max() + pd.Timedelta(days=14))
    out = []
    for d in report_dates:
        fri = d + pd.Timedelta(days=(4 - d.dayofweek) % 7)        # Friday of that week
        week = pd.date_range(fri - pd.Timedelta(days=4), fri)       # Mon..Fri
        t = fri + pd.Timedelta(hours=20, minutes=30)
        if any(x in hol for x in week):
            t = fri + pd.Timedelta(days=3, hours=20, minutes=30)    # next Monday
        t = t.tz_localize("UTC")
        if SHUTDOWN[0] <= d <= SHUTDOWN[1]:
            t = max(t, SHUTDOWN_KNOWN)
        out.append(t)
    return pd.DatetimeIndex(out)


def load() -> pd.DataFrame:
    """Weekly reports with a `known_at` column and the derived features.

    Every feature is computed on the WEEKLY series, where each row only sees
    itself and earlier rows, and then used from `known_at` onward."""
    df = pd.read_parquet(CACHE)
    df["known_at"] = released(df.index)
    oi = df.oi
    f = pd.DataFrame(index=df.index)
    f["known_at"] = df.known_at
    f["mm_net"] = (df.mm_long - df.mm_short) / oi
    f["pm_net"] = (df.pm_long - df.pm_short) / oi
    f["sd_net"] = (df.sd_long - df.sd_short) / oi
    # where managed money stands against its own last three years, 0..1
    f["mm_pct"] = f.mm_net.rolling(156, min_periods=52).apply(
        lambda x: (x[:-1] < x[-1]).mean() + 0.5 * (x[:-1] == x[-1]).mean(), raw=True)
    f["mm_d1"] = f.mm_net.diff(1)
    f["mm_d4"] = f.mm_net.diff(4)
    f["oi_d4"] = np.log(oi / oi.shift(4))
    return f


def asof(feat: pd.DataFrame, ts: pd.DatetimeIndex, col: str) -> np.ndarray:
    """The value of `col` from the latest report PUBLISHED at or before each ts."""
    k = feat.dropna(subset=[col]).sort_values("known_at")
    pos = np.searchsorted(k.known_at.values, np.asarray(ts, dtype="datetime64[ns]"),
                          side="right") - 1
    v = k[col].values
    return np.where(pos >= 0, v[np.clip(pos, 0, None)], np.nan)


def main() -> int:
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    df = download()
    df.to_parquet(CACHE)
    f = load()
    print(f"{len(df)} weekly reports  {df.index[0].date()} -> {df.index[-1].date()}")
    print(f"last known_at {f.known_at.iloc[-1]}")
    print(f.tail(3).round(3).to_string())
    return 0


if __name__ == "__main__":
    sys.exit(main())
