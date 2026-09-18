"""THE LOOP. Harvest, propose, screen, publish, repeat — unattended.

Kris, 2026-09-18: *"i would love for it to work 24/7 constantly testing new edges
... from quantity maybe we will get some quality."*

The arithmetic says he is right that quantity is affordable and wrong about where
to spend it. The luck bar grows with the LOGARITHM of the trial count — going
from 228 trials to a million costs 2.06 sigma — so volume is cheap. What is not
cheap is spending it in the same place twice: a re-test of dead space raises the
bar exactly as much as a new idea and buys nothing. So this loop is built around
one constraint and everything else follows from it:

    IT NEVER PROPOSES WHAT THE LEDGER HAS ALREADY SEEN.

THE HONEST CEILING, STATED UP FRONT. The cheap screen is seconds, so thousands a
day are possible here. A full walk-forward is hours, so the real throughput of
the whole pipeline is 5-20 studies a day on 28 cores. This loop runs the SCREEN
only. Its job is to kill 95% of candidates for free and hand over the survivors;
it does not produce results and a PASS here is not one.

WHERE IT RUNS — CORRECTED 2026-09-18. It runs ON THE VM, under systemd, and the
first version of this paragraph was wrong. It said the VM was too small and the
28-core desktop was the research machine, which missed the obvious: a desktop
that gets switched off is not a 24/7 loop, and Kris switches his off.

The VM is 2 cores and 952 MB, and that is enough because **the SCREEN is cheap**
- 8 candidates take about a second and need 18 MB of cached feeds and bars. What
must never move there is the walk-forward. That stays on the desktop, where the
28 cores are. The split is by cost, not by preference.

The live bot has priority on that box: the service is niced and idle-scheduled,
so the hourly cron that places real orders never waits on research.

    research/deploy_vm.sh              # sync and restart it there
    research/deploy_vm.sh --status     # is it alive, what has it done

    python -m research.loop --cycles 1            # one pass, then stop
    python -m research.loop --forever --every 900 # unattended
    python -m research.loop --mode llm -n 5       # let the model choose

SAFETY. Every cycle is wrapped: a failed harvest, a failed model call or a
candidate that raises does not stop the loop, it is recorded and the loop moves
on. A loop that halts on a bad parse is not unattended.
"""
from __future__ import annotations

import argparse
import json
import signal
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from research import dashboard, harvest, notify          # noqa: E402
from research.propose import propose, untried                    # noqa: E402
from research.run import run_batch                               # noqa: E402

STATE = ROOT / "backtests" / "loop_state.json"
LOG = ROOT / "backtests" / "loop.log"

_stop = False


def _sigterm(*_):
    global _stop
    _stop = True
    print("\n[loop] stop requested, finishing this cycle", flush=True)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def write_state(**kw) -> None:
    STATE.parent.mkdir(parents=True, exist_ok=True)
    cur = {}
    if STATE.exists():
        try:
            cur = json.loads(STATE.read_text())
        except ValueError:
            cur = {}
    cur.update(kw)
    STATE.write_text(json.dumps(cur, indent=1))


def note(msg: str) -> None:
    line = f"{_now()}  {msg}"
    print(line, flush=True)
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a") as fh:
        fh.write(line + "\n")


def cycle(n: int, mode: str, do_harvest: bool, cycle_no: int) -> int:
    """One pass. Returns the number of candidates screened."""
    write_state(status="harvesting", cycle=cycle_no, mode=mode, last_run=_now())

    if do_harvest:
        try:
            hs = harvest.harvest_all()
            bad = [h.feed for h in hs if h.status == "failed"]
            note(f"harvest: {len(hs) - len(bad)}/{len(hs)} ok"
                 + (f", failed {bad}" if bad else ""))
        except Exception as exc:                          # noqa: BLE001
            note(f"harvest raised, continuing: {type(exc).__name__}: {exc}")

    write_state(status="proposing")
    try:
        cands = propose(n, mode)
    except Exception as exc:                              # noqa: BLE001
        note(f"propose raised: {type(exc).__name__}: {exc}")
        cands = []

    if not cands:
        left = len(untried())
        note(f"nothing to propose ({left} untried in the space) — "
             "the registry is exhausted. Add a FEED, not a parameter.")
        write_state(status="exhausted", next="—")
        return 0

    write_state(status="screening", next=cands[0].name)
    note(f"cycle {cycle_no}: screening {len(cands)} "
         f"({', '.join(c.name for c in cands[:3])}"
         f"{'…' if len(cands) > 3 else ''})")

    try:
        results = run_batch(cands)
    except Exception:                                     # noqa: BLE001
        note("run_batch raised:\n" + traceback.format_exc()[-800:])
        results = []

    passed = [r for r in results if r.verdict == "PASS"]
    if passed:
        # Counts across the WHOLE loop, not this cycle: a pass is only readable
        # against how much was searched, and the mail says so.
        from core.ledger import read as _read
        loop_rows = [t for t in _read()
                     if t.params and "candidate_key" in t.params]
        total = len(loop_rows)
        survivors = sum(1 for t in loop_rows if t.verdict == "PASS")
        for r in passed:
            note(f"  SURVIVED: {r.candidate.name} — earned a study, nothing "
                 f"more. prereg {r.prereg_path}")
            ok, why = notify.alert_survivor(r, total, survivors)
            note(f"  alert: {'emailed' if ok else why}")

    write_state(status="publishing", survivors=len(passed))
    try:
        dashboard.OUT.write_text(dashboard.build())
        note(f"dashboard -> {dashboard.OUT.relative_to(ROOT)}")
    except Exception as exc:                              # noqa: BLE001
        note(f"dashboard raised: {type(exc).__name__}: {exc}")

    nxt = untried()
    write_state(status="idle", next=nxt[0].name if nxt else "—",
                left=len(nxt), last_run=_now())
    return len(results)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("-n", type=int, default=5,
                    help="candidates per cycle (default 5)")
    ap.add_argument("--mode", choices=("library", "llm"), default="library")
    ap.add_argument("--cycles", type=int, default=1)
    ap.add_argument("--forever", action="store_true")
    ap.add_argument("--every", type=int, default=900,
                    help="seconds between cycles when --forever (default 900)")
    ap.add_argument("--no-harvest", action="store_true")
    a = ap.parse_args(argv)

    signal.signal(signal.SIGTERM, _sigterm)
    signal.signal(signal.SIGINT, _sigterm)

    note(f"loop start: mode={a.mode} n={a.n} "
         f"{'forever' if a.forever else f'{a.cycles} cycle(s)'}")
    i = 0
    while not _stop:
        i += 1
        try:
            done = cycle(a.n, a.mode, not a.no_harvest, i)
        except Exception:                                 # noqa: BLE001
            note("cycle raised:\n" + traceback.format_exc()[-800:])
            done = 0
        if not a.forever and i >= a.cycles:
            break
        if done == 0 and not a.forever:
            break
        if _stop:
            break
        note(f"sleeping {a.every}s")
        for _ in range(a.every):
            if _stop:
                break
            time.sleep(1)

    write_state(status="stopped", last_run=_now())
    note("loop stopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
