"""SOURCE 3 — A MODEL PROPOSES THE IDEAS, WITH A REASON ATTACHED.

Kris, 2026-09-23: *"on a simple script that runs locally we wont achieve
anything without someone who can think."*

He is right, and the measurement agrees with him. `sources/invent.py`
enumerates a fixed grammar and that grammar has **308 combinations in total** -
it runs dry in about a week - while 87% of what it produces dies on trade
count. A generator that cannot think is what produces that.

WHERE THE MODEL SITS, AND WHERE IT DOES NOT. Step 1 only. It writes ideas into
the same queue the enumerator writes to and then exits. Steps 2 to 7 never call
a model: they are run thousands of times, they must give the same answer twice,
and a model in that path makes a result nobody can reproduce. In particular the
model is NOT allowed near step 4's repair list - choosing the tweak after
seeing the failure is the difference between a repair stage and a fishing
expedition, and this repo has measured that family dead three times.

WHAT THE MODEL CAN AND CANNOT EXPRESS, and this is the safety property.

It returns JSON in the `spec.Strategy` grammar - a side, entry conditions,
a stop, a target, a hold - and **never Python**. So a proposed idea:

  * cannot read a future bar, because `factory/guard.Window` exposes only
    negative indexing and the model is not writing the reader;
  * cannot invent an indicator, because `validate` rejects any `kind` outside
    `spec.INDICATORS`;
  * cannot smuggle in a parameter sweep, because one call returns N distinct
    fingerprints and `queue.add` drops anything already tried.

EVERY IDEA MUST CARRY A MECHANISM. `note` is required and an idea without one
is rejected with the reason sent back to the model. That is the whole point of
using a model rather than a loop: `CLAUDE.md` asks for the mechanism - who is
on the other side - to be stated BEFORE results, and an enumerator can never
supply it.

THE THING THIS MUST NOT BECOME. `core/searchcost.py` already reports 228 trials
charged against a budget of 13 on three years of data. **An agent that
generates a thousand rules a night makes that worse, not better.** The job here
is fewer, better-motivated ideas - and whether it is working is measurable:
compare this source's step-5 survival against the enumerator's. If the model's
ideas do not survive at a better rate, the model is not helping and the number
will say so.

    python -m factory.sources.agent -n 20          # propose and queue
    python -m factory.sources.agent -n 5 --dry-run # print, queue nothing
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from factory.spec import (COMPARISONS, INDICATORS, SIDES, Condition,  # noqa: E402
                          Strategy, Term)

#: `claude -p` on the logged-in session, so no API key is needed. Same route
#: `research/propose.py` uses and for the same reason.
CLI_MODEL = "sonnet"
TIMEOUT = 300
#: Run from a neutral directory so this repo's own CLAUDE.md is not pulled into
#: every call - it is 400 lines and it is not the prompt.
NEUTRAL_CWD = os.path.expanduser("~")

#: Bounds on what a proposal may set. Not taste - these are the ranges the rest
#: of the pipeline is built for, and a value outside them breaks a downstream
#: assumption rather than merely being unusual.
STOP_RANGE = (0.5, 5.0)
TARGET_RANGE = (0.5, 10.0)
HOLD_RANGE = (4, 480)
#: `sources/invent.py` fixes these; a proposal may move them, within the ranges.
DEFAULTS = {"stop_atr": 2.0, "target_atr": 3.0, "max_hold": 48}
#: A mechanism this short is not a mechanism.
MIN_NOTE = 30
#: Lookback bounds. The FLOOR exists because the first live batch proposed
#: `price above vwap1`, and a one-bar average is not an average - it is the bar
#: itself, so the condition is trivially true or false and the slot is wasted.
#: The enumerator's own `spec.LENGTHS` starts at 5; the model is allowed finer
#: than that, which is part of why it is here, but not degenerate.
MIN_LENGTH, MAX_LENGTH = 3, 400
#: A condition required to hold longer than this is a regime, not an entry,
#: and it will fail step 3's trade-count floor before it tells us anything.
MAX_HOLD = 20

#: THE BOTTLENECK, told to the model in its own words. 833 of 960 cell-tests
#: (87%) failed on trade count, against 99 on cost and 4 on the drift control.
#: `docs/STEP4.md`.
TRADE_FLOOR = "0.4 trades/day AND 100 trades minimum"


class ProposalError(ValueError):
    """Raised with a message meant for the MODEL, not for a human."""


def _grammar() -> str:
    names = ", ".join(sorted(k for k in INDICATORS if k != "hour"))
    return (f"indicators: {names}, or a plain number\n"
            f"  wpr = Williams %R, 0 at the top of the n-bar range, -100 at the bottom\n"
            f"  roc = rate of change in BASIS POINTS, not percent\n"
            f"comparisons: {', '.join(COMPARISONS)}\n"
            f'a condition may add "hold": N - it must have been true N bars '
            f"running. Only on above/below; a cross is a one-bar event.\n"
            f"sides: {', '.join(SIDES)}")


def _prompt(n: int, avoid: list[str]) -> str:
    seen = "\n".join(f"  {a}" for a in avoid[:60]) or "  (nothing yet)"
    return f"""You are proposing intraday trading rules for a systematic research pipeline.
