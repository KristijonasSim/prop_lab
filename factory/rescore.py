"""Re-price every stored idea's scorecard and timeframe ladder in place.

The scorecard is arithmetic on a fixed trade series, so a change to how it is
priced (2026-10-06: the risk rung) re-runs the backtest on the shown market and
rewrites `score` and `ladder` - nothing is re-selected and no verdict moves.

    python -m factory.rescore
"""
from __future__ import annotations

import json
import re

from factory.spec import INDICATORS, Condition, Strategy, Term

from factory import nightly, queue


def _specs() -> dict:
    out = {}
    for f in ("tried.jsonl", "survivors.jsonl", "queue.jsonl", "inflight.jsonl"):
        p = queue.DIR / f
        if not p.exists():
            continue
        for line in p.read_text().splitlines():
            try:
                s = queue._from_json(line)
            except Exception:
                continue
            out.setdefault((s.name, s.label()), s)
    return out


def _term(tok: str) -> Term:
    try:
        return Term("const", 0, float(tok))
    except ValueError:
        pass
    kind = max((k for k in INDICATORS if tok.startswith(k)), key=len)
    m = re.fullmatch(r"(\d*)(?:x([\d.]+))?", tok[len(kind):])
    return Term(kind, int(m.group(1) or 0), float(m.group(2) or 0.0))


def from_record(x: dict) -> Strategy | None:
    """Rebuild a strategy from its stored LABEL, for ideas whose spec is in no
    queue file - repaired variants are written to ideas.jsonl only. The label
    is the full rule (`Strategy.label`), so this is a parse, not a guess."""
    try:
        side, rule = x["idea"].split(" when ", 1)
        conds = []
        for part in rule.split(" and "):
            hold = 1
            m = re.fullmatch(r"(.+) for (\d+) bars", part)
            if m:
                part, hold = m.group(1), int(m.group(2))
            left, op, right = part.split(" ")
            conds.append(Condition(_term(left), op, _term(right), hold=hold))
        return Strategy(name=x.get("name") or x["idea"], side=side,
                        entry=tuple(conds), stop_atr=x["stop_atr"],
                        target_atr=x["target_atr"], max_hold=x["max_hold"],
                        source=x.get("source", "unknown"))
    except Exception:
        return None


def main() -> int:
    specs = _specs()
    lines = nightly.IDEAS.read_text().splitlines()
    out, done, missing = [], 0, 0
    for line in lines:
        x = json.loads(line)
        k = x.get("score") or {}
        s = specs.get((x.get("name"), x.get("idea"))) or from_record(x)
        if s is None or not k.get("market"):
            missing += bool(k.get("market"))
            out.append(line)
            continue
        x["score"] = nightly.scorecard(s, k["market"], k["tf"]) or k
        x["ladder"] = nightly.ladder_rows(s, k["market"])
        out.append(json.dumps(x, separators=(",", ":")))
        done += 1
    nightly.IDEAS.write_text("\n".join(out) + "\n")
    print(f"rescored {done}, no spec found for {missing}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
