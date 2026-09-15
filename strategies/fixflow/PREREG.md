# H-046 — benchmark-fix flow. PRE-REGISTERED 2026-09-15, before any number.

**Not H-027.** Kris set a contest against another agent: the best NEXT hypothesis
that is not the VWAP band breakout. This is the entry, and everything below the
line was written before a single number was computed.

---

## The mechanism, stated first

At **16:00 London** the WM/Reuters benchmark rate is fixed from trades in a
five-minute window (widened from one minute in February 2015). Index funds,
ETFs, custodians and corporates place orders to be executed **at that rate**, so
the flow is (a) price-insensitive, (b) concentrated, and (c) known about in
advance by the dealers who must fill it.

* **Who is on the other side.** A dealer who has accepted a fix order is short
  the fix. They hedge before the window, which pushes price in the direction of
  the order. That is the **pre-fix drift**.
* **Why it should revert.** The hedging pressure is inventory, not information.
  Once the window closes the dealer is flat and the pressure stops; whoever
  supplied liquidity into the drift now wants out of it. That is the **post-fix
  reversal**, and it is the thing being tested.
* Gold and silver carry the same structure and a second one: the **LBMA
  auctions** at 10:30 and 15:00 London are benchmark prints of exactly this kind.

Published: Evans (2014), Melvin & Prins (2015), Ito & Yamada (2017), Marsh,
Panagiotou & Payne (2017). All of them measure the effect **before** the 2015
window change, and the reform was designed to kill it. **The prior is that this
is a decayed effect, and the honest outcome of this study may be that it is
gone.** It is worth running anyway because the flow is still there — the reform
widened the window, it did not remove the orders.

## Why it fits this project's phase gate

One event per market per day, a hold of 30–120 minutes, five of the six standard
markets carrying the mechanism. ~750 events per market over three years, and a
round trip on gold costs **1.07bps** against 9bps on BTC — the FX/metals side of
this repo is the cheap side and has never been given a high-frequency rule.

## The design, fixed now

| | |
|---|---|
| anchor | **16:00 Europe/London**, DST-aware, so 15:00 or 16:00 UTC |
| pre-drift | close of the bar ending 15:05 London → close of the bar ending 16:05 London |
| entry | **open of the next bar** after the signal bar (16:05 London) |
| exits | **h = 30, 60, 120 minutes** after entry, all three reported |
| direction | **fade** the pre-drift |
| bars | 5m for FX/metals, 15m for BTC (no finer crypto cache exists) |
| dead bars | any day whose pre, signal, entry or exit bar has zero volume is dropped |
| markets | all six of `core/universe.STANDARD` |
| cost | `core/markets.COSTS`, mixed execution, round trip, quoted at 1x/2x/3x |

## The three controls, all of them fixed in advance

1. **An hour-matched null.** `core/probe.py`'s null shifts events to random
   positions and would compare a 16:00 event against a population drawn from
   every hour — the exact defect LESSON 2 of H-038 records. This null instead
   **permutes the pre-drift across DAYS at the same clock slot**, 500 seeds, so
   the hour, the session and the intraday volatility pattern are all held.
2. **A control market.** **BTCUSDT has no benchmark fix.** It is the placebo
   instrument, and a spread there that matches gold's kills the mechanism story.
3. **A placebo clock.** The identical test is run at **all 24 London hours**. The
   fix hour has to stand out from the other 23, and the 24 anchors also price the
   search: at a 95th percentile, 24 anchors × 6 markets expect **7.2 false
   passes** (LESSON 1 of H-038, `core/search_cost.py`).

## Kill criteria — written before the run, and the study stops if any fails

Gate 1 passes only if **all four** hold, at h = 60 unless stated:

1. The **per-trade gross edge** — half the quintile spread, because a book that
   trades the bottom and top quintile takes one position per event — exceeds the
   round trip charged at **2x cost** on **at least 3 of the 5 fix markets**.
   Quintile spread in bps must therefore clear `4 x round_trip_1x`.
2. The pooled fix-market spread beats its hour-matched null at **p < 0.05**.
3. The fix anchor ranks in the **top 3 of the 24 placebo anchors** on the pooled
   fix-market sample.
4. **BTCUSDT does not pass criterion 1.** A control that fires means the effect
   is not the fix.

If gate 1 passes, gate 2 is the blind walk-forward through `core/pipeline.py`
with the paired null, the risk ladder and the noise band, reported on the HOUSE
spec as expected days with its band — the same scoring sheet as `COMPETITION.md`,
so the two entries are comparable.

**If gate 1 fails it is written up as dead and nothing is built.** Seven of the
last nine hypotheses here died at this stage; that is the denominator.
