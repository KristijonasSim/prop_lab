# Footprint, heatmaps and liquidity — the research, and the next hypothesis

**Written 2026-09-16.** Kris asked for a big piece of research on what the next
hypothesis should be, naming footprint charts, heatmaps and liquidity, and left
the choice open. This is the answer. Three of its numbers were measured today rather than
argued, and one of those three retracts another — section 1b.

---

## THE ANSWER, IN SIX LINES

1. **Do not buy footprint data.** The footprint family was measured today on
   154,250,485 real trades and **0 of 35 cells clear any cost bar, 0 of 35 beat
   their own null**, with a detection floor that proves this is not a power
   problem.
2. **Do not buy heatmap data either.** The free half of it is already on disk
   and H-024 killed it.
3. **Do not build a cost-timing rule.** Measured today and killed today: the
   BTCUSDT spread is 1–2 ticks and **varies 1.28x**, so there is nothing to
   time. My own first estimator said 21x; it was measuring the bar's drift, and
   section 1c is the correction.
4. **The nomination is H-049 — re-price the crypto cost table for the size
   actually traded.** `core/markets.py` charges a 2.0bps/side slippage
   allowance that corresponds to a **$10,000,000** order. The live book trades
   **$877** legs. True round trip **14 → 10.0bps**.
5. That is not a pace fix and is not offered as one. It is the concrete route
   by which **a dead signal becomes a live one** — with H-048's maker path,
   H-024's 7.9bps cell clears.
6. The reason to believe any of this is the pattern in section 2. Full
   shortlist in section 7.

---

## 1. What was measured today

Three new results across two files, both runnable, both with their design
written before the run. **Section 1c retracts a number from section 1b**; both
are kept because the correction is the useful part.

### 1a. `strategies/footprint/stage1_location.py` — the footprint family

A footprint chart is a bar split by price level with aggressive buy and
aggressive sell volume printed side by side at each level. Everything read off
one is either:

* **how much** net aggression the bar carried — that is `delta`, and this repo
  has measured it three times already (H-006 flat, H-021 real and 5x too small,
  H-022 real at 6.55bps against an 8bps round trip); or
* **where inside the bar's range** that aggression sat — **never measured here,
  and it is the only thing a footprint adds to a feed this repo already owns.**
  `data/feeds/*_taker_5m.parquet` gives bar-level delta with no tick data. The
  price-level resolution is the entire reason a footprint costs money.

So the question is not "is order flow informative". That is answered: real, and
too small. The question is whether **location** adds anything on top of amount.

Built from `data/ticks/BTCUSDT-aggTrades-*.zip`, Binance USDT-M, **117
consecutive days 2026-05-01 → 2026-08-25, 154,250,485 trades**, into 11,232 15m
bars and 33,696 5m bars, ten price levels per bar. Five location features, each
one a named footprint pattern with a falsifiable claim about the counterparty:

| feature | the pattern | the claim |
|---|---|---|
| `absorb` | aggressive buying in the top decile that the close walks away from | somebody passive with quantity and no deadline is there; price fades |
| `unfin` | the extreme printed with **both** sides | a finished auction ends one-sided; price returns to complete it |
| `stack` | ≥3 consecutive levels at 3:1 on the diagonal | continuation — the most-cited footprint entry trigger |
| `dloc` | buyers working higher in the range than sellers | directional intent |
| `poc_loc` | most-traded level relative to the close | a POC left overhead is supply |

Two controls ride along — raw `delta` and H-022's `absorbq` — so the run reads
against a known quantity instead of asking to be trusted. Entry is at the **next
bar's open**, never close-to-close: two look-aheads of exactly that class have
already been found in this repo (H-019, H-023 stage 13).

**Result.**

| | 15m bars | 5m bars |
|---|---|---|
| location cells tested | 15 | 20 |
| clear 14bps taker unconditionally | **0** | **0** |
| clear 14bps inside delta terciles | **0** | **0** |
| beat their own best-of-200 null | **0** | **0** |
| largest \|q5−q1\| anywhere | **3.90bps** | 1.71bps |

`backtests/footprint/stage1_location_15min.csv`, `..._5min.csv`.

**Why this is a kill and not an underpowered shrug.** The controls are flat too
(`absorbq` reads −0.49bps at 1h where H-022 measured −2.5bps over six years), so
this window cannot resolve an H-022-sized effect. It does not need to. The
standard error of a q5−q1 spread here is:

