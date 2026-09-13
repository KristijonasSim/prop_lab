# H-034 — the term structure of leverage

**PRE-REGISTERED 2026-09-13, before the first measurement.** Kris: *"please test
next hypothesis."* Proposed in `NEXT_HYPOTHESIS_2026-09-13.md`.

## Mechanism, before any result

Binance lists **dated quarterly futures** beside the perpetual. A dated contract
must converge to spot on a known date, by arbitrage. Its premium is therefore not
sentiment — it is **the market's term price of leverage**, with a hard settlement
anchor.

Nothing in this repo has ever had a hard anchor. Every feed here is a level with
no reason to revert to anything. This one *must* reach zero on a stated day, and
the question is what the path there says.

**Who is on the other side, named:** cash-and-carry arbitrageurs. When the
annualised basis is rich they sell the future and buy spot and are paid to
compress it. When it collapses or inverts, that trade is being unwound — a
deleveraging signal from the one participant who is mechanically forced to act
rather than choosing to.

## Why this is not H-004 or H-013, which are both dead

Measured 2026-09-13 on BTCUSDT, 2,791 paired hourly observations, contract
`BTCUSDT_250926`:

| | annualised dated basis | annualised funding |
|---|---|---|
| median | 6.89% | 6.15% |
| stdev | **1.76** | **4.10** |
| min | −0.75% | −5.83% |
| correlation, **levels** | \- | **0.306** |
| correlation, **changes** | \- | **0.004** |

Funding is the instantaneous, clamped, 8-hourly cost of perp leverage and it is
noisy. The dated basis is the *term* price of the same thing and is less than
half as volatile. H-004 tested the noisy one; H-013 tested the perp-spot gap at
zero maturity. **A 0.004 correlation of changes is not the same series.**

## The data, and when it was knowable

`core/termstruct.py`. USDT-margined dated quarterlies from
`data.binance.vision`, **22 of 22 cycles present, 0 missing**, `BTCUSDT_210326`
→ `BTCUSDT_261225` (2021-03 → 2026-06). Hourly closes, same archive
`binance_metrics.py` already uses.

* **The dated contract is NEVER traded.** It does ~$16.3M/day against the perp's
  $16.57B — one thousandth. It is a FEED only; every trade is in the perp at the
  14bps round trip already modelled. It prints ~19,600 trades/day, so its hourly
  close is a real price, not a stale quote.
* **Front contract** = nearest expiry with **more than 3 days** remaining. The
  last days are excluded: basis goes to zero there by arithmetic, not by
  information, and liquidity thins.
* Expiry is the contract code at **08:00 UTC** (Binance quarterly settlement).
* Everything is read at the bar CLOSE and traded at the NEXT bar's open, which
  is what `core/probe.py` enforces.

## The three readings, fixed now

`basis_ann = (front_close − perp_close) / perp_close × 365 / days_to_expiry`

| id | reading | event | direction | control |
|---|---|---|---|---|
| **L+** | level, rich | `basis_ann` in the **top decile** of its trailing 90d | **short** the perp — leverage is crowded long | L− |
| **L−** | level, cheap | bottom decile of trailing 90d | **long** the perp | L+ |
| **K** | shock | 24h change in `basis_ann` below the **5th percentile** of trailing 90d changes | **short** — the cash-and-carry unwind | K′ (above the 95th) |
| **S** | slope | back−front curve, top/bottom decile | steepening → **long** | S′ |

**Every reading ships with its opposite as a control**, as H-030's gates did. A
reading that works and whose opposite also works is measuring the market, not the
mechanism.

Horizons: **4, 12, 24, 72 bars** (hours). Two markets: BTCUSDT, ETHUSDT.

## KILL CRITERION — fixed before the first number

### Gate A — PACE, checked FIRST and alone

The named most-likely death. The basis is smooth (stdev 1.76% annualised), so a
threshold may fire a handful of times a year and be untradeable regardless of
edge.

> **A reading must fire at least 40 times a year on BTCUSDT.** Below that it
> cannot resolve a 5–14 day evaluation and **H-034 dies without an edge test.**

This number is carried unchanged from `NEXT_HYPOTHESIS_2026-09-13.md`, written
before any of this was measured. It is not to be relaxed after seeing the count.

### Gate B — EDGE, only if Gate A passes

`core/probe.py`, forward return vs the same statistic on randomly shifted event
dates. All three must hold on the same reading:

