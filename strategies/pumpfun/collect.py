"""H-048 — the pump.fun launch collector. Builds the dataset that does not exist.

WHY A COLLECTOR AND NOT A BACKTEST. Kris: *"try something with pump.fun maybe
follow whales maybe follow telegram accounts"*. Probed 2026-09-17, and the
blocker is the population, not the idea:

    frontend-api-v3.pump.fun/coins   offset 500 -> 2026-09-17T07:05  (39 min back)
                                     offset 2000 -> EMPTY
    /coins/{mint}                    works for ANY mint, at any age
    /trades/...                      404 - the trade endpoint is gone
    GeckoTerminal OHLCV              1000 hourly bars a call, pages back fine

So **prices are available and the list of historical launches is not**: the API
serves about forty minutes of launch history, and wallet-level trades - real
whale following - need a Solana archive node, which costs money. What is free is
enough to build the dataset going forward, and that is what this does. Two to
four weeks of collection makes the test below possible; nothing makes it
possible today.

WHAT IT COLLECTS, AND WHY THOSE FIELDS. `creator` is in every record, which is
what turns "follow whales" into something testable without an archive node:
**follow the DEPLOYER, not the buyer.** `ath_market_cap` and `complete` are the
outcome, so a launch can be scored without holding a position in it.

THE HYPOTHESIS THIS IS FOR, stated now so the collection is not fitted later:

    Does a creator's TRACK RECORD predict their next launch?

Rank creators by the ATH market cap of their previous launches; test whether the
next one does better than a creator with no record. If prior success does not
predict even the ATH - a number nobody could actually sell at - it will not
predict a tradeable return, and the idea is dead without needing a price feed.

Run:  .venv/bin/python strategies/pumpfun/collect.py          one pass
      .venv/bin/python strategies/pumpfun/collect.py loop 900 every 15 min
"""
from __future__ import annotations

import json
import sys
import time
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "pumpfun"
NEW = OUT / "launches.jsonl"       # first sighting of each mint, append-only
SNAP = OUT / "snapshots.jsonl"     # outcome re-reads, so ATH and graduation land
API = "https://frontend-api-v3.pump.fun/coins"
UA = {"User-Agent": "Mozilla/5.0"}
#: fields kept. Everything else on the record is presentation (images, banners).
#: `metadata_uri` is the one that matters for the socials question and it was
#: MISSING from the first version of this list, so the first 225 launches have
#: no link to their Twitter. Every pass without it loses data that cannot be
#: recovered later, because the API only reaches back forty minutes.
#: `market_cap` is denominated in SOL and `ath_market_cap` in USD - they are not
#: the same unit and dividing one by the other gives the SOL price, not a return.
KEEP = ("mint", "creator", "symbol", "name", "created_timestamp",
        "market_cap", "ath_market_cap", "ath_market_cap_timestamp",
        "reply_count", "complete", "last_trade_timestamp", "nsfw",
        "is_banned", "real_sol_reserves", "total_supply",
        "metadata_uri", "image_uri", "bonding_curve", "pool_address",
        "virtual_sol_reserves", "virtual_token_reserves")


def _get(url: str, tries: int = 3):
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read())
        except Exception:
            time.sleep(2 * (i + 1))
    return None


def seen() -> set[str]:
    if not NEW.exists():
        return set()
    return {json.loads(l)["mint"] for l in NEW.read_text().splitlines() if l.strip()}


def page(limit: int = 500, offset: int = 0) -> list[dict]:
    d = _get(f"{API}?limit={limit}&offset={offset}"
             f"&sort=created_timestamp&order=DESC")
    return d if isinstance(d, list) else []


def collect(max_offset: int = 1500) -> tuple[int, int]:
    """One pass. Returns (new launches, records re-snapshotted).

    Paging stops at 1500 because the API returns empty beyond ~2000 - measured,
    not assumed. At roughly 500 launches per 39 minutes a 15-minute cadence
    leaves a wide margin, so nothing is missed between passes.
    """
    OUT.mkdir(parents=True, exist_ok=True)
    known = seen()
    now = datetime.now(UTC).isoformat()
    fresh, snaps = [], []
    for off in range(0, max_offset, 500):
        rows = page(500, off)
        if not rows:
            break
        for c in rows:
            rec = {k: c.get(k) for k in KEEP}
            rec["seen_at"] = now
            if rec["mint"] not in known:
                known.add(rec["mint"])
                fresh.append(rec)
            snaps.append(rec)
        time.sleep(1.0)                      # be a polite client
    if fresh:
        with NEW.open("a") as f:
            for r in fresh:
                f.write(json.dumps(r) + "\n")
    if snaps:
        with SNAP.open("a") as f:
            for r in snaps:
                f.write(json.dumps(r) + "\n")
    return len(fresh), len(snaps)


def main() -> int:
    if len(sys.argv) > 2 and sys.argv[1] == "loop":
        every = int(sys.argv[2])
        while True:
            n, s = collect()
            print(f"{datetime.now(UTC):%Y-%m-%d %H:%M:%S}  +{n} new  "
                  f"{s} snapshots  total {len(seen())}", flush=True)
            time.sleep(every)
    n, s = collect()
    print(f"+{n} new launches, {s} snapshots, {len(seen())} mints known")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
