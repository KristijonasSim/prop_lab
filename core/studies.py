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
        {"file": "book.json", "kind": "book",
         "title": "Two markets in one account — gold 1h + ETH 1h", "date": "2026-09-09",
         "note": ("The only two cells that clear profit factor 2.0 at double cost "
                  "AND beat their own null, traded together at half risk each."
                  "<br><b>Better than either leg on every axis: 72.7% pass in "
                  "12.4 days at 2% risk, against gold's 61.9% in 17.8.</b> Their "
                  "daily returns correlate -0.014 and both trade on only 7.7% of "
                  "days, so the diversification is measured, not hoped for.")},
        {"file": "concurrency.json", "kind": "concurrency",
         "title": "How many positions at once?", "date": "2026-09-09",
         "note": ("The five settings pile into gold together, and the DAILY cap "
                  "is what kills accounts - worst day -3.93% against a 3% limit."
                  "<br><b>Capping at two open positions lifts pass 65.8% to "
                  "75.1% and cuts blown accounts 29.5% to 17.5% - and costs 5 "
                  "days.</b> The book above beats every arm here.")},
        {"file": "assets.json", "kind": "markets",
         "title": "Does the gold rule work anywhere else?", "date": "2026-09-09",
         "note": ("The traded rule - wide stop, five settings, floor 30 / top 5 - "
                  "run unchanged on every market in the universe, scored at 2% "
                  "risk under a 1-step 2% target.<br><b>It ports to ETHUSDT 1h "
                  "and partly to SOL 1h and GBPUSD 4h. Silver 1h, BTC 1h, WTI 4h "
                  "and two FX cells lose to their own null.</b>")},
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
        if spec.get("kind") in ("book", "concurrency"):
            rows = []
            for r in (raw["rows"] if spec["kind"] == "book" else raw):
                if not r or r.get("days") is None:
                    continue
                label = (f"{r['tag']} @ {r['risk_pct']:g}%" if spec["kind"] == "book"
                         else f"max {r['cap']} open @ {r['risk_pct']:g}%")
                rows.append({"tf": "1h", "arm": label,
                             "baseline": "gold 1h alone" in label or r.get("cap") == 5,
                             "trades_per_day": r.get("tpd"), "win_pct": None,
                             "avg_r": None, "pf_2x": None,
                             "days_to_pass": r.get("days"), "band": r.get("band"),
                             "pass_pct": r.get("pass_pct"),
                             "stalled_pct": r.get("never_pct"),
                             "days60": None, "pass60": None, "risk60": None,
                             "band60": None, "rule60": None,
                             "blown_pct": r.get("blown_pct"), "beats_null": None})
            out.append({"title": spec["title"], "note": spec["note"],
                        "date": spec["date"], "rows": rows, "kind": spec["kind"],
                        "source": f"backtests/{sid}/{spec['file']}"})
            continue
        if spec.get("kind") == "markets":
            # one row per market x timeframe, not per arm: a different question
            # (where does this rule work) and a different shape on disk.
            rows = []
            for key, r in raw.items():
                sym, _, tf = key.partition("|")
                rows.append({"tf": tf, "arm": sym, "baseline": sym == "XAUUSD",
                             "trades_per_day": r.get("tpd"), "win_pct": r.get("win"),
                             "avg_r": r.get("avg_r"), "pf_2x": r.get("pf_2x"),
                             "days_to_pass": r.get("days"), "band": r.get("band"),
                             "pass_pct": r.get("pass_pct"),
                             "stalled_pct": None, "days60": None, "pass60": None,
                             "risk60": None, "band60": None, "rule60": None,
                             "beats_null": r.get("beats_null")})
            rows.sort(key=lambda r: (-(r["pf_2x"] or 0)))
            out.append({"title": spec["title"], "note": spec["note"],
                        "date": spec["date"], "rows": rows, "kind": "markets",
                        "source": f"backtests/{sid}/{spec['file']}"})
            continue
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
