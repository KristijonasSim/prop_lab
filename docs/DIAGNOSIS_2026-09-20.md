# What is wrong, and what has to change — 2026-09-20

Kris: *"do investigation what is wrong and what we need to do what we need to
change maybe we need to change EVERYTHING to reach our goals of prop firm
targets??"*

Code: `strategies/vwapbreak/research/funded.py`.
Data: `backtests/vwapbreak/funded.json`.
Series: the blind quarterly walk-forward of H-027 gold 1h, 634 days,
`backtests/vwapbreak/daily_traded.json`. **No parameter was searched, so nothing
here is charged to the trial ledger** — it is arithmetic on a fixed series, the
same standing as `firms.py`.

---

## The answer in six lines

1. **No. Not everything. One thing.** The strategy's profit arrives on ~10 days
   out of 634, and every symptom this project has catalogued for a month is that
   one fact wearing a different hat.
2. **The pace target and the business goal are in direct opposition, and this is
   now measured.** 5–14 days is reachable only at 4% risk, where **100% of
   funded seats die in a median of 7 days.**
3. **The half of the business that earns money has never been simulated.** 44
   firm products were scored on time-to-funded. Getting funded is a cost.
   Revenue is payouts, and there was no payout number in the repo until today.
4. **A funded seat is not survivable at any risk the board models.** Max
   drawdown is **19.4 R**; a 6% cap buys 6 R at 1% risk and 3 R at 2%. Death is
   arithmetic, not luck.
5. **The floor for a seat that survives is 0.30% risk and ~78 days** — the
   README's own formula, run honestly: `19.4 / 0.2972 × (10/6) = 109 days`.
6. **Nothing above retracts the edge.** H-027 still beats its paired null. The
   edge is real and the wrong *shape* for this product.

---

# Part 1 — The one fact

Of 634 walk-forward days, 221 traded and **53 closed positive.**

| | R | share of all profit |
|---|---|---|
| 2025-03-28 | **+79.24** | **42.1%** |
| 2024-11-19 | **+43.55** | 23.1% |
| 2025-02-28 | +16.21 | 8.6% |
| 2026-01-23 | +15.12 | 8.0% |
| 2025-02-18 | +13.80 | 7.3% |

**Two days are 65% of everything.** Take the largest ten out of 634 — 1.6% of
the calendar — and the strategy's total goes from **+188.4 R to −24.7 R.**

### The ablation, run end to end

Zero the N largest days, re-run the evaluation and a year of one seat slot:

| days dropped | total R | eval pass % | net EUR / slot-year |
|---|---|---|---|
| 0 | 188.4 | 58.5 | **18,175** |
| 1 | 109.2 | 58.5 | 5,496 |
| 2 | 65.6 | 55.5 | 5,496 |
| 3 | 49.4 | 53.9 | 3,344 |
| 5 | 20.5 | 39.9 | 2,785 |
| **10** | **−24.7** | 24.3 | **−591** |

Read the pass-rate column. **58.5% → 53.9% after removing the three days that
carry 74% of the profit.** The evaluation barely notices, because a 24.3% pass
rate is roughly what a series with no edge produces against a 6% static cap
(`README.md`: a coin flip funds an account 40.2% of the time under a trailing
cap, 57.1% under a static one). **The pass rate was never measuring the edge.**

### Why this is the design, not a bug

`core/chosen.py` says it in its own docstring, and has since 2026-09-09:

> *"the blind selector ranks configurations on profit factor, and profit factor
> is maximised by a very tight stop that wins 5% of the time and pays hugely
> when it does. **That is the opposite of what a prop evaluation rewards.**
> Until the selector's objective is fixed — the open TASK — the board's own pick
> is not the thing to trade."*

The shipped settings hold up to **384 hours — sixteen days** — on a 3–4 sigma
stop. A gold trend measured against a stop that small returns a very large
multiple of R or nothing. The lottery shape is what the objective function asked
for, and it got it.

---

# Part 2 — What that one fact causes

Every open problem in `NEXT.md`, `FIRMS.md` and `CHECK_NEXT.md` is downstream of
it. They are not five problems.

