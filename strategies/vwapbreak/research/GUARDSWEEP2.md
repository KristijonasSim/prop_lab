# H-043 — the −0.50% guard: a curve, or one lucky cell?

**Pre-registered 2026-09-14, before any number. Written after H-042's result and
before `guardsweep2.py` was run.**

Run: `.venv/bin/python strategies/vwapbreak/research/guardsweep2.py`

---

## Why this exists, and why it is the LAST one

H-042 closed the account-overlay axis and left exactly one loose end. Sixteen
cells were measured and **one** beat its own matched-drop null on both
timeframes — the **−0.50%** guard, which is *not* the arm H-041 nominated:

| fixed 3% rung | 1h blown% | its null p10 | 4h blown% | its null p10 |
|---|---|---|---|---|
| none | 49.3 | — | 70.5 | — |
| **−0.50%** | **42.3** | 45.6 | **50.6** | 60.3 |
| −0.75% | 40.8 | 43.9 | **70.8** | 66.7 |

The −0.75% neighbour shows **no improvement at all on 4h**, so −0.50% is an
isolated cliff with a flat neighbour. H-042 called that the H-038 signature and
did not claim it. But it was also the boundary of the swept range: **nothing
tighter than −0.50% has ever been run**, so the cliff has only ever been seen
from one side.

**This study looks at it from the other side.** If tightening past −0.50%
continues to help, it is a curve and the axis reopens. If −0.50% stands alone
between −0.35% and −0.75%, it is one cell out of sixteen and the axis is closed
permanently.

**The prior is that it is noise.** H-041's winner was −1.0%; H-042 fixed the
rung and the winner moved to −0.50%. A quantity whose optimum relocates when the
confound is removed is behaving like a draw, and two relocations would settle it.

## The arms — fixed now

**none, −0.15%, −0.25%, −0.35%, −0.50%, −0.65%, −0.75%.**

−0.15% and −0.25% are tighter than anything ever swept. At 3% risk a −0.15%
guard stops the day after roughly a twentieth of a stop-out, so it is close to
"one loser and the day is over" — deliberately past the point where a mechanism
is plausible, because **a monotone curve that keeps improving into the absurd is
itself evidence of an artifact** (it means size, not timing, is doing the work).

Cells, rung, costs and window are identical to H-042: XAUUSD 1h and 4h, blind
walk-forward, floors 30 / top 5, **every arm at 3.00% risk**, Thunderbolt
one-step. The matched-drop null is the same object, 40 permutations per arm.

## What counts as a win — all four, fixed now

1. **A CURVE, NOT A CLIFF.** At least **two** arms besides −0.50% sit ≥5pp below
   the baseline's blow-up rate on **both** timeframes, and the sequence
   −0.75 → −0.15 is weakly monotone in blow-up rate on both.
2. **THOSE ARMS BEAT THEIR OWN NULLS**, below the 10th percentile, both
   timeframes. Matched-drop, so "it trades less" is not an explanation.
3. **THE SUBSTITUTION BREAKS.** H-042's mechanism was that the guard converts
   daily-cap deaths into max-cap deaths roughly 1:1 and saves nobody. A real
   effect must cut the **total** by ≥5pp on both timeframes with `still_open`
   under 5%, not merely move the failure column.
4. **IT HOLDS IN BOTH HALVES OF THE SAMPLE.** The advantage is measured
   separately on the first and second half of the calendar. **A sign flip
   across halves is read as noise** — the same rule that killed BTC 30m, which
   cleared thirty quarters and then lost money from 2024.

## The price is reported whatever happens

Expected days for every arm. −0.50% already costs 17.8 → 20.8 days on 1h and
34.4 → **63.3** on 4h against a **5–14 day pace target**. An arm that survives
every condition above and still needs 60 days is **not usable** and will be
reported as such — survival that cannot fund an account on the business's
timescale is not an improvement to H-027, it is a different strategy.

## Kill criterion

> If condition 1 fails — if −0.50% still stands between flat neighbours on both
> sides — **the account-overlay axis is closed permanently and the −0.50% cell
> is recorded as one cell in sixteen that beat a null, which is what sixteen
> cells at a 10% threshold produce by construction (1.6 expected).** No further
> guard study is warranted without new evidence from outside this data.

