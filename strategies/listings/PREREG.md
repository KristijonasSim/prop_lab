# H-047 — the Binance listing effect. PRE-REGISTRATION, before any return is read.

2026-09-17. Kris's second pick: *"2. Then lets talk about new binance listings"*.

## The mechanism, before any number

A new listing puts a token in front of the largest retail order flow in crypto
with a float that has not yet distributed. **Who is on the other side:** early
holders, the team, and the market maker contracted to provide liquidity, all of
whom are structurally sellers into that attention. The effect being tested is
whether the attention arrives faster than the supply.

**The reason to doubt it before starting:** this is the single most widely known
pattern in crypto. Anything left in it after fees is what survived thousands of
people trying.

## Gate 1 — SURVIVORSHIP. Answered first, because it decides if the sample is real.

`exchangeInfo` returns only what trades today, and a new listing is exactly the
population most likely to be delisted. `docs/NEW_EDGES.md` called this the
serious flaw in the idea. **Measured, it is much smaller than claimed, and the
claim is corrected here rather than quietly dropped.**

`data.binance.vision` archives every symbol that ever traded, dead ones included.

| | |
|---|---|
| USDT pairs ever archived | **733** |
| still trading | 481 |
| **delisted** | **252 (34.4%)** |

So a third of all USDT pairs in history are gone. **But death takes years**, and
the window this project is allowed to test is three:

| listing year | all | survivors | died |
|---|---|---|---|
| 2021 | 127 | 62 | **65 (51%)** |
| 2022 | 41 | 23 | 18 (44%) |
| 2023 | 58 | 36 | 22 (38%) |
| 2024 | 63 | 58 | 5 (8%) |
| 2025 | 102 | 100 | 2 (2%) |
| 2026 | 92 | 92 | 0 |

**Listed since 2023-08: 278 events, of which 15 (5.4%) have since been
delisted.** At the hold this hypothesis proposes — hours, not years — a
delisting two years later cannot touch the trade. **Survivorship is close to a
non-issue here and my earlier framing of it as the main flaw was wrong.**

The honest population is still the 733-symbol archive, not the 481 survivors,
and that is what the study uses.

## Gate 2 — THE FEE TEST, and it decides this hypothesis

Binance spot taker is **10 bps a side, 20 bps round trip** with no BNB discount.
A freshly listed token is thinner than anything in `core/markets.py`, so its
spread is worse than BTC's and is **not yet measured**.

**Bar fixed now: the MEDIAN gross return must exceed 20 bps at some horizon.**

**Median, and not mean, and this is the whole methodological point.** Listing
returns are violently skewed — a handful of tokens go up 10x and drag any
average above any bar you care to set. A mean-based pass here would be the same
mistake as quoting a strategy off its three best trades. **Report the median,
the quartiles and the share of events that are positive.**

## The arms, fixed now

Entry at the **close of the first completed hour** of trading — never the first
print, which no retail order reaches. Horizons: **+1h, +4h, +12h, +24h, +72h**.
Both directions are reported; the mechanism argues long, and a negative result
at every horizon is a short hypothesis that has to be tested on its own terms.

**5 horizons x 1 entry = 5 cells.** Nothing else is searched. No filters on
market cap, category, or sector — those are the next pre-registration, not this
one.

## Kill criteria, fixed now

1. **Median gross below 20 bps at every horizon.** Dead.
2. **Positive only in the mean.** Dead, and recorded as the skew trap.
3. **Sign flips across horizons** with no monotone shape — the signature
   recorded four times in `CLAUDE.md`.
4. **The 2026 cohort disagrees with the 2024 cohort.** A pattern this famous
   decaying over the sample is the expected outcome, and a result that only
   exists in the oldest year is not tradeable now.

## What would make a pass a false one

* **The first hour is not tradeable at the printed price.** Klines record where
  trades happened, not what a retail market order would have paid. Any positive
  result needs a spread measurement from `aggTrades` before it is believed.
* **Listing announcements move price before the listing.** The tradeable event
  may be the announcement, not the listing, and they are different timestamps.

---

# RESULT — 2026-09-17. Dead on the long side, and it is not the market.

