"""The Pine indicator each hypothesis ships, filled in from its own board record.

WHY AN INDICATOR AND NOT A STRATEGY. Kris asked for something he can paste into
TradingView and look at. A Pine *strategy* would also print a profit factor and
an equity curve, and that number would be compared with this project's - by him,
by me, or by whoever reads the chart six months from now. It would not be
comparable: TradingView charges different costs, fills differently, uses another
vendor's volume on a volume-weighted rule, and re-selects nothing, while every
number on the board comes from a configuration chosen blind inside each quarter.
An indicator marks the bar the rule fires on and draws the stop it implies. That
is the thing worth looking at, and it cannot be mistaken for a result.

WHERE THE DEFAULTS COME FROM. Each `.pine` file carries `{{PLACEHOLDER}}` tokens
and this fills them from the record's own walk-forward: the promoted market's
busiest selection rule, and within it the MODAL value of each parameter across
the folds - what the blind selector chose most often. Not the best fold, which
would be a number picked by its own result.

A hypothesis with no `strategies/<sid>/indicator.pine` gets no button. Shipping a
generic VWAP script under a hypothesis' name would be worse than shipping
nothing, because it would be read as that hypothesis.
"""
from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

#: Placeholder -> (key in the stored fold row, how to render it, fallback).
#: The fold rows are written by `core/run_hypothesis.py` from the winning
#: configuration of each fold, so these key names are the strategy's own grid
#: keys and nothing else has to agree with them.
MODES = {0: "TREND", 1: "FADE", 2: "BREAK", 3: "RECLAIM", 4: "PULLBACK"}

FIELDS: dict[str, dict[str, tuple]] = {
    "vwapbreak": {
        "THR": ("thr", "float", 1.0),
        "STOP_SIG": ("stop_sig", "float", 1.0),
        "MAX_HOLD": ("max_hold", "int", 96),
        "HOUR_LO": ("hour_lo", "int", 0),
        "HOUR_HI": ("hour_hi", "int", 0),
        "MIN_RVOL": ("min_rvol", "float", 0.0),
    },
    "vwap": {
        "MODE": ("mode", "mode", "BREAK"),
        "BAND_K": ("band_k", "float", 2.0),
        "STOP_K": ("stop_k", "float", 1.0),
        "MAX_HOLD": ("max_hold_bars", "int", 0),
        "ANCHOR_HOUR": ("anchor_hour", "int", 0),
        "ANCHOR_MIN": ("anchor_minute", "int", 0),
        "WARMUP": ("warmup_bars", "int", 8),
        "MIN_RVOL": ("min_rvol", "float", 0.0),
    },
}


#: A CONFIGURATION KRIS HAS CHOSEN TO TRADE, which overrides everything the
#: record would otherwise fill in.
#:
#: 2026-09-09: he is running three demo accounts on H-027 gold 1h and wants the
#: indicator to ship exactly what those accounts trade. The settings are the
#: modal fold picks of the ONE arm that reaches his 60% goal fastest -
#: `research/exits.py`, the wide-stop arm, XAUUSD 1h, floor 30 / top 1: 60.1% of
#: accounts pass in 18.3 expected days at 4% risk per trade, band 15.9-25.4.
#:
#: It is pinned rather than derived because the shipped grid does NOT choose it:
#: given every stop width from 0.75 to 20 sigma the blind selector picks 0.75,
#: since it ranks configurations on profit factor and the tight-stop lottery has
#: the best profit factor. That is a real open problem (the selector is aiming at
#: something other than the goal) and until it is fixed, deriving the defaults
#: would ship the wrong thing quietly. Pinning ships the right thing loudly.
PINNED: dict[str, dict] = {
    "vwapbreak": {
        "params": {"THR": "1.25", "STOP_SIG": "8", "MAX_HOLD": "384",
                   "HOUR_LO": "0", "HOUR_HI": "7", "MIN_RVOL": "0"},
        "label": ("XAUUSD 1h, wide stop, floor 30 / top 1 — 60.1% of accounts "
                  "pass in 18.3 days at 4% risk (band 15.9–25.4). Pinned by Kris "
                  "2026-09-09 for the three-account demo test."),
    },
}


