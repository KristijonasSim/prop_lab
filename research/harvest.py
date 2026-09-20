"""Keep the feed cache current. The only thing here that touches the network.

WHY IT IS SEPARATE FROM EVERYTHING ELSE. `research/vocab.py` loads from disk and
never fetches, so a screen run can never be changed by a download happening
underneath it, and a study is reproducible from the cache alone. This file is
the only door to the outside.

WHAT IT REFRESHES. The free, no-key, daily series the registry already carries:
FRED (real yield, broad dollar, breakeven) and CBOE (GVZ, VIX, VIX3M). All of
them are plain CSV over HTTPS.

**REVISIONS ARE THE TRAP AND THEY ARE NOT HANDLED.** FRED restates. A value
downloaded today for a date last month may not be the value that was published
that day, and this cache keeps only the latest vintage. H-035 died on exactly
this - every value was `flash`, revised later, and only the current value was
ever served. So a result from these feeds is an UPPER BOUND on what was
tradeable, and any survivor must be re-checked against a point-in-time vintage
(ALFRED) before it is believed. The registry's `revised` flag marks which.

WHAT IS NOT HERE YET, AND IT IS THE BIGGEST ITEM ON THE PAGE. Dukascopy publishes
hourly XAUUSD tick files carrying ask, bid, **ask volume and bid volume**, and
`core/fx_spread.py` has been downloading them all along while discarding the two
volume fields on line 106. That is a real two-sided volume series on the one
market whose round trip is 1.83 bps. It is ~19k files for three years, so it is a
job with a worker pool rather than a line in this file - but it is the single
highest-value untested input this project has, and the loop should get it next.
"""
from __future__ import annotations

import argparse
import shutil
import sys
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from research import vocab                                       # noqa: E402

DATA = ROOT / "data"
FRED = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}&cosd={start}"
CBOE = "https://cdn.cboe.com/api/global/us_indices/daily_prices/{sym}_History.csv"
START = "2015-01-01"
TIMEOUT = 60

#: Per-source User-Agent, and this is NOT cosmetic.
#:
#: Measured 2026-09-18, same URL, four agents, 20s timeout:
#:
#:     (default python-urllib)   OK  48,956 bytes in 0.5s
#:     "prop_lab"                TimeoutError after 20.2s
#:     "Mozilla/5.0 (X11; ...)"  TimeoutError after 20.2s
#:     "curl/8.5.0"              OK  48,956 bytes in 0.4s
#:
#: FRED's CSV endpoint HANGS on a browser-like or unrecognised agent and serves
#: tool agents immediately - anti-scraping that fails closed rather than with a
#: 403, so it looks exactly like a network problem. The first version of this
#: file sent "prop_lab" to everything and reported three feeds down.
#: `None` means send no header at all and let urllib use its default.
AGENT: dict[str, str | None] = {"fred": None, "cboe": "prop_lab"}

#: feed name -> (url, destination under data/)
SOURCES: dict[str, tuple[str, str]] = {
    "DFII10": (FRED.format(sid="DFII10", start=START), "macro/DFII10.csv"),
    "DTWEXBGS": (FRED.format(sid="DTWEXBGS", start=START), "macro/DTWEXBGS.csv"),
    "T10YIE": (FRED.format(sid="T10YIE", start=START), "macro/T10YIE.csv"),
    "GVZ": (CBOE.format(sym="GVZ"), "vix/GVZ.csv"),
    "VIX": (CBOE.format(sym="VIX"), "vix/VIX.csv"),
    "VIX3M": (CBOE.format(sym="VIX3M"), "vix/VIX3M.csv"),
}


@dataclass
class Harvest:
    feed: str
    status: str          # fresh | updated | failed | skipped
    rows_before: int = 0
    rows_after: int = 0
    note: str = ""

    def __str__(self) -> str:
        d = self.rows_after - self.rows_before
        delta = f"{d:+d}" if d else "  ="
        return f"  {self.feed:14}{self.status:9}{self.rows_after:>7} rows {delta}  {self.note}"


def _rows(name: str) -> int:
    try:
        return len(vocab.FEEDS[name].load())
    except Exception:                                    # noqa: BLE001
        return 0


def fetch_one(name: str, force: bool = False) -> Harvest:
    """Download one feed into the cache, keeping the old copy until it parses.

    A truncated or rate-limited download that overwrites a good cache is worse
    than no download, so the new bytes are written beside the old file and only
    moved into place once `vocab` can load them and they are not SHORTER than
    what is already there.
    """
    if name not in SOURCES:
        return Harvest(name, "skipped", note="no source registered")
    url, rel = SOURCES[name]
    dest = DATA / rel
    before = _rows(name)
    if dest.exists() and not force:
        age = (datetime.now(timezone.utc).timestamp() - dest.stat().st_mtime)
        if age < 12 * 3600:
            return Harvest(name, "fresh", before, before, "cached < 12h")

    tmp = dest.with_suffix(dest.suffix + ".new")
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        ua = AGENT["fred" if "stlouisfed" in url else "cboe"]
        req = urllib.request.Request(
            url, headers={"User-Agent": ua} if ua else {})
        raw = urllib.request.urlopen(req, timeout=TIMEOUT).read()
        if len(raw) < 200:
            return Harvest(name, "failed", before, before,
                           f"response only {len(raw)} bytes")
        tmp.write_bytes(raw)
        keep = dest.with_suffix(dest.suffix + ".bak") if dest.exists() else None
        if keep:
            shutil.copy2(dest, keep)
        shutil.move(tmp, dest)
        after = _rows(name)
        if after == 0 or (before and after < before * 0.9):
            if keep:
                shutil.move(keep, dest)
            return Harvest(name, "failed", before, before,
                           f"new copy had {after} rows, kept the old one")
        if keep and keep.exists():
            keep.unlink()
        return Harvest(name, "updated", before, after)
    except Exception as exc:                             # noqa: BLE001
        if tmp.exists():
            tmp.unlink()
        return Harvest(name, "failed", before, before,
                       f"{type(exc).__name__}: {str(exc)[:80]}")


def harvest_all(force: bool = False) -> list[Harvest]:
    return [fetch_one(n, force) for n in SOURCES]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--force", action="store_true", help="ignore the 12h cache")
    ap.add_argument("--feed", help="just this one")
    a = ap.parse_args(argv)

    out = ([fetch_one(a.feed, a.force)] if a.feed else harvest_all(a.force))
    print(f"{'feed':16}{'status':9}{'rows':>12}")
    for h in out:
        print(h)
    bad = [h for h in out if h.status == "failed"]
    print(f"\n{len(out) - len(bad)}/{len(out)} ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
