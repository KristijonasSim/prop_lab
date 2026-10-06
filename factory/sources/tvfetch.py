"""SOURCE 1, the fetching half — pull open-source Pine scripts off TradingView.

Kris, 2026-09-28: *"yes please build it on tradingview first we need to test
everything from there firstly"* - after being told the terms of service
discourage automated collection and the risk is a blocked IP. His call.

    python -m factory.sources.tvfetch -n 40          # 40 new scripts
    python -m factory.sources.tvfetch --status

HOW. Two public, login-free endpoints:

    listing  www.tradingview.com/scripts/page-N/?script_type=strategies&script_access=open
             24 scripts a page, ~40-60 pages deep, newest first. Each card
             carries `script_id_part` = PUB;<hex>.
    source   pine-facade.tradingview.com/pine-facade/get/PUB;<hex>/last
             JSON with `source` for open scripts. Protected / invite-only
             scripts come back without it and are recorded as such.

POLITE BY CONSTRUCTION. One request every `DELAY` seconds, a browser UA, and a
hard stop on 403/429 - a block is the one outcome that ends this source, so
the fetcher backs off rather than pushes. Strategies are read before
indicators: a strategy names its own entries, an indicator usually does not.

EVERY ID IS RECORDED ONCE, whatever happened to it (`tv_seen.jsonl`), so a
script is never downloaded twice and never re-translated - the model call is
the expensive half.
"""
from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PINE_DIR = ROOT / "data" / "pine"
SEEN = ROOT / "backtests" / "factory" / "tv_seen.jsonl"

UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/128.0 Safari/537.36")
LIST_URL = "https://www.tradingview.com/scripts/{page}?script_type={kind}&script_access=open"
SRC_URL = "https://pine-facade.tradingview.com/pine-facade/get/{pid}/last?no_4xx=true"
#: Seconds between any two requests. ~700 requests an hour at most.
DELAY = 5.0
KINDS = ("strategies", "indicators")
MAX_PAGES = 60

_CARD = re.compile(r'"chart_url":"(https://www\.tradingview\.com/script/[^"]+)"'
                   r'.{0,800}?"script_type":"(\w+)"'
                   r'.{0,200}?"script_id_part":"(PUB;[0-9a-f]+)"', re.S)


class Blocked(RuntimeError):
    """TradingView refused us. Stop the source, do not retry harder."""


_last = [0.0]


def _get(url: str, timeout: int = 30) -> tuple[int, bytes]:
    wait = DELAY - (time.time() - _last[0])
    if wait > 0:
        time.sleep(wait)
    _last[0] = time.time()
    req = urllib.request.Request(url, headers={"User-Agent": UA,
                                               "Accept-Language": "en-US,en"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        if e.code in (403, 429):
            raise Blocked(f"HTTP {e.code} on {url}") from e
        return e.code, b""


def listing(kind: str, page: int) -> list[dict]:
    """One listing page -> [{id, url, kind}]. Empty past the last page."""
    p = "" if page == 1 else f"page-{page}/"
    code, body = _get(LIST_URL.format(page=p, kind=kind))
    if code != 200:
        return []
    out, seen = [], set()
    for m in _CARD.finditer(body.decode("utf-8", "ignore")):
        url, typ, pid = m.groups()
        if pid not in seen:
            seen.add(pid)
            out.append({"id": pid, "url": url, "kind": typ})
    return out


def source(pid: str) -> dict:
    """The script's JSON from pine-facade; `{}` on anything unexpected."""
    code, body = _get(SRC_URL.format(pid=urllib.parse.quote(pid, safe="")))
    if code != 200:
        return {}
    try:
        return json.loads(body)
    except ValueError:
        return {}


def seen() -> dict[str, dict]:
    if not SEEN.exists():
        return {}
    out = {}
    for line in SEEN.read_text().splitlines():
        try:
            r = json.loads(line)
            out[r["id"]] = r
        except (ValueError, KeyError):
            continue
    return out


def _mark(row: dict) -> None:
    SEEN.parent.mkdir(parents=True, exist_ok=True)
    row["when"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with SEEN.open("a") as fh:
        fh.write(json.dumps(row, separators=(",", ":")) + "\n")


def _slug(url: str) -> str:
    tail = url.rstrip("/").rsplit("/", 1)[-1]           # 0DGERJtx-Some-Name
    s = re.sub(r"[^A-Za-z0-9]+", "_", tail).strip("_").lower()
    return s[:70]


def fetch(n: int = 40, kinds=KINDS, max_pages: int = MAX_PAGES,
          folder: Path | None = None, log=print) -> list[Path]:
    """Download up to `n` NEW open-source scripts. Returns the files written.

    Walks listing pages in order and skips anything already in `tv_seen`, so a
    second call continues where the first stopped (cheaply: a known page costs
    one request and no source fetches).
    """
    folder = folder or PINE_DIR
    folder.mkdir(parents=True, exist_ok=True)
    known = seen()
    written: list[Path] = []
    for kind in kinds:
        for page in range(1, max_pages + 1):
            cards = listing(kind, page)
            if not cards:
                break
            for c in cards:
                if c["id"] in known:
                    continue
                d = source(c["id"])
                src, access = d.get("source"), str(d.get("scriptAccess", ""))
                row = {"id": c["id"], "url": c["url"], "kind": c["kind"],
                       "name": d.get("scriptName", "")}
                if not src or not access.startswith("open"):
                    row["status"] = f"no source ({access or 'unreadable'})"
                else:
                    p = folder / f"tv_{_slug(c['url'])}.pine"
                    head = (f"// prop_lab: fetched from TradingView "
                            f"{datetime.now(timezone.utc):%Y-%m-%d}\n// url: {c['url']}\n// id: {c['id']}  kind: {c['kind']}\n")
                    p.write_text(head + src.replace("\r\n", "\n"))
                    row["status"], row["file"] = "saved", p.name
                    written.append(p)
                _mark(row)
                known[c["id"]] = row
                log(f"  {row['status']:<22} {row['name'][:60]}")
                if len(written) >= n:
                    return written
    return written


def status() -> dict:
    rows = list(seen().values())
    out: dict[str, int] = {}
    for r in rows:
        k = "saved" if r.get("status") == "saved" else "no source"
        out[k] = out.get(k, 0) + 1
    return {"seen": len(rows), **out}


def _main(argv=None) -> int:
    import argparse

    ap = argparse.ArgumentParser(description="Download open Pine scripts from TradingView.")
    ap.add_argument("-n", type=int, default=40)
    ap.add_argument("--kind", action="append", choices=KINDS)
    ap.add_argument("--status", action="store_true")
    a = ap.parse_args(argv)
    if a.status:
        print(json.dumps(status(), indent=2))
        return 0
    got = fetch(a.n, tuple(a.kind) if a.kind else KINDS)
    print(f"\n{len(got)} new scripts in {PINE_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
