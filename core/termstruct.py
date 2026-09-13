"""The term structure of leverage — dated quarterly futures against the perp.

H-034. Pre-registered in `strategies/termstruct/notes.md` before any measurement.

WHAT THIS BUILDS. For each market, an hourly series carrying the perp close, the
FRONT dated quarterly's close, days to that contract's settlement, and the basis
both raw and annualised. Plus the back contract where it overlaps, which gives a
two-point curve.

WHY NOT `binance_metrics.klines`. That function is written for a perpetual: it
tops the monthly files up with DAILY files running to yesterday. A quarterly that
expired in 2021 has no days after its settlement, so asking for them means about
two thousand 404s per contract and twenty-two contracts of them. This fetches
only the months a contract was actually alive.

THE DATED CONTRACT IS A FEED, NEVER A TRADE. It turns over roughly one thousandth
of the perp's volume ($16.3M/day against $16.57B on a sampled day). Every trade
this hypothesis implies is in the PERP, at the 14bps round trip the rest of the
repo is priced at. The dated contract is only ever read.

THE STAMP SWITCH. The archive moved from millisecond to microsecond open_time
during 2025 and a batch spanning the change carries both, so the unit is decided
PER ROW. Deciding it per batch dates every millisecond row to 1970 - which is
exactly what happened to the spot series in `core/basis_data.py` once already.

Run:  .venv/bin/python core/termstruct.py            BTCUSDT and ETHUSDT
      .venv/bin/python core/termstruct.py BTCUSDT
"""
from __future__ import annotations

import io
import sys
import zipfile
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

FEEDS = ROOT / "data" / "feeds"
FEEDS.mkdir(parents=True, exist_ok=True)
BASE = "https://data.binance.vision/data/futures/um"
WORKERS = 16
KCOLS = ["open_time", "open", "high", "low", "close", "volume", "close_time",
         "quote_volume", "trades", "taker_buy_base", "taker_buy_quote", "ignore"]

MARKETS = ("BTCUSDT", "ETHUSDT")

#: Binance quarterly settlement codes, YYMMDD, 08:00 UTC on the day named.
#: Verified present in the archive for BTCUSDT and ETHUSDT, 22 of 22, 2026-09-13.
CODES = ("210326", "210625", "210924", "211231",
         "220325", "220624", "220930", "221230",
         "230331", "230630", "230929", "231229",
         "240329", "240628", "240927", "241227",
         "250328", "250627", "250926", "251226",
         "260327", "260626", "260925", "261225")

#: A contract is dropped this close to settlement. The basis goes to zero there
#: by arithmetic rather than by information, and the book thins.
MIN_DAYS = 3.0
#: How many months before settlement to look for bars. Binance lists a quarterly
#: about two quarters out; 9 covers it with room and costs only 404s.
LOOKBACK_MONTHS = 9


def expiry_of(code: str) -> datetime:
    """`250926` -> 2025-09-26 08:00 UTC."""
    return datetime(2000 + int(code[:2]), int(code[2:4]), int(code[4:6]),
                    8, 0, tzinfo=timezone.utc)


def _one(url: str, s: requests.Session) -> pd.DataFrame | None:
    try:
        r = s.get(url, timeout=60)
    except requests.RequestException:
        return None
    if r.status_code != 200:
        return None
    with zipfile.ZipFile(io.BytesIO(r.content)) as z:
        with z.open(z.namelist()[0]) as f:
            head = f.readline()
            f.seek(0)
            skip = 1 if b"open_time" in head else 0
            return pd.read_csv(f, header=None, names=KCOLS, skiprows=skip)


def _frame(raw: list[pd.DataFrame]) -> pd.DataFrame:
    df = pd.concat(raw, ignore_index=True)
    ts = df.open_time.astype("int64")
    us = ts > 10 ** 15                      # per ROW, not per batch
    df["ts"] = pd.to_datetime(ts.where(us, ts * 1000), unit="us", utc=True)
    # `open` IS LOAD-BEARING AND NEARLY WAS NOT HERE. `core/probe.forward_bps`
    # takes its entry from the NEXT bar's open; if this frame carries no open and
    # the caller falls back to close, every trade enters at the signal bar's own
    # close. That is the look-ahead that killed every crypto result in this repo
    # on 2026-09-05. It is selected explicitly rather than left to a fallback.
    out = df.set_index("ts")[["open", "high", "low", "close", "volume",
                              "quote_volume", "trades"]]
    return out.astype("float64").sort_index()


def contract(sym: str, code: str, tf: str = "1h") -> pd.DataFrame:
    """Hourly bars for one dated contract, over the months it was alive only."""
    exp = expiry_of(code)
    end = pd.Period(exp.date(), freq="M")
    months = pd.period_range(end - LOOKBACK_MONTHS, end, freq="M")
    name = f"{sym}_{code}"
    with requests.Session() as s, ThreadPoolExecutor(WORKERS) as ex:
        urls = [f"{BASE}/monthly/klines/{name}/{tf}/{name}-{tf}-{m}.zip"
                for m in months]
        raw = [g for g in ex.map(lambda u: _one(u, s), urls)
               if g is not None and len(g)]
    if not raw:
        return pd.DataFrame()
    df = _frame(raw)
    return df[~df.index.duplicated(keep="last")]


