"""THE FACTORY FLOOR — one page that says what is happening, live.

Kris, 2026-09-23: *"i want to have UI where i can see all 7 steps as in
workflow... i want to launch that page and understand everything what is going
on there."*

    python -m factory.dashboard              # serve on http://127.0.0.1:8765
    python -m factory.dashboard --once       # print the state as JSON and exit

WHY A LOCAL SERVER AND NOT A HOSTED PAGE. Every number on it is read from this
machine - `backtests/factory/live.json`, `runs.jsonl`, `queue.jsonl`,
`tried.jsonl` - and a page hosted anywhere else cannot see them. The server is
`http.server` from the standard library, binds to localhost only, and serves
two things: the page, and `/api/state`.

WHAT IT REFUSES TO DO. It does not run the factory and it has no route that
starts one. A dashboard that can launch a pass is a dashboard that launches one
by accident, on a box that also runs a live bot. Start passes with
`factory.nightly`; this only watches.
"""
from __future__ import annotations

import json
import sys
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from factory import live, nightly, queue                            # noqa: E402
from factory.sources import catalogue                               # noqa: E402

UI = Path(__file__).resolve().parent / "ui" / "index.html"
HOST, PORT = "127.0.0.1", 8765


def _survivors(limit: int = 12) -> list[dict]:
    out = []
    for r in reversed(nightly.history(200)):
        for s in (r.get("survivors") or []):
            out.append({**s, "when": r.get("started", "")})
            if len(out) >= limit:
                return out
    return out


def _candidates(limit: int = 8) -> list[dict]:
    out = []
    for r in reversed(nightly.history(200)):
        for c in (r.get("step7") or []):
            out.append({**c, "when": r.get("started", "")})
            if len(out) >= limit:
                return out
    return out


def _gates() -> dict:
    """Which gate is killing things, summed over every recorded pass.

    THE DIAGNOSIS, not decoration. 87% of cell-tests die on trade count and
    nothing downstream can repair that; a funnel that shows only "20 in, 1 out"
    hides the one fact that says what to fix next.
    """
    total = {"trades": 0, "cost": 0, "concentration": 0, "drift": 0, "other": 0}
    for r in nightly.history(1000):
        for k, v in (r.get("gates") or {}).items():
            if k in total:
                total[k] += v
    # THE PASS IN FLIGHT COUNTS TOO - BUT ONLY WHILE IT IS IN FLIGHT. A run
    # record is written when a pass FINISHES, so without this the panel sits
    # empty for the whole of the first pass while the thing it measures is
    # happening on screen. The trap: the FINAL beat of a pass is `resting`,
    # which is still "live", and its counts are the same ones already in the
    # record - so a finished pass was counted twice and Kris's single script
    # reported 46 cell-tests out of a possible 24. `step > 0` means a pass is
    # actually mid-flight; `resting` and `idle` both carry step 0.
    b = live.read()
    if b.step > 0 and live.is_live(b):
        for k, v in (b.counts.get("gates") or {}).items():
            if k in total:
                total[k] += v
    return total


def _funnel() -> dict:
    """Ideas in, survivors out, summed across every pass on record."""
    f = {"ideas": 0, "step3_pass": 0, "step4_repaired": 0,
         "step6_pass": 0, "step7": 0}
    for r in nightly.history(1000):
        f["ideas"] += r.get("ideas", 0)
        f["step3_pass"] += r.get("step3_pass", 0)
        f["step4_repaired"] += r.get("step4_repaired", 0)
        f["step6_pass"] += r.get("step6_pass", 0)
        f["step7"] += len(r.get("step7") or [])
    return f


def _last_null() -> dict | None:
    for r in reversed(nightly.history(200)):
        if r.get("step5"):
            return {**r["step5"], "when": r.get("started", "")}
    return None


def _fingerprint(row: dict) -> str:
    """WHAT the idea does, from a raw record, so one idea counts once.

    `spec.Strategy.fingerprint` is the real definition; this reproduces it from
    the stored dict rather than rebuilding a Strategy, because a row may be a
    survivor record, a death record, or a carried stub with fields missing.
    """
    try:
        terms = sorted(
            f"{c['left'].get('kind')}{c['left'].get('length') or ''}"
            f" {c['op']} "
            f"{c['right'].get('kind')}{c['right'].get('length') or ''}"
            f"{'' if c['right'].get('kind') != 'const' else c['right'].get('value')}"
            f"{'' if int(c.get('hold', 1) or 1) <= 1 else ' x' + str(c['hold'])}"
            for c in row.get("entry", []))
    except (AttributeError, KeyError, TypeError):
        return str(row.get("name", id(row)))
    return (f"{row.get('side')}|{'&'.join(terms)}|{row.get('stop_atr')}"
            f"|{row.get('target_atr')}|{row.get('max_hold')}")


