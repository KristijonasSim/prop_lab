# Pre-registration — the top-N result, rebuilt and tested. 2026-09-17.

Written BEFORE the run. `strategies/vwapbreak/research/topn.py`.

## Why this exists at all

The top-N study of 2026-09-15 is the best result in the repo — 8.9 expected days
on gold against the shipped 15.3, five markets, disjoint bands on three — and
**its code was never committed.** `git log` for `61f7be9`, `95c9b63` and
`c10292d` shows JSON, logs and a write-up, and no script. The headline of
`COMPETITION.md` is therefore not reproducible. That is the first thing fixed
here.

## The claim under test

> Trading twenty configurations in parallel at a wider training floor resolves an
> evaluation faster than trading five, *because the extra configurations trade the
> same edge*.

## The alternative it has never been tested against

**Expected days is `median_days / pass_rate`, and more trades per day shortens
`median_days` whether or not the trades have any edge.** The wide configuration
takes 9.13 trades a day against the shipped rule's 1.32. A series with the edge
shuffled out of it would also reach a verdict faster at twenty settings than at
five — it would simply reach the wrong verdict more often. Nothing in the
2026-09-15 run separates those two explanations, because no null was run.

## The criterion, fixed now

Define the **speed-up** of a configuration ladder as

    speedup = days(floor 30 / top 5) / days(floor 100 / top 20)

on the same market, same folds, same cost. The real gold number is 15.3 / 8.9 =
**1.72**.

**The top-N result survives only if the paired-null speed-up is clearly smaller
than the real one.**

* **PASS** — median null speed-up **< 1.25**, i.e. shuffling the sequence out of
  the series removes most of the gain. The gain is then a property of the edge.
* **FAIL** — median null speed-up **>= 1.4**. The ladder then speeds up a series
  with no edge in it almost as much as it speeds up gold, and 8.9 days is an
  artefact of trade frequency. The competition entry is withdrawn.
* **UNRESOLVED** — between 1.25 and 1.4. Report as unresolved, do not trade it.

Two null seeds per market, three on gold. The null is `paired` — returns and
volume permuted together — the same one every other study here uses.

## The second owed item

**BTCUSDT, the sixth standard market**, which the 2026-09-15 run skipped without
writing down a reason. `core/universe.check()` flags it. No criterion is
attached: crypto is expected to be dead here (every crypto price hypothesis in
this repo is), and it is run because the standing rule says all six, always.

## What is NOT being decided here

Blow-up rate. The wide configuration raises it on every market (gold 60.7% →
66.1%) and that is already recorded. This run does not re-litigate it.

---

# RESULT — 2026-09-17. FAIL on every market.

`backtests/vwapbreak/topn_rebuilt.json`, `topn_rebuilt.log`.

## The reproduction

The rebuilt script reproduces the 2026-09-15 numbers exactly on gold: **floor 30 / top 5 = 15.3 days [13–22]** and **floor 100 / top 20 = 8.9 [8–13]**. So what follows is a test of that study, not a different one.

## The criterion, and what happened

| market | shipped 30/5 | wide 100/20 | real speed-up | null speed-up (median) | null seeds | verdict |
|---|---|---|---|---|---|---|
| BTCUSDT | 28.2 | 14.5 | 1.94 | **1.74** | 1.97, 1.51 | **FAIL** |
| XAUUSD | 15.3 | 8.9 | 1.72 | **2.45** | 2.10, 3.97, 2.45 | **FAIL** |
| XAGUSD | 22.1 | 14.4 | 1.53 | **2.69** | 1.84, 3.53 | **FAIL** |
| EURUSD | 25.4 | 11.8 | 2.15 | **9.24** | 15.63, 2.85 | **FAIL** |
| GBPUSD | 43.9 | 11.4 | 3.85 | **5.04** | 5.59, 4.48 | **FAIL** |
| USDJPY | 26.8 | 15.8 | 1.7 | **4.11** | 0.99, 7.23 | **FAIL** |

**Six markets, six failures, and not one is marginal** — the threshold was 1.4 and the smallest null median is 1.74.

**On four of six the null speeds up MORE than the real data does.** Shuffling gold's sequence out of it makes the top-N ladder work better, not worse.

**Stated against this study's own standards, not in its favour.** Two seeds is
thin and the seeds are widely dispersed — USDJPY drew 0.99 and 7.23, so its 4.11
is a two-point median and should be read as "uninformative on its own". **Gold is
the market the claim was about and it has three seeds, 2.10 / 3.97 / 2.45, every
one of them above the real 1.72.** That is the result that decides this, and it
does not depend on the thin cells.

## The mechanism, seen naked on BTCUSDT

BTCUSDT was the market the 2026-09-15 run skipped. It is the clearest evidence in the study because **every one of its ten cells loses money**:

| cell | trades | per day | PF@2x | expected days | band | pass% | blown% |
|---|---|---|---|---|---|---|---|
| 30/1 | 117 | 0.16 | **0.797** | **29.6** | 24–48 | 27.0 | 72.6 |
| 30/5 | 641 | 0.88 | **0.766** | **28.2** | 23–42 | 24.8 | 72.6 |
| 30/20 | 2867 | 3.93 | **0.733** | **27.2** | 22–41 | 29.4 | 69.9 |
| 100/5 | 1491 | 2.04 | **0.642** | **13.0** | 11–18 | 30.8 | 69.2 |
| 100/20 | 6186 | 8.48 | **0.753** | **14.5** | 12–20 | 27.5 | 72.2 |

**A rule that loses a quarter of every dollar it risks reaches a verdict in 14.5 days instead of 28.2 when you widen it.** No edge is involved. That is the entire top-N effect.

## What this means, and what it does not

**It does not touch H-027's edge.** Gold at the shipped floor 30 / top 5 holds PF@2x 2.209 and that is unaffected by anything here. What is withdrawn is the claim that widening N buys speed.

**It does expose a hole in the project's primary metric.** `expected_days = median_days / pass_rate` treats a blown account as free, so any lever that raises trade frequency converts evaluation fees into speed and the board scores it as an improvement. Like for like on gold:

* shipped 30/5 — 39.3% pass = **2.5 accounts per funded seat**
* wide 100/20 — 33.9% pass = **2.9 accounts**

At EUR 40–100 an evaluation that is a real cost nothing in `core/scorecard.py` can see. **Owed: report accounts-consumed (1/pass_rate) beside every expected-days figure, and never compare expected days across configurations with different trade frequencies without a null.**

## The eighth axis is closed

Entry filters, timeframe, exit shape, selector objective, clock anchor, band shape, account overlay, and now top-N width. **H-027 is finished being tuned.**

