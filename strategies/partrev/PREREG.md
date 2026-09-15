# H-047 — participation decides whether a move reverses. PRE-REGISTERED 2026-09-15.

Written before any number. Second entry in the contest Kris set; the first
(H-046, the 16:00 London fix) is dead and its write-up is `../fixflow/`.

---

## The mechanism, stated first

A price move is either **information** or **inventory**, and the tape says which.

* Someone who knows something trades **size**. The move that carries volume with
  it is a repricing and there is no reason for it to come back.
* Someone who must trade — a hedge, a redemption, a margin call, a stop — moves
  price against a thin book. The move that carries **no** volume with it is the
  liquidity provider's inventory, and the provider wants that inventory off.
  Whoever supplies it is paid for that, and the payment is the reversal.

Campbell, Grossman & Wang (1993) is the canonical statement: return reversals
are **stronger after low-volume moves**, because a price change on light volume
is compensation for absorbing a liquidity shock rather than news. It is one of
the oldest results in the literature that has kept replicating out of sample.

**Why this repo should take it seriously in particular.** Participation is the
only conditioner that has ever worked here. H-002's paired-lift study across 44
market x timeframe combinations found `rvol > 2.5` the single strongest lever it
ever measured (+0.063, improving 64.6% of configurations), and the fold selector
then chose a participation filter in **498 of 536 folds**. Every use of it so far
has been as a FILTER ON THE VWAP RULE. **This tests it as the rule itself.**

## What makes it a new hypothesis and not a re-run of a dead one

"Fading an extreme" has died twice here (H-005 rolling high/low, H-011 previous
day/week levels) and CLAUDE.md forbids re-proposing it **without a genuinely new
ingredient**. There are two:

1. **The conditioner is the hypothesis, not a filter on it.** The claim is an
   INTERACTION — reversal in thin participation, continuation in heavy — and it
   is falsified by a flat response just as H-008 was falsified by a flat
   z-response. A fade that works equally at every volume is not this hypothesis.
2. **The cost bar is 20 to 70 times lower.** H-011's verdict was "real edge, too
   small for 28bps" on crypto. A round trip on EURUSD is **0.19bps**, on gold
   **1.06**, against BTC's 9.00. An edge of 2bps is dead on a coin and tradeable
   on a major. That is a measured difference, not an argument.

## The design, fixed now

| | |
|---|---|
| bars | **15m**, every market, because BTC has no finer cache |
| markets | all six of `core/universe.STANDARD` |
| window | 3 years, common end, `core.run_hypothesis.window` |
| move | the signal bar's own return, standardised by a **96-bar** (24h) trailing sd |
| participation | that bar's volume over its **96-bar trailing median**, in terciles |
| entry | **open of the next bar** — never the signal bar's own open or close |
| exits | **h = 1, 3, 6, 12 bars** (15m, 45m, 1.5h, 3h), all four reported |
| dead bars | signal, entry and exit bar must all have volume > 0 |
| cost | `core/markets.COSTS`, mixed execution, quoted at 1x/2x/3x |

## The controls, fixed in advance

1. **A block-permutation null**, block length = the horizon, so the overlap in
   the forward return is preserved and the signal-to-forward pairing is not.
   500 seeds per cell.
2. **The search is priced.** 6 markets x 3 terciles x 4 horizons = 72 cells. At a
   95th percentile that expects **3.6 false passes**, and the benchmark for the
   best cell is the **maximum over cells** of a null draw, not its own p-value.
   H-038's LESSON 1, which this repo wrote down and then failed to apply.
3. **A year split.** Three calendar years; the sign must hold in all three.

## Kill criteria — the study stops if any fails

1. **The interaction exists**: the reversal spread must be **monotone falling**
   in the participation tercile, on at least **4 of the 6 markets**, at the same
   horizon. A flat or sign-flipping response across terciles kills it outright —
   that is H-008's refutation and it is not appealable.
2. **The thin-participation cell clears cost**: edge (half the quintile spread)
   above the round trip at **2x**, on at least **4 of the 6 markets**.
3. **It beats the priced search**: best cell p < 0.05 against the best-of-72 null.
4. **It holds in every calendar year** on the markets that pass 2.

Pass all four and gate 2 is the blind walk-forward through `core/pipeline.py`,
reported as expected days with its noise band on the HOUSE spec — the same sheet
as `COMPETITION.md`. Fail any and it is written up dead.

---

## ADDENDUM, pre-registered 2026-09-15 after stage 1, before stage 2

Stage 1 says the signal is real and too small: **28 of 72 cells at p < 0.05
against 3.6 expected, and the best cell beats the best-of-72 null at p = 0.000**
— while **0 of 6 markets** clear the 2x round trip. Every number there is a
QUINTILE average, which is the mean over the widest 20% of moves. A strategy
would not trade a quintile; it would trade the tail.

**So the question stage 1 leaves is one question, and H-008 already wrote the
test for it: is the response monotone in the SIZE of the move?** H-008 died
because a 3-sigma residual reverted no harder than a 1.5-sigma one — PF 1.000 /
0.997 / 1.006 / 1.013 as entry went 1.5 to 3.0 sigma. A flat response means there
is no tail to trade and the quintile number is the whole story.

Fixed before the run:

* within the **thin** participation tercile only, bucket by `|z|` into deciles,
  and cut the **top 1%** as its own bucket;
* the readout is the fade return, `−sign(z) x forward`, in bps, which is what one
  position actually earns — no quintile differencing;
* horizons 6 and 12 bars, the two where stage 1's interaction was strongest;
* same block-permutation null, same 6 markets.

**Kill criteria.** Both, or H-047 is dead: (1) the fade return rises with `|z|`
across the deciles on at least **4 of 6** markets; (2) the **top-1% bucket** beats
the round trip at **2x** on at least **4 of 6**. A tail that does not clear the
bar cannot be rescued by a stop or a target — those move R, not bps.