| bars | horizon | SE | 3σ floor | **a 14bps effect would be** |
|---|---|---|---|---|
| 5min | 1h | 0.71bps | 2.12bps | **19.8σ** |
| 5min | 4h | 1.38bps | 4.13bps | **10.2σ** |
| 15min | 1h | 1.23bps | 3.70bps | **11.4σ** |
| 15min | 4h | 2.39bps | 7.17bps | **5.9σ** |

The scout is blind to a 2.5bps effect and **cannot miss a tradeable one**. The
largest location reading anywhere in 35 cells is 3.90bps. A footprint edge big
enough to pay a 14bps round trip would have shown at six to forty sigma. It is
not there.

**Scope, and it is the honest limit:** one market, one regime, 117 days, ten
levels rather than one per tick. This kills the family *as a cheap purchase
decision*. It does not prove no footprint edge exists anywhere.

### 1b. RETRACTED — "the round trip varies 21x"

The first version of `strategies/costmap/stage0_dispersion.py` measured the cost
of a bar as `vwap(aggressive buys) − vwap(aggressive sells)` and reported a p10
of 0.17bps against a p90 of 3.69 — **21x dispersion** — with a median of
1.08bps.

**It was measuring the bar's own drift.** Over fifteen minutes the two sides are
separated by where price went as well as by the spread, so a rising bar reads
far too wide and a falling bar reads *negative*. The run dropped the negatives,
which silently threw away **39% of the bars, all of them falling ones**, and
inflated everything that followed. The retracted numbers are: 21x dispersion,
1.08bps median, spearman 0.186, and "cheap bars are 8.7–9.7x better per unit of
cost". **None of them stand.**

### 1c. The corrected measurement — and it closes the direction

The estimator is now the **bid-ask bounce on adjacent trades**: take every pair
of consecutive aggTrades whose aggressor sign flips, and measure the buy price
minus the sell price. Consecutive trades are milliseconds apart, so drift
between them is negligible and what is left is the spread. No bars are dropped —
all 11,232 survive.

| | retracted (drift) | **corrected (bounce)** |
|---|---|---|
| median round trip | 1.08bps | **0.02bps** |
| p10 → p90 | 0.17 → 3.69 | **0.01 → 0.02** |
| **dispersion p90/p10** | 21.1x | **1.28x** |
| spearman(cost_t, cost_t+1) | 0.186 | 0.998 |

**0.02bps of a $110,000 price is about two ticks.** The BTCUSDT perpetual is
one to two ticks wide essentially all of the time. Its dispersion is 1.28x, its
next-bar correlation is 0.998 because the value is quantised and constant, and
**there is nothing whatsoever to time.** Q3 agrees: the cheap cost quartile is
1.04–1.06x better per unit of cost at 15m and 1h, and **0.97x — worse — at 4h.**

**A cost-timing rule on crypto is dead, killed by the corrected version of the
measurement that suggested it.**

### 1d. What the correction exposes instead

`core/markets.py` charges BTCUSDT a `half_spread` of **2.0bps per side**, with
the comment that it is *assumed* and *"the weakest number in this table"*. The
quoted spread is **0.01bps per side**. The 2.0 is not a spread at all — it is an
unmeasured **slippage allowance**, and the depth feed prices exactly how big an
order it belongs to.

`data/feeds/BTCUSDT_depth_5m.parquet` holds the resting notional within 0.2% of
mid: median **$69.7M**, p10 $48.7M, p90 $99.8M. Walking a book that is uniform
out to 0.2%, an order of size S pays about `20 × (S/depth) / 2` bps:

| order | at p10 depth | at median | at p90 |
|---|---|---|---|
| $1k | 0.000 | 0.000 | 0.000 |
| $100k | 0.021 | 0.014 | 0.010 |
| $1M | 0.205 | 0.143 | 0.100 |
| **$10M** | **2.052** | 1.435 | 1.002 |

**The repo's 2.0bps/side allowance is the cost of a ten-million-dollar order.**
The live book's legs in this morning's cron log are **$877**. At that size the
spread is 0.01bps a side and the impact is zero to three decimal places.

**BTCUSDT's true per-side cost at the size actually traded is the 5.0bps taker
fee plus about 0.01bps. Round trip 10.0bps, not 14.0 — the repo is charging
40% too much on crypto, and all of the excess is a slippage allowance sized for
an order 11,000 times larger than the one it places.**

---

## 2. The pattern, which is the real finding

