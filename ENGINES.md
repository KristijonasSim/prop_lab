# The three engines — 2026-09-08

Kris's framing: the project is a machine with three engines. This is what each
one is, what exists, and what does not.

---

## Engine 1 — Hypothesis generator

**Job:** produce candidate mechanisms and kill the bad ones before any code.

| piece | state |
|---|---|
| `core/target_profile.py` — what shape a strategy must have to pass the firm | built |
| `CANDIDATES.md` — what survived 26 hypotheses, what is untested, what is closed | written |
| A gate that every idea must pass before code is written | **missing** |

**Not started properly.** Agreed with Kris: after Engine 2.

---

## Engine 2 — Strategy builder

**Job:** turn an idea into a scored, verified board record without hand-writing
a pipeline every time.

| piece | state |
|---|---|
| `core/strategy.py` — the `Strategy` interface and the output contract | built |
| `core/pipeline.py` — blind quarterly walk-forward + paired null | built, **reproduces the old hand-written walk-forward exactly** |
| `core/markets.py` — one loader, per-market costs, maker/taker/mixed execution | built |
| `core/nulls.py` — phase-randomised markets, byte-identical to the originals | built |
| `core/run_hypothesis.py` — walk-forward every market, promote the best per class | built |
| `core/build_board.py` + `core/board_template.html` — the page | built |
| `tests/test_pipeline.py` — 12 tests, including a direct proof of no leakage | built |
| Parallelism | **missing** — single-threaded; the old stage6 used 14 processes |

**A hypothesis is now one file.** `strategies/vwap/hypothesis.py` is the shape:
say what to run it on, and the pipeline does the rest. The old H-002 needed 25
hand-written files to reach the same place.

**The ~90 old stage scripts are still on disk.** They come out once anything
worth keeping has been ported. Deleting them before extracting the pipeline
would have destroyed the only reference implementation.

---

## Engine 3 — Testing engine

**Job:** decide whether a result can be believed.

| piece | state |
|---|---|
| 130 tests, ~13 seconds | green |
| CI on every push, full cross-check nightly | green on GitHub |
| Look-ahead (truncation), degenerate inputs, cost linearity, golden trade lists | green |
| Both kernels against NautilusTrader | green |
| Fingerprint + automatic staleness | green |
| Verification gate — no score above 3.0 without passing every check | green |
| Prop simulator (18 tests) and data integrity (24) | green |
| **2 cross-check disagreements** — 30m (4 trades), 15m (1 trade) | **open**, failing in `pytest -m slow` on purpose |
| Nightly slow suite has never completed clean end to end | **unproven** |

---

## What the machine cannot do

Everything above proves the CODE does what we think. None of it says a strategy
makes money. The previous repo had a strategy that backtested at PF 3.0 and
traded live at 0.7 — the code was correct and the fill assumption was not. Two
bugs of exactly that class were found and fixed on 2026-09-08 (exits on dead
bars, stops filling through a gap). The only real test is a broker.

---

## Known stale

`core/verify_board.py` still hardcodes the old 8% / 4% / 8% firm spec. It is a
deliberately independent auditor — it does not import from the repo, by design —
so it did not move when the real firm did, and it will now disagree with the
board for the wrong reason.
