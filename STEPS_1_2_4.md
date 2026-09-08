# STEPS — items 1, 2, 4. Chosen by Kris 2026-09-08.

Plan of record is `NEXT.md`. This file is the step list only.
Why any of it exists: `SESSION_2026-09-07.md` §7.

**Kris picked 1, 2 and 4. Item 3 (pytest + CI) was not picked.**

One dependency has to be stated up front, because it changes the order:

* `core/KERNEL_CONTRACT.md` §4 says **item 4 must not start until five tests
  exist** — truncation, degenerate inputs, cost monotonicity, golden output,
  second-engine agreement. Item 4 moves code between files. Moving kernels
  without those tests is how a fix becomes a silent regression.
* **Item 2 builds four of those five anyway** — they are the gate's checks.
  So the plan below folds the missing frame (pytest runner, golden test, CI)
  into item 2 as ~2 hours of work, and item 4 stays last.
* Net effect: **1 → 2 (+ the frame) → 4.** Item 3 is not skipped, it is absorbed.

Standing rule still in force: **no new hypotheses until 1 and 2 are in.**

---

## ITEM 1 — kernel fingerprint and automatic staleness — **DONE 2026-09-08**

**Done-when condition met.** Appending one comment line to
`strategies/vwap/engine.py` and rerunning `core/build_scoreboard.py` takes H-002
from `6.0/10 TOO SLOW` to `3.0/10 STALE - scored on code that has since changed`,
naming the file, with no human editing a note. Same for H-016 on the ribbon
kernel. `core/fingerprint_selftest.py` covers all twenty cases and passes.

**What shipped:** `core/fingerprint.py`, `strategies/{vwap,ribbon}/manifest.py`,
`manifest=` now required by `core.board.write_board`, staleness rehashed in
`core/build_scoreboard.py`, a `STALE` banner in `core/scoreboard_template.html`,
a 3.0 cap in `core/scorecard.py`, and both live boards backfilled - each rewrote
byte-identical apart from the new `fingerprint` key.

**Three things the plan did not anticipate:**

1. **Two tiers, not one.** A change to the trade arithmetic (`engine.py`,
   `sweep.py`, the walk-forward stage) is a hard stale: the trade list is wrong.
   A change to `core/board.py` or `core/riskladder.py` is a **note**: the trades
   stand, the stored summary was computed by code that moved. One tier would have
   flagged every card on every cosmetic edit, and a flag that is always on is
   ignored.
2. **`stage18_goldbook.py` rewrote the board on import.** Its trigger was
   `if "--board" in sys.argv` at module level, so `stage20_deadfix.py --board` -
   which imports it - silently wrote the superseded pre-dead-bar-fix record
   first and the corrected one second. `stage11_reprice.py` had the identical
   bug. Both now guard on `__name__ == "__main__"`.
3. **The live ribbon board is written by `stage11_reprice.py --board`, not
   `stage10_board.py`.** Running stage 10 replaces the record with the
   superseded four-leg book that still contains **silver** - which is on the
   do-not-trade list in `CLAUDE.md`. Found by running it. Both stages now carry
   their own manifest so neither can claim the other's provenance.

### Steps as planned

**Goal.** The board marks its own records stale when the code that produced them
changes. Today `SUPERSEDED — SCORED ON A BROKEN KERNEL` is a note typed by hand
after someone noticed. H-009 held score 8.9 on a kernel that no longer existed.

**Done when.** Edit one byte of `strategies/vwap/engine.py`, rerun
`core/build_scoreboard.py`, and H-002 renders `STALE` — with no human editing a
note, and no rerun of the sweep.

### Steps

1. **`core/fingerprint.py`** — new file, no dependencies on anything else.
   * `hash_files(paths) -> str` — sha256 over sorted `(relpath, bytes)`. Not
     mtime; mtime changes on a checkout and would cry stale every clone.
   * `git_sha() -> str` — `git rev-parse HEAD`, plus a `dirty` bool from
     `git status --porcelain`. A result produced from a dirty tree must say so.
   * `hash_data(paths) -> dict` — per data file: sha256, row count, first and
     last timestamp. The date range matters on its own: the feeds grow daily and
     a result scored on a shorter series is not the same result.
   * `fingerprint(kernels, data, costs) -> dict` — assembles the record.

2. **Every hypothesis declares its inputs.** Add to each strategy folder a
   `manifest.py` (or a dict in the board stage) naming:
   `kernels = [...]`, `data = [...]`, `costs = {...}`.
   Start with `vwap` and `ribbon` — they are the only two live boards.