Every microstructure signal ever measured in this repo lands in the same narrow
band, and every round trip sits just above it:

| hypothesis | measured edge | the bar it died against |
|---|---|---|
| H-021 quarter-hour | 2.67bps | "5x too small to pay for" |
| H-022 absorption | **6.55bps** | 8bps (cheapest maker round trip) |
| H-024 depth imbalance | **7.9bps** | 14bps taker — 0 of 935 cells |
| H-013 perp premium | ~10.9bps | died in the grid |
| H-011 level fade | "real edge" | "too small for 28bps" |
| H-047 participation | 0.53 (std) | 0.82 — 0 of 6 markets |
| **H-049 footprint location** | **≤3.90bps** | **anything** |

Six independent signals, six deaths, one cause. **Signals: 2.7 to 10.9bps.
Round trips: 8 to 14bps.** That is not six coincidences, it is what an
arbitraged market looks like — informed short-horizon flow gets competed down to
roughly the cost of trading on it, which is also why the academic literature
puts order-flow imbalance's predictive content at *seconds to minutes* (Cont,
Kukanov & Stoikov) and why VPIN's apparent power turned out to be mechanical in
trading intensity (Andersen & Bondarenko).

**The implication, and it is the whole reason for the nomination: the remaining
room is on the cost side of the inequality, not the signal side.** Six attempts
to find a bigger signal have failed. Nobody has finished checking whether the
bar itself is right — and section 1d says it is not: **10.0bps, not 14.0**, once
the slippage allowance is sized for the order this project actually places.

**And the counter-caveat, stated up front so nobody reads this as a pace fix.**
H-023 stage 14 priced an entire book from 14bps down to **zero** and it moved
57 expected days to 32. **Free execution buys 33–44% of the days; the 5–14 day
target needs about 85%.** Fixing the cost model can turn a dead signal into a
live one. It cannot make the book fast. Those are different wins and only the
first is on offer.

---

## 3. The families, priced

### Footprint / order flow at price-level resolution
**Edge source:** aggressive flow that meets a passive counterparty with quantity
and no deadline. **Status: DEAD HERE, measured 2026-09-16** (section 1a), on top
of H-006 / H-021 / H-022 which killed the amount axis. The practitioner
literature is candid that it is context, not prediction — *"no tool predicts
price direction reliably"*, *"divergence is informative but not predictive on
its own"*. **Verdict: buy nothing.**

### Liquidity heatmap — resting orders over time (Bookmap-style)
**Edge source:** large resting size marks a level somebody is defending; voids
mark where price travels fast; pulled liquidity marks a spoof.
**What is free:** Binance `bookDepth`, **2024-05-17 → current**, one snapshot a
minute at ±0.2/1/2/3/4/5%, depth and notional. This repo already collects it —
`data/feeds/*_depth_5m.parquet`, 11 coins, 2023-01 → 2026-09.
**What is not free:** per-price-level resting size — the actual heatmap — needs
full L2 reconstruction from the diff-depth stream. Binance publishes no
historical archive of it. Tardis.dev or equivalent, or forward collection.
**Status:** the imbalance reading is **H-024 — real, monotone, beats its null,
stable across years, and 0 of 935 cells across 11 coins clear 14bps; best honest
cell 7.9bps.** The *level* reading (how far price must travel to clear the book,
i.e. a Kyle-λ impact term) is **untested** — see shortlist #2.
**Verdict: the free half is on disk and mostly dead; do not buy the paid half
until #1 and #2 are done.**

### Liquidation heatmaps / stop clusters
**Status: DEAD (H-031)** — a 30m OI collapse with price down scored +26.7bps
gross against +11.8 for a shuffled null and +20.5 for a same-fall control, then
PF@2x **0.924** with no stop and worse with every stop, 10 of 10 coins firing
together in a cascade. **Also undownloadable:** `liquidationSnapshot` has **zero
keys for USDT-M** on Binance's archive (verified today). Coinglass sells the
heatmap and publishes no history. **Verdict: closed twice over.**

### Volume profile / POC / value area
`poc_loc` in section 1a is the single-bar version: 1.10 / 1.16 / 0.41bps, inside
its null at every horizon. The multi-day naked-POC version is untested but sits
inside **"fading an extreme, as a family"**, which has already failed twice on
two definitions (H-005 rolling extreme, H-011 prior day/week extreme).
**Verdict: needs a genuinely new ingredient, per `CLAUDE.md`.**

