# Step 5 — the luck check. Design, 2026-09-23

Kris: *"should we keep step 5? what he does? does it worth it?... it seems like
similar things are done in step 3."*

He is right that they overlap. He is wrong that they are the same, and the gap
between them is the single most expensive blind spot this repo has had.

`factory/null.py`, `tests/test_factory_steps567.py`.

---

## 1. What step 3 already does, and what it cannot reach

**Step 3 gate 4** takes the rule, keeps its side, its stop, its target, its hold
and its trade COUNT, and moves only the entry bars to random positions. Twenty
seeds, and the rule must beat the 90th percentile. On 45 generated ideas it
removed fourteen of the nineteen that made money — gold rose 123% in the window
and fourteen "winners" were worse than entering at random.

That gate is doing real work and nothing here replaces it.

**What it cannot see is the SEARCH.** It is applied to one cell at a time. The
factory tests 24 cells and keeps an idea if **any** of them passes, then hands
the best near-miss up to twelve more repairs. A survivor is the best of roughly
thirty draws, and no gate anywhere prices that.

| | step 3 gate 4 | step 5 |
|---|---|---|
| unit | one cell | the whole pipeline |
| what is scrambled | the entry bars | the market |
| question | did the rule pick better bars than random? | how many survivors does best-of-30 give when there is nothing to find? |
| run | per idea, always | per batch |

**Why the distinction is not academic here.** On 2026-09-08 six gates carrying
no information by construction were walked forward on gold, and *the
best-scoring arm of the entire day's work was one of them* — 60% pass in 14.5
days, the exact target, from noise. On 2026-09-17 the fastest number this
project had ever produced (8.9 expected days) was withdrawn because the paired
null sped up **more** than the real data did, on six markets out of six. Both
times the missing number was the same one: what does this procedure produce on
data with no edge?

---

## 2. The scramble, and every choice in it

Bars are resampled in blocks and re-chained. Each live bar contributes its
`(open, high, low, close) / previous live close`; blocks of those factors are
drawn with replacement and multiplied back out into a new price path.

**What survives, and why each one has to.**

* **The drift.** Gold rose 123% over the window. A null that flattened it would
  be one that every long rule beats for a reason that has nothing to do with
  edge. Block-resampling factors preserves the drift in expectation — measured
  over twelve seeds on gold 1h: real total return 2.087, null mean **2.164**.
* **The volatility, and its clustering inside a block.** Measured: real
  bar-to-bar log-return sd 0.00260, null 0.00262.
* **The calendar.** Timestamps, the `hour` column and the `volume` column never
  move off their rows. So an hour-concentrated rule is compared against an
  hour-matched population. This is the defect `core/probe.py` was caught with on
  2026-09-13 — it shifted events to random positions, so a 00:00 UTC event was
  scored against a population drawn from every hour and gifted about 5 bps. This
  null scrambles by ROW, not by time, which closes that by construction.
* **The closed market.** 21.5% of the gold series is padded weekend at a frozen
  price. Those rows are frozen again after re-chaining, so the null trades the
  same market the real data does.
* **The bar shapes and the weekend gaps**, because the factors come from real
  bars and are chained off the previous **live** close.

**What is destroyed:** the alignment between a rule's signal and what follows
it. That is the only thing an edge can live in, and it is the only thing taken
away.

**Block length was tested, not assumed.** The obvious objection is that a
one-day block destroys structure at horizons longer than a day, most factory
ideas hold up to 48 bars, and real markets mean-revert at multi-day horizons -
removing that would flatter a breakout rule in the null. Measured on the first
run, four seeds each: 1 day **4.2**, 1 week **4.0**, 1 month **4.5** survivors,
against the real market's 2. Flat, so the null is not winning on block length.

**One block is one trading day** — 96 bars on 15m, 24 on 1h, 6 on 4h, 5 on 1d.
Fixed on 2026-09-23 before the first run. Shorter and the null keeps no intraday
structure; longer and it copies stretches of the real market back in.

---

## 3. What it reports

```
python -m factory.null -n 40 --seeds 10
```

The real pipeline over a fixed idea list, then the same ideas through the same
code on each scrambled market. Survivors are counted in two columns — passed
step 3, and repaired at step 4 — because step 4 only earns its place if repaired
ideas do not die at step 6 more often than first-try ones.

The p-value is `(seeds that matched or beat the real count + 1) / (seeds + 1)`.
**One-sided and deliberately crude:** with ten seeds the smallest number it can
report is 0.09, and quoting a smaller one than the seed count supports is how
this repo has been wrong before.

**If the scrambled markets produce as many survivors as the real one, the honest
statement is "nothing above what luck gives".** That sentence has never been
available here across 457 charged trials.

### First run, 2026-09-23 — and it failed

25 enumerated ideas, gold 1h and 4h, four scrambled markets:

| market | step 3 | repaired | survivors |
|---|---|---|---|
| **real** | 0 | 2 | **2** |
| scrambled #0 | 3 | 4 | 7 |
| scrambled #1 | 2 | 1 | 3 |
| scrambled #2 | 0 | 1 | 1 |
| scrambled #3 | 3 | 3 | 6 |

Real 2, scrambled mean **4.2**, p = 0.80. Three of four scrambled markets beat
the real one. Small run - 25 ideas, two cells, four seeds, and four seeds cannot
report a p below 0.20 - so it is a reason to run it at 40 x 24 x 10 overnight,
not a verdict. The full write-up is in `RESEARCH_LOG.md`.

**The likely mechanism is already known:** 87% of cell-tests die on trade count
(`docs/STEP4.md`). A rule firing a few times a year survives or dies mostly on a
coin flip, on real bars and scrambled ones alike. That points at the generator,
not at the gates.

---

## 4. Cost

Roughly 12 minutes per scrambled pass over 40 ideas on all 24 cells, so ten
seeds is an overnight job and no model tokens at all. It is the cheapest gate
in the pipeline relative to what it settles.

---

## 5. What it does not do

It does not license a survivor. A pass means the batch produced more survivors
than scrambled data does — a statement about the **pipeline**, not about any one
idea. The idea still has to clear step 6 on bars it has never seen.