3. **`core/board.py::write_board`** — new keyword `manifest`, and write
   `rec["fingerprint"] = fingerprint(...)`. Make it **required**: a board record
   without a fingerprint is exactly the hole this item closes, so raise rather
   than default to `None`.

4. **`core/build_scoreboard.py::load`** — recompute the fingerprint from the
   files on disk and compare against the stored one. Emit
   `stale: {kernel: bool, data: bool, git: bool, detail: str}`.
   Data drift is a **note**, not a kill — the feeds legitimately grow. A kernel
   hash change is a **hard stale**.

5. **Render it.** `core/scoreboard_template.html` — a `STALE` badge on the card,
   listing which file changed. Same visual weight as `TOO SLOW`; both are facts
   that override the score.

6. **`core/scorecard.py`** — a hard-stale record cannot exceed `EVIDENCE_CAP`
   (3.0). It was measured on code that no longer exists, which is the same
   epistemic position as never having been measured.

7. **Backfill.** Run it over the existing `backtests/*/board.json`. Every record
   predating this work has no fingerprint — mark those `UNFINGERPRINTED` rather
   than inventing one. Expect H-002 and H-016 to be the only clean rows.

**Cost.** ~1 day. Self-contained; touches no kernel arithmetic.

---

## ITEM 2 — a verification gate in code — **DONE 2026-09-08**

**Done-when condition met.** H-016 dropped from 5.0 to **3.0 / UNVERIFIED
(second_engine)** by itself. Its ribbon kernel has never been through a second
engine, the test for it exists and skips with that reason, and the gate reads
the skip. H-002 passes all eight checks and keeps 6.0. Nobody typed either
outcome.

```
H-002 VWAP - gold only    6.0/10  TOO SLOW - 144d against a 5-14d target
H-016 MA ribbon           3.0/10  UNVERIFIED - has not passed the checks
                                  UNVERIFIED (second_engine)
```

**What shipped:** `pytest` + `hypothesis` pinned, `pytest.ini`, `tests/` with a
shared kernel adapter (`tests/kernels.py`), 64 tests, `core/verification.py`
writing `backtests/<sid>/verification.json`, a 3.0 cap and an `UNVERIFIED`
verdict in `core/scorecard.py`, a per-check banner on the board card, and
`.github/workflows/tests.yml` - the repo's first CI.

**A skip is not a pass.** The gate reads junit XML rather than an exit code,
because "everything passed" and "everything was skipped" both exit 0 and the
difference between them is the entire point.

**Four real bugs found by writing the tests:**

1. **Both kernels crashed on an empty series.** `IndexError` from `pc[0] = c[0]`
   in `strategies/ribbon/engine.py::atr_wilder` and
   `strategies/vwap/sweep.py::features`. Not hypothetical:
   `sweep.load_tf` **returns an empty frame** for a timeframe the cache cannot
   serve, and a walk-forward fold can open on a window with no bars.
2. **`strategies/ribbon/test_parity.py` was never run by anything.** It is named
   like a test, it is a good check, and it is a *script* with a `main()` and no
   test functions - so pytest never collected it. Worse than not having it: it
   made ribbon's indicators look covered. Now wrapped by
   `tests/test_ribbon_parity.py`.
3. **The truncation test's first failure was real but not a look-ahead.** Both
   kernels force-close an open position at the end of the data, so truncating
   manufactures one extra "closed" trade. Ribbon's alternate config, 126 against
   127. The comparator now excludes the final bar and says why.
4. **`-k vwap` selected the slow cross-check.** The gate would have run 5m gold
   at ~270,000 bars on every invocation. Slow tests are deselected by default and
   `verification.json` records the depth, so a fast pass cannot claim the full
   cross-check.

**One design change:** checks are required by default - "no tests matched" fails,
because a hypothesis with no look-ahead test has not been shown to be free of
look-ahead. `OPTIONAL` holds the exceptions (ribbon's Pine parity has no vwap
equivalent, and inventing one so the table looks symmetrical would be theatre).

### Steps as planned

**Goal.** A hypothesis cannot carry a real board score until it has passed the
checks, in code. Today the scorecard has an evidence *weight* but nothing
*gates* — H-009 reached 8.9 without a second engine ever looking at it.

**Done when.** A new hypothesis with no `verification.json` is capped at 3.0 on
the board automatically, and `pytest` runs the five checks against both kernels.

