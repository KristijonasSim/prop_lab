# H-046 — the 16:00 London fix. DEAD at gate 1, and it takes the clock with it.

Pre-registered in `PREREG.md` before any number; the criteria below are the ones
written there, unedited. Run: `stage1_response.py`, `stage2_clock.py`.
Records: `backtests/fixflow/stage1.json`, `stage2.json`.

**Window** 2023-09 → 2026-07, three years, common end, `core.run_hypothesis.window`.
**Bars** 5m for FX and metals, 15m for BTCUSDT (no finer crypto cache exists).
**Universe** all six of `core/universe.STANDARD` — nothing skipped.

---

## The claim that was tested

Dealers who accept benchmark orders hedge before the 16:00 London window, which
pushes price into the fix; once the window closes the inventory pressure stops
and the move should partly come back. Fade the drift into the fix, hold an hour.

## The answer, at the anchor, h = 60 minutes

Per-trade edge is **half** the quintile spread, because a book trading the top
and bottom quintile takes one position per event. The bar is the round trip at
**2x cost**.

| market | events | spread (bps) | edge | 2x round trip | edge / bar | p vs hour-matched null |
|---|---|---|---|---|---|---|
| **XAUUSD** | 748 | +4.58 | 2.29 | 2.13 | **1.08** | 0.062 |
| XAGUSD | 692 | +9.56 | 4.78 | 9.40 | 0.51 | 0.108 |
| EURUSD | 755 | −0.44 | −0.22 | 0.37 | −0.59 | 0.676 |
| GBPUSD | 725 | −1.50 | −0.75 | 0.82 | −0.92 | 0.844 |
| USDJPY | 754 | +0.99 | +0.50 | 1.10 | 0.45 | 0.246 |
| *BTCUSDT (control)* | 1,096 | −10.27 | −5.14 | 18.00 | −0.29 | 0.962 |

**One market of five clears the cost bar, and it clears it by 8%.** Two of the
five have the wrong sign. Nothing reaches p < 0.05 against its own hour-matched
null.

### The four kill criteria, as written

| | criterion | result | |
|---|---|---|---|
| 1 | edge > 2x round trip on ≥ 3 of 5 fix markets | 1 of 5 | **FAIL** |
| 2 | pooled fix-market spread beats its null at p < 0.05 | p = 0.418 | **FAIL** |
| 3 | the fix ranks in the top 3 of the 24 placebo clocks | **11th of 24** | **FAIL** |
| 4 | BTCUSDT, which has no fix, stays silent | −0.29 of the bar | PASS |

Criterion 3 is the one that settles it. If the fix were doing anything, its own
hour would not sit in the middle of the twenty-three hours that have no fix in
them.

**This is what the prior said would happen.** The five-minute window replaced the
one-minute window in February 2015 and was designed to make exactly this trade
unprofitable. Every published measurement of the effect predates it. The finding
here is that the reform worked, measured on data eight years after it.

---

## Stage 2 — then is any hour tradeable? No, and this is the useful half

Killing one anchor leaves the obvious follow-up: something else on the clock. So
the identical test ran on **every** usable London hour, both signs, five markets
— **200 cells** — and the search was priced the way H-038's LESSON 1 says to
price it, against the **maximum over cells** of a null draw rather than each
cell's own p-value.

Four anchors (20:00–23:00 London) are dropped: the exit bar falls past the FX
weekly close too often to leave 200 clean days. The search is over 20 anchors.

| | |
|---|---|
| cells searched | 200 |
| false passes expected at p < 0.05 | 10.0 |
| **observed at p < 0.05** | **16** |
| best cell | XAGUSD 17:00 London, follow, t = 0.350, **cell p = 0.001** |
| **best cell vs the best-of-200 null** | **p = 0.130** |
| that anchor's sign across the five markets | 3 of 5 positive |

**A cell at p = 0.001 that is p = 0.130 once the search is priced.** That is the
whole lesson of this study in one line, and it is the same arithmetic as H-028's
p = 0.0000 in one slot against p = 0.187 best-of-48. Sixteen observed passes
against ten expected is not nothing, but it is one extra pass per thirty-three
tests, and the best of them cannot be told from the best of two hundred coin
flips.

And its own anchor contradicts it: at 17:00 London the same rule is +18.9bps on
silver, +1.2 on gold, +0.1 on cable and **negative** on EURUSD and USDJPY. A
quantity that flips sign across markets is this repo's signature for no effect —
the same shape as H-026's fibonacci and H-041's guard.

### The one thing worth carrying forward

**Stage 1's pooled statistic was built wrong and stage 2 had to replace it.**
Pooling `edge / cost` across markets hands the cheapest market the largest
weight: EURUSD's round trip is 0.19bps against gold's 1.06, so a 4.7bps EURUSD
spread scored **6.35** and dragged a pooled number that no other market
supported. Stage 2 standardises every cell by its own forward-return dispersion
and applies the cost bar separately, afterwards. **Never pool a ratio whose
denominator varies by 50x across the things being pooled.**

## What is now closed

**The clock, as an axis, on FX and metals.** Not "the fix is dead" — 20 anchors ×
5 markets × 2 signs at a one-hour horizon, all measured identically, best
survives nothing. Combined with the 25-filter screen's finding that every session
window makes H-027 slower, and H-021's quarter-hour result on crypto, the hour of
the day has now been tested as a filter, as a crypto microstructure effect, and
as a standalone rule.

**What would reopen it:** an event list, not a clock. The fix is a time; a
central-bank decision, a CPI print and an LBMA auction are times *with a known
flow attached*, and this study cannot tell them apart from the 250 ordinary days
that share their slot. That needs a calendar the repo does not have.
