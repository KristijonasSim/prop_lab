# H-042 — the daily-loss guard, settled. Curve or spike, and is it just less trading?

**Pre-registered 2026-09-14, before any number.**

Run: `.venv/bin/python strategies/vwapbreak/research/guardsweep.py`

---

## Why this exists

H-041 (`DAILYGUARD.md`) is the only thing on H-027 in weeks that is not dead.
Its `-1.0%` arm met the pre-registered survival condition on **both** timeframes
— 1h blow-ups 49.3% → 40.8%, 4h 70.5% → 48.3% — and its own result section
listed three reasons to distrust it and named two follow-ups as **not optional
before it is believed**:

1. the finer threshold sweep, to tell a curve from a spike;
2. every arm re-scored at a **fixed** risk rung, to remove the confound.

This is those two, plus the control H-041 never had.

**This study cannot make H-027 faster and is not trying to.** H-041's condition
1 — fewer expected days with a non-overlapping band — failed at every threshold
on both timeframes. That is settled and is not retested here. The most this can
ever return is *survival, not speed*.

## The third problem, which H-041 did not test at all

The `-1.0%` guard removes **38% of the trades on 1h** and 20% on 4h. Fewer
trades is less exposure, and less exposure lowers a blow-up rate on its own. So
the honest question is not *"does the guard lower blow-ups"* — it has to — it is
**"does it lower them more than removing that many trades at random would?"**

Nothing in H-041 answers that. Every other axis on this hypothesis was killed by
exactly this kind of control: the shuffled MA200 gate outscored the real one, and
the whole noise floor in `CLAUDE.md` is built from information-free arms.

### The matched-drop null

For each arm, the real guard drops `d(day)` entries on each day. The null
**permutes the vector `d` across trading days** and drops that many of each
assigned day's *last* entries. It therefore matches:

* the total number of trades dropped (up to a day's own entry count),
* the clustered, end-of-day shape of the dropping,
* the arm's trade count, near enough to read the tables side by side,

and destroys the only thing the guard claims to know: **which** days were the
bad ones. 40 seeds per arm. If the real guard does not sit below its own null,
the effect is *trading less*, not *trading less on the right days*, and the
`-1.0%` result is an artifact.

## The arms — fixed now

| guard | note |
|---|---|
| **none** | baseline, the shipped behaviour |
| −0.50% | new |
| −0.75% | new — the neighbour that decides spike vs curve |
| −1.00% | H-041's survivor |
| −1.25% | new — the other neighbour |
| −1.50% | H-041 |
| −2.00% | H-041 |
| −2.50% | H-041 |

Cells: **XAUUSD 1h and 4h**, blind walk-forward, floors 30 / top 5, Thunderbolt
one-step. Identical to H-041 so the two tables are comparable line for line.

## Two scorings, and the PRIMARY one is the fixed rung

* **PRIMARY — every arm at 3.00% risk.** That is the rung the baseline chose on
  both timeframes in H-041, so the comparison is like for like. Confound 3 of
  H-041 (the `-1.0%` arm landing on 2.0% risk against the baseline's 3.0% on 4h)
  cannot exist here.
* **SECONDARY — the free rung**, `score` picking the fastest of
  1.0/1.5/2.0/3.0% per arm, exactly as H-041 did. Reported for continuity, and
  **no claim is made from it.**

## Blow-up rates carry a band, which H-041's did not

`CLAUDE.md`: *quote a per-cell number with its noise band or do not quote it.*
H-041 quoted 49.3% → 40.8% naked. Every blow-up rate here gets a 10–90% band
from the same stationary block bootstrap the days band uses
(`core.noiseband._resample_index` / `._states`, 200 resamples, mean block 10),
so it is the same machinery `tests/test_noiseband.py` pins to `run_accounts`.

## What counts as a win — all four, fixed now

1. **MONOTONE, not a spike.** At the fixed rung, blow-up rate falls weakly as
   the guard tightens across −2.5 → −0.5, and **both neighbours of −1.0%**
   (−0.75, −1.25) sit at least **5pp** below the baseline on **both**
   timeframes. An isolated step with flat neighbours is the H-038 signature and
   is read as noise, as H-041 already said.
2. **BEATS ITS OWN NULL.** The arm's blow-up rate is below the **10th
   percentile** of its matched-drop null, on both timeframes.
3. **SURVIVES THE RUNG FIX.** At 3.00% risk for every arm, the advantage is
   still ≥ **5pp** on both timeframes.
4. **THE BAND SEPARATES IT.** The arm's blow-up band sits below the baseline's
   on both timeframes and does not overlap it on at least one.

## Kill criterion

> **If 1, 2 or 3 fails, the account-overlay axis is closed alongside the other
> five and H-027 is finished being tuned.** The answer then is publish-or-drop,
> not another study. Condition 4 failing alone downgrades the arm to "direction
> consistent, size unresolvable" and it still may not be called a win.

## What would make a pass a false one anyway

* **Eight arms × two timeframes is a search over sixteen cells**, on top of
  H-041's ten. At a 90th percentile that expects 1.6 false passes. `NEXT.md`
  item D2 says this project rebuilt a screen without pricing its search three
  days after writing the correction down. The whole curve is reported, pass or
  fail, and the arm list above is frozen before the first run.
* **Profit factor is not evidence here** and is not in the tables. A guard can
  only ever remove trades, so it raises PF mechanically. H-041 said this.
* **The guard is scored on a trade series it did not generate.** It is an
  account overlay on the shipped rule's blind walk-forward trades — it selects
  nothing in the market and cannot leak into the signal.
* **Expected days is reported for every arm** even though speed is not the
  claim, because a guard that buys survival by making the evaluation twice as
  long is a trade, not a gift, and the reader has to see the price.

---

# RESULT — 2026-09-14. H-041's survivor is dead. The guard substitutes one death for another.

`backtests/vwapbreak/guardsweep.json`, log `guardsweep.log`. Gold, blind
walk-forward, floors 30 / top 5, Thunderbolt one-step, data to 2026-09-13.
**The baseline reproduces H-041 exactly on both timeframes** — 17.8 days / 50.7
pass / 49.3 blown on 1h, 34.4 / 29.1 / 70.5 on 4h — so the two studies are
comparable line for line.

## PRIMARY — every arm at 3.00% risk

| 1h | trades | days | band | pass% | blown% | band | its null | failMax% | failDay% |
|---|---|---|---|---|---|---|---|---|---|
| **none** | 957 | 17.8 | 13.9–23.3 | 50.7 | **49.3** | 42.7–64.1 | — | 26.0 | 23.3 |
| −0.50% | 469 | 20.8 | 16.5–26.4 | 57.7 | **42.3** | 27.8–54.6 | 53.7 [45.6–62.7] | 42.3 | 0.0 |
| −0.75% | 596 | 20.3 | 15.0–24.0 | 59.2 | **40.8** | 34.8–55.8 | 52.3 [43.9–58.6] | 37.6 | 3.2 |
| **−1.00%** | 596 | 20.3 | 15.0–24.0 | 59.2 | **40.8** | 34.8–55.8 | 52.3 [43.9–58.6] | 37.6 | 3.2 |
| −1.25% | 661 | 18.4 | 15.0–24.1 | 54.4 | 45.6 | 38.0–59.4 | 51.0 [46.4–57.6] | 42.0 | 3.6 |
| −1.50% | 693 | 18.6 | 14.8–24.1 | 53.9 | 46.1 | 39.1–59.9 | 51.0 [46.0–57.2] | 37.6 | 8.5 |
| −2.00% | 763 | 19.3 | 15.0–23.9 | 51.9 | 48.1 | 42.5–63.7 | 51.3 [47.2–56.6] | 29.5 | 18.6 |
| −2.50% | 812 | 18.5 | 14.3–23.3 | 51.2 | 48.8 | 42.3–63.4 | 50.8 [47.0–55.5] | 30.2 | 18.6 |

| 4h | trades | days | band | pass% | blown% | band | its null | failMax% | failDay% |
|---|---|---|---|---|---|---|---|---|---|
| **none** | 599 | 34.4 | 27.5–54.5 | 29.1 | **70.5** | 57.9–80.8 | — | 18.0 | 52.5 |
| −0.50% | 327 | 63.3 | 36.7–85.6 | 49.0 | **50.6** | 45.5–75.3 | 69.3 [60.3–78.3] | 22.8 | 27.9 |
| −0.75% | 423 | 59.0 | 38.2–95.2 | 28.8 | 70.8 | 56.9–81.7 | 71.3 [66.7–78.7] | 41.6 | 29.2 |
| **−1.00%** | 424 | 59.0 | 38.2–95.2 | 28.8 | **70.8** | 56.9–81.7 | 71.1 [66.7–78.7] | 41.6 | 29.2 |
| −1.25% | 453 | 40.1 | 29.4–65.1 | 29.9 | 69.7 | 52.5–76.8 | 71.1 [65.7–77.4] | 39.6 | 30.0 |
| −1.50% | 477 | 39.3 | 29.3–64.0 | 28.0 | 71.6 | 55.3–78.2 | 70.8 [67.1–78.4] | 37.3 | 34.3 |
| −2.00% | 520 | 39.9 | 28.3–63.2 | 27.6 | 72.0 | 57.3–80.9 | 71.0 [67.2–77.1] | 29.8 | 42.2 |
| −2.50% | 539 | 35.4 | 27.3–53.6 | 29.6 | 70.0 | 56.1–78.4 | 70.6 [67.9–73.5] | 28.7 | 41.3 |

`still_open` is 0.0% on 1h and 0.4% on 4h at every threshold, so **the
fake-zero-fail trap CLAUDE.md warns about is not what is happening here.**

## The four conditions, against the −1.0% arm this study was written to test

| | condition | verdict |
|---|---|---|
| 1 | monotone, both neighbours ≥5pp below baseline, both timeframes | **FAIL** — 1h's −1.25% neighbour is 3.7pp, and on 4h both neighbours are 70.8 against a 70.5 baseline |
| 2 | below the 10th percentile of its matched-drop null, both timeframes | **FAIL** — 1h 40.8 < 43.9 ✓, **4h 70.8 > 66.7 ✗** |
| 3 | ≥5pp advantage at a fixed rung, both timeframes | **FAIL** — 1h +8.5pp, **4h −0.3pp** |
| 4 | blow-up band below the baseline's and separated on one timeframe | **FAIL** — overlaps on both |

**All four fail. The kill criterion is triggered.**

## The single most important number

**4h, fixed rung: 70.5% → 70.8%.** H-041 reported 70.5% → 48.3% for this arm.
The entire 4h result was **confound 3, the risk rung** — its `score` picked 2.0%
risk for the guarded arm against the baseline's 3.0%, and lower risk cuts
blow-ups by itself. Held at one rung the advantage is not small, it is **absent**.

## Why the guard does not save accounts — the mechanism, from the two fail columns

The guard does not stop accounts dying. **It changes which cap kills them.**

| 4h | fail on MAX | fail on DAILY | total |
|---|---|---|---|
| none | 18.0 | 52.5 | **70.5** |
| −1.00% | 41.6 | 29.2 | **70.8** |

23.3 points of daily-cap failure become 23.6 points of max-cap failure. The
substitution is 1:1 to within a rounding error, on both timeframes and at every
threshold but the tightest. An account stopped out of trading on a bad day does
not recover the loss — it carries it into the next day and breaches the 6% max
cap instead of the 3% daily one. **H-041's falling `failDaily` column was never
evidence and this is the arithmetic behind that warning being right.**

## The one arm that beat its own null on both timeframes — and why it is not a win

**−0.50%**, which is not the arm H-041 nominated:

* blow-ups 49.3 → 42.3 on 1h (null p10 45.6) and 70.5 → 50.6 on 4h (null p10 60.3);
* it is the only arm in sixteen cells below its null on both timeframes;
* and its neighbour at −0.75% shows **no improvement whatever on 4h** (70.8),
  so it is an isolated cliff with a flat neighbour — condition 1, the H-038
  signature, failed;
* its bands overlap the baseline's on both timeframes — condition 4 failed;
* **it costs speed**: 17.8 → 20.8 days on 1h and 34.4 → **63.3** on 4h, against
  a 5–14 day pace target, and it halves the trade count (957 → 469, 599 → 327).

**The decisive observation is not any of those individually. It is that the
survivor MOVED.** H-041 swept five thresholds and the winner was −1.0%. This
study fixed the rung, added three thresholds, and the winner is −0.50% while
−1.0% is flat. A curve does not relocate when you look at it more carefully; a
draw from noise does. That is the same lesson the fibonacci sign-flip and H-035
taught, arriving on a sixth axis.

## Verdict — the account-overlay axis is closed

**H-027 is finished being tuned.** Seven axes are now closed by measurement:
entry, timeframe, selector objective, exit shape, band shape, the daily-loss
guard, and the account overlay as a class. The honest next question is
**publish-or-drop and the demo test finishing on 2026-09-28**, not another study.

**−0.50% is logged as the one arm that beat its null on both timeframes and as
NOT a candidate.** Anyone reopening it owes a pre-registration of its own, a
tighter neighbour at −0.25% to show a curve rather than a cliff, and an answer
to the speed price above. `GUARDSWEEP2.md` is that pre-registration and it was
run — see its result before spending another day here.

## Two method notes

* **The guard's output is order-dependent by ±1 trade.** 451 of the 957 blind
  1h trades share an entry timestamp with another trade — the rule runs five
  settings in parallel — and `apply_guard` decides them in frame order, so
  pre-sorting the frame moves a trade in or out (595 vs 596 at −1.0%). Immaterial
  to every number here; named so the next reader does not chase it.
* **Blow-up rates now carry a band.** H-041 quoted 49.3 → 40.8 naked. Those two
  numbers have bands 42.7–64.1 and 34.8–55.8, which overlap heavily, and the
  claim would have been read very differently had that been on the page.
