# Two attempts to beat H-027 — PRE-REGISTERED 2026-09-13, before any number

Kris: *"go and find something that works and beats our vwap."*

**What "beats" means, fixed now so it cannot be softened later.** The traded rule
is XAUUSD 1h, floor 30 / top 5, budget-linear sizing. To beat it an arm must
resolve an evaluation **faster in expected days**, with a **band that does not
overlap** the baseline's, scored under the **same sizing rule** and the same
walk-forward. A faster number with an overlapping band is not an improvement —
that rule killed the flat percentage band and it applies to my own work here.

Both arms live inside H-027's own axes. Neither is a new hypothesis, so neither
needs Kris to pick a direction first.

---

## Arm 1 — the fold selector, under the sizing rule that was adopted after it

### Why this is not the 2026-09-09 study

`SELECTOR OBJECTIVE (task 3)` compared what the blind fold selector maximises.
On XAUUSD 1h it measured, at **2% flat risk**:

| ranked on | expected days | pass % | trades/day |
|---|---|---|---|
| profit factor @2x (**shipped**) | 15.2 | 65.8 | 0.93 |
| R per day | 11.1 | 44.9 | 2.59 |
| **days = maxDD_R / R_per_day** | **10.9** | 54.9 | 1.52 |

Ranking on `days` was **4.3 days faster** and was left unadopted because the
pass rate fell and the bands overlapped.

**That study is dated 2026-09-09. Budget-linear sizing was adopted on
2026-09-10** and its entire effect is on the axis where the days-selector is
weak: blown accounts **29.5% → 16.9%**, pass **65.8% → 77.0%**, for 1.7 days.

Nobody has run them together — verified by grep, zero rows mention both. If the
sizing rule repairs the days-selector's pass rate while keeping its speed, that
is a genuine improvement to the thing we trade, with no new data and no new
mechanism.

`Pipeline.SELECT_ON` already accepts `"1x"`, `"2x"`, `"rday"`, `"days"`, and
`run_market` passes `pipe_kw` straight through, so this needs no new machinery.

**Arms:** `select_on` ∈ {`2x` (baseline, what is shipped), `rday`, `days`}.
**Tests: 3.** A narrow search, and it is stated up front.

---

## Arm 2 — the Asian range break, on every market

### The gap

The Asian range break is the one genuinely new signal this project found. It is
**0.114 correlated** with the VWAP break, it is second-engine clean 10/10, and
over eleven years it is the most robust arm ever measured here: **71.4% pass,
lowest quarter concentration (30.4%), smallest best-day share (23%)**.

**It has only ever been run on gold.** Verified: the three rows mentioning it are
`volume.py` (XAUUSD 1h and 4h), the second-engine check, and the eleven-year run.
No non-gold market appears in any of them. H-027 got a full nineteen-cell
cross-market screen through `assets.json`; its sibling signal never did.

`VolumeVariant(name, "asia")` is market-agnostic — `asia_range` reads only the
bar's hour, high and low — so this is a screen, not a rewrite.

### The honest problem with it

**A 00:00–07:00 UTC window is not "the Asian session" on every instrument.** On
gold and FX it is a real, low-liquidity overnight window that a London/NY move
then breaks out of. On BTC it is nothing in particular — crypto has no session.
So a hit on crypto is more likely to be noise than a hit on FX or silver, and
that expectation is written down **before** the run rather than invented to
explain a result afterwards.

**Universe:** EURUSD, GBPUSD, USDJPY, AUDUSD, XAGUSD, WTI, BTCUSDT, ETHUSDT,
SOLUSDT at 1h and 4h, with XAUUSD as the reference. **Tests: 18 (+2 reference).**

---

## KILL CRITERION — fixed before the first number

Every arm is scored the same way: blind quarterly walk-forward, paired null,
identical folds, grid and costs, then **budget-linear sizing** over the risk
ladder, best rung by expected days, with the repo's 10–90% block-resampled band
computed **under the same sizing rule as the number it wraps**. A flat-risk band
around a budget-linear number would be two different measurements and is not
allowed.

An arm survives only if **all three** hold:

1. expected days **below** the baseline's — arm 1's baseline is `select_on=2x`,
   arm 2's is XAUUSD;
