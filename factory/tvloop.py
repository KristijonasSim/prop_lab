"""THE TRADINGVIEW RUN — fetch, translate, test, repeat, for a fixed time.

Kris, 2026-09-28: automate the search with TradingView and run it at least 24h.

    python -m factory.tvloop --hours 24          # the run
    python -m factory.tvloop --status            # what it has done so far

ONE ROUND
    1  fetch     `sources.tvfetch` pulls FETCH new open scripts (strategies first)
    2  translate the regex, then the model, on those files only
    3  test      `nightly.run_once(only_source="tradingview")` - steps 3 to 7,
                 luck check included, on the TradingView ideas and nothing else

Rounds repeat until the deadline. A TradingView block (403/429) stops the
fetching but not the testing - whatever is already queued still runs.
Every round is one line in `backtests/factory/tvloop.jsonl`.

SURVIVES A REBOOT, 2026-09-30. The first 24h run was started from a terminal
and died with the PC at 16:26 on 2026-09-28, after 2 rounds, taking the eight
ideas it was testing with it. Now the deadline lives in `tvloop_state.json`,
`--resume` carries on to it, held ideas go back on the queue at start
(`queue.recover`), and `factory/tvloop.sh start 24` runs it as a systemd user
service that restarts on a crash and comes back after a reboot.

    ./factory/tvloop.sh start 24     # a new 24h run, as a service
    ./factory/tvloop.sh status|stop|log
"""
from __future__ import annotations

import json
import os
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from factory import cells, nightly, queue                           # noqa: E402
from factory.sources import tradingview, tvfetch                    # noqa: E402

LOG = queue.DIR / "tvloop.jsonl"
STATE = queue.DIR / "tvloop_state.json"
FETCH = 20
BATCH = 20


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def waiting() -> int:
    return queue.status().get("waiting_by_source", {}).get("tradingview", 0)


def intake(n: int) -> dict:
    """Steps 1-2: download n new scripts, translate them, queue the readable."""
    out = {"fetched": 0, "translated": 0, "skipped": 0, "queued": 0}
    try:
        files = tvfetch.fetch(n)
    except tvfetch.Blocked as exc:
        out["blocked"] = str(exc)
        return out
    out["fetched"] = len(files)
    if not files:
        return out
    got, skipped = tradingview.load(paths=files, ai=True)
    tradingview.record_skips(skipped, translated={p.stem for p in files}
                             - {n for n, _ in skipped})
    out["translated"], out["skipped"] = len(got), len(skipped)
    if got:
        out["queued"] = queue.add(got, quiet=True)["added"]
    return out


def _state() -> dict:
    try:
        return json.loads(STATE.read_text())
    except (OSError, ValueError):
        return {}


def _save(st: dict) -> None:
    tmp = STATE.with_suffix(".tmp")
    tmp.write_text(json.dumps(st, indent=2))
    tmp.replace(STATE)


def start(hours: float) -> dict:
    """A NEW run: the deadline is fixed now and survives restarts."""
    st = {"run": _now(), "end": time.time() + hours * 3600, "hours": hours,
          "rounds": 0}
    _save(st)
    return st


def run(hours: float | None = 24.0, fetch_n: int = FETCH, batch: int = BATCH,
        seeds: int = 5) -> None:
    """`hours=None` resumes the saved run; past its deadline it just returns."""
    st = start(hours) if hours is not None else _state()
    if not st or time.time() >= st.get("end", 0):
        print("no run in progress" + (" - deadline passed" if st else ""))
        return
    st["pid"] = os.getpid()
    _save(st)
    back = queue.recover()
    if back:
        _log({"run": st["run"], "note": f"recovered {back} ideas a killed round was holding",
              "started": _now()})
    blocked = False
    while time.time() < st["end"]:
        st["rounds"] = rnd = st.get("rounds", 0) + 1
        st["beat"] = _now()
        _save(st)
        rec, t0 = {"run": st["run"], "round": rnd, "started": _now()}, time.time()
        try:
            if not blocked and waiting() < batch:
                rec["intake"] = intake(fetch_n)
                blocked = "blocked" in rec["intake"]
            if waiting() == 0:
                rec["note"] = "nothing to test" + (" - TradingView blocked" if blocked else "")
                _log(rec)
                if blocked:
                    break
                time.sleep(300)
                continue
            r = nightly.run_once(batch=batch, seeds=seeds, use_agent=False,
                                 cell_list=cells.all_cells(),
                                 only_source="tradingview")
            nightly.record(r)
            rec["tested"] = r.get("ideas", 0)
            rec["step3"] = r.get("step3_pass", 0)
            rec["step4"] = r.get("step4_repaired", 0)
            rec["step5"] = r.get("step5")
            rec["step7"] = [{k: s.get(k) for k in
                             ("idea", "cell", "pass_pct", "expected_days", "trades_per_day")}
                            for s in (r.get("step7") or [])]
        except Exception as exc:                    # keep the run alive
            rec["error"] = f"{type(exc).__name__}: {exc}"
            rec["trace"] = traceback.format_exc()[-1500:]
            # An exception, unlike a kill, is not retried: the round's ideas
            # are dropped as before, with the error on record.
            queue.finish()
            time.sleep(60)
        rec["seconds"] = round(time.time() - t0)
        _log(rec)


def _log(rec: dict) -> None:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a") as fh:
        fh.write(json.dumps(rec, separators=(",", ":")) + "\n")
    print(json.dumps({k: v for k, v in rec.items() if k != "trace"}), flush=True)


def status() -> dict:
    rows = ([json.loads(l) for l in LOG.read_text().splitlines() if l.strip()]
            if LOG.exists() else [])
    tot = {"rounds": len(rows), "fetched": 0, "translated": 0, "tested": 0,
           "step3": 0, "step4": 0, "errors": 0, "step7": []}
    for r in rows:
        i = r.get("intake") or {}
        tot["fetched"] += i.get("fetched", 0)
        tot["translated"] += i.get("translated", 0)
        for k in ("tested", "step3", "step4"):
            tot[k] += r.get(k, 0) or 0
        tot["errors"] += "error" in r
        tot["step7"] += r.get("step7") or []
    tot["waiting"] = waiting()
    tot["tv"] = tvfetch.status()
    st = _state()
    if st:
        left = (st["end"] - time.time()) / 3600
        alive = _alive(st.get("pid"))
        tot["run"] = {"started": st["run"], "rounds": st.get("rounds", 0),
                      "last_round": st.get("beat"),
                      "hours_left": round(max(left, 0), 1),
                      "state": ("finished" if left <= 0 else
                                "running" if alive else "STOPPED - not running")}
    return tot


def _alive(pid) -> bool:
    if not pid:
        return False
    try:
        os.kill(int(pid), 0)
    except (OSError, ValueError):
        return False
    return True


def _main(argv=None) -> int:
    import argparse

    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--hours", type=float, default=24.0)
    ap.add_argument("--fetch", type=int, default=FETCH)
    ap.add_argument("-n", "--batch", type=int, default=BATCH)
    ap.add_argument("--seeds", type=int, default=5)
    ap.add_argument("--resume", action="store_true",
                    help="carry on to the saved deadline (what the service runs)")
    ap.add_argument("--status", action="store_true")
    a = ap.parse_args(argv)
    if a.status:
        print(json.dumps(status(), indent=2))
        return 0
    run(None if a.resume else a.hours, a.fetch, a.batch, a.seeds)
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
