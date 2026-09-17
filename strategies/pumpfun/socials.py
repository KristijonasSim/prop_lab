"""Resolve each launch's IPFS metadata into its social links.

WHY A SEPARATE PASS. IPFS is slow and flaky and the launch collector must not
block on it - a missed collector pass is data that cannot be recovered, because
the pump.fun API only reaches back forty minutes. This runs behind it and
backfills.

WHICH GATEWAY. `ipfs.io` - the host in every `metadata_uri` - now serves a
"switching to a service worker gateway" notice instead of the file, so the URI
as published is dead for a script. `pump.mypinata.cloud` serves the same CID and
is what pump.fun's own frontend uses.

WHAT IT IS FOR. Kris: *"maybe twitter read some twitter pump.fun or simillar
channels searching for coins"*. Reading Twitter itself needs a paid API key, but
**whether a coin has socials at all, and which, is free and is captured here** -
and it is the cheap half of that question: a launch with a real account attached
is a different population from one without.

Run: .venv/bin/python strategies/pumpfun/socials.py
"""
from __future__ import annotations

import json
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "pumpfun"
NEW = OUT / "launches.jsonl"
DEST = OUT / "socials.jsonl"
GATEWAY = "https://pump.mypinata.cloud/ipfs/"
UA = {"User-Agent": "Mozilla/5.0"}
FIELDS = ("twitter", "telegram", "website", "coin_community", "description")


def cid(uri: str) -> str | None:
    return uri.rsplit("/ipfs/", 1)[-1] if "/ipfs/" in uri else None


def one(rec: dict) -> dict | None:
    c = cid(rec.get("metadata_uri") or "")
    if not c:
        return None
    try:
        req = urllib.request.Request(GATEWAY + c, headers=UA)
        with urllib.request.urlopen(req, timeout=20) as r:
            d = json.loads(r.read())
    except Exception:
        return None
    low = {k.lower(): v for k, v in d.items()}
    out = {"mint": rec["mint"], "creator": rec.get("creator")}
    for f in FIELDS:
        v = low.get(f)
        out[f] = str(v)[:400] if v else None
    out["has_twitter"] = bool(out["twitter"])
    out["n_socials"] = sum(1 for f in ("twitter", "telegram", "website")
                           if out[f])
    return out


def main() -> int:
    done = set()
    if DEST.exists():
        done = {json.loads(l)["mint"] for l in DEST.read_text().splitlines() if l.strip()}
    rows = [json.loads(l) for l in NEW.read_text().splitlines() if l.strip()]
    todo = [r for r in rows if r.get("metadata_uri") and r["mint"] not in done]
    print(f"{len(rows)} launches, {len(done)} already resolved, {len(todo)} to do",
          flush=True)
    if not todo:
        return 0
    with ThreadPoolExecutor(12) as ex:
        got = [x for x in ex.map(one, todo) if x]
    with DEST.open("a") as f:
        for r in got:
            f.write(json.dumps(r) + "\n")
    tw = sum(1 for r in got if r["has_twitter"])
    print(f"resolved {len(got)}/{len(todo)}   with a Twitter link: {tw} "
          f"({tw/max(1,len(got))*100:.1f}%)")
    import collections
    print("socials per coin:", dict(collections.Counter(r["n_socials"] for r in got)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
