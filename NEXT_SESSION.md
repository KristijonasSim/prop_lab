# Next session — start here

Written 2026-09-08 at session close. Read `ENGINES.md` for the machine,
`CLAUDE.md` for the rules. This file is only what to do next.

---

## The state in five lines

* **Engines 2 and 3 are built and green.** 130 tests, CI on every push, blind
  walk-forward pipeline, fingerprinting, verification gate. Engine 1 (hypothesis
  generator) is not started.
* **The firm is real:** Thunderbolt, 1 step, **6% target, 3% daily drawdown, 6%
  max drawdown**, unlimited time, €21.89 an account.
* **Kris's goal: ≥60% pass rate within 14 days.** NOT MET, and further away
  than it looked on 2026-09-08 — see TASK 1 below.
* **Best blind result reaching 60%: ETHUSDT 1h, 62.1% pass in 27.4 days**
  (floor 100, topn 5, 0.75% risk). **Gold no longer reaches 60% at all.**
* The board is `backtests/board.html`. It no longer auto-refreshes (removed on
  Kris's instruction 2026-09-08) — reload it by hand and check the build time.

---

## TASK 1 — DONE 2026-09-08 evening. IT FAILED ITS OWN HYPOTHESIS.

Both levers were run (`strategies/vwapbreak/hypothesis.py`, 37 min, then
`core/build_board.py`). The prediction was that `topn` 3 or 5 would cut the
blown rate and carry gold over 60% inside 14 days. **It did the opposite.**

### Gold 1h, promoted rule, before and after the wider grid

| risk | pass% before | pass% after | blown% before | blown% after | days before | days after |
|---|---|---|---|---|---|---|
| 0.25% | 70.5 | **47.4** | 24.0 | **45.5** | 32.6 | 38.0 |
| 0.50% | **62.6** | **54.8** | 35.3 | 45.2 | 19.2 | 25.6 |
| 0.75% | 55.1 | 51.8 | 43.5 | 48.2 | 14.5 | 19.3 |
| 1.00% | 53.7 | 49.6 | 48.8 | 50.4 | 13.0 | 18.1 |

**Gold 1h's peak pass rate went 70.5% → 54.8%. It no longer touches 60% at any
risk level on the ladder.** PF@2x also fell, 1.903 → 1.679.

### The middle of TOPN was tested and it does not help

All eight selection rules on gold 1h, blind:

| floor | topn | trades/day | PF | days to pass | pass% |
|---|---|---|---|---|---|
| 30 | 1 | 0.46 | 1.054 | 54.3 | 35.0 |
| 30 | 3 | 1.53 | 1.210 | 60.2 | 39.1 |
| 30 | 5 | 2.37 | 1.383 | 53.3 | 45.0 |
| 30 | 10 | 4.86 | 1.683 | 55.0 | 40.0 |
| 100 | 1 | 0.57 | 1.210 | 47.4 | 43.2 |
| 100 | 3 | 1.64 | 1.356 | 42.0 | 45.3 |
| 100 | 5 | 2.75 | 1.502 | 44.0 | 47.7 |
| **100** | **10** | **5.42** | **1.772** | **38.0** | 47.4 |

`topn=10` still wins. 3 and 5 sit between, exactly as expected on PF and
trades/day, and **neither converts that into a lower blown rate or a higher pass
rate.** The "ten correlated positions against a 3% daily cap" story predicted
they would. They did not, so that story is wrong or incomplete.

### What this actually means — read this before running anything else

**The 62.6% / 19.2-day headline did not survive widening the grid.** Nothing
about the market changed; only the number of configurations the blind selector
could choose from. That is the signature of a number that was partly a lucky
draw from a narrow grid, and it is the same failure mode this repo has retracted
results for before.

Corollary about the old `HOLD_HOURS` note: 192 being chosen in **all seven
folds** was read as a binding grid edge worth relieving. Relieving it made the
out-of-sample result worse, so 192 was a lucky pick, not a constrained one.
**A binding grid edge is not by itself evidence that the edge continues.**

### Where the 60% goal now stands

Only three markets reach 60% pass on any selection rule at any risk, and **none
inside 14 days**:

| market | floor | topn | risk | pass% | days |
|---|---|---|---|---|---|
| **ETHUSDT 1h** | 100 | 5 | 0.75% | **62.1** | **27.4** |
| ETHUSDT 1h | 100 | 1 | 0.50% | 61.0 | 34.4 |
| ETHUSDT 4h | 100 | 5 | 0.25% | 67.1 | 83.5 |
| SOLUSDT 4h | 100 | 1 | 0.25% | 65.6 | 83.0 |
| BTCUSDT 1h | 30 | 5 | 0.25% | 75.6 | 175.2 |

**The fastest route to 60% is now ETH 1h at 27.4 days, not gold.** Note this is
crypto, on a hypothesis whose crypto ancestor (H-002) died to a look-ahead fix —
H-027 is a different formalisation (follow, no target, long hold) so it is not
automatically covered by that verdict, but it deserves the same suspicion.

### Silver woke up

XAGUSD went from losing to clearing the gate on the wider grid: 1h PF@2x
**0.831 → 1.371** (78.5 days), 4h **0.802 → 1.240**. It is charged its full
**measured** 9.108bps spread, so the old "costed at half its spread" objection in
`TASKS.md` no longer applies. **But it moved for the same reason gold moved, in
the other direction** — treat it as grid noise until something separates the two.

### What to do next, in order

1. **Do not chase the topn/hold axis further.** It has been tested end to end.
2. **Quantify the selection noise before believing any of these cells.** Re-run
   the identical pipeline with a different null seed and with the grid split in
   half; if gold and silver swap places again, the per-cell numbers are draws
   from a distribution and only the distribution should be quoted. This is the
   single highest-value thing left and nothing else is safe until it is done.
3. **Persist the per-fold chosen configuration.** `cells[].rules` records the
   outcome of each selection rule but not *what* it chose, so "which hold did it
   pick" cannot be answered from the record — it had to be inferred. Add it.
4. Only then: the two-leg XAUUSD 1h + 4h book, anchor variations, trailing stop.

---

## What H-027 is, and why it is not H-002 retuned

Three findings from the deep dive, each measured rather than assumed:

* **The direction is FOLLOW, not fade.** On identical bars, thresholds and
  holds, follow beat fade in **79 of 100 paired cells** (25 of 25 on ETH 4h and
  XAUUSD 1h). H-002's own walk-forward already agreed — it picks `MODE_BREAK` in
  100 of 140 folds. **H-002 is named after a trade it does not make.**
* **A fixed target was destroying the payoff.** Average R rose monotonically with
  reward:risk to the edge of every grid. Removing the target moved XAUUSD 1h from
  **+0.155R to +0.684R**. The shape is one winner in nine carried a long way.
* **It survives its null.** The identical 375-cell search on phase-randomised
  markets found **0 hits in 1,125 cells** across three seeds; its fastest route
  to 60% pass was 30.8 days against the real 12.9.

**And one that contradicts the repo's own prior:** the blind selector picked the
**Asia session (00–07 UTC) in all seven folds** on gold 1h. Asia was put in the
grid *because* H-001 found it the worst session for ORB. Seven independent folds
choosing it is a regime, not a fit. Worth understanding — nobody has explained it.

---

## Do NOT redo these

* **Class-wide baskets.** Failed twice, same mechanism both times. Equal
  weighting divides the book's R/day by the leg count while drawdown falls by far
  less, and the classes contain markets that lose alone. H-027's baskets never
  resolve an account at all. A *two-leg book of two strong legs* is a different
  proposition and is untested.
* **Execution cost as a route to pace.** Measured and closed: 14bps → **0bps**
  moves a book only 57 → 32 days. Free execution buys 33–44% of the days; the
  target needs ~85%. Take the maker fill because it is free and measured safe —
  do not expect it to fix pace.
* **Fading a VWAP extreme.** 0 of 100 cells cleared PF 1.20 and beat their null;
  gold is negative at every threshold and hold.

---

## Open bugs and gaps

| | |
|---|---|
| 2 second-engine disagreements | vwap 30m (4 trades of 330) and 15m (1 of 416). Both at boundaries, neither reaches the board. Fail in `pytest -m slow` on purpose. |
| Nightly slow suite | has never completed clean end to end |
| `core/verify_board.py` | still hardcodes the old 8%/4%/8% firm spec — will disagree with the board for the wrong reason |
| Engine 1 | not started; `core/target_profile.py` and `CANDIDATES.md` exist, no gate |
| The ~90 old stage scripts | still on disk, superseded by `core/pipeline.py` |

---

## House rules that are easy to break

* **Always rebuild and open the UI before reporting.** Kris reads the board, not
  the chat. `.venv/bin/python core/build_board.py`.
* **Always push to `main`.** Every change, straight away.
* **Answer in short key points.** See `HOW_TO_ANSWER.md`. A long reply is a bug.
* **Three years of data, one common window**, snapped to a month start so adding
  a market never moves another market's numbers.
* **Never quote a number that has not beaten its own paired null**, and never one
  chosen on the window it was scored on.