### Steps

1. **The frame (this is the absorbed part of item 3, ~2h).**
   * `pip install pytest hypothesis`, pin both in `requirements.txt`.
   * `pytest.ini`, `tests/` at the repo root, `conftest.py` with fixtures that
     load a small fixed slice of BTCUSDT 15m and XAUUSD 1h.
   * `hypothesis` earns its place here: every bug this project has found was a
     degenerate input nobody thought to write by hand. Let it generate them.

2. **`tests/test_no_lookahead.py`** — highest value, write it first.
   Truncate the series at N, rerun the kernel, assert every trade before N is
   **byte-identical**. Run over both kernels and a sample of configs.
   *This single test would have caught the 2026-09-05 look-aheads immediately.*

3. **`tests/test_degenerate.py`** — zero-volume bars, flat OHLC, `sd = 0`,
   one bar, constant price, empty series. Property-based.
   Assert the two FX rules from `CLAUDE.md` hold: **no decision or fill on a
   zero-volume bar**, and the volatility guard uses `sd <= price * 1e-6`, never
   `sd <= 0.0`. Both are last session's bugs; they must not come back.

4. **`tests/test_costs.py`** — PF strictly falls as cost rises 0x → 1x → 2x → 3x,
   and the linear identity `reprice` depends on holds.

5. **`tests/test_golden.py`** — pin one known config's trade list per kernel to a
   checked-in fixture. Any edit that moves it must be explained in the commit
   message rather than discovered three weeks later.

6. **`tests/test_second_engine.py`** — make the NautilusTrader cross-check
   automatic. It ran once by hand for gold (26/26 exact). **It is the check that
   has actually found bugs**; running it once by hand is the whole gap.
   Mark it `@pytest.mark.slow` and exclude from the fast run.

7. **`core/verification.py`** — runs the checks for one hypothesis and writes
   `backtests/<id>/verification.json`:
   `{check: {passed, when, detail, fingerprint}}`. The fingerprint field matters
   — a pass earned on an old kernel is not a pass. This is where item 1 pays for
   itself twice.
   Include the **paired null** here as a check with a pass/fail, not a number
   read by eye.

8. **`core/scorecard.py`** — read `verification.json`. Any check missing or
   failed caps the total at `EVIDENCE_CAP`. Render *which* check is missing on
   the card, so the fix is obvious.

9. **CI.** GitHub Actions on push: fast tests on every push, `slow` nightly.
   There is no CI today.

10. **Backfill.** Run the gate over H-002 and H-016. Expect H-016 to cap — it has
    the null but has **never** been through a second engine. That is the correct
    answer, not a bug in the gate.

**Cost.** ~2 days including the frame.

---

## ITEM 4 — one `Strategy` interface — **steps 1-3 and 5 done 2026-09-08**

`core/strategy.py` holds the `Strategy` Protocol, the fixed column indices, a
`conforms()` check over the trade array and `as_frame()`. Both kernels declare
themselves through `strategies/<x>/strategy.py`, and `tests/kernels.py` now goes
THROUGH those declarations rather than around them - an interface the tests
bypass is untested decoration. `tests/test_contract.py` asserts conformance.
The golden trade lists did not move, which is the whole point of a declaration:
no arithmetic was touched.

**Step 5 — extracting the shared pieces — was measured and declined.** The plan
assumed cost application, R computation and the min-risk floor were worth
pulling into one place. Counted, they are **one line each per kernel**:

```
strategies/vwap/engine.py    393 lines   cost 1  fees 1  min-risk 1  R 1
strategies/ribbon/engine.py  337 lines   cost 1  fees 1  min-risk 1  R 1
```

Moving three lines out of a `@njit` kernel means either jitted helper calls in
the hottest loop in the project, with no guarantee numba inlines them, or
nothing. The protection that actually matters is already in place and is
behavioural rather than structural: `tests/test_costs.py` asserts cost
monotonicity and the affine-in-cost identity **for both kernels**, so the two
implementations cannot drift apart without a test going red. Recorded rather
than skipped.

### Steps as planned

**Goal.** Kernels become a tested shared library instead of each hypothesis
reinventing the engine. **This is a refactor, not a fix.** It makes future work
cheaper. It does not stop the bleeding — items 1 and 2 do that.

**Do not start until items 1 and 2 are green**, and specifically until the five
tests in step 2 above pass on both kernels. That is the whole reason they come
first: this item moves code across files, and the tests are what prove the move
changed nothing.

