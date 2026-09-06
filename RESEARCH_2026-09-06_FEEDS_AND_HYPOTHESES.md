# Deep research — data feeds and the next ten hypotheses

2026-09-06. Commissioned by Kris: find the best feeds and the best hypotheses,
rank ten, build the top three.

Everything marked **VERIFIED** was checked against the live source today, not
taken from a search result.

---

## 0. What today's engine fix did to the ranking

The look-ahead fix landed before this research started, and it changes what is
worth chasing.

| symbol | walk-forward cells clearing PF>=1.20 @2x | best PF @2x |
|---|---|---|
| BTCUSDT | **11 -> 0** | **2.305 -> 0.992** |
| XAUUSD | 3 -> 11 | 1.461 -> 1.762 |
| EURUSD | 2 -> 3 | 1.289 -> 1.273 |
| every other FX | 0 -> 0 | < 1.05 |

The wide crypto rebuild agrees: on the fixed engine the H-017 legs are printing
PF@2x of 0.735 (LINK 2h), 0.813 (SOL 30m), 0.839 (BTC 30m), 0.948 (DOT 15m),
0.972 (ETH 30m). **Not one clears.**

Three consequences for what to research:

1. **The crypto price-pattern book is gone**, not weakened. Ten dead price
   hypotheses have become eleven. There is now no honest case for another price
   geometry idea on crypto.
2. **Gold is the only thing standing**, and it has no feed layer at all. Every
   feed this project has ever built is a Binance crypto feed.
3. The standing pattern is now much stronger than it was: **every leg that ever
   worked came from a data feed; every leg that came from price has died.** The
   ranking below weights that above everything else.

---

## 1. Feed inventory — VERIFIED against the sources today

### 1a. Binance USD-M public archive (`data.binance.vision`), free, no key

I enumerated the bucket with paginated `list-type=2` calls rather than trusting
documentation. Exact counts and ranges:

| dataset | coverage | size | used here? |
|---|---|---|---|
| **`bookDepth`** | **2023-01-01 -> 2026-09-05, 1341 days** | ~550 KB/coin-day | **NO — the one genuinely new feed** |
| `premiumIndexKlines` | 2019-12-24 -> 2026-09-05, 2442 days | tiny | yes — `core/basis_data.py`, tested as H-013, **dead** |
| `fundingRate` (monthly) | 2020-01 -> 2026-08, 80 files | tiny | yes — `core/binance_metrics.py:funding` |
| `metrics` | 2020-09-01 -> 2026-09-05, 2196 days | small | yes — H-006/H-009/H-017 |
| `aggTrades` | 2019 -> 2026, 2441 days | ~1.3 GB/coin-month | yes — H-023 queue study |
| `bookTicker` | **2023-05-16 -> 2024-03-30 only** | large | no — series stopped |
| `liquidationSnapshot` | **does not exist for USD-M** | — | — |

**A correction I made mid-research.** My first draft ranked the perp premium
second and called it unused. It is not. `core/basis_data.py` has downloaded it
for all eleven coins since 2026-09-02, and H-013 tested it to destruction the
same day: the stage-2 grid cleared PF 1.20 at 2x on **3 of 2,112** configs while
the null cleared 2.0 per seed and the **null's best (1.280) beat the real best
(1.245)**; as a second gate on H-009 it halved R/day and cut return/drawdown from
37.3 to 30.1. Re-proposing it would have broken this project's own rule. The
ranking below is the corrected one. I also had to restore three premium parquets
from git — my duplicate downloader had appended a second set of columns to them.

`bookDepth` and `premiumIndexKlines` were confirmed present for all eleven coins
the metrics archive covers: BTC, ETH, SOL, BNB, XRP, DOGE, ADA, AVAX, LINK, DOT,
LTC — 1339-1342 days each, no gaps worth naming.

**`bookDepth` decoded** (downloaded 2026-09-01 BTCUSDT and read it):

```
columns    timestamp, percentage, depth, notional
cadence    every ~30 seconds -> 2,880 snapshots/day
levels     +/- 0.2, 1, 2, 3, 4, 5 percent from mid
sides      negative percentage = bids, positive = asks
cumulative CHECKED, not assumed: bid side reads 6,391 / 8,967 / 10,267 base
           at 3 / 4 / 5 percent on 2026-09-01
```

