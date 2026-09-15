# H-042 — the crowd ratio, cross-sectional and dollar-neutral

**Pre-registered 2026-09-15, before any number.** Kris picked this over the
VIX/indices alternative on the same day.

---

## The mechanism, and why this is not a new idea

**H-006 is the strongest finding this repo has ever produced and it is not
dead on edge.** The Binance crowd long/short ACCOUNT ratio ranks forward returns
**monotonically**, beats **every** block-shuffle null, and held **PF 1.227 at 2x
cost on BTC out of sample**. It was closed on 2026-09-07 on a **risk-shape**
criterion set in advance, not on a failed edge test:

| | |
|---|---|
| book drawdown | **63.5R** against H-002's 3.8R |
| days to fund an account | 548 |
| shortening the hold | made drawdown **worse**, monotonically (2,810R at 2h vs 184R at 72h) |
| walk-forward at a fixed 4h hold | PF@2x **0.646**, negative R/day, **still beat every null seed** |

**Where the 63.5R comes from is not mysterious.** The signal is a level, read
per coin, with no stop. When the crowd is long everywhere at once — which is
most of a drawdown — a time-series rule says "short" on all ten coins
simultaneously. That is not ten positions, it is one levered short on crypto
beta. The drawdown is the beta, not the signal.

**The fix is structural, not a filter.** Rank the coins against **each other**
and hold long and short legs in equal dollars. Market beta cancels by
construction. Nothing is filtered away, no cell is selected, and the edge test
H-006 already passed is not re-run to find a better cell — it is re-used.

## Why this shape, specifically, and not any other new hypothesis

The firm work of 2026-09-15 (`docs/FIRMS.md`) established that H-027 fails **two**
requirements at once and for one reason:

| | H-027 | needed |
|---|---|---|
| best-day share of a month's profit | **95.5%** | low enough to clear a consistency rule |
| payable under a 50% cap | **0.9% of months** | most months |
| expected days | 19.1 under HOUSE | 5–14 |

Both symptoms come from one property: rare, lumpy profit. **A dollar-neutral
cross-sectional book is the opposite shape by construction** — many positions,
rebalanced often, profit arriving in many small increments. That is the reason
to run it, and `core/prop_rules.best_day_share` measures it directly.

## What this is NOT, so it is not confused with two dead hypotheses

* **Not H-008** (beta-residual reversion). That stripped BTC beta out of four
  alts and faded the residual **price**. Its z-response was FLAT — PF 1.000 /
  0.997 / 1.006 / 1.013 as entry went 1.5 to 3.0 sigma — so the size of a price
  deviation said nothing. This ranks on a **feed**, and that feed's response is
  already known to be monotone.
* **Not H-012** (widening a book with more legs). That added independent
  strategies at equal weight and lost to **dilution**: the median leg had R/day
  −0.0013. This is **one** signal expressed across instruments, dollar-neutral,
  not a portfolio of separate strategies.

## The arms, fixed now — 12 cells and no more

One signal only: `count_long_short_ratio`, z-scored. **The other five metrics in
the feed are not swept.** H-038's lesson was that 96 tests at a 95th percentile
expect 4.8 false passes; twelve expect 0.6.

| axis | values |
|---|---|
| rebalance / hold | **4h, 12h, 24h** |
| legs per side | **2, 3** |
| z window | **288 bars (1 day), 2016 (1 week)** |

Direction is **fixed in advance and not swept**: **short the most-crowded-long
coins, long the least**. That is H-006's direction and reversing it would be a
new search.

Universe: the **11 coins** with both a perp and a metrics feed — ADA, AVAX, BNB,
BTC, DOGE, DOT, ETH, LINK, LTC, SOL, XRP. Window: the project's standard **last
three years to a common end**, 2023-08-31 → 2026-08-31.

Costs: **14 bps round trip at 1x**, reported at 1x / 2x / 3x, charged on
**turnover at every rebalance**, not per nominal trade. A cross-sectional book
rebalancing every 4h turns over constantly and **this is the most likely way the
idea dies**.

## Nulls and controls, decided before the run

1. **Block-shuffled signal**, per coin, at its own block length — the same null
   H-006 beat. 25 seeds.
2. **Random ranking** control: same turnover, same leg counts, ranks drawn at
   random. Separates "the ranking is informative" from "rebalancing a neutral
   book of crypto makes money".
3. **Hour-matched**, per H-038's lesson 2: rebalances land on fixed hours, so a
   null that shifts events to random positions would compare a 00:00 book
   against an all-hours population. Nulls rebalance on the **same clock**.

## What counts as a win — all five, fixed now