### Steps

1. **Freeze the contract.** `core/KERNEL_CONTRACT.md` §1 is already written and
   already true of both kernels. Promote §3's sketch to `core/strategy.py` as a
   `Protocol`: `features()`, `grid()`, `run()`, returning the `(n, 8)` array.
   Nothing downstream changes — `sweep`, walk-forward, null, `board.py`,
   `riskladder` and `scorecard` all already work off that array. **That is why
   this refactor is safe and also why it is not urgent.**

2. **Port `vwap` first.** It is the better-tested kernel: second-engine checked,
   26/26 exact. Golden test from item 2 step 5 must produce a byte-identical
   trade list before and after. If it moves, the port is wrong — not the test.

3. **Port `ribbon` second.** Same bar. Its `test_parity.py` covers indicators
   only, so it leans harder on the new golden and truncation tests.

4. **Do not touch `strategies/orderflow/orderflow.py`.** It is **not** a strategy
   kernel — it is the shared feed loader imported by 20+ files across a dozen
   hypotheses. It survived H-006's death for that reason. Folding it into the
   contract or deleting it would break twelve things.

5. **Shared pieces out of the kernels, once both are ported:** cost application,
   R computation, the `live` / zero-volume mask, the volatility guard tolerance.
   One implementation, one place to fix the next bug.

6. **Re-run both boards.** Fingerprints change (item 1 does its job and marks
   everything stale). Scores must land identical to three decimals. Any drift is
   a regression introduced by the refactor and must be explained before the
   board is republished.

**Cost.** ~1 week. Lowest urgency of the three.

---

---

## TASK A — port the ribbon kernel to a second engine — **DONE 2026-09-08**

Not on the original list. It became the top item the moment item 2 shipped,
because it was the ONLY thing capping H-016: everything else passed.

`strategies/ribbon/stage12_nautilus.py` streams the kernel through
NautilusTrader one bar at a time. The strategy holds no array it could index
into, so it cannot reproduce a look-ahead even by accident.

**108 of 108 rule shapes match exactly** across 15m/30m/1h/4h — every entry bar,
every exit bar, `max |dR| = 0`.

| timeframe | shapes | exact |
|---|---|---|
| 15m | 27 | 27 |
| 30m | 27 | 27 |
| 1h | 27 | 27 |
| 4h | 27 | 27 |

**Say which half a cross-check covers.** This one verifies the TRADE LOGIC —
entry timing, initial stop, both trailing forms, flip exit, time stop, intrabar
ordering, dead-bar guards, cost and R. It does NOT verify the twenty moving
averages; those are covered by `test_parity.py` against a literal reading of the
Pine and are handed to the stream one bar at a time. "It agrees" without saying
what agreed is not a claim anyone can check.

**Two things went wrong and both are worth keeping:**

1. `self.stop = 0.0` in the strategy silently overwrote NautilusTrader's
   `Strategy.stop()` lifecycle method, and the engine died on shutdown with
   `'numpy.float64' object is not callable`. Renamed `stop_px`.
2. **The first run was nearly worthless and looked fine.** It drew its
   configurations from the fold file and got twelve rows that were all
   `mode 0, entry_thr 1.0, trail_mode 0`. Twelve passes, no coverage — the
   board's own legs use the **chandelier** trail, which recomputes its distance
   from ATR on every bar and is the branch most likely to break in a streaming
   port. `covering_configs` now takes one configuration per distinct CODE PATH
   plus the board's own rule. A cross-check is about branches, not about tuning.

**Result: H-016 3.0 → 6.0.** It did not get the score back by being argued for;
it got it back by being checked.

---

## Order and rough calendar

| # | item | cost | gate to start |
|---|---|---|---|
| 1 | fingerprint + auto-stale | ~1 day | nothing — start here |
| 2 | verification gate (+ pytest, golden, CI) | ~2 days | item 1, for the fingerprint field |
| 4 | one `Strategy` interface | ~1 week | items 1 and 2 green, 5 tests passing |

**No new hypotheses until 1 and 2 are done.** Kris, 2026-09-07.

## What this does NOT fix

Stated plainly so it is not a surprise later. None of these three items makes a
strategy faster. The board's two survivors need **143.6** and **175.9** expected
days against a **5-14 day** target. Items 1, 2 and 4 make the numbers
*trustworthy*; they do not make them *good*. The pace problem is a hypothesis
problem and it is still open — see `IDEAS.md` and `NEXT.md` "the hard fact".