Typical BTCUSDT book on that day: **$81M resting within +/-0.2%**, $1.43bn within
+/-5%. Imbalance at +/-0.2% has daily std 0.10 and swings -0.26 to +0.36.

**`premiumIndexKlines` decoded**: OHLC of the perp's premium over the index as a
fraction. `-0.00045` = perp 4.5bps below index. 5m bars, and it works as far back
as **2020-03-01**, tested directly. Already in the repo and already dead as a
standalone signal — see the correction above.

**`liquidationSnapshot` is gone.** The path returns zero files for USD-M
BTCUSDT, and `um/daily/` contains only `aggTrades, bookDepth, bookTicker,
indexPriceKlines, klines, markPriceKlines, metrics, premiumIndexKlines, trades`.
Search results and third-party write-ups agree Binance discontinued the per-event
dumps. Historical liquidation microstructure is not obtainable free.

### 1b. Deribit — free, no authentication. VERIFIED with a live call

`GET /api/v2/public/get_volatility_index_data?currency=BTC&resolution=3600`
returns DVOL OHLC. Sample from the call: `[1784401200000, 35.79, 35.83, 35.73,
35.78]`. History runs from 2021-04. DVOL is the crypto VIX — 30-day implied vol
off the whole option smile. Free, hourly, and this project has no volatility
feed of any kind.

### 1c. Hyperliquid — unique, but expensive and short

- Official `s3://hyperliquid-archive` (L2 books, asset contexts) and
  `s3://hl-mainnet-node-data/node_fills_by_block` — both **requester-pays**, and
  fills alone are 0.8-1.0 GiB per day.
- Free mirrors exist: SonarX (L2 top-20, CC0, HIP-3 markets) and Hydromancer
  Reservoir (all fills, 1s OHLCV, daily account snapshots, 1-minute 20-level
  books) — Reservoir is also requester-pays for egress, no subscription.
- **Crypto perps only from August 2025** — thirteen months. Too short to
  walk-forward the way everything else here is walk-forwarded.
- Price discovery runs the wrong way for us: Binance **leads** Hyperliquid by
  roughly 700ms, because HL matching waits on ~200ms block finality. That is an
  HFT edge, not a cTrader-prop edge.

What is genuinely unique: HL publishes **account-level fills and positions**.
Nowhere else can you see who is winning. That is a real dataset, badly matched to
this project's horizon and history requirements.

### 1d. Gold and FX — thin, and that is the finding

Gold is now the only surviving market and it has the worst feed coverage.

- **CFTC COT**: weekly, free, published Friday for Tuesday's positions. Three
  days stale on arrival. Usable as a slow gate, never as a trigger.
- **CME daily volume and open interest** for GC/SI: free on cmegroup.com, daily.
- No free intraday order-flow equivalent to the Binance metrics feed exists for
  spot gold. The venue is fragmented and OTC.

### 1e. Bitcoin spot ETF flows

Free daily series: TFTC's tracker publishes the full history as open JSON
(CC BY 4.0); Farside Investors tabulates per-fund. A 2026 SSRN study (Lim)
reports daily ETF flows explain **21% of daily return variation** and predict
next-day returns, with **$100M of net flow ~ 53bps of same-day return**, over 313
days from Jan 2024. Daily frequency, published after the US close, history begins
2024. One trade a day at best.

### 1f. Paid, priced for completeness

Tardis.dev (tick books, liquidations, options chains), Kaiko, Amberdata, CoinAPI,
Coinglass. All would supply liquidation history. None is needed for the top of
this list, and buying data before the free data is exhausted would be the wrong
order.

---

## 2. What the literature actually says

Filtered to findings with numbers attached.

- **Order-book imbalance is the strongest microstructure feature there is** —
  but measured at 3 seconds. *Explainable Patterns in Cryptocurrency
  Microstructure* (arXiv 2602.00776), Binance perps, 1-second data, Jan 2022 to
  Oct 2025. Top-of-book imbalance ranks first across every asset tested.
- **And the edge is concentrated away from BTC.** Same paper, same features,
  after realistic taker costs: **BTC 0.13% annualised, Sharpe 0.25**, while ETC
  is 5.78%/8.97, ROSE 7.00%/5.28, ENJ 4.06%/6.58. Ranked 1, 20, 40, 60, 100 by
  market cap. This is a direct challenge to this repo's "BTCUSDT first" rule.
