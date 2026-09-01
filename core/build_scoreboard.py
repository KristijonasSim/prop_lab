"""The strategy board: one page, every hypothesis, one 0-10 score each.

Answering "do we need a database": no. Every number here already lives in a file
on disk that git versions and a clone reproduces. This script reads one
`backtests/<id>/board.json` per hypothesis and writes one manifest plus one
page. A database would add a service to run, a schema to migrate and a backup to
worry about, and would buy nothing until there are enough strategies that you
want to query across individual trades rather than read summaries. At that point
the answer is a single SQLite file, not a server.

**Adding a hypothesis is one call.** Give `core.board.write_board` a stitched
walk-forward trade series and it produces the board record - prop simulation,
full risk ladder, mandatory fields, all identical to what is already here. This
script then picks it up automatically; there is nothing per-strategy in this
file. See `strategies/orb/stage14_board.py` for the shortest example.

Run: .venv/bin/python core/build_scoreboard.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.scorecard import compute, expected_days, WEIGHTS, PHASE_DAYS  # noqa: E402

BT = ROOT / "backtests"

LADDER_NOTE = (
    "Risk per trade is the only lever left once the configuration is chosen blind, "
    "and it moves speed and survival in opposite directions. <strong>Click any "
    "row</strong> to score the strategy at that risk level. The recommended row is "
    "the fewest expected days to a funded account among the levels that keep the "
    "breach rate under 5% <em>and</em> the drawdown inside the 8% cap."
)


def _risk_row(x: dict, base: dict, fields: dict, pf_2x) -> dict:
    """One risk level, scored end to end.

    Profit factor, Sharpe and the R-multiples are scale-invariant, so only the
    risk-dependent inputs change: how many accounts pass, how many are killed by
    each cap, how fast the passers get there, and how deep the drawdown runs in
    percent."""
    m = dict(base)
    m.update(median_days_pass=x["median_days"], pass_rate=x["pass_rate"],
             fail_max=x["fail_max"], fail_daily=x["fail_daily"], max_dd=x["max_dd"])
    card = compute(m).as_dict()
    return {
        **x,
        "score": card["total"], "verdict": card["verdict"],
        "components": card["components"], "evidence_capped": card["evidence_capped"],
        "headline": {
            "pf": fields["pf"], "pf2x": pf_2x,
            "tpd": fields["trades_per_day"], "trades": fields["trades"],
            "n_books": fields.get("n_books", 1),
            "tpd_per_book": fields.get("tpd_per_book", fields["trades_per_day"]),
            "r_per_day": fields.get("r_per_day"),
            "max_dd": x["max_dd"], "pass_rate": x["pass_rate"],
            "fail_max": x["fail_max"], "fail_daily": x["fail_daily"],
            "median_days": x["median_days"], "still_open": x["still_open"],
            "expected_days": x["expected_days"],
        },
    }


def load(sid: str) -> dict | None:
    p = BT / sid / "board.json"
    if not p.exists():
        return None
    b = json.loads(p.read_text())
    pick, fields = b["pick"], b["fields"]

    measured = dict(b["measured"])
    measured.update(median_days_pass=pick["median_days"], pass_rate=pick["pass_rate"],
                    fail_max=pick["fail_max"], fail_daily=pick["fail_daily"],
                    max_dd=pick["max_dd"])
    card = compute(measured).as_dict()

    return {
        "id": b["id"], "hid": b["hid"], "name": b["name"], "tagline": b["tagline"],
        "period": b["period"], "report": b["report"],
        "candidate": f'{b["candidate"]}, {pick["risk"]*100:.2f}% risk per trade',
        "measured": measured, "score": card, "note": b.get("note"),
        "headline": {
            "pf": fields["pf"], "pf2x": b.get("pf_2x"),
            "tpd": fields["trades_per_day"], "trades": fields["trades"],
            "n_books": fields.get("n_books", 1),
            "tpd_per_book": fields.get("tpd_per_book", fields["trades_per_day"]),
            "r_per_day": fields.get("r_per_day"),
            "max_dd": pick["max_dd"], "pass_rate": pick["pass_rate"],
            "fail_max": pick["fail_max"], "fail_daily": pick["fail_daily"],
            "median_days": pick["median_days"], "still_open": pick["still_open"],
            "expected_days": expected_days(pick["median_days"], pick["pass_rate"]),
        },
        "ladder": {
            "picked": pick["risk"], "note": LADDER_NOTE,
            # Every row carries its own fully-computed scorecard. The page never
            # scores anything: duplicating the rubric in JavaScript would let the
            # page and core/scorecard.py drift apart silently.
            "rows": [_risk_row(x, b["measured"], fields, b.get("pf_2x"))
                     for x in b["ladder"]],
        },
        "grid": b.get("grid") or {}, "todo": b.get("todo") or [],
    }


def main():
    ids = sorted(p.parent.name for p in BT.glob("*/board.json"))
    out = []
    for sid in ids:
        s = load(sid)
        if s:
            out.append(s)
        else:
            print(f"  skip {sid}: unreadable board.json")
    if not out:
        print("no board.json anywhere - run each strategy's board stage first")
        return
    out.sort(key=lambda s: -s["score"]["total"])

    data = {"strategies": out, "weights": WEIGHTS, "phase_days": PHASE_DAYS}
    (BT / "scoreboard_data.json").write_text(json.dumps(data, indent=1))
    tpl = (ROOT / "core" / "scoreboard_template.html").read_text()
    (BT / "scoreboard.html").write_text(tpl.replace("/*__DATA__*/", json.dumps(data)))

    print("wrote backtests/scoreboard.html")
    for s in out:
        print(f"  {s['hid']} {s['name']:26s} {s['score']['total']:4.1f}/10  "
              f"{s['score']['verdict']}")


if __name__ == "__main__":
    main()