1. `edge_bps` **>** the measured hurdle, **14.0 bps** on BTCUSDT/ETHUSDT;
2. `pctile` **≥ 95** against 400 shuffled-date nulls;
3. `by_year` carries the **same sign in at least 4** of the 6 calendar years —
   BTC 30m cleared thirty quarters here and still lost money from 2024, so a
   single-year story is not a result.

And the control must NOT also clear (1) and (2). If L+ and L− both work, both die.

**Anything else and H-034 is closed by measurement.**

## Honest prior

**It probably fails, most likely on pace.** Carry is slow, and slow is what
killed H-006. The reasons to spend the day anyway: the anchor is real and no
other feed here has one, the data is free and already verified complete, and the
whole thing is decidable without writing a kernel.

Not claimed in advance: that a term structure carries anything. It is a
measurement, and the measurement has not been made yet.

---

# RESULT, 2026-09-13 — DEAD at gate 2. Nothing clears Gate B.

48,837 hourly rows per market, 2021-02 → 2026-08, 23 dated contracts.

## Gate A — PASSED

All six readings fire far above the floor of 40/year, on both markets.

| reading | BTC events/yr | ETH events/yr | in state | median run |
|---|---|---|---|---|
| L+ rich | 153.2 | 139.1 | 15.5% | 2h |
| L− cheap | 235.2 | 243.1 | 19.6% | 2h |
| K shock down | 165.3 | 178.1 | 4.8% | 1h |
| K′ shock up | 176.9 | 190.6 | 4.9% | 1h |
| S steep | 62.1 | 57.4 | 10.3% | 2h |
| S′ flat | 82.7 | 90.7 | 11.4% | 2h |

**The predicted death did not happen.** Pace was the named most-likely killer and
the basis fires plenty often. Over the full window it is also far wilder than the
2025 sample suggested — stdev **8.38** against 1.76, range **−46.6% to +75.3%** —
because 2021's bull and 2022's backwardation are in it.

## Gate B — NOTHING SURVIVES

### The level reading is not there at all

L+ and L− never approach the gate on either market. Best percentile **78.2**, and
most edges are negative or sit far inside their nulls. Whether leverage is
currently expensive says nothing about the next 4 to 72 hours.

### The closest thing, and why it still fails

**ETHUSDT, S steep, h=72: edge 205.13 bps, pctile 95.2, hurdle 14.0.** It clears
two of three conditions. It dies on the third:

| year | 2023 | 2024 | 2025 | 2026 |
|---|---|---|---|---|
| edge bps | **−49.35** | +325.36 | +254.69 | +224.81 |

**3 of 4 years, with a sign flip in 2023.** That is H-026's signature.

Three more things say the same, and any one of them is enough:

* **The same reading fails outright on BTC.** S steep h=72 scores 139.22 bps
  against a null p95 of **171.46** — the shuffled dates beat the real ones. A
  mechanism that works on ETH and not BTC, on the same contract structure and the
  same clock, is not a mechanism.
* **The null is as big as the edge.** At h=72 the ETH edge is 205.13 and its own
  null p95 is 201.96. A 72-hour horizon has enormous variance and the noise floor
  is doing exactly the job it was built for.
* **K flips across markets.** K shock down on BTC is the other near-miss —
  h=72 edge 35.15, pctile 94.5, just under both thresholds — and on ETH the same
  reading is **−11.26**. Opposite signs on two markets.

### A criterion/data mismatch, and it is mine

Gate B was written as "same sign in **≥4 of 6** years". The slope readings only
span **2023–2026**: the back contract overlaps on 54% of rows and only from 2023,
which the proposal flagged as a risk and the criterion then failed to account
for. The rule should have been stated relative to the years each reading actually
has. It changes nothing here — S steep failed at 3 of 4 — but the criterion was
written sloppier than the study deserved and that is worth recording.

## What is closed, and what is not

**Closed: the term structure of leverage as an entry or a directional gate on the
perp, at 4–72 hour horizons, on BTC and ETH.** The hard convergence anchor is
real — the basis decays 153 → 8.6 bps into settlement, exactly as arbitrage says
it must — but the *path* there carries nothing that survives a shuffled-date null
at a 14bps hurdle.

**Not claimed:** that the dated curve carries nothing anywhere. Untested here are
longer horizons than 72h, the basis as a position-SIZE input rather than a
direction, and the roll window itself. Those are new questions with new searches
and they are logged, not run.

The honest summary: the feed is real, obtainable, five years deep, free, and
genuinely distinct from funding (0.004 correlation of changes). It still does not
predict the perp.
