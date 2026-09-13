# The next hypothesis — no VWAP, and a data class this repo has never held

Kris, 2026-09-13: *"research on what we could test next but it should be not
vwap, it must be completely different data."*

**Nothing here is built. Kris picks.** Feasibility was checked FIRST this time,
because the most attractive idea died on it and would otherwise have been the
recommendation.

---

## The constraint that decides everything

Every feed this repo holds is **backward-looking and perp-only**: open interest,
taker ratio, depth, funding, perp-spot premium. All of them say what already
happened on one book. The standing pattern in `CLAUDE.md` — every leg that ever
worked came from a data feed, not a price pattern — is still unbeaten, and 12+
price hypotheses have died against it.

So a new candidate has to be a FEED, and it has to be one we can actually get:
**three years minimum** (`run_hypothesis.YEARS`), free, and with enough
resolution to decide inside a 5–14 day evaluation.

---

## KILLED ON FEASIBILITY, before proposing — options skew

This was going to be the recommendation. **It is not obtainable.**

The reasoning was good: H-025 (DVOL) is the only live survivor here and the only
forward-looking feed — somebody quoted those options and is short the risk. But
DVOL is a single 30-day number. The *shape* of the smile — 25-delta risk
reversal, term structure, put/call — has **0 occurrences in `STRATEGY_LOG.md`**
and would be genuinely new.

| route | verdict |
|---|---|
| Deribit public API | works with no key, but **collects forward from today only**. Useless for a 3-year walk-forward. |
| `public/get_historical_volatility` | **realised** vol, not skew. Wrong object. |
| CryptoDataDownload | options chains are **paid** (Plus tier). Free tier is DVOL OHLC, which we already have. |
| Tardis.dev | full history from 2019-03-30, **paid**. |

**No free 3-year skew history exists.** Recorded here so it is not re-proposed
in three weeks. It becomes available the day someone pays for Tardis, and not
before.

---

## 1. H-034 — THE TERM STRUCTURE OF LEVERAGE  ← the pick

### Mechanism, before any result

Binance lists **dated quarterly futures** alongside the perpetual. A dated
contract must converge to spot on a known date, by arbitrage. Its premium over
spot is therefore not sentiment — it is **the market's term price of leverage**,
quoted out to nine months, with a hard settlement anchor.

Nothing in this repo has ever had a hard anchor. Every feed we hold is a level
with no reason to mean-revert to anything in particular. This one *must* go to
zero on a specific day, and the whole question is what the path there says.

**Who is on the other side, named:** cash-and-carry arbitrageurs. When the
annualised basis is rich they sell the future and buy spot, and are paid to
compress it. When it collapses toward zero or inverts, that trade is being
unwound — which is a deleveraging signal from the one participant who is
mechanically forced to act rather than choosing to.

### What was verified today, not assumed

| check | result |
|---|---|
| coverage | `BTCUSDT_210326` → `BTCUSDT_261225`, **22 of 22 quarterly cycles present, 0 missing**, 2021-03 → 2026-06 |
| free | yes — `data.binance.vision`, same archive `core/binance_metrics.py` already uses |
| convergence | basis decays **153.2 → 137.0 → 89.8 → 29.9 bps** at 102/72/41/13 days to expiry; **8.6 bps in the final week** |
| the signal varies | annualised **5.46% → 7.06% → 7.70% → 7.56%** over one contract's life; range −0.75% to +29.3% |
| two points, not one | front and back contracts overlap — curve slope (Dec−Sep) median **182.9 bps** |

### THE TEST THAT MATTERED, and it passed

H-004 (funding) and H-013 (perp-spot premium) are both dead. If the dated basis
were the same quantity, this would be a corpse re-proposed.

| | annualised basis | annualised funding |
|---|---|---|
| median | 6.89% | 6.15% |
| stdev | **1.76** | **4.10** |
| min | −0.75% | −5.83% |
| max | +29.30% | +10.95% |

Correlation between the two, 2,791 paired hourly observations:

| | |
|---|---|
| levels | **0.306** |
| changes | **0.004** |

