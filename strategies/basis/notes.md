# H-013 — the derivative against the cash market it is supposed to track

Opened 2026-09-02, after Kris asked for a hypothesis that is not VWAP and not a
variation on one, and that could plausibly beat H-009's board score of 8.9.

## The mechanism, stated before any result

A perpetual has no expiry, so nothing drags it back to spot except two things:
the people who arbitrage the gap, and the funding transfer that bills whichever
side is crowded. Neither cares about direction. Both care that the gap closes.

So the claim is narrower than "price reverts", and it names its victim:

> a move paid for with leverage rather than with cash has to be unwound,
> because the people holding it are being charged to hold it.

The counterparty is named — basis traders short the perp against cash, and every
eight hours the crowded side pays them — which is the property every leg that has
ever worked in this project had and no price pattern has.

## Why this is not H-004, H-006 or H-009 again

| | what it measures | verdict |
|---|---|---|
| H-004 funding fade | the 8-hourly SETTLED funding rate | rejected: 0.20 trades/day, walk-forward 0 of 12 |
| H-006 order flow | POSITIONING — a headcount of who is standing where | 1.3, signal real, no stop, 49.8R drawdown |
| H-009 crowd gate | the same headcount, used to veto H-002's trades | **8.9, top of the board** |
| **H-013** | **PRICE and PAYMENT — what the crowded side is being charged** | this file |

Funding is a clamped 8-hour TWAP of the premium. H-004 tested the summary, at
7,645 observations. This tests the thing itself at 5-minute resolution, 699,230
observations, which is the one honest reason to reopen a family the project has
already rejected once.

Against H-006/H-009 the difference is not resolution but quantity: positioning is
who holds the risk, the premium is what they pay for it. **Measured, not assumed:
Spearman correlation between `prem_z` and `crowd_z` is −0.05 (BTC), −0.12 (ETH),
−0.16 (SOL).** It is not a re-measurement of the signal already in the best book.

## The data — free, six years, and it was there the whole time

`core/basis_data.py` pulls two series nothing here had used:

    premiumIndexKlines   (mark − index) / index, 5m, from 2020-01, every symbol
    spot klines          the cash book's own bars WITH taker_buy_base

699,230 premium bars and 701,106 spot bars per major, unauthenticated, from the
same archive `core/binance_metrics.py` already uses. Every flow feature in this
repo before today was perp-only, so nothing here could tell a move the cash
market was paying for from one it was not. This can.

**One bug found writing the loader**, of a shape this repo has hit before: the
archive switched from millisecond to microsecond stamps during 2025, and a batch
spanning the switch carries both. Choosing the unit from the batch maximum dates
every millisecond row to 1970. Caught because the spot series claimed to start
1970-01-19. The test is now per row. `core/binance_metrics.py` has the same
latent construction and has not yet been corrected.

## Stage 1 — the diagnostic, before any strategy existed

Same construction, same three gates and the same block-shuffle null as H-006's
`stage1_ic.py`, imported rather than reimplemented, so the two are read off one
ruler. 240 feature × horizon × symbol cells.

| feature | mean abs IC | mean abs spread | beats null | stable across years |
|---|---|---|---|---|
| **prem_z** | **0.023** | 10.9bps | **15 of 15** | 0.90 |
| lead_4h | 0.016 | 9.7bps | **15 of 15** | 0.88 |
| dprem_4h | 0.014 | 8.1bps | **15 of 15** | 0.88 |
| *H-006's best, `crowd_z`* | *0.022* | *19.6bps* | *53%* | *—* |

`prem_z` carries a higher information coefficient than the best feature in H-006
and beats its null in **every** cell, which no H-006 feature managed. Its
quintile spread is smaller — but a quintile spread averages over the tails a
strategy actually trades.

### The tail, which is what gets traded

Per-side edge in basis points, BTC, fading the top tail and buying the bottom
(round trip is 14bps at 1x, 28bps at 2x):

| tail | 4h | 8h | 24h | 48h |
|---|---|---|---|---|
| 20% | 5.0 | 8.5 | 11.1 | 19.7 |
| 10% | 6.4 | 9.1 | 15.7 | 31.7 |
| 5% | 7.3 | 13.8 | 25.2 | **51.4** |

Monotone in **both** directions — deeper tail and longer horizon both pay more —
and it beats its block-shuffle null in 12 of 12 cells. That shape is what a
mechanism looks like. H-008 was killed by the absence of exactly this: a flat
z-response, where a 3σ deviation did not revert harder than a 1.5σ one.

**These are non-overlapping estimates.** The first pass reported t-statistics of
6–23; those were on 5-minute observations with 24-hour forward windows, which
overlap 288-fold and inflate t by roughly √288. Sampled one observation per
horizon the honest t-statistics are 1.0–2.9. The effect is real and consistently
signed; the sample of independent observations at 48h is only ~122–486 in six
years, so the error bars are wide and stage 2 is what decides.

## The confound that had to be ruled out, and was

The premium spikes when price moves fast, so `prem_z` could simply be short-term
price reversal wearing a costume — and this project has rejected five price
patterns against zero successes. If that were true, controlling for recent
returns would kill it.

It does not. BTC, hourly-thinned, 58,171 observations:

| horizon | IC(prem_z) | IC(ret_4h) | **partial IC(prem_z given ret_1h, ret_4h)** |
|---|---|---|---|
| 8h | −0.0323 | −0.0207 | **−0.0331** |
| 24h | −0.0353 | −0.0167 | **−0.0356** |
| 48h | −0.0326 | +0.0007 | **−0.0325** |

The partial IC is not merely positive, it is **unchanged** — the premium's
information is orthogonal to what price just did, and it is twice as strong as
price reversal on its own. The double sort says the same thing: on BTC the
q1−q5 premium spread is positive inside **all five** recent-return buckets
(+44.7, +16.9, +33.1, +33.2, +17.9 bps at 24h). It works regardless of what price
just did.

## Weaknesses, unprompted

- **BTC carries it.** ETH is weaker, SOL is weakest and its 48h partial IC is
  +0.002, i.e. nothing. H-004 had exactly this shape — 826 of its 828
  gate-clearing configs were BTC alone — and it died in walk-forward. Until this
  clears a walk-forward on more than one market it is the same story with a
  better feed. Eight more symbols are being pulled to test that.
- **One venue, one feed.** Binance's own premium index. If the exchange changes
  how it computes the index, the signal changes with it.
- **No TradingView port.** Pine cannot fetch the premium index, the same
  limitation H-009 has.
- **Nothing is walk-forwarded yet.** Everything above is a diagnostic. H-004 had
  the widest stage-1 null margin in the project — 828 gate-clearing configs
  against 2 — and still failed the moment configurations had to be chosen blind.
  A stage-1 margin is necessary and has never been sufficient here.
- **The stop is unproven.** H-006's stop test made its book worse on every
  measure under two different fold selectors. There is no reason yet to think
  this one behaves differently.