def per_source() -> list[dict]:
    """One row per source: found, tested, where they died, what survived.

    Kris, 2026-09-23: *"its not really possible to see how many strategies were
    found in tradingview, how many tested, how many passed / failed."* This is
    that table, and it is built from the RECORDS rather than from the run
    summaries - a run record knows how many ideas it took, not which source
    each one came from once they are mixed in a batch.

    Every source in the catalogue appears even with nothing against it. A
    source missing from the page is indistinguishable from a source that found
    nothing, and the whole point of the catalogue is to say which is which.
    """
    # Rows flagged `carried` are fingerprints kept by `factory.reset` so an
    # archived idea is never re-tested. They are not results of this board and
    # counting them would make a cleared board report 158 tested ideas.
    tried = [r for r in queue.rows(queue.TRIED) if not r.get("carried")]
    kept = [r for r in queue.rows(queue.SURVIVORS) if not r.get("carried")]
    waiting = queue.rows(queue.QUEUE)

    # SCRIPTS READ IS NOT IDEAS FOUND, and the difference is the point.
    # A source can read a script and refuse it: `boxes_pro` was read, understood
    # and correctly rejected, and with only `found` on the page TradingView
    # showed 0 - indistinguishable from a source nobody had pointed at anything.
    refused = queue.rows(queue.DIR / "skipped.jsonl")

    keys = {c.key for c in catalogue.CATALOGUE}
    keys |= {r.get("source", "?") for r in tried + kept + waiting}
    keys |= {r.get("source", "?") for r in refused}

    out = []
    for key in sorted(keys, key=lambda k: catalogue.get(k).order):
        src = catalogue.get(key)
        t = [r for r in tried if r.get("source") == key]
        k = [r for r in kept if r.get("source") == key]
        w = [r for r in waiting if r.get("source") == key]
        ref = [r for r in refused if r.get("source") == key]

        # COUNT IDEAS, NOT ROWS. One idea writes to BOTH files when it passes
        # step 3 and then fails step 6 - `keep` records the survivor and
        # `mark_tried` records the death - so summing the files reported Kris's
        # single translated script as two tested ideas. Keyed by fingerprint,
        # each idea appears once and carries the furthest stage it reached.
        seen: dict[str, dict] = {}
        for r in k + t:                       # survivors first, deaths second
            fp = _fingerprint(r)
            e = seen.setdefault(fp, {"reached": 0, "died_at": 0, "gate": ""})
            if "reached" in r:
                e["reached"] = max(e["reached"], int(r.get("reached") or 3))
            if r.get("died_at"):
                e["died_at"] = int(r["died_at"])
                e["gate"] = r.get("gate") or "other"

        gates = {}
        for e in seen.values():
            if e["died_at"] == 3:
                g = e["gate"] or "other"
                gates[g] = gates.get(g, 0) + 1

        tested = len(seen)
        out.append({
            "read": len(w) + tested + len(ref),
            "refused": len(ref),
            "gaps": sum(1 for r in ref if r.get("gap")),
            "key": key, "label": src.label, "how": src.how,
            "status": src.status, "note": src.note,
            "waiting": len(w),
            "found": len(w) + tested,
            "tested": tested,
            "passed3": sum(1 for e in seen.values() if e["reached"] >= 3),
            "repaired4": sum(1 for e in seen.values() if e["reached"] == 4),
            "held6": sum(1 for e in seen.values() if e["reached"] >= 7),
            "scored7": sum(1 for e in seen.values() if e["reached"] >= 7),
            "failed": sum(1 for e in seen.values() if e["died_at"]),
            "failed_at_3": sum(1 for e in seen.values() if e["died_at"] == 3),
            "failed_at_6": sum(1 for e in seen.values() if e["died_at"] == 6),
            "gates": gates,
        })
    return out


def gaps() -> list[dict]:
    """Scripts a source could read but the GRAMMAR could not express.

    The most actionable thing the factory produces. The enumerator's grammar
    holds 308 combinations in total; a named gap is a term that multiplies that
    rather than adding to it, and these come from scripts people actually
    trade. They were being printed to a terminal and lost.
    """
    return queue.rows(queue.DIR / "skipped.jsonl")


def state() -> dict:
    """Everything the page draws, in one object."""
    b = live.read()
    runs = nightly.history(40)
    return {
        "now": time.time(),
        "live": live.is_live(b),
        "uptime_s": live.uptime(b),
        "beat": b.to_dict(),
        "steps": [{"n": n, "name": name, "detail": d} for n, name, d in live.STEPS],
        "queue": queue.status(),
        "funnel": _funnel(),
        "gates": _gates(),
        "by_source": nightly.by_source(),
        "sources": per_source(),
        "gaps": gaps(),
        "step5": _last_null(),
        "survivors": _survivors(),
        "candidates": _candidates(),
        "runs": [{"started": r.get("started"), "ideas": r.get("ideas", 0),
                  "step3": r.get("step3_pass", 0),
                  "step4": r.get("step4_repaired", 0),
                  "step6": r.get("step6_pass", 0),
                  "step7": len(r.get("step7") or []),
                  "seconds": r.get("seconds", 0),
                  "p_value": (r.get("step5") or {}).get("p_value")}
                 for r in reversed(runs)],
        "passes": len(nightly.history(10_000)),
    }


class _Handler(BaseHTTPRequestHandler):
    def _send(self, body: bytes, ctype: str) -> None:
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):                                    # noqa: N802
        if self.path.startswith("/api/state"):
            self._send(json.dumps(state()).encode(), "application/json")
        elif self.path in ("/", "/index.html"):
            if not UI.exists():
                self._send(b"factory/ui/index.html is missing", "text/plain")
            else:
                self._send(UI.read_bytes(), "text/html; charset=utf-8")
        else:
            self.send_error(404)

    def log_message(self, *a):                           # noqa: D102
        pass                       # a polling dashboard would fill the console


def serve(host: str = HOST, port: int = PORT) -> None:
    srv = HTTPServer((host, port), _Handler)
    print(f"factory floor on http://{host}:{port}   (ctrl-c to stop)")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")


def _main(argv=None) -> int:
    import argparse

    ap = argparse.ArgumentParser(description="Watch the factory.")
    ap.add_argument("--host", default=HOST)
    ap.add_argument("--port", type=int, default=PORT)
    ap.add_argument("--once", action="store_true", help="print state, exit")
    a = ap.parse_args(argv)
    if a.once:
        print(json.dumps(state(), indent=2))
        return 0
    serve(a.host, a.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
