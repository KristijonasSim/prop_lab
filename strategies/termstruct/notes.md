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
