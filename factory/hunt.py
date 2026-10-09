"""THE HUNT - one strategy, 1-2 trades a day, PF >= 1.5, no trade over 24h.

Kris, 2026-10-09: *"i always wanted a strategy that would provide 1 - 2
MAXIMUM trades per day with PF of 1.6"*. The arithmetic says that is the
right target: +0.3R a trade at 2% risk reaches +8% in ~13 trades, ~7-9 days.

PRE-REGISTERED 2026-10-09, before the first run:
  CANDIDATES  every idea ever scored (board + archive), best record per rule,
              with >= 1.0 trades/day; the 40 with the highest profit factor.
  SEARCH      `improve.py` unchanged - timeframe, one filter, exits, picked on
              the older half - except: trades capped at 24h, and every choice
              must keep >= 1.0 trades/day on the older half.
  LUCK CHECK  the identical search on random entries, 40 seeds, 95th pct.
  A FIND      REAL by the luck check AND full-window PF >= 1.5 at 1x AND
              >= 1.0 trades/day. 40 at 95% expect ~2 false REALs.

    python -m factory.hunt        # hunt_list.json, hunt.json, HUNT.md
"""
import glob
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from factory import improve, queue  # noqa: E402

N, TPD = 40, 1.0
# `python -m factory.hunt 0.5` - Kris, 2026-10-09: "what about strategies that
# trade ... at least 0.5 tpd". Same rules, the floor at 0.5, files suffixed,
# and ideas already hunted are skipped so no rule is searched twice.
TAG = ""
if sys.argv[1:]:
    TPD = float(sys.argv[1])
    TAG = f"_{sys.argv[1].replace('.', '')}"
improve.MAX_HOURS = 24
improve.MIN_TPD = TPD
improve.LIST = queue.DIR / f"hunt{TAG}_list.json"
improve.OUT = queue.DIR / f"hunt{TAG}.json"
improve.TABLE = queue.DIR / f"HUNT{TAG}.md"
DONE = set()
for f in ("hunt_list.json", "step8_list.json"):
    if TAG and (queue.DIR / f).exists():
        DONE |= {x["idea"] for x in json.loads((queue.DIR / f).read_text())}


def candidates() -> list[dict]:
    rows = []
    for f in [queue.DIR / "ideas.jsonl", *map(Path, glob.glob(str(queue.DIR / "archive/*/ideas.jsonl")))]:
        rows += queue.rows(f)
    best = {}
    for r in rows:
        s = r.get("score") if isinstance(r.get("score"), dict) else None
        if not s or (s.get("per_day") or 0) < TPD or not s.get("pf") or r["idea"] in DONE:
            continue
        if r["idea"] not in best or s["pf"] > best[r["idea"]]["score"]["pf"]:
            best[r["idea"]] = r
    top = sorted(best.values(), key=lambda r: -r["score"]["pf"])[:N]
    return [{"by": "hunt", "name": r["name"], "idea": r["idea"], "side": r["side"],
             "cell": r["score"]["cell"], "pass_pct": r["score"].get("pass_pct"),
             "eval_days": r["score"].get("eval_days"), "pf": r["score"]["pf"],
             "tpd": r["score"]["per_day"], "stop_atr": float(r["stop_atr"]),
             "target_atr": float(r["target_atr"]), "max_hold": int(r["max_hold"]),
             "source": r.get("source")} for r in top]


if __name__ == "__main__":
    improve.LIST.write_text(json.dumps(candidates(), indent=1))
    improve.cmd_grid()
    improve.cmd_null()
    improve.cmd_table()
    res = json.loads(improve.OUT.read_text())
    finds = [r for r in res if r["null_final"]["real"]
             and (r["final"]["full"]["pf"] or 0) >= 1.5 and r["final"]["tpd"] >= TPD]
    print(f"\nFINDS: {len(finds)}")
    for r in finds:
        print(r["name"], r["final"]["rule"], r["final"]["exits"], r["final"]["tf"],
              r["final"]["full"]["pf"], r["final"]["tpd"], r["final"]["pace"])
