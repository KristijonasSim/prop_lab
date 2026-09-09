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


def _sid_base(sid: str) -> str:
    """A basket page trades the same rule as its parent, so it ships the same
    indicator. `vwapbreak_basket` -> `vwapbreak`."""
    return sid[:-7] if sid.endswith("_basket") else sid


def _headline_rule(rec: dict) -> tuple[dict | None, str]:
    """The promoted row's busiest selection rule, and a label for it.

    Busiest, not best: `core.run_hypothesis.best_cell` promotes the rule with the
    most trades precisely so the choice is independent of the outcome, and the
    defaults shipped here should be the ones the board's headline is computed
    from rather than the flattering ones.
    """
    rows = [r for r in rec.get("rows", []) if r.get("rules")]
    rows = [r for r in rows if r.get("days_to_pass")] or rows
    if not rows:
        return None, ""
    row = min(rows, key=lambda r: r.get("days_to_pass") or 1e9)
    rules = row["rules"]
    rule = max(rules, key=lambda x: x.get("trades") or 0)
    label = f"{row.get('sym')} {row.get('tf')} (floor {rule['floor']} / top {rule['topn']})"
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

    rule, label = _headline_rule(rec)
    folds = (rule or {}).get("folds") or []
    fields = FIELDS.get(sid, {})
    params: dict[str, str] = {}
    for token, (key, kind, default) in fields.items():
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
        "n_folds": len(folds),
    }
