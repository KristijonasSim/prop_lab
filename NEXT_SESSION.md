# Next session — start here

Written 2026-09-09 at session close. `ENGINES.md` is the machine, `CLAUDE.md` the
rules, `SESSION_2026-09-09.md` the workings behind everything below. This file is
only what to do next.

---

## The state in six lines

* **Bands are on the board.** Every ranked number carries its own 10–90% band
  (`core/noiseband.py`) and rows that cannot be told apart share a tier.
  `core/scorecard.rank_tiers` refuses to order them.
* **Both second-engine disagreements are closed and neither was a look-ahead.**
  `pytest -m slow` is **7 passed** — clean end to end for the first time.
* **The board had been showing pre-fix numbers.** The fold-selector fix landed 16
  minutes after the last record was written and was never re-run. Both
  hypotheses have now been re-run on current code; every cell moved.
* **Kris's goal — ≥60% pass inside 14 days — is not met**, and the old
  "ETHUSDT 1h, 62.1% in 27.4 days" headline does not survive the re-run.
* Every hypothesis page now has a **Copy Pine indicator** button: a TradingView
  *indicator* (signals and the stop level, no orders, no equity curve), with its
  defaults taken from what the blind selector chose most often.
* The board is `backtests/board.html`; it does not auto-refresh, so check the
  build time in the header. Serve it with
  `python3 -m http.server 8899 --bind 127.0.0.1` from `backtests/`.

## The two numbers that matter

**H-027, promoted rows, at the 2% risk floor:**

| class | market | expected days | band | pass % | PF@2x | beats null |
|---|---|---|---|---|---|---|
| Metals | XAUUSD 1h | **14.1** | 11.6–20.2 | 42.5 | 1.715 | yes |
| Crypto | SOLUSDT 1h | 13.9 | 10.8–17.9 | 36.0 | 0.902 | yes |
| FX | AUDUSD 4h | 17.4 | 13.4–22.1 | 34.5 | 0.924 | yes |

**Every rung on either board that reaches 60% pass:** three, and the fastest is
**54.6 expected days** (H-027 XAUUSD 4h at 0.50% risk, 60.4% pass, band
39.4–92.3 days, pass band 29.0–65.6%). At 2% risk **nothing reaches 60%**.

---

## TASK 1 — the ranking metric is not doing its job. Decide what replaces it.

**Fourteen of H-027's twenty cells are one tier**: 13.9 to 23.8 expected days,
no pair distinguishable. That tier holds XAUUSD 1h at PF@2x **1.715** and GBPUSD
4h at **0.692** — one makes money at double cost, one loses at it, and the
board's own ranking metric cannot tell them apart.

The cause is in the definition: `expected_days = median_days / pass_rate`, and at
a 2% position a losing book funds the occasional account on variance before it
dies. Speed is blind to edge.

What is NOT blind: PF@2x and the paired null. But `RESEARCH_LOG.md` 2026-09-08
measured `correlation(PF@2x, expected days) = +0.231` — higher profit factor goes
with MORE days — so PF cannot simply replace speed either.

**This is a decision for Kris, not a search.** The options are on the table:
rank on expected days but only between tiers; rank on a joint criterion (edge
first, speed as the tie-break inside a tier); or accept that the board ranks
nothing and reports tiers plus evidence. Do not run another sweep before this is
settled — every sweep since 2026-09-08 has produced differences smaller than the
tier width.

## TASK 2 — nothing re-runs a stale record, and the board does not check

The record on disk is what the page renders. `core/build_board.py` never looks at
the fingerprint, so a hypothesis whose kernel changed keeps showing its old
numbers until somebody remembers. That is exactly how the board spent a day on a
replaced selector.

Two lines of work, in order:
1. `build_board` should mark a stale record on the page, using the fingerprint
   the record already carries (`core/fingerprint.py`, and `core/build_scoreboard`
   already does this for the other page).
2. A `make board` style entry point that re-runs any hypothesis whose
   fingerprint no longer matches, then rebuilds. Roughly 25 minutes per
   hypothesis on this box, and both can run in parallel.

## TASK 3 — the firm questions, still unanswered and still blocking

* Static or trailing max drawdown? Worth 17 points of pass rate.
* Minimum trading days? Modelled as none.
* A consistency rule?
* **Is XAUUSD tradeable on Thunderbolt at all?** Both boards' best rows are gold.

## Then, and only then

* The two-leg XAUUSD 1h + 4h book — with its band, not a point estimate.
* Engine 1 (hypothesis generator): still not started.
* The ~90 superseded stage scripts still on disk.

---

## Do NOT redo these

Unchanged from 2026-09-08, and the list has grown:

* **Entry filters on H-027 gold, as a family.** 25 screened, 24 of 25 raise PF by
  cutting R per day; the one survivor lost to a shuffled copy of itself.
* **Class-wide baskets.** Failed twice on the same mechanism.
* **Execution cost as a route to pace.** 14bps → 0bps moves a book 57 → 32 days;
  the target needs ~85% of the days, not 40%.
* **The topn / hold axis.** Widening the grid took the headline away rather than
  improving it, which is what a lucky draw from a narrow grid looks like.
* **Quoting a per-cell number without its band.** The board now refuses to.