## What would make a pass a false one

* **This is a search on a search.** H-042 swept 16 cells; this adds 12 more. The
  correction is in the kill criterion above: at a 10th-percentile null threshold,
  28 cells expect **2.8** false passes, and one cell clearing a null is therefore
  expected rather than surprising. **Only a monotone family of arms means
  anything here.** That is why condition 1 is the kill criterion and conditions
  2–4 are not.
* **Trade count collapses at these thresholds.** −0.50% already halves it
  (957 → 469). Tighter arms will trade less again, and a strategy that takes
  0.3 trades a day cannot resolve an evaluation whatever its blow-up rate. Trade
  count is in the table for every arm.

---

# RESULT — 2026-09-14. Not a curve and not a cliff: one rule, four names.

`backtests/vwapbreak/guardsweep2.json`, log `guardsweep2.log`. Same cells, same
window, same blind walk-forward, **every arm at 3.00% risk**.

| 1h | trades | tpd | days | pass% | blown% | band | its null | 1st half | 2nd half | failMax% | failDay% |
|---|---|---|---|---|---|---|---|---|---|---|---|
| **none** | 957 | 1.32 | **17.8** | 50.7 | **49.3** | 42.7–64.1 | — | 44.6 | 54.0 | 26.0 | 23.3 |
| −0.15% | 467 | 0.64 | 20.8 | 57.7 | **42.3** | 27.7–54.6 | 53.7 [45.6–61.1] | 36.1 | 48.5 | 42.3 | 0.0 |
| −0.25% | 468 | 0.64 | 20.8 | 57.7 | **42.3** | 27.7–54.6 | 53.7 [45.6–61.1] | 36.1 | 48.5 | 42.3 | 0.0 |
| −0.35% | 469 | 0.65 | 20.8 | 57.7 | **42.3** | 27.8–54.6 | 53.7 [45.6–62.7] | 36.1 | 48.5 | 42.3 | 0.0 |
| −0.50% | 469 | 0.65 | 20.8 | 57.7 | **42.3** | 27.8–54.6 | 53.7 [45.6–62.7] | 36.1 | 48.5 | 42.3 | 0.0 |
| −0.65% | 581 | 0.80 | 20.2 | 59.5 | **40.5** | 33.9–55.7 | 51.7 [43.8–60.5] | 34.4 | 46.6 | 37.3 | 3.2 |
| −0.75% | 596 | 0.82 | 20.3 | 59.2 | **40.8** | 34.8–55.8 | 52.3 [43.9–58.6] | 35.0 | 46.6 | 37.6 | 3.2 |

| 4h | trades | tpd | days | pass% | blown% | band | its null | 1st half | 2nd half | failMax% | failDay% |
|---|---|---|---|---|---|---|---|---|---|---|---|
| **none** | 599 | 0.82 | **34.4** | 29.1 | **70.5** | 57.9–80.8 | — | 69.0 | 68.0 | 18.0 | 52.5 |
| −0.15% | 322 | 0.44 | 63.3 | 49.0 | **50.6** | 45.5–75.5 | 69.0 [59.7–78.3] | 51.1 | 50.1 | 22.8 | 27.9 |
| −0.25% | 325 | 0.45 | 63.3 | 49.0 | **50.6** | 45.5–75.3 | 69.1 [60.1–78.3] | 51.1 | 50.1 | 22.8 | 27.9 |
| −0.35% | 327 | 0.45 | 63.3 | 49.0 | **50.6** | 45.5–75.3 | 69.3 [60.3–78.3] | 51.1 | 50.1 | 22.8 | 27.9 |
| −0.50% | 327 | 0.45 | 63.3 | 49.0 | **50.6** | 45.5–75.3 | 69.3 [60.3–78.3] | 51.1 | 50.1 | 22.8 | 27.9 |
| −0.65% | 400 | 0.55 | 60.2 | 29.9 | 69.7 | 55.5–80.2 | 70.6 [60.9–78.5] | 68.1 | 69.9 | 39.8 | 29.9 |
| −0.75% | 423 | 0.58 | 59.0 | 28.8 | 70.8 | 56.9–81.7 | 71.3 [66.7–78.7] | 70.1 | 69.9 | 41.6 | 29.2 |