- **Short-horizon reversion in crypto is real and uneconomic.** arXiv 2608.21888,
  183 Binance pairs, Jan 2025 - Feb 2026: 15-minute reversal is significant on
  90% of pairs, and the gross edge peaks at **1.3bps per trade** — a tenth of the
  taker band. Confirms this project's own dead ends from an independent direction.
- **Liquidation cascades have no reproducible early warning.** arXiv 2607.27070,
  seven BTC cascades 2022-2025: price carries the critical-slowing-down signature
  in five of seven events and is silent in exactly the two news-driven ones. The
  October 2025 $19bn event is the outlier, not the template.
- **Cross-sectional crypto anomalies are liquidity anomalies.** Recent factor
  work finds two to three factors absorb all portfolio alpha, dominated by
  turnover volatility, bid-ask spreads and blockchain-native ratios; size and
  volume effects live in micro-caps of negligible capacity.
- **Funding as a range governor.** arXiv 2601.06084 argues that when funding
  aligns with the prevailing 4-hour context price expands, and when it diverges
  the market compresses into a range. The paper is qualitative — no effect sizes
  survive reading it — but the claim is sharp enough to test, and it is the
  closest thing in the literature to Kris's Power of Three.

---

## 3. The ten, ranked

Ranking criteria, in order: is it a feed rather than a price pattern; can I get
the data free and today; is the plausible effect size big against a 14bps round
trip; does it fit intraday-to-few-days holds; is it genuinely new here.

### 1. H-024 — Order-book depth imbalance (`bookDepth`)

**Mechanism.** Open interest says who is positioned. Taker ratio says who is
aggressing. Neither says what is *standing in the way*. Depth is resting supply
and demand — the inventory a market order must consume. When the bid side within
1% carries twice the ask side, the cheap direction is up, and the counterparty is
whoever must trade immediately against a thin book.

**Why it might clear 14bps.** It is the highest-ranked feature in the
microstructure literature, and it has never been tested at a horizon this project
can trade. The literature's 3-second result is not the claim being made here; the
claim is that depth *asymmetry persists* long enough at 15m-4h to be worth 14bps.

**Why it might fail.** Depth is quoted, not committed — spoofing and fast
cancellation are real. The 30-second cadence means we see a slow-motion book. And
BTC's book is enormous ($81M within 0.2%), so imbalance may be pure noise there
even if it works on thinner coins.

**Second deliverable, independent of the signal.** Depth at +/-0.2% and +/-1%
prices what a given clip would actually have paid, every 5 minutes, for 3.6
years. **Every number in this repo rests on an assumed 14bps.** This turns the
project's largest assumption into a measurement. That alone justifies the rank.

**Data:** free, downloading now, 1341 days x 11 coins.

### 2. H-025 — Implied volatility regime, from Deribit DVOL

**Mechanism.** DVOL is the option market's 30-day forecast, priced by people
taking the other side with real money. It is the only feed on this list that is
**forward-looking**: open interest, taker flow, depth and premium all describe
what has already happened. Two objects, and they are different:
implied *level* (is risk cheap or dear) and implied *minus realised* (is the
option market over- or under-charging for the vol that actually arrives).

**Why it might clear 14bps.** It probably will not on its own, and that is not
the claim. The claim is that it **gates**. This project's single reproducible
lesson is that the only thing that ever worked was a gate from a feed, and there
has never been a volatility feed here at all — verified: no reference to DVOL,
Deribit, implied vol or options exists anywhere in the repo. A VWAP mean-reversion
leg should behave very differently when implied vol is collapsing than when it is
expanding, and nothing here has ever conditioned on that.

**Why it might fail.** Gate-sized gains are small by definition, and H-017's
stage 5/6 already showed that stacking gates on H-009 **lengthens** time to
funded even while it improves return/drawdown — gates cut trades and make returns
lumpier. Any DVOL result has to be scored on days-to-funded, not on PF.

**Data:** free, no authentication, hourly OHLC from 2021-04. Endpoint called and
confirmed working today.

### 3. H-026 — Power of Three, funding-conditioned (Kris's idea, feed-gated)

**Mechanism.** Accumulation, manipulation, distribution: a session builds a
range, sweeps it in the wrong direction to trigger stops, then delivers the real
move the other way. Bare, this is a price pattern, and price patterns have died
eleven times here — worse, "fade an extreme" is explicitly on the known-dead list
on two separate definitions of extreme.

