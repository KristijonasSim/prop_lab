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


#: THE CHOSEN STRATEGY fills the indicator, not the pipeline's own pick.
#:
#: `core/chosen.py` holds what Kris trades - XAUUSD 1h, five settings in
#: parallel, 2% total risk - and the reason it is pinned rather than derived is
#: written there: the blind selector ranks on profit factor, and profit factor is
#: maximised by a tight stop that wins 5% of the time. That is the opposite of
#: what a prop evaluation rewards, so deriving the indicator's defaults from the
#: board would quietly ship the wrong thing.
def _chosen_params(sid: str) -> tuple[dict, str] | None:
    """Placeholder values for the sid Kris has chosen, or None."""
    from core.chosen import CHOSEN

    if CHOSEN.get("sid") != sid:
        return None
    m = CHOSEN["measured"]
    params: dict[str, str] = {}
    for i, cfg in enumerate(CHOSEN["settings"], start=1):
        params[f"THR{i}"] = f"{cfg['thr']:g}"
        params[f"STOP{i}"] = f"{cfg['stop_sig']:g}"
        params[f"HOLD{i}"] = str(int(cfg["max_hold"]))
        params[f"HLO{i}"] = str(int(cfg["hour_lo"]))
        params[f"HHI{i}"] = str(int(cfg["hour_hi"]))
        params[f"RVOL{i}"] = f"{cfg['min_rvol']:g}"
    params["RISK_EACH"] = f"{CHOSEN['risk_each_pct']:g}"
    params["RISK_TOTAL"] = f"{CHOSEN['risk_pct']:g}"
    params["TRAINED_TO"] = CHOSEN["trained_to"]
    params["REFRESH_ON"] = CHOSEN["refresh_on"]
    label = (f"{CHOSEN['market']} {CHOSEN['tf']}, {CHOSEN['rule']}, "
             f"{CHOSEN['risk_pct']:g}% risk — {m['pass_pct']}% of accounts pass "
             f"in {m['days_to_pass']} expected days "
             f"(band {m['days_band'][0]}–{m['days_band'][1]}), "
             f"{m['trades_per_day']} trades/day")
    return params, label


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

    pin = _chosen_params(sid)
    if pin:
        params, label = dict(pin[0]), pin[1]
        folds = []
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