| symptom, already measured | the cause |
|---|---|
| **unpayable at 11 of 22 firms** — one day is 95.5% of a typical month | 2 days are 65% of all profit |
| **deflated Sharpe 0.000 searched, 0.996 pre-registered**; skew 15.2, kurtosis 287 | a distribution made of 10 observations cannot be certified |
| **21.7 expected days, never below 16.8 at any of 48 ladder cells** | you are waiting for a lottery day, not accumulating |
| **every one of 25 entry filters raised PF and lowered R/day** | filters remove ordinary days; the lottery day still has to arrive |
| **a 50% consistency gate costs 316 expected days** | the gate forbids exactly the shape of the edge |
| **funded seat dies — new today** | 19.4 R of drawdown against a 3–6 R budget |

**Seven tuning axes, a tripled drawdown budget, a target sweep and 1,247 charged
trials have all failed to move the pace number.** They were all applied to the
strategy. None was applied to the objective that picks the strategy.

---

# Part 3 — The number nobody had: what a funded seat is worth

Every firm table in this repo stops at "funded". `docs/FIRMS.md` admits the gap
for the trailing rows — *"the trailing cap would bite on a funded account held
for months, which this table does not simulate"* — and it is true of every row,
static or trailing.

Modelled: FundingPips 1-Step Flex (10% / 3% daily / 6% static, cTrader, no
consistency rule), EUR 10,000 seat, 80% split, EUR 61 per attempt, 365-day
horizon, payout every 30 days. Both payout-floor readings are run; the table
below is the **friendly** one (`reset` — a withdrawal restores the full buffer).

## SPEED vs SURVIVAL — the same account, both halves

| risk | DD budget | eval pass % | median days to pass | **seat died %** | median days alive |
|---|---|---|---|---|---|
| 0.25% | 24.0 R | 39.4 | 63 | **0.0** | 365 (full horizon) |
| **0.30%** | **20.0 R** | **48.4** | **78** | **0.0** | **365** |
| 0.35% | 17.1 R | 59.5 | 67 | 14.1 | 235 |
| 0.40% | 15.0 R | 58.0 | 65 | 55.7 | 139 |
| 0.50% | 12.0 R | 62.3 | 63 | 51.9 | 235 |
| 0.75% | 8.0 R | 58.2 | 34 | 79.1 | 128 |
| 1.00% | 6.0 R | 63.2 | 28 | **100.0** | 79 |
| **2.00%** | 3.0 R | 58.5 | **16** | **99.7** | **29** |
| **4.00%** | 1.5 R | 44.0 | **9** | **100.0** | **7** |

**Read the last two rows against the pace target.** 5–14 days exists — at 4%
risk, where the seat lives a median of **seven days** and every one of them
dies. The board's shipped 2% rung resolves in 16 days and kills 99.7% of seats
in 29.

**The crossover is 0.30–0.35% risk**, and it is the max-drawdown arithmetic and
nothing else: 6% ÷ 19.4 R = **0.309%**. Above it the seat cannot survive its own
historical worst stretch; below it, it always does.

## The business number: one seat slot held for a year

Buy an evaluation, fail, re-buy, pass, trade until the seat dies, re-buy. Net
euros per slot-year:

| risk | net mean | net median | p25 | P(loss) | fees | attempts | days funded |
|---|---|---|---|---|---|---|---|
| 0.30% | 1,040 | 605 | 544 | 24.2% | 107 | 1.8 | 235 |
| 0.50% | 2,689 | 3,770 | 573 | 3.0% | 123 | 2.0 | 226 |
| 1.00% | 7,081 | 8,549 | 1,339 | 0.0% | 263 | 4.3 | 202 |
| 2.00% | **13,491** | **18,175** | 3,635 | 0.0% | 511 | 8.4 | 151 |

**Do not read this table as a plan.** 76% of the 269 available 365-day windows
contain 2025-03-28. It is one observation reported 205 times — the repo's own
rule (*"one shuffle seed is a sample of size one"*) applied to a calendar. The
ablation in Part 1 is the honest version of this table: remove five days and
2% risk pays **2,785**, not 18,175.

---

# Part 4 — What to change

## 4.1 Change the objective, not the strategy