def perp(sym: str, tf: str = "1h", first: str = "2021-01") -> pd.DataFrame:
    """Perp hourly bars, cached under a name of this module's own.

    NOT `{sym}_perp_{tf}.parquet`: that is `binance_metrics.klines`'s cache path,
    and it stores a different column set (it carries `taker_buy_base`, this does
    not). Today nothing collides because the repo caches 5m there and this is
    1h - but the first call to `klines(sym, "1h")` would read this file as its
    own cache and KeyError on a missing column, which is a miserable thing to
    debug months later. Separate namespace, no shared state.
    """
    out = FEEDS / f"{sym}_perpbars_{tf}.parquet"
    if out.exists():
        have = pd.read_parquet(out)
        if len(have) and have.index.min() <= pd.Timestamp(first, tz="UTC"):
            return have
    months = pd.period_range(pd.Period(first, freq="M"),
                             pd.Period(date.today() - timedelta(days=1), freq="M"),
                             freq="M")
    with requests.Session() as s, ThreadPoolExecutor(WORKERS) as ex:
        urls = [f"{BASE}/monthly/klines/{sym}/{tf}/{sym}-{tf}-{m}.zip"
                for m in months]
        raw = [g for g in ex.map(lambda u: _one(u, s), urls)
               if g is not None and len(g)]
    if not raw:
        return pd.DataFrame()
    df = _frame(raw)
    df = df[~df.index.duplicated(keep="last")]
    df.to_parquet(out)
    return df


def build(sym: str, tf: str = "1h", force: bool = False) -> pd.DataFrame:
    """The term-structure series for one market.

    At every hour the FRONT contract is the nearest settlement more than
    MIN_DAYS away, and the BACK contract is the one after it. `days` is to the
    front's settlement, so `basis_ann` is comparable across the roll.
    """
    out = FEEDS / f"{sym}_termstruct_{tf}.parquet"
    if out.exists() and not force:
        return pd.read_parquet(out).sort_index()

    p = perp(sym, tf)
    if not len(p):
        raise RuntimeError(f"no perp bars for {sym}")
    print(f"  {sym} perp: {len(p):,} bars "
          f"{p.index[0]:%Y-%m-%d} -> {p.index[-1]:%Y-%m-%d}", flush=True)

    closes: dict[str, pd.Series] = {}
    for code in CODES:
        d = contract(sym, code, tf)
        if len(d):
            closes[code] = d.close
        print(f"  {sym}_{code}: {len(d):,} bars", flush=True)
    if not closes:
        raise RuntimeError(f"no dated contracts for {sym}")

    idx = p.index
    front = pd.Series(index=idx, dtype="float64")
    back = pd.Series(index=idx, dtype="float64")
    days = pd.Series(index=idx, dtype="float64")
    code_col = pd.Series(index=idx, dtype="object")

    exp = {c: pd.Timestamp(expiry_of(c)) for c in CODES}
    order = sorted(closes, key=lambda c: exp[c])
    for i, c in enumerate(order):
        d_front = (exp[c] - idx).total_seconds() / 86400.0
        # NEAREST EXPIRY WITH DATA WINS, and iterating in expiry order while
        # requiring `front.isna()` is sufficient on its own: a nearer contract
        # that had a bar here has already claimed it. An explicit "the previous
        # contract has rolled" test was written and removed - it ALSO blocked
        # this contract on every bar where the nearer one existed but had not
        # listed yet, silently dropping the earliest weeks of every cycle.
        is_front = (d_front > MIN_DAYS) & front.isna()
        s = closes[c].reindex(idx)
        front = front.where(~(is_front & s.notna()), s)
        days = days.where(~(is_front & s.notna()), pd.Series(d_front, index=idx))
        code_col = code_col.where(~(is_front & s.notna()), c)
        if i + 1 < len(order):
            nxt = closes[order[i + 1]].reindex(idx)
            back = back.where(~(is_front & nxt.notna()), nxt)

    df = pd.DataFrame({
        # No `if "open" in p else p.close` fallback on purpose: a missing open
        # must raise here, not quietly become the close and turn every entry
        # into a look-ahead. See the note in `_frame`.
        "open": p.open,
        "close": p.close, "volume": p.volume,
        "front": front, "back": back, "days": days, "code": code_col,
    })
    df["basis_bps"] = (df.front - df.close) / df.close * 1e4
    df["basis_ann"] = (df.front - df.close) / df.close * (365.0 / df.days) * 100.0
    df["slope_bps"] = (df.back - df.front) / df.close * 1e4
    df = df.dropna(subset=["basis_ann"])
    df.to_parquet(out)
    print(f"  {sym} termstruct: {len(df):,} hourly rows "
          f"{df.index[0]:%Y-%m-%d} -> {df.index[-1]:%Y-%m-%d}, "
          f"slope on {df.slope_bps.notna().sum():,}", flush=True)
    return df


def main(argv: list[str]) -> int:
    syms = argv[1:] or list(MARKETS)
    for s in syms:
        build(s, force="--force" in argv)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