**So it must not be built bare.** The new ingredient is the feed: test whether
the sweep-and-reverse pays *conditional on positioning and financing state*.
arXiv 2601.06084's claim — funding aligned with the 4H context gives expansion,
funding divergent gives compression and range — is exactly the conditioning
variable this pattern needs, and funding, crowd ratio and depth are all in hand.
The mechanism becomes: a sweep against crowded, expensively-financed positioning
is a liquidation of that positioning; a sweep against flat positioning is noise.

Note the premium is *dead standalone* (H-013) but has never been used as a
conditioner on a session-structure pattern. That is a genuinely different test,
not a re-proposal — and if the conditioning adds nothing, that is the answer and
the hypothesis dies with the rest of the price-pattern family.

**Why it might fail.** The AMD literature is entirely qualitative — no
peer-reviewed backtest exists, and the sources found are educational sites, not
studies. The honest prior is low. It is ranked third because it is Kris's, it has
a real feed ingredient, and the control (the same sweep with funding neutral) is
a clean falsification.

**Data:** free, in hand.

### 4. H-027 — Depth-derived execution cost model

Not a strategy. The correction H-023 was, done properly. Price the true round
trip for our clip from real resting depth, minute by minute, per coin, and
re-score every existing result on measured costs instead of 14bps. Could move the
board either way. Folded into H-024's build because it uses the same download.

### 5. H-028 — The long tail, weighted by signal-to-cost — **TESTED, CLOSED**

*Result, same day.* Run over all eleven coins: **0 of 935 cells clear a 14bps
taker round trip**, family median |spread| 0.76-1.24bps, best honest cell 7.9bps
(SOL `imbz_5`@4h). The literature's Sharpe 5-9 on small caps is a **3-second**
result and does not transfer to 15m-4h. Cost was not the obstacle either — the
measured impact spread from BTC to DOT is 80x but the whole range is trivial
against 14bps. **Cross this off: the cap curve does not rescue this project at
this horizon.** Original reasoning kept below for the record.

The literature's cleanest number: identical features give **Sharpe 0.25 on BTC
and 5-9 on rank-20-to-100 coins**. This repo's rule is "BTCUSDT first, other coins
only to re-test". That rule may be the reason everything dies. The obstacle is
cost — small coins are wider — and H-012 already proved that widening a book with
equal weights makes it *slower*, not faster. H-024's depth data supplies the
missing piece: per-leg true cost, so legs can be weighted by signal divided by
cost rather than equally.

Ranked below the feeds because it depends on H-024 landing first.

### 6. H-029 — Premium conditioned on depth

H-013 killed the perp premium standalone and as a flat gate. It was never
conditioned on **how thin the book was when the premium moved**. A rich premium
into a deep book is arbitrage capital doing its job; a rich premium into a hollow
book is leverage with nothing underneath it. Those are different states and H-013
averaged over both. bookDepth is what makes the distinction measurable, so this
becomes testable only after item 1 lands — which is why it sits here and not
higher. If item 1 fails, this dies with it.

### 7. H-030 — A feed layer for gold

Gold is the only survivor of the engine fix and it trades naked. COT (weekly,
3 days stale) and CME daily volume/OI are free. Both are too slow to trigger and
possibly fast enough to gate. Ranked here rather than higher because the honest
expectation from weekly data on an intraday strategy is small, but the asymmetry
is good: it is the only market we still have.

### 8. H-031 — Liquidation-pressure proxy

Binance's per-event liquidation dumps are gone (verified: zero files), so this
must be reconstructed from what we have — a sharp open-interest collapse plus an
adverse price move plus one-sided taker flow, all present in the 5m metrics feed.
Fade the flush. Two strikes against it: "fading an extreme" is on the known-dead
list, and the cascade literature says early warning is event-heterogeneous and
does not generalise. The OI ingredient is what makes it new rather than a repeat.

### 9. H-032 — Spot ETF flows

Strong published effect — 21% of daily return variation, 53bps per $100M — but
daily, published after the US close, history only from 2024, and worth at most one
trade a day. It fails this project's phase constraint on frequency, not on edge.
Logged as a future candidate, explicitly not built now.

### 10. H-033 — Hyperliquid account-level flow

The most interesting dataset in crypto and the worst fit for this project.
Thirteen months of perp history cannot be walk-forwarded, egress is requester-pays,
and Binance leads the venue by 700ms so the obvious edge is an HFT edge. Kept on
the list because "follow the accounts that actually win" is a mechanism nothing
else here can express, and the history grows every day.

