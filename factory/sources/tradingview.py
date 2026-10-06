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

from dataclasses import replace

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


#: What a model is asked to produce when the regex gives up. Kris, 2026-09-23:
#: "so for example we take 1 strategy from tradingview so AI will take it? or
#: script will take it and AI will adapt it for step 2?" - the script fetches,
#: the MODEL translates, the script tests. This is the translating half.
_AI_PROMPT = """Translate this TradingView Pine script into one JSON object
describing the ENTRY RULE it trades. Return ONLY the JSON object, no prose.

{{"side": "long"|"short",
  "entry": [{{"left": {{"kind": "...", "length": 0, "value": 0.0}},
              "op": "...", "right": {{...}}, "hold": 1}}],
  "stop_atr": 2.0, "target_atr": 3.0, "max_hold": 48,
  "name": "short label",
  "note": "what the author says this captures, in one sentence"}}

TRANSLATE THE ENTRY ONLY. Our engine exits on a fixed stop, target and hold,
so a script's own exit logic - trailing stops, state machines closing a
position, hysteresis on the way out - is OUT OF SCOPE and its absence is NOT a
reason to refuse. Say what makes the script ENTER.

"hold": N means the condition must have been true N bars running. This is how
a confirmation rule is expressed - "momentum has sat in the zone for 2 bars
before we signal". Only on above/below.

GRAMMAR - nothing outside it exists:
{grammar}
kind "const" carries its number in "value". Others carry a lookback in "length";
band / supertrend / range terms also read "value" as described above.
A script's ATR trailing stop, UT Bot, HalfTrend or Chandelier flip is a
Supertrend flip - translate it as one and list the difference as a simplification.
ALL entry conditions must hold on the same bar. 1-3 conditions.
stop_atr 0.5-5.0, target_atr 0.5-10.0, max_hold 4-480 bars. A script value
outside these is clamped to the nearest end and listed as a simplification.

THREE OUTCOMES, NOT TWO. Choose honestly:

1. EXACT - the entry trigger maps cleanly. Return the object.

2. SIMPLIFIED - you can express the TRIGGER, but some of the script's
   machinery around it does not fit. Return the object AND a
   "simplified": ["what you dropped", "..."] list saying exactly what.
   This is the normal outcome for a real script and it is WANTED. Dropping
   exit machinery is not a simplification worth listing - it is out of scope
   by definition. Do list: a threshold you had to collapse, a second
   condition you could not state, a smoothing you ignored.

3. CANNOT - the ENTRY TRIGGER ITSELF is not expressible. Return only
   {{"cannot": "<the exact Pine feature that is missing>"}}.
   Use this when there is no honest trigger to extract, not when the
   translation would merely be approximate. Naming the missing feature is
   useful on its own - it is how the grammar gets extended.

A silent wrong translation occupies a test slot and tells us nothing about the
original. A translation that SAYS what it dropped does not have that problem,
which is why 2 exists.

SCRIPT:
{pine}"""