### The clock, sessions, anchors
**Closed by H-046** — 200 cells, best p = 0.001 alone and **p = 0.130 against
the best-of-200 null**, and the London fix ranks 11th of its own 24 placebo
hours. What would reopen it is **an event list, not a clock.**

---

## 4. The data ledger

| source | on disk | free range | note |
|---|---|---|---|
| BTC aggTrades (ticks) | **117 days** | 2021-05-13 → now | footprint, effective spread, queue. The workhorse |
| `bookDepth` | 11 coins via `depth_5m` | **2024-05-17 → now** | ±0.2–5% bands, 1/min. H-024's feed |
| `bookTicker` (L1 + sizes) | no | 2023-05-16 → **2024-03-30 only** | the true spread; archive discontinued |
| `metrics` (OI, crowd ratios) | 17 coins, 2020-09 → | 2022-01-13 → now | H-006/H-009/H-015 |
| `liquidationSnapshot` | no | **none for USDT-M** | H-031's feed does not exist |
| per-level L2 heatmap | no | **paid only** | Tardis.dev or forward collection |
| Dukascopy FX/metals ticks | on demand | free | bid **and** ask — the only spread series this project has for gold |
| gold order flow | **no, and it cannot be had** | — | `CLAUDE.md`: gold trades naked |

**The asymmetry worth noticing.** The one hypothesis that survived here trades
**gold**, the market with no order-flow data at all. Every hypothesis that died
on cost traded **crypto**, the market with the richest data and the tightest
arbitrage. Footprints and heatmaps are a push toward the rich-data corner. That
is the corner where six signals have already been competed down to the round
trip.

---

## 5. THE NOMINATION — H-049, re-price the cost table for the size traded

**Not a strategy. A correction, in the class that has actually produced keepers
here** (the risk ladder, budget-linear sizing, the H-023 fill study).

**Claim.** `core/markets.py` charges every crypto market a `half_spread` it
labels *assumed* and *"the weakest number in this table"*. It is 2.0bps/side on
BTCUSDT. Measured today: the quoted spread is **0.01bps/side** and the book
impact at the traded size is **zero to three decimals**. The 2.0 is the cost of
a **$10M** order; the live book trades **$877** legs. **Taker round trip
14.0 → 10.0bps.**

**What it is worth, stated honestly.**

* On its own it revives **nothing**. H-024's best honest cell is 7.9bps and
  10.0bps is still above it — 79% of the way instead of 56%.
* **Combined with H-048** — which re-prices the round trip under the limit fill
  H-023 already validated on ticks, taking Binance futures 9.0 → 4.0bps —
  **H-024's 7.9bps cell clears, and clears comfortably.** That is the concrete
  route by which a dead signal becomes a live one, and it needs no data that is
  not already on disk.
* It does **not** touch the pace target (section 2's caveat).
* **It is not a cost-timing rule.** Section 1c killed that: 1.28x dispersion.
  This is a one-off re-pricing of a constant, not a gate that selects bars.

**Stage plan, with the kill criterion written first.**

| stage | what | kills it |
|---|---|---|
| 0 | done today — spread by bounce, impact from the depth feed, both at the traded size | had the measured cost come back near 2.0bps/side, stop here. It came back at 0.01 |
| 1 | the same two measurements on ETH, SOL, XRP, BNB, and back to 2021 | if the measured cost is **within 30% of the assumed** on 3 of 5 coins, the table is fine and the direction closes |
| 2 | re-run H-024's 935 cells and H-047's six markets at the corrected cost, **paired**, so the lift is a difference and not a new fit | if **0 cells cross the bar**, the cost side is exhausted and section 2's pattern is structural rather than fixable |
| 3 | only if stage 2 revives something: the surviving cells through the full kernel with stops, sizing and the prop rules | the usual — a response-test edge is not a strategy |

**The two things most likely to kill it.** (a) The fee dominates and does not
move: 5.0 of BTC's corrected 5.01bps per side is the taker fee, so the entire
remaining lever is H-048's maker path, not this. (b) Position size is only small
while the account is small — the allowance that is 11,000x too big at $877 is
correctly sized at $10M, so this correction has a shelf life measured in account
growth, and the stage-1 code should print the size at which it stops being true.

## 6. Where this leaves gold, which is what is actually traded

H-049 is a **crypto** correction and H-027 is gold-only, so it changes no board
number. The gold cost line is already measured, not assumed — 0.915bps/side from
Dukascopy ticks. Two things in this research do touch gold:

* **Its spread varies 4.5x across the day** — hourly medians run **1.01 to 4.49
  bps**, silver's run **4.16 to 56.18** (`backtests/propfirms/fx_spread_measured.csv`,
  478 and 330 sampled hours). A single average is charged everywhere. **This one
  is a real quoted spread**, measured as ask minus bid on Dukascopy ticks, so
  section 1b's drift error does not apply to it — unlike the crypto perp, a
  retail gold CFD genuinely does widen and narrow through the day.
