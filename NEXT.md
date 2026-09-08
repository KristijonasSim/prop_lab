# What to do next — rewritten 2026-09-07

Read `SESSION_2026-09-07.md` first for why. This file is only the plan.

**Standing instruction from Kris, 2026-09-07: no new hypotheses until items 1–3
are done.** The project keeps producing results and then invalidating them weeks
later. That stops before anything else is built.

---

## STATE AS OF 2026-09-08 — items 1, 2, 3, 4 and task A are DONE

Full detail in `STEPS_1_2_4.md`. What changed:

| | before today | now |
|---|---|---|
| H-002 VWAP — gold | 6.0/10, 143.6d | **6.0/10, 143.6d, every check passes** |
| H-016 ribbon — gold | 5.0/10, 175.9d | **4.7/10, 260.1d, every check passes** |
| provenance | a hand-typed `SUPERSEDED` note | fingerprinted; the board flags itself |
| tests | none on either kernel | **77, no skips, plus CI** |
| second engine | vwap only, run by hand twice | **both, automatic** |

**Eight bugs were found by building this**, six of them by the tests rather than
by reading code. The one that mattered: **the 2026-09-07 dead-bar fix guarded the
decision bar and the fill bar and never guarded the EXIT.** 1,079 of H-002's
17,432 exits and 1,532 of H-016's 8,610 landed on a bar where nothing traded.
See `RESEARCH_LOG.md` 2026-09-08.

**The standing freeze on new hypotheses is satisfied.** Items 1 and 2 are in.

**Nothing above made a strategy faster, and that is now the only open problem.**

---

## Where the project stands in five lines

* **One market is left: gold.** All crypto price hypotheses are dead.
* **Two survivors, and BOTH are flagged TOO SLOW.** H-002 (VWAP, 4.41 trades/day,
  **143.6** expected days) and H-016 (ribbon, 0.53 trades/day, **260.1** days —
  it went 175.9 → 127.6 on the exit-path fix and then to 260.1 once the
  gap-through fill was priced). Both beat their nulls, both are now
  second-engine checked; neither is close to the pace target, and H-016 is
  now further away than it looked this morning.
* **The pace target is 5-14 days** (Kris, 2026-09-07, across several firms).
  Past 50 expected days the board flags `TOO SLOW` and the flag overrides the
  score. **Nothing here has ever been within reach of 5-14 days on honest
  numbers.**
* **The problem is speed, not edge.** Both survivors are ~10x the target.
* **H-009 and H-017 were deleted from the board** — both scored on the broken
  kernel. Their log rows stay; the failures are the denominator.

---

## THE PLAN — items 1, 2, 3. Agreed with Kris 2026-09-07.

**UPDATE 2026-09-08: Kris picked items 1, 2 and 4.** The step-by-step build
order is in `STEPS_1_2_4.md`. Item 3 is not skipped — item 2 needs four of its
five tests anyway, so the pytest frame, the golden test and CI are folded into
item 2. Item 4 still starts last, because it moves code and the tests are what
prove the move changed nothing.

The root cause of every "it worked, then it was a bug" event is that **results
are published before they are verified.** The order is backwards:

```
now:      kernel -> sweep -> walk-forward -> BOARD -> (verify, ad hoc, later)
should:   kernel -> VERIFY -> sweep -> walk-forward -> BOARD
```

H-009 reached board score **8.9 without ever being checked by a second engine**,
and nothing in the system stopped it. These three items make that impossible.

---

### ITEM 1 — kernel fingerprint and automatic staleness *(highest value, do first)*

**The problem.** `SUPERSEDED 2026-09-07 — SCORED ON A BROKEN KERNEL` is a note a
human typed by hand, after noticing. If nobody notices, the board keeps
publishing numbers produced by code that no longer exists.

**The fix.** Every board record records what produced it:

* the **git SHA** of the repo at write time,
* a **content hash of every kernel file** the result depends on
  (`strategies/<x>/engine.py`, `sweep.py`),
* a **content hash of the input data files** and their date ranges,
* the cost assumption used.

Then a checker recomputes those hashes and **marks any record stale
automatically** when the kernel it was built on has changed. The board renders
the flag; nobody has to remember.

**Why this one first.** It is self-contained, it needs no new tests, and it is
the item that directly answers Kris's complaint. It converts "oops, that was a
bug" from a discovery into a notification.

**Where.** `core/board.py::write_board` writes the fingerprint;
`core/build_scoreboard.py` checks it and renders the flag; a small
`core/fingerprint.py` holds the hashing.

**Done when.** Touching `strategies/vwap/engine.py` and rebuilding the board
makes H-002 render as stale without any human editing a note.

---

### ITEM 2 — a verification gate in code

**The problem.** A hypothesis can reach the board having passed nothing. The
scorecard has an evidence weight, but it does not *gate*.

**The fix.** A hypothesis cannot receive a board score above a floor until it
passes, in code:

| check | what it catches | status today |
|---|---|---|
| **look-ahead truncation** — cut the last N bars, earlier output must not change | the bug that killed all of crypto | exists for ribbon indicators only |
| **paired null** — same search on phase-randomised data | search noise | done by hand per hypothesis |
| **second-engine match** — NautilusTrader, trade by trade | kernel flaws | done once, by hand, for gold |
| **degenerate inputs** — zero volume, flat bars, zero sigma, single bar | this session's fix | none |
| **cost monotonicity** — PF must fall as cost rises | sign errors in cost | none |