def translate_ai(pine: str, name: str, *, model: str | None = None,
                 timeout: int | None = None, text: str | None = None
                 ) -> tuple[Strategy | None, str]:
    """The model's reading of one script, validated as hard as a proposal is.

    WHY A MODEL AT ALL. The regex above understands four patterns and skips
    everything else silently, which on a real library is most of it. A model
    reads Pine properly - and these ideas come from people who trade them, so
    each arrives with a mechanism already attached, which is the thing the
    enumerator can never supply.

    WHAT IT IS STILL NOT ALLOWED TO DO. It returns a `spec.Strategy`, never
    Python, so a translated script cannot read a future bar any more than an
    enumerated one can: `factory/guard.Window` exposes only negative indexing
    and the model is not writing the reader. Anything outside the grammar is
    validated to death by `sources.agent.validate` rather than approximated.

    `text` short-circuits the model call, for tests.
    """
    from factory.sources import agent

    prompt = _AI_PROMPT.format(grammar=agent._grammar(), pine=pine[:40000])
    try:
        out = text if text is not None else agent._call(
            prompt, model or agent.CLI_MODEL, timeout or agent.TIMEOUT)
    except agent.ProposalError as exc:
        return None, f"model call failed: {exc}"

    a, b = out.find("{"), out.rfind("}")
    if a < 0 or b < a:
        return None, f"no JSON object in output: {out[:120]}"
    import json as _json
    try:
        item = _json.loads(out[a:b + 1])
    except ValueError as exc:
        return None, f"bad JSON: {exc}"
    if "cannot" in item:
        # NOT a failure. The model naming the missing Pine feature is the
        # signal that widens the grammar, so it is reported in those words.
        return None, f"grammar gap: {item['cannot']}"
    try:
        s = agent.validate({**item, "name": item.get("name") or name})
    except agent.ProposalError as exc:
        return None, f"invalid translation: {exc}"

    # WHAT WAS DROPPED TRAVELS WITH THE IDEA. Kris's first real script was
    # refused twice for machinery our engine replaces anyway - the fixed
    # stop/target/hold means a script's own exit logic can never be carried,
    # so "not exact" was being treated as "not testable". A simplification
    # recorded in the note is honest and testable; a silent one is neither.
    dropped = item.get("simplified") or []
    if isinstance(dropped, str):
        dropped = [dropped]
    note = s.note
    if dropped:
        note = (note + "  SIMPLIFIED: " + "; ".join(str(d) for d in dropped))[:600]
    return replace(s, source="tradingview", note=note), ""


def load(folder: Path | None = None, *, ai: bool = False, model: str | None = None,
         paths=None) -> tuple[list[Strategy], list[tuple[str, str]]]:
    """Every readable script in the folder, plus what was skipped and why.

    `ai=True` sends whatever the regex could not read to a model. The regex
    runs FIRST and always: it is free, deterministic and reproducible, so the
    model is only paid for the remainder. On a library that is most of it.

    `paths` reads just those files - the fetcher's fresh downloads - so a
    folder of hundreds is not re-sent to the model every pass.
    """
    folder = folder or PINE_DIR
    if paths is None and not folder.exists():
        return [], [("(folder)", f"{folder} does not exist - nothing to read")]
    files = sorted(paths) if paths is not None else sorted(folder.glob("*.pine"))
    return _read_all(files, ai=ai, model=model)


def _read_one(p: Path, ai: bool, model: str | None):
    body = p.read_text(errors="ignore")
    s, why = translate(body, p.stem)
    if s is None and ai:
        s, why = translate_ai(body, p.stem, model=model)
    return p.stem, s, why


def _read_all(files, *, ai: bool, model: str | None, workers: int = 1):
    """Order is kept whatever `workers` is: results come back in `files` order."""
    from concurrent.futures import ThreadPoolExecutor

    with ThreadPoolExecutor(max(1, workers)) as ex:
        res = list(ex.map(lambda q: _read_one(q, ai, model), files))
    out = [s for _, s, _ in res if s]
    skipped = [(n, why) for n, s, why in res if not s]
    return out, skipped


#: What the reader could NOT take, and why. Kris, 2026-09-23: he wants to see
#: "how many strategies were found in tradingview" - a script that was read and
#: refused is part of that count, and a grammar gap is the most actionable
#: thing this source produces. Printing it and throwing it away meant the two
#: extensions that would widen the whole factory lived in a terminal scrollback.
SKIPPED = ROOT_DIR = None                       # set below, after ROOT resolves