---

## 3a. RESULTS — all three were built and tested the same day

Full detail in `SESSION_2026-09-06.md` and seven new rows in `STRATEGY_LOG.md`.

| # | hypothesis | verdict |
|---|---|---|
| 1 | H-024 book depth, signal | **FAILS ON COST.** Real, monotone, beats its null, stable across years — and 0 of 935 cells over 11 coins clear 14bps. Best honest cell 7.9bps |
| 1b | H-024 book depth, **cost model** | **THE USEFUL HALF.** Impact at a $50k clip is 0.018bps on BTC, not the 2bps/side assumed. The 14bps round trip is fee + spread, not impact |
| 2 | H-025 DVOL | **ONE MARGINAL SURVIVOR.** BTC `dvolz`@4h, 8.9bps, beats 1d/1w/1mo block nulls, same sign in 5/5 realised-vol buckets. ETH's larger 9.9bps was a null artifact |
| 3 | H-026 Power of Three | **FAILS.** Reversal loses gross on BTC and ETH, wins on SOL. Sign flips across coins at ~1,500 events each. 3 of 24 conditioners beat a permutation null |
| 5 | H-028 cap curve | **CLOSED** as a by-product of the H-024 wide run — see above |

The one thing that survived a strong null is 8.9bps against an 8bps maker round
trip. That is a 0.9bps margin, and it is dead against taker. Nothing here is
tradeable yet.

## 4. What was built

Kris asked for the top three coded and tested. In order:

1. **H-024 depth imbalance** — `core/binance_depth.py` written, downloading now.
   First test is a response study in the shape of H-022's: does depth imbalance
   at a bar's close predict forward return at 15m / 1h / 2h / 4h, in bps, against
   a paired null, monotone across quantiles, same-sign across years — before any
   strategy is written. The cost model comes out of the same data.
2. **H-025 DVOL regime** — downloader against Deribit's public endpoint, then the
   same response study, then the gate test scored on **days-to-funded** rather
   than PF, because H-017 stage 5/6 already showed gates can improve PF and make
   the book slower.
3. **H-026 Power of Three** — the session structure built explicitly, then scored
   only where the feeds say positioning is crowded, with the neutral-positioning
   version kept as the falsification control.

Every one reports the mandatory fields, is measured at 1x/2x/3x cost, and is
scored against a paired null before it is believed. Anything that lands under
14bps is dead on arrival and will be logged as dead, not massaged.

---

## Sources

- [Binance public data archive](https://data.binance.vision/) — enumerated directly
- [binance/binance-public-data](https://github.com/binance/binance-public-data)
- [Deribit DVOL](https://insights.deribit.com/exchange-updates/dvol-deribit-implied-volatility-index/) — endpoint called directly
- [Explainable Patterns in Cryptocurrency Microstructure (arXiv 2602.00776)](https://arxiv.org/html/2602.00776v1)
- [Short-horizon mean reversion in cryptocurrency markets (arXiv 2608.21888)](https://arxiv.org/html/2608.21888v1)
- [Where does the criticality live? (arXiv 2607.27070)](https://arxiv.org/abs/2607.27070)
- [Measuring the engine of a liquidation cascade (arXiv 2608.03616)](https://arxiv.org/html/2608.03616)
- [Who sets the range? Funding mechanics and 4h context (arXiv 2601.06084)](https://arxiv.org/abs/2601.06084)
- [The Price Impact of Spot Bitcoin ETF Flows (SSRN)](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=6592830)
- [Hyperliquid historical data](https://hyperliquid.gitbook.io/hyperliquid-docs/historical-data)
- [Hydromancer Reservoir](https://hydromancer.xyz/historical-data)
- [SonarX public Hyperliquid order books](https://www.sonarx.com/blog/sonarx-releases-hyperliquid-order-book-snapshots)
- [Cryptocurrency anomalies and economic constraints (ScienceDirect)](https://www.sciencedirect.com/science/article/abs/pii/S1057521924001509)
- [Cross-sectional interactions in cryptocurrency returns (ScienceDirect)](https://www.sciencedirect.com/science/article/abs/pii/S1057521924007415)
- [Bitcoin ETF flow tracker, open JSON](https://www.tftc.io/bitcoin-etf-flows)
- [CFTC COT via CME / Goldhub](https://www.gold.org/goldhub/data/gold-open-interest)