This is the cheapest and largest item and the repo already named it.
`core/pipeline.py` selects on **train-slice profit factor**. PF rewards exactly
the lottery shape. Replace it with an objective that prices survival:

```
maximise   net EUR per seat-slot-year        (funded.slot)
subject to max_DD_R <= max_loss / risk       (the seat survives)
           best_day_share_30d < 0.50         (the seat is payable anywhere)
```

Both constraints are already computable — `funded.py` does the first,
`research/bestday.py` the second. **Nothing in this project has ever been ranked
on either.** Eight closed axes were all searched under an objective its own
author flagged as pointed the wrong way.

**Do this before any new hypothesis.** A new feed selected by profit factor will
produce another lottery ticket, and the loop currently running on the VM screens
on effect size and monotonicity — neither of which sees concentration.

## 4.2 Add the two gates that would have caught this on day one

Cheap, and both are seconds to compute:

| gate | kill criterion | why |
|---|---|---|
| **concentration** | drop the top 5 days; if total R falls by more than half, reject | the edge must exist on more than a handful of days |
| **seat survival** | `max_DD_R > max_loss / traded_risk` → reject | a strategy that cannot hold the seat cannot pay |

`core/screen.py` has five checks and neither of these. H-027 passes all five and
fails both of these.

## 4.3 Retire the 5–14 day pace target, or retire the income goal

They are incompatible on this edge and the table in Part 3 is the proof. One of
them has to be rewritten, and it is Kris's call which:

* **Keep 5–14 days** → the seat is a disposable lottery ticket, income comes
  from re-buying evaluations at scale, and the plan should say so and be priced
  that way.
* **Keep the income goal** → the target becomes ~0.30% risk, ~78 days to fund, a
  seat that survives the year, and **the pace target is deleted from
  `README.md`** rather than missed for a fourth month.

The second is the one the stated business — *"bots he runs live with his own
money"*, 10–20 funded seats — actually describes.

## 4.4 What does NOT need changing

State this plainly, because "change EVERYTHING" is the question asked:

* **The evidence machinery is good and should not be touched.** Paired nulls,
  walk-forward with train-only selection, noise bands, the trial ledger, the
  cheap screen, `verify_board.py`. It killed what it should have killed.
* **The feed-over-price prior is correct** and is the strongest evidence in the
  repo. Route B in `docs/WORKFLOW.md` stands.
* **The firm research is finished.** FundingPips 1-Step Flex, no consistency
  rule, cTrader. Do not re-run it; **no firm choice fixes this** — `FIRMS.md`
  proved it when Finotive's tripled drawdown budget moved expected days by
  almost nothing.
* **H-027 should still be published and should still trade the demo.** It beats
  its null. It is just not the product.

---

# Part 5 — Order of work

| # | item | cost | blocks |
|---|---|---|---|
| 1 | **Answer 4.3 — which target is real.** | one decision | everything below |
| 2 | Add the concentration and seat-survival gates to `core/screen.py`. | 1 hour | every future candidate, including the VM loop's |
| 3 | Re-rank the H-027 fold selector on net-EUR-per-slot-year instead of PF. | half a day | whether the 8 closed axes were closed against the wrong objective |
| 4 | Send the B1/B2 email. **Open since 2026-09-08 — twelve days.** | 10 min | every pass-rate number in the repo |
| 5 | PBO on the fold selector (`WORKFLOW.md` 3.2). | half a day | whether the selector beats random at all |
| 6 | The Dukascopy ask/bid volume feed (`core/fx_spread.py:106`). | 1 day | the largest untested input, on the market whose cost bar is 1.83 bps |

Items 2 and 4 are independent of the decision in 1 and should happen regardless.

---

## Caveats

* **One series, 634 days, one market.** Everything here is H-027 gold 1h. The
  concentration finding is about this strategy, not about gold.
* **Firm rules are third-party.** FundingPips 1-Step Flex is modelled from
  `docs/FIRMS.md`'s reading of 2026-09-15 and no contract is signed. The payout
  policy (every 30 days, 80% split, EUR 10k seat) is an input and is swept in
  `funded.json`, not a quoted rule.
