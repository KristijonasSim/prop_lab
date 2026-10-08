"""FINISH THE TRADINGVIEW LIST IN DAYS, NOT WEEKS.

Kris, 2026-10-08: *"i want to be done with tradingview in 2-3 days max"*.
`tvloop` does one thing at a time: download 20, translate them one by one,
test them, rest. This splits the two halves so they overlap:

    python -m factory.harvest -w 4      # download + translate, 4 model calls at once
    python -m factory.drain -j 12       # test, on every core (run alongside)

Steps 1-2 only - nothing here tests. Same fetch order (`tvfetch.MODE`, most
liked gold/FX first), same translator, same queue, same skip records as
`tvloop.intake`, so a script read here is indistinguishable from one read there.
When the model hits its usage limit it waits and carries on.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from factory import queue                                             # noqa: E402
from factory.sources import tradingview, tvfetch                      # noqa: E402
from factory.tvloop import _limited                                   # noqa: E402

LIMIT_WAIT = 30 * 60


_retried: set[str] = set()


def once(n: int, workers: int) -> dict:
    # Scripts a model crash or usage limit refused go first, as in tvloop.
    got, skipped = tradingview.retry(limit=n, workers=workers, exclude=_retried)
    _retried.update(k for k, why in skipped if not _limited([(k, why)]))
    if got or skipped:
        return {"fetched": -1, "retried": len(got) + len(skipped),
                "queued": queue.add(got, quiet=True)["added"] if got else 0,
                "limited": _limited(skipped)}
    files = tvfetch.fetch(n)
    out = {"fetched": len(files)}
    if not files:
        return out
    got, skipped = tradingview._read_all(sorted(files), ai=True, model=None,
                                         workers=workers)
    tradingview.record_skips(skipped, translated={p.stem for p in files}
                             - {k for k, _ in skipped})
    out.update(translated=len(got), skipped=len(skipped),
               queued=queue.add(got, quiet=True)["added"] if got else 0,
               limited=_limited(skipped))
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("-n", type=int, default=20, help="scripts per batch")
    ap.add_argument("-w", "--workers", type=int, default=4)
    a = ap.parse_args(argv)
    while True:
        t = time.time()
        try:
            r = once(a.n, a.workers)
        except tvfetch.Blocked as exc:
            print(json.dumps({"blocked": str(exc)}), flush=True)
            return 1
        r["seconds"] = round(time.time() - t)
        print(json.dumps(r), flush=True)
        if not r["fetched"]:
            print(json.dumps({"done": "ranked list exhausted"}), flush=True)
            return 0
        if r.get("limited"):
            time.sleep(LIMIT_WAIT)


if __name__ == "__main__":
    raise SystemExit(main())