**Levels correlate 0.31; changes correlate 0.004.** They are different objects.
Funding is the instantaneous, clamped, 8-hourly cost of perp leverage and it is
noisy. The dated basis is the term price of the same thing, and it is less than
half as volatile. H-004 tested the noisy one.

### The liquidity finding that shapes the design

The dated contract does **$16.3M a day against the perp's $16.57B** — about one
thousandth. **It must never be traded.** But it prints ~19,600 trades a day,
roughly 13 a minute, so its hourly close is a real price rather than a stale
quote.

So the design is the repo's own winning shape: **read the term structure, trade
the perp.** Cost stays the perp's ~14bps that every number here is already
priced at. This is a GATE or an entry trigger on BTCUSDT/ETHUSDT perp, exactly
as H-015 and H-025 are gates.

### The three readings, and they are different hypotheses

1. **Level** — is leverage expensive or cheap right now.
2. **Slope** — front vs back contract: is the curve steepening or flattening.
   Steepening is leverage demand arriving; flattening is it leaving.
3. **Shock** — a fast collapse in annualised basis. The cash-and-carry unwind.
   This is the one with the sharpest mechanism and the fewest events.

### How it dies, named in advance

* **Pace.** The basis is smooth (stdev 1.76%). If a threshold crossing fires a
  handful of times a year, it fails the 5–14 day target the way H-032 did. **This
  is the most likely death and it is testable first, in an hour.**
* **It is a carry signal, and carry is slow.** H-006 died on risk shape doing
  something similar; a slow drift cannot pay 14bps in four hours.
* **Overlap windows are short.** The back contract lists ~3 months before the
  front expires, so the *slope* reading has far less history than the *level*.

### Cost

**Zero downloads beyond one collector.** The archive path is the same one
`binance_metrics.py` already walks. `core/probe.py` — gate 2, event vs
shuffled-date null — kills or advances it in an hour without a kernel.

---

## 2. H-035 — ON-CHAIN EXCHANGE FLOWS  (weak, and here is why)

Coins moving onto an exchange are being positioned to sell; coins leaving are
being withdrawn to hold. That is a genuinely different data class — the only
candidate here that is not derived from an order book at all.

**Free and verified working:** CoinMetrics Community API, **no key**,
`FlowInExNtv` / `FlowOutExNtv` / `FlowInExUSD` / `FlowOutExUSD` for BTC and ETH.
Netflow is In − Out (`FlowNetExNtv` itself is not served free).

**Three things demote it, all verified today:**

1. **Daily only.** `frequency=1h` returns `forbidden: not available with
   supplied credentials`. One observation a day.
2. **Published ~24h late.** The 2026-09-10 bar carried a status-time of
   2026-09-11T01:27.
3. **Provisional.** Every value returns `"status":"flash"`. It is revised. A
   backtest reading final values is **look-ahead** — the exact bug class this
   repo has been burned by three times.

Daily, lagged a day, and revised is why **H-032 (spot ETF flows) was already
rejected**. This has the same shape plus a revision trap. Worth one afternoon
through `probe.py` only if H-034 dies.

---

## 3. Not proposed, and why

* **Hyperliquid account-level flow** — the best mechanism nobody here can
  express, and 13 months of history cannot be walk-forwarded. Unchanged from
  2026-09-10.
* **Anything price-only.** Seventeen have died. Sub-hour and the volume clock
  died this week.
* **More VWAP.** The entry axis is closed by measurement and tier 1 of
  `VWAP_BACKLOG.md` is now fully closed.

---

## The recommendation

**H-034, and test the PACE before the edge.** It is the only candidate with a
hard arbitrage anchor, it is the only genuinely new feed obtainable free with
five years of history, it passed the one test that would have made it a
re-proposal of a dead thing, and its most likely cause of death is known in
advance and costs an hour to check.

Run order if picked:

1. Build the basis series from the archive — front-contract annualised basis,
   hourly, 2021-03 → 2026-08, on BTCUSDT and ETHUSDT.
2. **Count the events first.** If a sensible threshold fires fewer than ~40 times
   a year, stop — it cannot resolve an evaluation and nothing else matters.
3. Only then `probe.py`: forward return after the event vs the same statistic on
   randomly shifted dates.
4. Kill criterion written down before step 3, not after.

**Kris picks. Nothing is built until then.**