2. its 10–90% band **does not overlap** the baseline's;
3. it **beats its own paired null**.

### And the search is priced, because I got this wrong today

`STRATEGY_LOG` 2026-09-13: a four-candidate screen produced 7 apparent passes
from 96 tests against 4.8 expected from pure noise, because the gate priced the
per-test null and never the width of the search. **Arm 2 runs 18 tests**, so at a
conventional threshold roughly **one apparent winner is expected from noise
alone**.

Therefore, for arm 2 specifically: **a single market clearing all three
conditions is NOT a result.** It is a candidate, and it must then show the same
sign and direction on a *related* market — another FX major, or the other metal —
before anything is claimed. One isolated winner among eighteen is what noise
looks like, and today it looked exactly like that.

**If nothing clears, both arms are closed by measurement and I will say so
plainly rather than present the best-looking row.**

## Honest prior

Arm 1 is the better bet and it is still under 50/50: the days-selector's speed
was real but its bands already overlapped once. Arm 2 is a screen of a signal
that works on one market, and the base rate for "works on a second market" in
this repo is poor — sixteen markets were screened for H-027 and none beat gold.

---

# ARM 1 RESULT, 2026-09-13 — FAIL. And the specific thesis was wrong.

Written before arm 2 finished, so this verdict cannot be quietly softened later
to salvage something from a bad day.

| arm | risk % | days | band | pass % | blown % | open % | PF@2x | null | tpd |
|---|---|---|---|---|---|---|---|---|---|
| **`2x` shipped** | 3.0 | 11.8 | 10–16 | **67.8** | **27.6** | 4.6 | **2.872** | 1.107 | 0.93 |
| `rday` | 2.0 | **10.4** | 9–14 | 47.9 | 50.9 | 1.3 | 1.446 | 0.956 | 2.59 |
| `days` | 3.0 | **10.6** | 9–14 | 56.8 | 40.7 | 2.5 | 1.408 | 1.051 | 1.52 |

Both alternatives are nominally faster than the shipped selector. **Both bands
overlap it**, so neither is resolvable and both fail condition 2.

## The thesis, and why it was wrong

The prediction was specific: the days-selector's one weakness is its pass rate,
budget-linear sizing exists to repair exactly that, and nobody had combined them.

**Sizing did not repair it.** Blown accounts stayed at **40.7%** (`days`) and
**50.9%** (`rday`) against the shipped selector's 27.6%. The sizing rule shrinks
position as the drawdown budget is consumed, which helps a book that dies slowly;
it cannot help a book whose selector *chooses* configurations that die. The
mechanism was misdiagnosed — the problem was never the sizing, it was what the
objective picks.

The second half says the same thing louder: profit factor collapses **2.872 →
1.446 / 1.408**, and `rday`'s edge barely clears its own null (1.446 against
0.956). Ranking on speed buys trade frequency — 0.93 → 2.59 per day — by
accepting configurations with a far worse edge, and the extra trades then blow up
half the accounts.

## What this closes

**The selector-objective question, properly this time.** The 2026-09-09 study
left it open on the grounds that the comparison predated the sizing rule. It no
longer does. Ranking on `days` or `rday` is faster on the headline and worse on
every other axis, and the speed gain does not survive its own band.

`Pipeline.SELECT_ON` stays at `2x`. Note also that switching it would move every
number on the board, so the bar for changing it was always going to be a
resolvable win, not a 1.2-day nudge inside the noise.

**Not claimed:** that a better objective does not exist. `days` and `rday` are
two candidates; an objective that penalises blow-ups directly — maximise R/day
subject to a drawdown constraint, rather than minimising a ratio that ignores it
— is untested and is the obvious next question if anyone reopens this.

---

# ARM 2 RESULT, 2026-09-13 — FAIL. The Asian range does not travel.

18 tests plus 2 reference cells. **Nothing clears on any market.**

| 1h | days | band | pass % | blown % | PF@2x | null |
|---|---|---|---|---|---|---|
| **XAUUSD** | 18.5 | 17–27 | **75.9** | 17.8 | **1.747** | **0.504** |
| XAGUSD | 17.7 | 16–27 | 73.3 | 15.6 | 1.213 | 0.818 |
| USDJPY | 17.8 | 16–27 | 50.6 | 47.0 | 0.939 | 0.624 |
| SOLUSDT | 20.0 | 17–27 | 59.9 | 20.9 | 0.941 | 1.082 |
| EURUSD | 26.6 | 19–37 | 41.4 | 43.8 | 0.818 | 0.684 |
| BTCUSDT | 28.5 | 22–41 | 35.1 | 57.4 | 0.644 | 0.949 |

