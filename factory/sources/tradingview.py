"""SOURCE 1 — TradingView. Kris set it first in the order.

WHAT THIS DOES. Reads Pine scripts from a local folder and translates the ones
it fully understands into `spec.Strategy`. It does NOT download anything.

**WHY IT DOES NOT DOWNLOAD — Kris needs to decide this.** TradingView's public
script library is readable in a browser, but bulk automated collection is a
different thing from reading, and their terms are the place that question gets
answered, not this docstring. The session's `tradingview` MCP server also
failed to connect. So the fetching half is deliberately left out and the
translating half - which is the part with the engineering risk in it - is
built, tested and ready for whatever supplies the files.

Put `.pine` files in `data/pine/` and this reads them.

THE RULE THAT MATTERS: IT SKIPS WHAT IT CANNOT PARSE.

A translator that guesses produces a strategy that is not the one the author
wrote, which then occupies a test slot, gets charged, and tells us nothing
about the original. Silence is cheap and a wrong translation is not, so
anything outside the patterns below is reported as `skipped` with the reason,
never approximated.

WHAT IT UNDERSTANDS TODAY
    ta.crossover / ta.crossunder  of two moving averages
    ta.sma / ta.ema               with a literal length
    ta.rsi                        against a literal level
    price above / below           ta.highest / ta.lowest

That is a small subset of Pine and it is meant to be. It covers the crossing
and breakout shapes, which is most of what the public library actually is, and
every pattern added later has to earn a test.
"""
from __future__ import annotations

import re
from pathlib import Path

from factory.spec import Condition, Strategy, Term

ROOT = Path(__file__).resolve().parents[2]
PINE_DIR = ROOT / "data" / "pine"

_MA = re.compile(r"ta\.(sma|ema)\s*\(\s*close\s*,\s*(\d+)\s*\)")
_RSI = re.compile(r"ta\.rsi\s*\(\s*close\s*,\s*(\d+)\s*\)")
_HL = re.compile(r"ta\.(highest|lowest)\s*\(\s*(?:high|low|close)\s*,\s*(\d+)\s*\)")
_CROSS = re.compile(r"ta\.(crossover|crossunder)\s*\(")


def _args(text: str, start: int) -> tuple[list[str], int] | None:
    """Split a call's arguments at the TOP level only.

    A plain regex cannot do this: `ta.crossover(ta.sma(close, 50), ta.sma(close,
    200))` has commas inside the nested calls, and splitting on all of them
    produces nonsense like `ta.sma(close`. Counting depth is the fix.
    """
    depth, buf, out, i = 0, [], [], start
    while i < len(text):
        ch = text[i]
        if ch == "(":
            depth += 1
            if depth == 1:
                i += 1; continue
        elif ch == ")":
            depth -= 1
            if depth == 0:
                out.append("".join(buf))
                return out, i + 1
        elif ch == "," and depth == 1:
            out.append("".join(buf)); buf = []; i += 1; continue
        if depth >= 1:
            buf.append(ch)
        i += 1
    return None
_CMP = re.compile(r"close\s*(>|<)\s*(ta\.(?:highest|lowest)\s*\([^)]*\))")


def _term(text: str) -> Term | None:
    text = text.strip()
    if m := _MA.fullmatch(text):
        return Term(m.group(1), int(m.group(2)))
    if m := _RSI.fullmatch(text):
        return Term("rsi", int(m.group(1)))
    if m := _HL.fullmatch(text):
        return Term("highest" if m.group(1) == "highest" else "lowest", int(m.group(2)))
    if re.fullmatch(r"-?\d+(\.\d+)?", text):
        return Term("const", value=float(text))
    if text == "close":
        return Term("price")
    return None


def translate(pine: str, name: str) -> tuple[Strategy | None, str]:
    """One script -> one strategy, or None and the reason it was skipped."""
    body = "\n".join(l.split("//")[0] for l in pine.splitlines())
    conds: list[Condition] = []
    for m in _CROSS.finditer(body):
        parsed = _args(body, m.end() - 1)
        if not parsed or len(parsed[0]) != 2:
            return None, "could not split the crossover arguments"
        (a, b), _ = parsed
        lt, rt = _term(a), _term(b)
        if lt is None or rt is None:
            return None, f"cannot read {a.strip()!r} or {b.strip()!r}"
        conds.append(Condition(
            lt, "cross_above" if m.group(1) == "crossover" else "cross_below", rt))
    for m in _CMP.finditer(body):
        rt = _term(m.group(2))
        if rt is None:
            return None, f"cannot read {m.group(2)!r}"
        conds.append(Condition(Term("price"),
                               "above" if m.group(1) == ">" else "below", rt))
    if not conds:
        return None, "no entry condition recognised"
    if len(conds) > 2:
        conds = conds[:2]
    side = _side(body)
    if side is None:
        return None, ("cannot tell which way it trades - no long/short or "
                      "buy/sell marker on the signal")
    return Strategy(name=name, side=side, entry=tuple(conds), source="tradingview",
                    note="translated from Pine; only the entry was read"), ""


_LONG = re.compile(r"\b(long|buy|bull)\w*\s*[:=]", re.I)
_SHORT = re.compile(r"\b(short|sell|bear)\w*\s*[:=]", re.I)


def _side(body: str) -> str | None:
    """Which way does it trade?

    **This is not inferred from the comparison, and that was a real bug.** A
    first version called `ta.crossunder(ta.rsi(close,14), 30)` a SHORT because
    the comparison points down. It is the classic dip-BUY. Reading the
    direction off the operator gets the oscillator family exactly backwards,
    and testing a strategy the wrong way round is worse than not testing it:
    it occupies a slot and answers a question nobody asked.

    So the direction is read from what the author named the signal, and when
    the script does not say, the script is skipped. Silence is cheap.
    """
    lo, sh = bool(_LONG.search(body)), bool(_SHORT.search(body))
    if lo == sh:              # both, or neither - ambiguous either way
        return None
    return "long" if lo else "short"


def load(folder: Path | None = None) -> tuple[list[Strategy], list[tuple[str, str]]]:
    """Every readable script in the folder, plus what was skipped and why."""
    folder = folder or PINE_DIR
    if not folder.exists():
        return [], [("(folder)", f"{folder} does not exist - nothing to read")]
    out, skipped = [], []
    for p in sorted(folder.glob("*.pine")):
        s, why = translate(p.read_text(errors="ignore"), p.stem)
        (out.append(s) if s else skipped.append((p.stem, why)))
    return out, skipped