Return ONLY a JSON array of {n} objects. No prose, no markdown fence.

Each object:
{{"side": "long"|"short",
  "entry": [{{"left": {{"kind": "...", "length": 0, "value": 0.0}},
              "op": "...",
              "right": {{"kind": "...", "length": 0, "value": 0.0}}}}],
  "stop_atr": 2.0, "target_atr": 3.0, "max_hold": 48,
  "name": "short label",
  "note": "the MECHANISM: who is on the other side of this trade and why they lose"}}

A condition may carry "hold": N, meaning it must have been true for N bars
running before the rule fires. Use it for confirmation rules.

GRAMMAR - anything outside it is rejected:
{_grammar()}
kind "const" carries its number in "value" and length 0.
Any other kind carries its lookback in "length" (3-400) and value 0.
ALL entry conditions must hold on the SAME bar. 1-3 conditions.
stop_atr {STOP_RANGE[0]}-{STOP_RANGE[1]}, target_atr {TARGET_RANGE[0]}-{TARGET_RANGE[1]},
max_hold {HOLD_RANGE[0]}-{HOLD_RANGE[1]} bars.

WHAT IS TESTED: gold, silver, BTC, EURUSD, GBPUSD, USDJPY on 15m/1h/4h/1d,
three years, costs charged, and every rule is compared against the SAME rule
entered at random bars. A rule that only works because the market rose is
killed by that control.

THE BINDING CONSTRAINT, and it is why most proposals die:
87% of everything tested fails on TRADE COUNT. The floor is {TRADE_FLOOR}.
Rare crossings on long lookbacks fire a few times a year and are wasted.
PREFER conditions that are true often - states, not rare events - or short
lookbacks. A rule firing under ~0.4 times a day cannot be tested here at all.

"note" is REQUIRED and must name the mechanism. "momentum works" is not a
mechanism. Who is forced to trade against this, and why can they not stop?

ALREADY TESTED - do not repeat these or trivial reparameterisations:
{seen}

