"""Sort the "could not translate" list by WHAT IS MISSING, for free.

Kris, 2026-10-06: retrying the refused backlog burned a 5-hour usage window in
about 15 minutes and cleared 5 scripts. Re-asking the model about every refusal
each time the grammar grows is the expensive way. Most refusals name a feature
the grammar will never have (another symbol, a neural net, a DCA bot with no
entry), and re-asking about those gets the same answer at full price.

So the model's own refusal reason - already on disk - is sorted here with
regexes, no model call:

    never      no grammar change could ever express it. Never re-asked.
    retry      the grammar has grown to cover it. Worth ONE model call.
    <feature>  a named missing feature. Build the feature, then retry only
               that bucket: `python -m factory.sources.tradingview
               --retry-gaps --bucket <feature>`.

First matching rule wins, so the order below is the priority.
"""
from __future__ import annotations

import re
from collections import Counter

#: (bucket, label shown on the board, pattern on the refusal reason)
RULES: list[tuple[str, str, re.Pattern]] = [(b, lbl, re.compile(p, re.I)) for b, lbl, p in [
    # --- never: no single-symbol bar grammar can carry these ---------------
    ("never", "no entry rule (DCA / always-in)",
     r"no entry condition exists|unconditional re-entry|whenever the script is flat"),
    ("never", "ML / neural net / closed library",
     r"xgb|neuron|spiking|\bimport\b.*/|closed ext"),
    ("never", "another symbol or earnings data",
     r"request\.earnings|another symbol|other symbol|different symbol|CBOE:VIX|"
     r"cross-symbol|two other symbols"),
    ("never", "user-picked input source",
     r"input\.source"),
    ("never", "calendar / one-off entry",
     r"calendar|startDate|dayofweek|day-of-week|bar_index >= lastBuy"),
    ("never", "price grid with per-level state",
     r"(fixed|geometric|grid|precomputed|hardcoded).{0,60}(price )?levels|gridLevels"),
    # --- features that also block a two-bar-back script: checked first ------
    ("mtf", "higher-timeframe data (request.security)",
     r"request\.security|higher[- ]timeframe|multi-timeframe|15S-timeframe"),
    ("state", "remembered level / zone (var state)",
     r"\bvar\b|stateful|stored|remember|persistent|pending|\barms\b"),
    # --- retry: the grammar now covers it (offset on any term, 2026-10-06) --
    ("retry", "two-bar-back values - offset now covers it",
     r"high\[2\]|low\[2\]|one-bar-back|only lagged terms"),
    ("retry", "value out of range - clamp rule now in prompt",
     r"^invalid translation"),
    # --- features: build one, unlock its bucket ----------------------------
    ("pivots", "pivot events, divergence, zigzag, fib from pivots",
     r"pivot|divergence|zigzag|fibonacci|fib "),
    ("custom_series", "indicator on an indicator / custom series",
     r"applied to (an indicator|the rsi|a custom)|on the rsi series|custom computed|"
     r"custom diff|wavetrend|heikin|tmo|for-loop|ichimoku|accel"),
    ("or_logic", "OR across many rules / patterns",
     r"(?-i:\bOR\b)|any one rule|if/else-if|vote count"),
    ("time", "exact clock-time anchor",
     r"time-of-day|09:30|hour\(time|clock-window|minute\("),
    ("levels", "price lattice / round numbers",
     r"round-number|lattice|floor"),
]]

LABEL = {b: lbl for b, lbl, _ in RULES}


def bucket(why: str) -> tuple[str, str]:
    """(bucket, label) for one refusal reason."""
    text = re.sub(r"^grammar gap:\s*", "", str(why))
    for b, lbl, pat in RULES:
        if pat.search(text) or pat.search(str(why)):
            return b, lbl
    return "other", "other"


def tag(rows: list[dict]) -> list[dict]:
    """Rows with `bucket` and `label` added. Input is not modified."""
    out = []
    for r in rows:
        b, lbl = bucket(r.get("why", ""))
        out.append({**r, "bucket": b, "label": lbl})
    return out


def summary(rows: list[dict]) -> list[tuple[str, int]]:
    return Counter(r["bucket"] for r in tag(rows)).most_common()


def _main() -> int:
    from factory import queue

    rows = queue.rows(queue.DIR / "skipped.jsonl")
    tagged = tag(rows)
    for b, n in summary(rows):
        print(f"{n:4}  {b}")
        for r in tagged:
            if r["bucket"] == b:
                print(f"        {r['label'][:40]:40}  {r['script']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