**Where.** `core/verification.py` runs the checks and writes a
`verification.json` per hypothesis; `core/scorecard.py` reads it and caps the
score when a check has not passed.

**Note.** The individual checks have to exist before the gate can read them, so
item 3 partly feeds this. Build the checks as pytest tests, then have the gate
read their results.

---

### ITEM 3 — pytest, real tests, and CI

**The problem.** No test suite exists. Verified: `smoke_test.py` checks the
environment, `strategies/ribbon/test_parity.py` covers ribbon's indicators, and
that is all. **The VWAP kernel has zero tests.**

**Buy the frame, build the invariants.** No package on GitHub knows that a trade
must not use a bar that has not closed — that is a fact about our strategy.

```
pip install pytest hypothesis
```

`hypothesis` matters here: it **generates** adversarial inputs (zero volume, flat
bars, one bar, all-equal prices) instead of us guessing which ones to write.
Every bug this project has found was a degenerate input nobody thought of.

**The tests to write, in order of value:**

1. **`test_no_lookahead.py`** — for **every** kernel. Truncate the series, rerun,
   assert earlier bars and earlier trades are byte-identical. *This single test
   would have caught the 2026-09-05 look-aheads instantly.*
2. **`test_degenerate.py`** — zero-volume bars, flat OHLC, zero sigma, empty
   series, one bar, constant price. Property-based via `hypothesis`.
3. **`test_costs.py`** — profit factor must be monotone decreasing in cost;
   R at 0x/1x/2x must satisfy the linear identity `reprice` relies on.
4. **`test_golden.py`** — pin a known config's trade list. Any kernel edit that
   moves it must be explained in the commit, not discovered in three weeks.
5. **Make the Nautilus cross-check a test**, not a session job. It is the thing
   that has actually found bugs; running it once by hand is the gap.

**CI.** GitHub Actions on push. There is no CI today.

---

### After 1–3, not before: ITEM 4 — one `Strategy` interface

Kernels become a tested library with a shared interface instead of each
hypothesis reinventing the engine. **This is a refactor, not a fix** — it makes
future work cheaper, it does not stop the bleeding. Roughly a week. Do not start
it until 1–3 are in.

---

## OPEN — the two vwap cross-check disagreements

Precisely localised in `CLAUDE.md`. 4 trades of 330 on a 30m config at the weekly
reopen (cannot reach the board — wrong quarter), and 1 trade of 416 on a 15m
config 7 bars from the end of the series. Exit bars and R agree everywhere they
share a trade, so neither reads as a look-ahead. Both are boundary cases: one at
a session edge spanning padded weekend bars, one at the end of the dataset.

**Next step:** instrument the kernel and the port on those exact bars and print
the state each is carrying — `sess_start`, `blocked_until`, `prev` close and
VWAP, `stretched_*`. Do not weaken `tests/test_second_engine.py` to make it
green; the failure is the finding.

---

## Blocked on Kris

| # | question | blocks |
|---|---|---|
| B1 | **Which prop firms?** Kris will use several. Still need at least one real spec: static vs trailing max loss, min trading days, consistency rule, EAs allowed. | worth 17pp of pass rate |
| B2 | **Power of Three — your exact entry, stop and target rules.** The tested version had a session-close hold, no stop, no target. Only that formalisation is dead. | rerun of H-026 |

**ANSWERED 2026-09-07:** pace target is **5-14 days** across several firms;
anything past **50 days** is flagged `TOO SLOW`. The two dead board records were
**deleted**. Both surviving hypotheses were **kept and flagged** rather than
deleted, so they remain worked examples and test targets for items 1-3.

**Four project-level levers are written up in `IDEAS.md`** — measuring the six
unmeasured FX spreads, splitting evaluation risk from funded risk, screening on
speed instead of profit factor, and modelling parallel accounts. **None is agreed
work yet.** Two of them are cheap and look large: re-pricing EURUSD at its
measured cost took it from 3 of 20 cells clearing the gate to **10 of 20**, and
the risk ladder shows 3% risk funding an account **2.5x faster** than the 1% the
board picks, after paying for every blown account.

### The hard fact this creates

The pace target is now **~10x away**, not 3x. Every lever already measured has
been tried on H-002: combining cells (worked, 193 → 100 days pre-fix), re-pricing
at measured cost (worth 0.33 PF), and raising risk (**no headroom — the max-loss
cap binds first**). **Speed is not going to come from tuning these two books.**
It has to come from a genuinely faster mechanism, and per the standing pattern in
`CLAUDE.md` that means a **data feed**, not another price geometry. That is a
hypothesis question for after items 1-3, not before.

---

## Do NOT do

Carried forward and still true. Full reasoning in `CLAUDE.md`.

* **New hypotheses of any kind** until items 1–3 are in. Kris's call, 2026-09-07.
* **More single-feed crypto hypotheses.** Six measured, all in the 1–9bps band
  against a spec needing 8–20bps net. The band looks structural.
* **Signal stacking.** Combining nearly-independent feeds scored 3.1bps *worse*
  than the best single ingredient.
* **Moving down the cap curve.** 0 of 935 depth cells clear 14bps across 11
  coins; the small-cap effect is a 3-second one.
* **Three copies of one strategy on three accounts.** Perfectly correlated.
* **Silver.** Loses to its own null and was costed at half its measured spread.
* **A wider universe as a drawdown cure** without solving weighting first (H-012).
* **A database or a VM to fix correctness.** It would not have caught one of
  these bugs. A VM *is* justified for the **feed collector** — it runs on Kris's
  laptop via cron and gaps over ~41h are unrecoverable forever.