def _sid_base(sid: str) -> str:
    """A basket page trades the same rule as its parent, so it ships the same
    indicator. `vwapbreak_basket` -> `vwapbreak`."""
    return sid[:-7] if sid.endswith("_basket") else sid


def _headline_rule(rec: dict) -> tuple[dict | None, str]:
    """The selection rule the indicator should ship the settings of.

    KRIS, 2026-09-09: "in this table and in the Pine script I always want to see
    the BEST settings." So the rule that reaches his goal - 60% of accounts
    passing - the fastest wins, across every promoted market and every selection
    rule on it. That is a choice made on the walk-forward's own out-of-sample
    result, which is why the board reports it with a band next to it rather than
    as a promise.

    When no rule anywhere reaches 60%, this falls back to the BUSIEST rule on the
    fastest market - busiest, not best, because with nothing to aim at the
    remaining choice should not be made on its own outcome.
    """
    rows = [r for r in rec.get("rows", []) if r.get("rules")]
    if not rows:
        return None, ""

    goal = [(r, x) for r in rows for x in r["rules"] if x.get("days60")]
    if goal:
        row, rule = min(goal, key=lambda p: p[1]["days60"])
        label = (f"{row.get('sym')} {row.get('tf')} (floor {rule['floor']} / "
                 f"top {rule['topn']}, 60% pass in {rule['days60']:.1f} days "
                 f"at {rule['risk60']:.2f}% risk)")
        return rule, label

    rows = [r for r in rows if r.get("days_to_pass")] or rows
    row = min(rows, key=lambda r: r.get("days_to_pass") or 1e9)
    rule = max(row["rules"], key=lambda x: x.get("trades") or 0)
    label = (f"{row.get('sym')} {row.get('tf')} (floor {rule['floor']} / "
             f"top {rule['topn']} — no setting reaches 60% pass)")
    return rule, label


def _modal(folds: list[dict], key: str):
    """What the blind selector chose most often. Ties break on the first
    occurrence, which is the earliest quarter - arbitrary, and stated rather than
    hidden, because a tie means the folds genuinely disagreed."""
    vals = [f.get(key) for f in folds if f.get(key) is not None]
    if not vals:
        return None
    return Counter(vals).most_common(1)[0][0]


def _fmt(kind: str, v) -> str:
    if kind == "mode":
        return MODES.get(int(v), "BREAK")
    if kind == "int":
        return str(int(round(float(v))))
    f = float(v)
    return f"{f:g}"


def for_record(rec: dict) -> dict | None:
    """`{text, params, source, defaults_from}` for one hypothesis record, or None
    when that hypothesis ships no indicator."""
    sid = _sid_base(rec.get("sid", ""))
    src = ROOT / "strategies" / sid / "indicator.pine"
    if not src.exists():
        return None
    text = src.read_text()

    pin = PINNED.get(sid)
    if pin:
        params = dict(pin["params"])
        label, folds = pin["label"], []
    else:
        rule, label = _headline_rule(rec)
        folds = (rule or {}).get("folds") or []
        params = {}
        for token, (key, kind, default) in FIELDS.get(sid, {}).items():
            v = _modal(folds, key)
            params[token] = _fmt(kind, v) if v is not None else _fmt(kind, default)
    params["MARKET"] = label or (rec.get("universe") and "the promoted market") or ""

    for token, value in params.items():
        text = text.replace("{{" + token + "}}", str(value))
    left = re.findall(r"\{\{([A-Z_]+)\}\}", text)
    if left:
        raise ValueError(f"{src.name}: no value for {sorted(set(left))} - add it "
                         f"to core/pine.FIELDS[{sid!r}] or remove the token")
    return {
        "text": text,
        "params": {k: v for k, v in params.items() if k != "MARKET"},
        "source": str(src.relative_to(ROOT)),
        "defaults_from": label,
        "pinned": bool(pin),
        "n_folds": len(folds),
    }