At 4h the picture is the same: gold PF@2x **2.215 against a null of 0.459**, and
every other market between 0.63 and 1.12.

**The margin over the null is the whole story.** Gold beats its own
phase-randomised copy by 3.5x on 1h and 4.8x on 4h. No other market beats its
null by more than ~1.5x, and BTC, SOL and AUDUSD **lose to theirs**.

**The near-miss is silver, and it is a real near-miss:** 17.7 days against gold's
18.5, 73.3% pass, PF 1.213 over a null of 0.818. It is nominally faster. Its band
is 16–27 against gold's 17–27 — almost total overlap, so it is not resolvable,
and condition 2 refuses it. Silver is also the market this repo has already
caught out once: H-027's own cross-market screen found XAGUSD 1h at 59.9% pass
and 16.7 days, and it **lost to its own null**. Anyone reading the pass rate
alone would have traded it.

**The pre-registered expectation held.** The note written before the run said a
00:00–07:00 UTC window is a real overnight session on gold and FX but nothing in
particular on crypto, so a crypto hit would more likely be noise. The two markets
that lose to their nulls outright are BTC and SOL.

## What this closes

**The Asian range is a gold signal, not a portable one.** It stays exactly where
it is — the second signal on the one market, already traded, already
second-engine clean. There is no second market to add and no book to widen.

Combined with arm 1 this closes the two cheapest routes to beating H-027: you
cannot get faster by changing what the selector maximises, and you cannot get
more uncorrelated trades by taking the same signal somewhere else.

---

# Arm 3 — R/day under a DRAWDOWN CAP  (PRE-REGISTERED, before any number)

Opened immediately by arm 1's failure, not by a hunch. Reading `_score` shows
why `days` blew up 40.7% of accounts while looking fast:

```python
if self.select_on == "days":
    eq = np.concatenate(([0.0], np.cumsum(r)))
    dd = float((eq - np.maximum.accumulate(eq)).min())
    return rpd / max(abs(dd), 1e-9)      # bigger = fewer days
```

**It returns a RATIO, so it is scale-free.** R/day 1.0 against a −50R drawdown
scores identically to R/day 0.1 against −5R. A fixed-percentage account with a
6% max-loss cap does not see those as equivalent — the first breaches
constantly. The objective is structurally blind to the magnitude of the very
thing that ends evaluations.

`rday` is worse: it ignores drawdown entirely and blew 50.9%.

## The change

`Pipeline.SELECT_ON = "rday_capped"` with `max_dd_r`: maximise R per day, but
**reject** any config whose train-slice drawdown exceeds a cap in R. Drawdown
becomes a constraint, not a denominator. The shipped `2x` path is untouched, so
no board number can move; only the file fingerprint changes.

## Arms, and the search priced up front

Three caps, declared now: **max_dd_r ∈ {5, 10, 20}**, against the shipped `2x`
baseline. **3 tests.** A narrow search, stated before running, and no cap will be
added afterwards to rescue a near-miss.

Cap units are R on the train slice, the same units `_score` already computes.

## Kill criterion — the same one, unchanged

Faster than `select_on=2x` in expected days, **band disjoint**, and beats its own
paired null, all under budget-linear sizing with ASH rules. A 1-day nudge inside
overlapping bands is not an improvement — that is what killed arms 1 and 2's
predecessors and it applies here identically.

**Extra condition, because this arm's whole claim is about blow-ups:** it must
also show **blown % at or below the shipped selector's 27.6%**. An arm that gets
faster by blowing up more has not solved the problem it was built to solve, it
has just moved along the same trade-off `rday` and `days` already sit on.

## Honest prior

Better than arm 1's, because this fixes a defect that was *measured* rather than
guessed — but still under 50/50. The cap may simply select the same
low-drawdown, low-frequency configs the profit-factor selector already finds, in
which case it reproduces the baseline and closes the objective question for good.