`backtests/listings/listing_event.json`, `listing_events.csv`.
**278 listings since 2023-08**, honest population from the archive, 15 of them
already delisted and kept in.

## Gate 2, against the bar fixed before the run

Entry at the close of the first completed hour. Gross, in basis points.

| horizon | n | **median** | mean | q25 | q75 | positive | vs 20 bps |
|---|---|---|---|---|---|---|---|
| 1h | 278 | **−39.8** | −19.0 | −377 | +193 | 41.0% | fail |
| 4h | 278 | **−78.9** | −53.3 | −682 | +307 | 42.4% | fail |
| 12h | 269 | **−180.8** | −163.4 | −1080 | +202 | 39.4% | fail |
| 24h | 264 | **−313.1** | −298.5 | −1404 | +239 | 35.6% | fail |
| 72h | 247 | **−847.6** | −426.1 | −2110 | +349 | 35.2% | fail |

**Negative at every horizon, monotonically worse with time, and only a third of
listings are positive at all.** Kill criterion 1 is met on the first line.

**The skew trap did not even get a chance to matter.** The pre-registration
warned that a few 10x tokens would drag the mean over any bar. Here the **mean
is negative too**, so this fails on both statistics rather than on the choice
between them. The warning stands for the next study; it was not load-bearing
here.

## The control — and it is what makes this conclusive

A falling number over 2023–2026 could just be a falling market. It is not. BTC
over the identical hours from each listing:

| horizon | listings | BTC | **excess** |
|---|---|---|---|
| 1h | −39.8 | −0.6 | **−39.2** |
| 4h | −78.9 | +2.2 | **−81.2** |
| 12h | −180.8 | +7.9 | **−188.7** |
| 24h | −313.1 | −18.9 | **−294.1** |
| 72h | −847.6 | −28.3 | **−819.3** |

**BTC was flat and the listings fell.** Essentially the entire move is excess.
New listings underperform the market from their first hour, and the effect grows
for three days.

## Every year agrees on the part that matters

| listing year | n | r1 | r4 | r12 | r24 | r72 |
|---|---|---|---|---|---|---|
| 2023 | 21 | +74.6 | −63.4 | +57.1 | −124.1 | −1059.5 |
| 2024 | 63 | −119.5 | +8.1 | −193.0 | −231.0 | −596.8 |
| 2025 | 102 | −34.1 | −171.6 | −588.3 | −782.1 | −1627.6 |
| 2026 | 92 | −41.7 | −53.8 | −98.7 | −160.7 | −184.1 |

The short horizons flip sign between years — kill criterion 3, and exactly the
signature this repo has now recorded five times. **The 72h column does not
flip:** negative in all four years. That is the only stable thing in the table
and it points the wrong way for a buyer.

## The entry price is a fiction, and this would sink it even if the sign were right

**The first hour's high/low range has a median of 9,098 bps — 91% — and a 75th
percentile of 40,000 bps, 400%.** A kline records where trades happened, not
what a market order pays. At that dispersion the difference between the printed
close and a real fill is larger than every effect in the table above.

## The short side, reported because the pre-registration required it

The mirror of −847.6 bps at 72h is **+847.6 gross**, which clears the 20 bps bar
by forty times. It is not a strategy:

* **You cannot short a token on its listing day.** There is no borrow and no
  perpetual; Binance lists futures for a new token weeks to months later, by
  which time this is a different event.
* **The risk shape is H-006's, and worse.** q75 is +349 bps at 72h, so a quarter
  of these run hard against a short, with no bound on the loss. H-006 was closed
  for exactly this and its drawdown was 63.5R on a *bounded* signal.
* **The fill problem above applies identically**, and to the side that gets hurt
  by it.

**Recorded as a real, large, untradeable effect** — the same category as H-034's
dated futures, which was a feed and never a trade.

## Verdict

**H-047 is dead as proposed (buy the listing).** The measurement is unusually
clean: 278 events, honest population, a control that isolates the effect from
the market, and agreement across four years on the only horizon that does not
flip.

**Cost to reach this: about twenty minutes**, because gate 2 ran before anything
else. That ordering came from H-043 and has now saved two days in four attempts.
