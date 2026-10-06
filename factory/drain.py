"""TEST THE WHOLE QUEUE, ON EVERY CORE, AND STOP WHEN IT IS EMPTY.

Kris, 2026-10-06: "everything must be tested". One `tvloop` tests about one
idea every 2-3 minutes on one core; 500 waiting ideas is a day. This starts N
workers, each running the same `nightly.run_once` pass a TradingView round
runs (steps 3-7, no model calls), until no idea of that source is left.

    python -m factory.drain -j 12            # TradingView ideas
    python -m factory.drain -j 12 --source agent

The queue's own lock (`queue._locked`) keeps two workers off the same idea.
Workers never call `queue.recover()`: one worker's in-flight ideas are not
another's to put back. If the whole drain is killed, `tvloop --resume`
recovers them as usual.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def _worker(k: int, source: str | None, batch: int, seeds: int) -> int:
    import os
    os.environ.setdefault("OMP_NUM_THREADS", "1")
    from factory import cells, nightly, queue
    done = 0
    while True:
        left = [s for s in queue._read(queue.QUEUE) if s.source == source]
        if not left:
            return done
        r = nightly.run_once(batch=batch, seeds=seeds, use_agent=False,
                             cell_list=cells.all_cells(),
                             only_source=source)
        nightly.record(r)
        done += r.get("ideas", 0)
        print(json.dumps({"worker": k, "tested": r.get("ideas", 0), "total": done,
                          "step3": r.get("step3_pass", 0),
                          "step7": len(r.get("step7") or []),
                          "left": len(left) - r.get("ideas", 0)}), flush=True)
        if not r.get("ideas"):
            return done


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("-j", "--jobs", type=int, default=12)
    ap.add_argument("-n", "--batch", type=int, default=6)
    ap.add_argument("--seeds", type=int, default=5)
    ap.add_argument("--source", default="tradingview")
    a = ap.parse_args(argv)
    src = a.source
    t0 = time.time()
    with ProcessPoolExecutor(a.jobs) as ex:
        futs = [ex.submit(_worker, k, src, a.batch, a.seeds) for k in range(a.jobs)]
        total = sum(f.result() for f in futs)
    print(json.dumps({"drained": total, "minutes": round((time.time() - t0) / 60, 1)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
