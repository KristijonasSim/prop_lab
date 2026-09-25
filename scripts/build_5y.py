"""Build the five-year caches step 6 tests on, from raw .bi5 already on disk.

WHY A SEPARATE FILE AND NOT A LONGER `{sym}_dukascopy_{tf}.parquet`. Extending
the three-year cache in place would change the input of every board number in
the repo - H-027's walk-forward reads exactly those files - for a gain step 6
can have without it. These are written as `{sym}_dukascopy5y_{tf}.parquet` and
only `factory/cells.py` looks for them.

THE CEILING IS FIVE YEARS AND IT IS A CEILING (Kris, 2026-09-15). The window
here is [end - 5y, end], not "everything on disk"; gold has eleven years of raw
files and gets five of them.

    .venv/bin/python scripts/build_5y.py            # all six markets
    .venv/bin/python scripts/build_5y.py XAUUSD     # one
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core import fx_data, markets                                    # noqa: E402
from factory.cells import DEEP_SUFFIX, MARKETS, RECHECK_YEARS        # noqa: E402

#: 1d is resampled from 1h by `cells.untrimmed`, on the 22:00 FX day, so it is
#: deliberately not built here.
TFS = ("15m", "1h", "4h")
_RULE = {"15m": "15min", "1h": "1h", "4h": "4h"}


def _end(sym: str) -> pd.Timestamp:
    """The last bar the three-year cache has. The deep cache ends where it does
    so the two share a right edge and the holdout is a clean prefix."""
    return markets.load(sym, "1h").index[-1]


def build(sym: str, years: int = RECHECK_YEARS) -> dict[str, int]:
    """Read every cached raw day in the window once, resample to each tf."""
    if sym in markets.CRYPTO:
        return {}                     # BTC's own cache already has 9 years
    end = _end(sym)
    start = end - pd.DateOffset(years=years)
    frames = []
    t = start.to_pydatetime().replace(tzinfo=timezone.utc)
    stop = end.to_pydatetime().replace(tzinfo=timezone.utc)
    missing = 0
    while t <= stop:
        cache = fx_data.RAW_DIR / sym / f"{t:%Y%m%d}.bi5"
        if cache.exists():
            d = fx_data._decode(cache.read_bytes(), sym, t)
            if d is not None:
                frames.append(d)
        elif t.weekday() != 5:
            missing += 1
        t += timedelta(days=1)
    if not frames:
        raise FileNotFoundError(f"{sym}: no raw .bi5 in {start:%Y-%m-%d}..{end:%Y-%m-%d}")

    m1 = pd.concat(frames).sort_index()
    m1 = m1[~m1.index.duplicated(keep="last")]
    out = {}
    for tf in TFS:
        df = (m1.resample(_RULE[tf], label="left", closed="left")
                .agg(fx_data.AGG).dropna(subset=["open"]))
        df.to_parquet(markets.DATA / f"{sym}_{DEEP_SUFFIX}_{tf}.parquet")
        out[tf] = len(df)
    print(f"{sym}  {m1.index[0]:%Y-%m-%d} -> {m1.index[-1]:%Y-%m-%d}  "
          f"{missing} weekdays missing  " +
          "  ".join(f"{k} {v}" for k, v in out.items()), flush=True)
    return out


def main(argv=None) -> int:
    syms = (argv or sys.argv[1:]) or MARKETS
    for sym in syms:
        try:
            build(sym)
        except FileNotFoundError as e:
            print(f"SKIP {e}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