## The finding, and it is not the one the study was designed to find

**−0.15%, −0.25%, −0.35% and −0.50% are the same rule.** Identical blow-up
rates, identical pass rates, identical days, trade counts within two of each
other on both timeframes. They are four names for *stop for the day once the day
has booked any real loss at all*.

**The arithmetic.** At 3% risk one stop-out is 1R = 3% of the account, so a
threshold of 0.15%, 0.25%, 0.35% or 0.50% is **0.05R to 0.17R** — every one of
them is tripped by the same loser. The thresholds only separate where they cross
the size of an actual loss: at −0.65% (0.22R) 112 trades on 1h come back, and at
−0.75% (0.25R) another 15. **Losses on this rule cluster at the stop and are
rare in between, so the guard is a step function and the "cliff" H-042 saw at
−0.50% is where the threshold fell below one loser.**

## Against the four conditions

| | condition | verdict |
|---|---|---|
| 1 | a curve, not a cliff | **the kill criterion is NOT triggered** — −0.50% does not stand between flat neighbours: on 4h three tighter arms match it at 50.6, and on 1h −0.65% is better still at 40.5. The monotonicity sub-clause **fails on 1h by 1.8pp** (40.5 at −0.65% against 42.3 tighter), which the plateau above explains. |
| 2 | below its null's 10th percentile, both timeframes | **MET** by the whole plateau — 1h 42.3 < 45.6, 4h 50.6 < 60.3. And on 4h only the plateau clears it: −0.65% and −0.75% do not. |
| 3 | total cut ≥5pp, `still_open` <5% | **MET** — 1h 49.3 → 42.3 (−7.0pp), 4h 70.5 → 50.6 (−19.9pp), `still_open` 0.0% and 0.4%. |
| 4 | holds in both halves of the sample | **MET** — 1h 44.6→36.1 and 54.0→48.5; 4h 69.0→51.1 and 68.0→50.1. Same sign, same rough size, both halves, both timeframes. |

**This is the first thing on H-027 that has survived a pre-registered
confirmation.** It beat a matched-drop null on both timeframes, held in both
halves of the sample, and its mechanism is legible.

## And it is still not a win, because it fails on the one thing that decides

| | baseline | the guard | pace target |
|---|---|---|---|
| 1h expected days | **17.8** [13.9–23.3] | 20.8 [16.5–26.4] | 5–14 |
| 4h expected days | **34.4** [27.5–54.5] | 63.3 [36.7–85.6] | 5–14 |
| 1h trades/day | 1.32 | **0.65** | — |
| 4h trades/day | 0.82 | **0.45** | — |

**It halves the trade count, so it is slower — on 4h nearly twice as slow.** A
guard that survives everything and takes 63 days cannot fund an account on this
business's timescale. Measured at a fixed 3% rung, **survival has been bought
with speed**, and speed is the binding constraint.

## The bands still overlap and the search is still priced

* Blow-up bands overlap the baseline's everywhere (1h 42.7–64.1 against
  27.7–54.6). The direction is consistent across four independent checks; **the
  size is not resolvable on two years of gold.**
* `core.search_cost.verdict(28, 90.0, 200)`: *28 tests at the 90th percentile
  expect 2.8 false passes; holding the family at 0.05 needs the 99.82nd, which
  200 resamples cannot resolve.* One cell clearing a null would be expected. **A
  four-arm plateau clearing it in both halves of both timeframes is not**, and
  that distinction is the only reason this result is written down at all.

## Verdict and the one question left

**The account-overlay axis is NOT closed. It is redirected.** The guard is real
and it is a survival tool that costs speed. H-042's closure stands for the
*thresholds it tested*; this plateau is a different object and it survived.

**The open question is whether survival converts into speed on the risk ladder,
and it has never been asked.** H-041, H-042 and H-043 all capped the ladder at
**3%** — inherited from H-041 and never questioned — while `core/riskladder.
RISK_LADDER` runs to **5%**. The guard's whole product is drawdown headroom, and
headroom is what buys a bigger position. Until both arms are run over the full
ladder, "the guard is slower" is a statement about 3% risk and nothing else.

`LADDER.md` is that study, pre-registered, and it is the last one.
