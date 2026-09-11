# The next hypothesis — top 3, ranked

Written 2026-09-10, after five candidates died in one session (H-028, H-029, the
dollar/gold lead-lag and the LBMA fix; see `RESEARCH_2026-09-10_REOPEN.md`).

**The thing that should decide this.** Every one of today's five deaths was a
**price pattern**, and that is now the seventeenth or so. The standing pattern in
`CLAUDE.md` has never been contradicted:

> every leg that ever worked came from a data feed — funding, open interest,
> taker delta, long/short ratio — not from a price pattern.

All three options below are therefore feed-driven. Option 1 was measured while
writing this file.

---

## 1. H-031 — LIQUIDATION-PRESSURE FADE  ← the pick

> **DEAD 2026-09-11** on its pre-registered kill criterion — PF@2x 0.667–0.924
> across eight stop arms, R/day negative on all of them, every stop worse than
> none. The feed adds ~15bps over a random long against a 28bps round trip.
> H-006-R (#3) closes with it. `strategies/liqflush/notes.md`.

**The mechanism.** A leveraged position that gets liquidated is closed by an
exchange engine at market, regardless of price. That seller is not expressing a
view: they are **forced**. Forced flow overshoots and the overshoot is paid back
by whoever supplies liquidity into it. The payer is nameable and so is the
victim.

**Why this is not the dead "fade an extreme" family.** H-005 and H-011 faded a
price extreme with **no information about why the price moved**. This uses the OI
feed to separate a fall caused by leverage unwinding from a fall caused by
information — and that distinction is the entire hypothesis. Binance's per-event
liquidation dump is gone (verified: zero files), so the flush is reconstructed
from OI collapse + adverse price, both already in `data/feeds/*_metrics_5m`.

**MEASURED TODAY.** Ten coins, six years of 5m data. A flush is the bottom 2% of
30-minute OI change with price down over the same window. The control is the
critical part: **price down by the same amount but OI stable.**

| forward return | FLUSH | control | difference |
|---|---|---|---|
| +1h | **+8.4 bps** | −0.2 | +8.6 |
| +4h | **+17.9 bps** | −1.4 | +19.3 |
| **+24h** | **+28.0 bps** | **−6.1** | **+34.1** |

**Flush beats control on 10 of 10 coins.** Per coin at 24h:

| | BTC | ETH | SOL | BNB | XRP | ADA | DOGE | LINK | LTC | DOT |
|---|---|---|---|---|---|---|---|---|---|---|
| flush | +46.1 | +4.0 | +42.3 | +11.6 | +59.0 | +48.0 | +56.0 | +0.9 | −0.3 | +12.0 |
| t | +9.11 | +0.73 | +4.23 | +2.20 | +8.26 | +5.66 | +6.83 | +0.11 | −0.05 | +1.60 |
| control | +8.7 | −7.4 | −11.3 | +1.2 | +0.8 | −11.5 | −9.0 | −3.2 | −5.5 | −24.0 |

Price falling *without* an OI collapse drifts **further down** (−6.1 bps mean).
Price falling *with* one reverts **+28.0**. The feed is doing the work, not the
price move — which is exactly the split that killed the earlier fade hypotheses
and is present here.

The response is also **monotone in horizon** (+8.4 → +17.9 → +28.0), and 28 bps
is 2x the 14 bps crypto round trip rather than inside it.

**What is NOT done, and none of it is optional.** No block-shuffle null. No
walk-forward. No cost ladder at 1x/2x/3x. No noise band. ~5–6k events per coin
from a 2% tail, so the selection is a real multiple-comparison surface (the
threshold, the window, the horizon were all picked by hand today).

**The way it most likely dies, named in advance:** *risk shape, exactly like
H-006.* A 24h hold with no stop is how H-006 drew 63.5R against H-002's 3.8R and
needed 548 days. H-006's signal was never what failed. **So the drawdown study
comes before the return study**, and the kill criterion is set now: if maxDD in R
does not come down under budget-linear sizing plus a stop, it dies and stays
dead.

**Cost:** zero downloads. Everything is on disk. Decidable in a day.

---

## 2. H-030 — A FEED LAYER FOR GOLD

> **DEAD 2026-09-11 (COT).** Eight pre-registered COT gates on the traded rule;
> every one is slower than no gate (26.3–64.1 days vs 21.7). Refusing the
> crowded side cuts PF@2x 2.872 → 1.766. `strategies/goldfeed/notes.md`.

**Why it ranks second despite serving the only survivor.** Gold is the one market
left and it **trades naked** — every file in `data/feeds/` is a Binance crypto
symbol, and `data/dukascopy_raw/XAUUSD` holds one-minute BID candles, so there is
no bid/ask volume on disk at all. H-027 is a pure price pattern on an
instrument with no feed, which is the least favourable combination this repo's
own history describes.

Two free sources: **CFTC COT** positioning (weekly, published Friday for Tuesday,
so 3 days stale) and **CME daily volume/OI** on GC.

**Honest expectation:** too slow to trigger an entry, possibly fast enough to
**gate** one. That is a modest claim and it should stay modest — the 25-filter
study established that gates on H-027 raise profit factor and lower R/day, which
makes the evaluation *slower*, and the one survivor lost to its own shuffled
control.

**Why it still ranks here:** it is the only route to putting a feed under the
strategy we actually trade, and it is the one backlog item whose value does not
depend on finding a new edge.

**Cost:** needs a download. Half a day.

---

## 3. H-006-R — CROWD POSITIONING, RE-OPENED ON A CHANGED RISK FRAMEWORK

Already written up as Candidate B in `SECOND_HYPOTHESIS.md`; repeated here so
the ranking is complete.

The long/short **account** ratio ranks forward returns monotonically (+25.0 /
+21.8 / +13.5 / −0.9 / −13.2 bps by quintile), holds the same sign in 6 of 7
years, beats every block-shuffle null, and scored PF 1.227 at 2x out of sample on
BTC. **It was closed on risk shape, not on signal.** Two things changed since:
budget-linear sizing (cut blown accounts 29.5% → 16.9% on H-027) and the finding
that a stop measured in many sigma makes the round trip 0.22% of a full stop.

**Ranked third because it shares H-031's failure mode without H-031's fresh
evidence** — and because the repo already tried adding a stop and reverted it,
the fold selector picking *no stop* in 37 of 52 folds. If H-031's drawdown study
works, it transfers here; if it does not, this dies too. **Do H-031 first: the
drawdown question is common to both, and H-031 answers it on better numbers.**

---

## Not in the top 3, and why

* **H-032 spot ETF flows** — strong published effect (53bps per $100M) but daily,
  published after the US close, history only from 2024. Fails the pace
  constraint, not the edge test.
* **H-033 Hyperliquid account-level flow** — the one mechanism nothing else here
  can express ("follow the accounts that actually win"), but 13 months of history
  cannot be walk-forwarded.
* **Anything price-only.** Seventeen have died. Today five died in one session.

## The recommendation

**H-031, and run the drawdown study before the return study.** It is the only one
of the three with new evidence measured today, it needs no download, its control
is already in hand, and its most likely cause of death is known in advance and
testable first. **Kris picks. Nothing is built until then.**

---

# BACKLOG — the SMC surface that has never been tested here

Added 2026-09-10 at Kris's request: *"what about standard strategies like Order
flow SMC, EMAS, etc — i see we dont choose these paths?"*

**We did choose most of them.** They are the dead list. What follows is the
part that genuinely has not been tested, kept here so it is not re-proposed from
memory and not forgotten either.

## First, what IS already tested, so nobody re-runs it

| family | tested as | outcome |
|---|---|---|
| EMA / MA cross | H-003, 284k backtests, 9 markets, 4 exits | real median PF **0.705** vs phase-randomised **0.757** — worse than noise |
| MA ribbon (20 MAs) | H-016 | **alive**, beats its null 13 of 16 cells vs 3.0 — and **260 expected days** |
| MA position / slope / counter-trend as a filter | H-027 25-filter study | all lower R/day; the survivor lost to its own shuffled control |
| Book depth imbalance (order flow) | H-024, 11 coins | real, monotone, beats its null — **0 of 935 cells clear 14bps** |
| Crowd long/short ratio (order flow) | H-006 | real, PF 1.227 at 2x OOS — killed on **risk shape**, 63.5R drawdown |
| Order flow on **gold** | — | **not testable.** No tick data on disk; gold trades naked |
| Liquidity sweep / stop hunt | H-005, 541k backtests, 12 markets | real clears PF 1.20 on 1,702 configs, the null clears **19,062** |
| Power of Three / AMD | H-026 | sign **flips** across BTC/ETH/SOL; 3 of 24 cells beat a permutation null |
| Prior day/week highs & lows | H-011 | real, beats its null at every cost level — **too small for 28bps** |
| Breakout + retest | BTC 3m-4h, every filter family | best robust PF ~0.85 |

## The untested list

Verified by grep on 2026-09-10 — **zero occurrences anywhere in this repo**:

1. **Fair value gaps (FVG)** — a three-candle imbalance; price returns to fill it.
2. **Order blocks** — the last opposing candle before a displacement move.
3. **CHoCH / BOS** — change of character and break of structure as a trend-state
   machine over swing highs and lows.
4. **Killzones** — London and New York sub-session windows as an entry filter.
5. **Premium / discount arrays** — position within a dealing range, i.e. only buy
   the lower half of a leg.

## Why these are NOT ranked above H-031 today

Three reasons, and they should be argued with rather than ignored.

* **The load-bearing primitive already failed.** Liquidity sweeps (H-005) and AMD
  (H-026) *are* the mechanism underneath order blocks and FVGs. If the sweep does
  not pay, a zone drawn around the sweep is unlikely to.
* **"Price returns to a zone" is a family with a bad record here.** It is the same
  claim as H-010 and as the fibonacci zones in the 25-filter study, which
  **sign-flipped across timeframes** (fib100 beyond .618: −25.7 days on 1h,
  **+344.6** on 4h) — H-026's signature for no effect.
* **Killzones are closed by measurement already.** Every one of six session
  windows tested on H-027 was **slower on both timeframes**. A killzone is a
  session window with a different name.

And a methodological warning that applies to all five: **they are defined loosely
enough that a backtest can almost always be made to look good.** Which candle
starts the order block, how deep a mitigation counts, whether a wick or a body
breaks structure — every one of those is a free parameter. That flexibility is
the thing this repo's null machinery exists to price. **Any test of these must
fix every definition in writing BEFORE the first backtest**, and must be run
against a paired null and the noise band, or it is worthless.

## The one door that IS genuinely open

`CLAUDE.md` already carries this caveat on H-026 and it has never been acted on:

> Caveat: tested with a fixed hold to the session close and **no stop and no
> target** — a stop-and-target version is untested and Kris trades one.

That is the honest SMC path: it **re-opens a specific tested thing on a specified
change**, rather than adding a new name to the pile. If an SMC hypothesis is
wanted, run that one first — it inherits H-026's event definitions, its ~1,500
events per coin, and its permutation null, so only the exit changes.

## If these are run anyway, the order to run them in

1. **H-026 with a stop and target** — re-opens existing work, definitions already
   fixed, null already built.
2. **FVG** — the only one of the five with a mechanical, unambiguous definition
   (a three-candle gap is either there or it is not), so it is the least
   corruptible by researcher choice.
3. **Premium / discount** — testable as a pure filter on H-027's existing entries,
   which makes it a one-day paired-lift study, not a new strategy.
4. **Order blocks**, **CHoCH/BOS** — most free parameters, worst prior, do last.
5. **Killzones** — do not run. Already closed by the six-window session study.