Return the JSON array only."""


def _term(d: dict, where: str) -> Term:
    if not isinstance(d, dict):
        raise ProposalError(f"{where}: not an object")
    kind = d.get("kind")
    if kind == "const":
        try:
            return Term("const", 0, float(d.get("value", 0.0)))
        except (TypeError, ValueError):
            raise ProposalError(f"{where}: const needs a numeric value")
    if kind not in INDICATORS:
        raise ProposalError(f"{where}: unknown indicator {kind!r}")
    if kind == "hour":
        raise ProposalError(f"{where}: 'hour' is step 4's, not an entry term")
    needs_n = INDICATORS[kind][1]
    n = int(d.get("length", 0) or 0)
    if needs_n and not MIN_LENGTH <= n <= MAX_LENGTH:
        raise ProposalError(f"{where}: {kind} needs a length "
                            f"{MIN_LENGTH}-{MAX_LENGTH}, got {n}")
    return Term(kind, n if needs_n else 0, 0.0)


def validate(item: dict) -> Strategy:
    """One proposal into a Strategy, or a ProposalError naming what is wrong.

    HARD, and the errors are written for the model. Anything that fails is
    dropped and the reason is printed, never approximated into something that
    parses - a guessed rule occupies a test slot, gets charged to the ledger,
    and tells us nothing about what was proposed.
    """
    if not isinstance(item, dict):
        raise ProposalError("not an object")
    side = item.get("side")
    if side not in SIDES:
        raise ProposalError(f"side must be one of {SIDES}, got {side!r}")

    conds = item.get("entry")
    if not isinstance(conds, list) or not 1 <= len(conds) <= 3:
        raise ProposalError("entry must be a list of 1-3 conditions")
    entry = []
    for i, c in enumerate(conds):
        if not isinstance(c, dict) or c.get("op") not in COMPARISONS:
            raise ProposalError(f"condition {i}: op must be one of {COMPARISONS}")
        left = _term(c.get("left"), f"condition {i} left")
        right = _term(c.get("right"), f"condition {i} right")
        if left == right:
            raise ProposalError(f"condition {i}: both sides are the same term")
        try:
            hold = int(c.get("hold", 1) or 1)
        except (TypeError, ValueError):
            raise ProposalError(f"condition {i}: hold must be a whole number")
        if not 1 <= hold <= MAX_HOLD:
            raise ProposalError(f"condition {i}: hold must be 1-{MAX_HOLD}, got {hold}")
        try:
            entry.append(Condition(left, c["op"], right, hold=hold))
        except ValueError as exc:
            raise ProposalError(f"condition {i}: {exc}") from exc

    note = str(item.get("note", "")).strip()
    if len(note) < MIN_NOTE:
        raise ProposalError("note must state the MECHANISM - who is on the "
                            "other side and why they lose")

    nums = {}
    for key, (lo, hi) in (("stop_atr", STOP_RANGE), ("target_atr", TARGET_RANGE),
                          ("max_hold", HOLD_RANGE)):
        v = item.get(key, DEFAULTS[key])
        try:
            v = int(v) if key == "max_hold" else float(v)
        except (TypeError, ValueError):
            raise ProposalError(f"{key}: not a number")
        if not lo <= v <= hi:
            raise ProposalError(f"{key} must be {lo}-{hi}, got {v}")
        nums[key] = v

    return Strategy(name=str(item.get("name") or "model idea")[:60],
                    side=side, entry=tuple(entry), source="agent",
                    note=note, **nums)


def _call(prompt: str, model: str, timeout: int) -> str:
    try:
        proc = subprocess.run(["claude", "-p", prompt, "--model", model],
                              capture_output=True, text=True, timeout=timeout,
                              cwd=NEUTRAL_CWD)
    except FileNotFoundError as exc:
        raise ProposalError("the `claude` CLI is not on PATH") from exc
    except subprocess.TimeoutExpired as exc:
        raise ProposalError(f"model call timed out after {timeout}s") from exc
    if proc.returncode != 0:
        raise ProposalError(f"model exited {proc.returncode}: {proc.stderr[:300]}")
    return proc.stdout.strip()


def parse(text: str) -> list[dict]:
    """The JSON array out of whatever the model wrapped it in."""
    a, b = text.find("["), text.rfind("]")
    if a < 0 or b < a:
        raise ProposalError(f"no JSON array in output: {text[:200]}")
    try:
        raw = json.loads(text[a:b + 1])
    except ValueError as exc:
        raise ProposalError(f"bad JSON: {exc}") from exc
    if not isinstance(raw, list):
        raise ProposalError("top level is not an array")
    return raw


def propose(n: int = 20, *, model: str = CLI_MODEL, timeout: int = TIMEOUT,
            avoid: list[str] | None = None, text: str | None = None
            ) -> tuple[list[Strategy], list[str]]:
    """Ask for `n` ideas. Returns (accepted, rejection reasons).

    `text` short-circuits the model call and is what the tests use.
    """
    from factory import queue

    if avoid is None:
        avoid = sorted(queue.fingerprints())
    out = text if text is not None else _call(_prompt(n, avoid), model, timeout)

    kept: list[Strategy] = []
    rejected: list[str] = []
    seen = set(avoid)
    for item in parse(out):
        try:
            s = validate(item)
        except ProposalError as exc:
            rejected.append(f"{str(item)[:40]}: {exc}")
            continue
        fp = s.fingerprint()
        if fp in seen:
            rejected.append(f"{s.label()}: already tested")
            continue
        seen.add(fp)
        kept.append(s)
    return kept[:n], rejected


def fill(n: int = 20, **kw) -> dict:
    """Propose and queue. The entry point `factory/nightly.py` calls.

    An unattended loop that stops on a bad parse is not unattended, so a failed
    call is REPORTED and returns zero rather than raising. The caller tops up
    from `sources/invent.py` when this returns nothing.
    """
    from factory import queue

    try:
        kept, rejected = propose(n, **kw)
    except ProposalError as exc:
        print(f"[agent] {exc}", file=sys.stderr)
        return {"added": 0, "rejected": 0, "error": str(exc)}
    # Reported, never swallowed: a generator that has started emitting invalid
    # proposals looks from outside exactly like one that is working.
    if rejected:
        print(f"[agent] kept {len(kept)}, rejected {len(rejected)}:", file=sys.stderr)
        for r in rejected:
            print(f"  - {r}", file=sys.stderr)
    res = queue.add(kept, quiet=True)
    return {**res, "rejected": len(rejected)}


def _main(argv=None) -> int:
    import argparse

    ap = argparse.ArgumentParser(description="Step 1: a model proposes ideas.")
    ap.add_argument("-n", "--count", type=int, default=20)
    ap.add_argument("--model", default=CLI_MODEL)
    ap.add_argument("--timeout", type=int, default=TIMEOUT)
    ap.add_argument("--dry-run", action="store_true", help="print, queue nothing")
    a = ap.parse_args(argv)

    if a.dry_run:
        kept, rejected = propose(a.count, model=a.model, timeout=a.timeout)
        for s in kept:
            print(f"{s.label():60}  stop {s.stop_atr:g} tgt {s.target_atr:g} "
                  f"hold {s.max_hold}\n    {s.note}")
        print(f"\n{len(kept)} valid, {len(rejected)} rejected")
        for r in rejected:
            print(f"  - {r}")
        return 0
    print(json.dumps(fill(a.count, model=a.model, timeout=a.timeout), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
