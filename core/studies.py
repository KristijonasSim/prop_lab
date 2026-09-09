"""Research arms, on the board page rather than in a log file nobody opens.

WHY. `strategies/*/research/` produces the comparisons that decide what the
hypothesis becomes - is a wider stop better, does a filter help, does taking
fewer trades help - and until now every one of them lived in a JSON file plus a
row in `STRATEGY_LOG.md`. Kris reads the board. A comparison he cannot see is a
comparison that gets re-proposed in three weeks.

WHAT IS SHOWN. One row per arm, with the two numbers that decide anything here:
expected days WITH ITS BAND, and the trader-facing shape (win rate, profit
factor, the fastest route to 60% pass). The baseline arm is marked, so a reader
can see what the change is being compared against rather than guessing.

WHAT IS NOT DONE HERE. No ranking and no verdict. Arms whose bands overlap have
not been shown to differ, the page says so, and `core/scorecard.rank_tiers`
tiers them exactly as it tiers the board's own cells.
"""
from __future__ import annotations

from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[1]

#: sid -> the studies to show, newest first. `file` is under backtests/<sid>/.
#: `baseline` names the arm every other arm is being compared against.
STUDIES: dict[str, list[dict]] = {
    "vwapbreak": [
        {"file": "exits.json", "title": "Exit study — how wide should the stop be?",
         "baseline": "baseline", "date": "2026-09-09",
         "note": ("Same entries, same costs. Only the stop changes.<br>"
                  "<b>Today's stop is half of one bar wide</b>, so noise kills the "
                  "trade. A wider stop wins more often but takes the same number "
                  "of days.")},
        {"file": "quality.json", "title": "Fewer trades, better trades — does it help?",
         "baseline": "baseline", "date": "2026-09-09",
         "note": ("Trade less, trade better: a higher entry bar, and only one "
                  "trade per move.<br><b>It does not help.</b> Same days, fewer "
                  "accounts pass.")},
    ],
}


def _best60(res: dict):
    hit = [r for r in res.get("rules", []) if r.get("days60")]
    return min(hit, key=lambda r: r["days60"]) if hit else None


def _stalled(res: dict):
    picked = [x for x in res.get("ladder", []) if x.get("picked")]
    return picked[0].get("still_open_pct") if picked else None


def for_sid(sid: str) -> list[dict]:
    """Every study recorded for one hypothesis, ready for the page."""
    out = []
    for spec in STUDIES.get(sid, []):
        path = ROOT / "backtests" / sid / spec["file"]
        if not path.exists():
            continue
        raw = json.loads(path.read_text())
        rows = []
        for key, res in raw.items():
            tf, _, arm = key.partition("|")
            b60 = _best60(res)
            rows.append({
                "tf": tf, "arm": arm,
                "baseline": arm == spec.get("baseline"),
                "trades_per_day": res.get("trades_per_day"),
                "win_pct": res.get("win_pct"),
                "avg_r": res.get("avg_r"),
                "pf_2x": res.get("pf_2x"),
                "days_to_pass": res.get("days_to_pass"),
                "band": res.get("band"),
                "pass_pct": res.get("pass_pct"),
                "stalled_pct": _stalled(res),
                # The 60% route in full. "60% in 18.3 days" is not readable
                # without the size it is taken at and the pass rate it buys -
                # 18.3 days at 4% risk with 60.1% passing is a different
                # proposition from 12.9 days at 4% with 34.8% passing, and the
                # column was showing only the first number of each.
                "days60": b60["days60"] if b60 else None,
                "pass60": b60["pass60"] if b60 else None,
                "risk60": b60.get("risk60") if b60 else None,
                "band60": b60.get("band60") if b60 else None,
                "rule60": (f"floor {b60['floor']} / top {b60['topn']}"
                           if b60 else None),
                "beats_null": res.get("beats_null"),
            })
        rows.sort(key=lambda r: (r["tf"], not r["baseline"], r["arm"]))
        out.append({"title": spec["title"], "note": spec["note"],
                    "date": spec["date"], "rows": rows,
                    "source": f"backtests/{sid}/{spec['file']}"})
    return out