* **But that is an hour rule, and H-046 closed the clock on FX and metals.**
  Turning "spread is cheap at 14:00 UTC" into a gate re-opens a measured-dead
  axis, and 24 of 25 entry filters on H-027 raised profit factor while lowering
  R per day — which makes it *slower*, and days is the target.

**So: do not build a gold cost gate.** Note the dispersion and leave it.

---

## 7. The shortlist, ranked

| # | hypothesis | data | cost | why this rank |
|---|---|---|---|---|
| **1** | **H-049 — re-price the crypto cost table for the size traded** | **on disk** | half a session | the weakest number in `core/markets.py`, sized for a $10M order against an $877 leg. Stage 0 run today |
| 2 | **Depth LEVEL as a travel conditioner** — not H-024's imbalance but the Kyle-λ term: does a break into a thin book travel further? A **magnitude** claim, so it belongs in sizing, not gating | `depth_5m`, on disk, 11 coins 2023→ | one session | untested; the one overlay class that has produced keepers. **Gold has no book, so it cannot help the traded market** |
| 3 | An **event list** for H-046's reopening — CPI, FOMC, NFP with a known flow attached, not a clock | free calendars | one session | H-046 names this itself as the only thing that reopens it |
| 4 | Per-level L2 heatmap | **paid / forward collection** | money + months | do not spend until 1 and 2 report |
| — | ~~footprint / order flow location~~ | — | — | **killed 2026-09-16**, section 1a |
| — | ~~liquidation clusters~~ | — | — | **H-031**, and no free USDT-M data |
| — | ~~depth imbalance~~ | — | — | **H-024**, 0 of 935 cells |
| — | ~~delta / VPIN / aggression~~ | — | — | **H-006, H-021, H-022** + Andersen–Bondarenko |
| — | ~~cost-timing / trade only the cheap bars~~ | — | — | **killed 2026-09-16**, section 1c — 1.28x dispersion, nothing to select on |

---

## 8. What would change any of this

* **The footprint kill** would reopen if a location feature were measured above
  14bps on a *different* regime or market. The scout runs on any aggTrades
  archive; ETH and SOL are one download away.
* **H-049** closes at stage 1 if the measured cost comes back within 30% of the
  assumed on 3 of 5 coins, and expires on its own as the account grows — the
  allowance it calls wrong at $877 is right at $10M.
* **Section 2's pattern** — the 2.7–10.9bps band — is the load-bearing claim in
  this document. One microstructure signal measured cleanly above 14bps on a
  full sample, surviving its null, would break it. Six have tried.

## Files

```
strategies/footprint/stage1_location.py    the footprint scout
strategies/costmap/stage0_dispersion.py    dispersion, predictability, edge-vs-cost
backtests/footprint/stage1_location_15min.csv
backtests/footprint/stage1_location_5min.csv
backtests/footprint/BTCUSDT_footprint_{5min,15min}.parquet
backtests/footprint/BTCUSDT_espread_15min.parquet   (bounce estimator)
```

**Sources for the outside literature cited above:**
[Cont, Kukanov & Stoikov — the price impact of order book events](https://arxiv.org/pdf/1011.6402) ·
[Cross-impact of order flow imbalance in equity markets](https://www.tandfonline.com/doi/full/10.1080/14697688.2023.2236159) ·
[VPIN, liquidity and return volatility](https://www.sciencedirect.com/science/article/abs/pii/S1044028318302679) ·
[Binance public data archive](https://data.binance.vision/) ·
[Bookmap — heatmap and hidden liquidity](https://bookmap.com/blog/advanced-order-flow-trading-spotting-hidden-liquidity-iceberg-orders) ·
[NinjaTrader — footprint charts](https://ninjatrader.com/futures/blogs/footprint-charts-guide/) ·
[OrderFlowLabs — reading delta, bid/ask and absorption](https://orderflowlabs.com/blogs/theblog/footprint-chart-guide)