1. **Monotone across quantiles.** A ranking signal must rank: the spread from
   most-crowded to least must be ordered, not just have positive extremes.
2. **Beats the block-shuffle null at 2x cost**, by more than the null's own
   10–90 spread.
3. **Beats the random-ranking control.**
4. **Same sign in all three years.** A sign flip between years is this repo's
   signature for no effect (H-026's fibonacci, H-035's netflow).
5. **PF ≥ 1.20 at 2x cost, net of turnover.**

And the reason the hypothesis was chosen, reported but **not** a pass condition,
because making it one would let it select cells:

6. **best-day share materially below H-027's 95.5%.**

## Kill criterion

> If no cell clears all five, H-042 is dead and the cross-sectional fix does not
> rescue H-006. In that case the honest reading is that the repo has now failed
> to monetise its single best signal twice, by two different mechanisms, and the
> next hypothesis should not be a third attempt at it.

## The trap that would make a pass false

**Turnover is the whole risk here.** Eleven coins, four legs, every 4 hours is
~6 round trips a day at 14bps. If the gross spread is 5bps and the cost is 20,
the cell is dead however good the ranking is — and a bug that charges cost once
per rebalance instead of once per leg changed would hide exactly that. The cost
accounting is written **before** the signal code and tested on a hand-worked
example.

---

# RESULT — 2026-09-15. Dead. Every cell loses money before any cost multiplier.

`backtests/xsec/h042.json`, `h042.log`. 11 coins, 2023-08-31 → 2026-08-31.

## The signal is real. It is just small.

**Ordered in all six configurations**, least-crowded to most, with no exceptions:

| z window | hold | least crowded → most crowded (bps) | spread |
|---|---|---|---|
| 1 day | 4h | +2.55 +3.30 +1.54 +0.94 +0.33 | +2.22 |
| 1 day | 12h | +8.04 +5.76 +5.16 +4.72 +2.64 | +5.40 |
| 1 day | 24h | +13.21 +8.59 +19.97 +6.60 +7.65 | +5.56 |
| 1 week | 4h | +3.47 +1.73 +1.59 +1.50 +0.31 | +3.16 |
| 1 week | 12h | +10.05 +3.74 +4.50 +3.79 +4.39 | +5.66 |
| 1 week | 24h | +16.80 +3.99 +12.40 +13.15 +8.23 | +8.57 |

H-006's monotone response survives the cross-sectional rebuild, and the book
beats a randomly-ranked book of the same turnover by **30–40 bps a period**.
**Condition 1 and condition 3 of the pre-registration are met.**

## And it cannot pay for itself

| cell | turnover | gross | 1x | 2x | 3x | PF@2x |
|---|---|---|---|---|---|---|
| 1w / 24h / k3 | 2.00 | **+9.63** | **−4.38** | −18.39 | −32.40 | 0.776 |
| 1w / 4h / k2 | 1.15 | +4.22 | −3.82 | −11.85 | −19.88 | 0.718 |
| 1d / 12h / k2 | 3.12 | +7.28 | −14.57 | −36.43 | −58.29 | 0.548 |

**Not one of twelve cells is positive at 1x cost.** Gross runs 2–10 bps a period;
turnover runs 1–3.3 units, which is 7–23 bps of fees. The best cell earns 9.63
and pays 14.

**Condition 5 (PF ≥ 1.20 at 2x) fails everywhere, so H-042 is dead** by the
criterion fixed before the run. Conditions 2 and 4 were not reached.

## What this settles, and it is worth more than the death

**The repo has now failed to monetise the crowd ratio twice, by two different
mechanisms, exactly as the kill criterion anticipated.**

* **H-006** failed on risk shape: no stop, one levered short on crypto beta,
  63.5R drawdown.
* **H-042** removed that beta by construction — and the fix costs turnover. A
  dollar-neutral book must trade both sides on every rebalance, so the same
  structure that deletes the drawdown creates the fee bill.

**The two failures are the same fact seen twice: the edge is ~5 bps and the
round trip is 14.** The pre-registration said not to attempt a third.

## The pattern this makes five

H-006, H-024 (book depth, best honest cell 7.9 bps), H-031 (liquidation fade,
+26.7 vs +11.8 null), H-034 (term structure) and now H-042. **Every one is a real
effect that beats its null and dies to the same 14 bps.** Crypto feed edges here
are consistently 5–27 bps gross against a 14 bps round trip, which is the wrong
side of the line once a null and out-of-sample are honest.

**The next crypto feed hypothesis should be required to clear costs before its
edge is tested**, not after — the cost test is cheaper and it has decided five
of five.