def record_skips(skipped, path=None, translated=()) -> int:
    """Persist the refusals so the dashboard can show them.

    A script in `translated` read fine THIS time, so an old refusal of it is
    dropped - Quadapt was refused, the grammar grew, and it then showed as
    both refused and tested (2026-09-24).
    """
    import json as _json
    from factory import queue as _queue

    p = path or (_queue.DIR / "skipped.jsonl")
    p.parent.mkdir(parents=True, exist_ok=True)
    # A script read again REPLACES its old row, refused or not: a retry after
    # a model crash has a new reason, and the stale crash must not stand.
    redo = set(translated) | {n for n, _ in skipped}
    keep, dropped, before = [], False, set()
    if p.exists():
        for line in p.read_text().splitlines():
            if line.strip():
                try:
                    row = _json.loads(line)
                except ValueError:
                    continue
                before.add(row.get("script"))
                if row.get("script") in redo:
                    dropped = True
                    continue
                keep.append(line)
        if dropped:
            p.write_text("".join(l + "\n" for l in keep))
    new = [{"source": "tradingview", "script": n, "why": w,
            "gap": w.startswith("grammar gap")}
           for n, w in dict(skipped).items()]
    if new:
        with p.open("a") as fh:
            for r in new:
                fh.write(_json.dumps(r, separators=(",", ":")) + "\n")
    return sum(r["script"] not in before for r in new)     # scripts new to the file


#: Refusals worth another model call. A crash says nothing about the script;
#: an invalid translation may pass now the prompt states the ranges. A grammar
#: gap is the model's considered answer and is NOT re-asked.
RETRYABLE = ("model call failed", "invalid translation", "no JSON", "bad JSON")


def retry(limit: int | None = None, model: str | None = None, workers: int = 4,
          exclude=(), gaps: bool = False) -> tuple[list[Strategy], list[tuple[str, str]]]:
    """Re-translate refused scripts whose refusal was not the script's fault.

    Kris, 2026-09-30: 234 of 373 refusals were `model exited 1` with nothing
    said - the model was unreachable, not the script unreadable - and the loop
    only ever reads FRESH downloads, so they were never tried again.
    """
    import json as _json
    from factory import queue as _queue

    p = _queue.DIR / "skipped.jsonl"
    rows = [_json.loads(l) for l in p.read_text().splitlines()
            if l.strip()] if p.exists() else []
    # `gaps`: also re-ask scripts refused for a GRAMMAR gap - worth doing once
    # each time the grammar grows (2026-10-06: factory/terms.py).
    names = [r["script"] for r in rows
             if (str(r.get("why", "")).startswith(RETRYABLE)
                 or (gaps and r.get("gap")))
             and r["script"] not in exclude]
    paths = [PINE_DIR / f"{n}.pine" for n in names[:limit]]
    paths = [q for q in paths if q.exists()]
    if not paths:
        return [], []
    got, skipped = _read_all(paths, ai=True, model=model, workers=workers)
    record_skips(skipped, translated={q.stem for q in paths}
                 - {n for n, _ in skipped})
    return got, skipped


def _main(argv=None) -> int:
    """Read data/pine/, translate, and queue what came through."""
    import argparse

    from factory import queue

    ap = argparse.ArgumentParser(description=_main.__doc__)
    ap.add_argument("--ai", action="store_true",
                    help="send what the regex cannot read to a model")
    ap.add_argument("--folder", type=Path)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--retry", action="store_true",
                    help="re-ask the model only for refusals that were not the "
                         "script's fault (crashes, invalid output)")
    ap.add_argument("--retry-gaps", action="store_true",
                    help="--retry, plus scripts refused for a grammar gap "
                         "(run after the grammar grows)")
    a = ap.parse_args(argv)

    if a.retry or a.retry_gaps:
        got, skipped = retry(gaps=a.retry_gaps)
        print(f"{len(got)} translated, {len(skipped)} still refused")
        for n, w in skipped:
            print(f"  SKIP {n}: {w[:120]}")
        if not a.dry_run and got:
            print(queue.add(got, quiet=True))
        return 0

    got, skipped = load(a.folder, ai=a.ai)
    for s in got:
        print(f"  {s.label()}")
    gaps = [(n, w) for n, w in skipped if w.startswith("grammar gap")]
    for n, w in skipped:
        print(f"  SKIP {n}: {w}")
    folder = a.folder or PINE_DIR
    names = {q.stem for q in folder.glob("*.pine")} if folder.exists() else set()
    record_skips(skipped, translated=names - {n for n, _ in skipped})
    print(f"\n{len(got)} translated, {len(skipped)} skipped, "
          f"{len(gaps)} naming a grammar gap")
    if not a.dry_run and got:
        print(queue.add(got, quiet=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
