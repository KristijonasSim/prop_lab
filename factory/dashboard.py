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
    # THE PASS IN FLIGHT COUNTS TOO. A run record is written when a pass
    # FINISHES, so on the first run of a fresh install this panel sat empty for
    # nineteen minutes while the thing it measures was happening on screen.
    # The heartbeat carries the running tally, so it is added here.
    if live.is_live():
        for k, v in (live.read().counts.get("gates") or {}).items():
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
