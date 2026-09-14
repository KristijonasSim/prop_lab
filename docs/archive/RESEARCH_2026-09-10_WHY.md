# Why gold and not bitcoin — and what actually moves the win rate

Written 2026-09-10, answering Kris: *"make investigation why exactly BTC and other
major assets like silver is not performing with this strategy… how to improve it,
how to increase maybe win % so we could take our profits because this 20% rule
will kill us… i think later we could even do a basket of 6-7 assets."*

Nine studies, all on H-027, none of them a new hypothesis:
`strategies/vwapbreak/research/{why,fixed,newmarkets,spread,stability,exitshape,payable,basket,payout_policy}.py`.
Every row is in `STRATEGY_LOG.md` and the JSON is under `backtests/vwapbreak/`.

**The four things that matter, before the detail:**

1. **FX and oil fade a VWAP band break; metals and crypto continue.** Measured two
   independent ways. It was knowable before any backtest.
2. ~~BTC is a cost failure, not a mechanism failure.~~ **WRONG — corrected the same
   day, see §2.** BTC's trades re-priced at ZERO cost still score PF 0.791 and
   −24.4R. The signal is negative on BTC at any spread.
3. **Only gold 1h survives deleting its best quarter.** ETH 1h is 94% one quarter.
   That weakens yesterday's two-market book.
4. **Taking half the position off at +2R roughly doubles the win rate** — 20.3% to
   41.9% on gold, 22.8% to 40.1% on ETH — with profit factor and pace inside their
   bands. The 20% best-day rule still survives it.

---

## 1. THE MECHANISM SPLITS BY ASSET CLASS

`why.py` takes the strategy away entirely. For every market: what happens *after* a
close finishes 1.0 sigma from its own session VWAP? Enter at the next open exactly
as the kernel would, hold a fortnight, record the move in the break's direction.

| class | follow-through, 384h | fixed-config PF@2x | cost bps | sigma/cost |
|---|---|---|---|---|
| **Metals** (XAU, XAG) | **+30.7 bps** | 1.12 | 1.1–4.7 | 11.0 |
| **Crypto** (BTC, ETH, SOL) | +9.8 | 1.24 | 9–10 | 4.9 |
| **Indices** (NAS100, SPX500, US30) | +8.4 | 0.75 | 1.8 (assumed) | 5.3 |
| **FX** (7 pairs) | −3.2 | 0.75 | 0.2–0.8 | 19.4 |
| **Energy** (WTI) | **−23.5** | 0.85 | 2.8 | 10.3 |

Two independent methods agree on the split: the raw forward move (no strategy at
all) and the strategy run at one fixed configuration (`fixed.py`). The five cells
whose bootstrap band excludes 1.0 **on the downside** — GBPUSD 1h, USDJPY 1h,
AUDUSD 1h, AUDUSD 4h, WTI 4h — are every one of them FX or energy.

**"It does not work on EURUSD" is not bad luck. It is the wrong market for the
mechanism.** Variance ratios are 0.88–1.24 everywhere, so ordinary "trendiness" is
*not* what separates them; it is specifically what follows a stretched VWAP.

## 2. BTC — THE COST EXPLANATION WAS WRONG, AND HERE IS WHAT KILLED IT

**Read this before the table below it.** The cost story was built on a rank
correlation across ten cells (sigma/cost against the walk-forward result, 0.73) and
it does not survive a direct test. Re-pricing each cell's own trades at a range of
cost multiples — exact arithmetic, since the pipeline stores every trade at 1x and
2x, so `cost_R = r − r_2x`:

| cell | PF at **zero** cost | at 1x | at 3x | total R at zero cost |
|---|---|---|---|---|
| **BTCUSDT 1h** | **0.791** | 0.735 | 0.642 | **−24.4** |
| BTCUSDT 4h | 0.747 | 0.706 | 0.635 | −19.1 |
| ETHUSDT 1h | 2.274 | 2.142 | 1.916 | +108.6 |
| XAUUSD 1h | 3.035 | 2.951 | 2.797 | +191.3 |

**BTC loses money with execution free.** It is not a cost failure; the signal is
negative there. And the reason cost barely moves any of these is structural: the
stop is 8–20 sigma wide, so a round trip is **0.22% of a full stop on gold and
0.56% on BTC**. This strategy family is close to cost-insensitive everywhere.

Gold at **ten times** Dukascopy's spread — 10.65bps, wider than BTC pays — still
scores PF 2.361 and 53.9% pass. That also downgrades "measure the firm's gold
spread" from a blocker to a routine check.

The sigma/cost table below is kept because the QUANTITIES are right and worth
knowing; the causal claim built on them is not.

## 2b. The cost table, as measurement rather than explanation

| | gold 1h | silver 1h | ETH 1h | BTC 1h |
|---|---|---|---|---|
| round trip | **1.06 bps** | 4.70 | 9.00 | **9.00** |
| band sigma | 18 bps | 35 | 49 | 34 |
| **sigma / cost** | **17.2** | 7.4 | 5.5 | **3.8** |
| follow-through 384h | +24.6 | +35.8 | −5.7 | +4.5 |
| walk-forward PF@2x | 2.872 | 0.942 | 2.023 | 0.686 |

Inside the classes where the mechanism has the right sign, sigma/cost ranks the
walk-forward result at 0.73 across ten cells — which is what made the cost story
look convincing, and is exactly the kind of evidence the direct test above
overturns. **Ten points and a rank correlation are not a mechanism.**

What survives from this table: the quantities themselves. Gold's band is 17x its
round trip and BTC's is under 4x, and that is worth knowing when a new market is
proposed. What does not survive: using it to explain why BTC fails.

### The crypto spread, for the record

Crypto's half-spread in `core/markets.py` is **assumed** at 2bps; Binance's
`bookTicker` archive stopped in 2024-03. Estimating it from bars
(Corwin–Schultz, `spread.py`) was tried and **failed its own calibration**: on the
four markets whose spread IS measured from ticks it lands at 1.39x, 4.00x, 1.60x
and 0.58x of the truth. No number from it can be quoted.

It no longer blocks anything either way: BTC loses at zero cost, so no spread
measurement rescues it, and ETH's PF only moves 2.274 → 1.916 across a 0–3x cost
range.

## 3. SILVER: RIGHT MECHANISM, FOUR TIMES THE COST, AND THE NULL CATCHES IT

Silver has the **strongest raw follow-through in the universe** — +35.8bps at 1h
against gold's +24.6 — and still loses to its own phase-randomised null (1.104 vs
1.002). Round trip 4.70bps against gold's 1.06. At one fixed configuration its
PF@2x is 1.07 with a band of **0.69–1.54**. It is not a losing market; it is an
indistinguishable one.

## 4. THE UNCOMFORTABLE PART: THE BOARD'S MARKET RANKING IS MOSTLY SELECTION

Rank the twenty cells by one fixed configuration; rank them again by the
walk-forward number the board shows. **The two rankings agree at 0.231.**
Follow-through ranks the fixed-config result at 0.50 and the walk-forward at
**0.10**. Nineteen of twenty fixed-config bands overlap.

That does not make the walk-forward wrong — the selector adapts per fold, which is
its job. It means the board's **cross-market ordering** is driven by what the
quarterly selector happened to pick. Statements like *"it ports to ETH but not to
BTC"* are weaker than the board makes them look.

## 5. ONLY GOLD SURVIVES ITS BEST QUARTER

Sum the walk-forward daily R by calendar quarter; delete the best one.

| cell | total R | best quarter | its share | without it | quarters still + |
|---|---|---|---|---|---|
| **XAUUSD 1h** | 188.4 | 106.8 | 57% | **+81.6** | 5 of 7 |
| ETHUSDT 1h | 103.0 | 97.0 (2025Q3) | **94%** | **+6.0** | 4 of 8 |
| SOLUSDT 1h | 35.7 | 32.8 | 92% | +2.8 | 4 of 8 |
| XAUUSD 4h | 20.8 | 14.0 | 67% | +6.8 | 3 of 7 |
| BTCUSDT 1h | −33.0 | — | — | −43.9 | 2 of 8 |

**The ETH leg of the two-market book is one quarter of one year.** The book result
from 2026-09-09 stands as arithmetic and its weakness is now named.

## 6. WHAT RAISES THE WIN RATE: TAKE HALF OFF

The entry axis is exhausted; the exit axis had exactly one arm ever tested (stop
width). `exitshape.py` adds three shapes, walk-forwarded blind on identical folds.
The kernel is copied rather than imported, so the shipped one gains no exit axis;
the baseline arm reproduces the board's gold cell exactly (591 trades, 20.3% win,
PF@2x 2.872), which is the check that the copy is faithful.

**Gold 1h**

| exit shape | trades | win % | PF@2x | expected days | pass % | best day |
|---|---|---|---|---|---|---|
| baseline | 591 | 20.3 | **2.872** | 11.7 [9–14] | 59.8 | 42% |
| partial 1R | 550 | 21.6 | 2.399 | 13.2 [11–16] | 75.7 | 29% |
| **partial 2R** | 540 | **41.9** | 2.668 | 12.6 [10–16] | 71.3 | 35% |
| trail 2R | 518 | 36.7 | 1.451 | 14.6 [12–19] | 68.3 | 39% |
| **partial 1R + trail 3R** | 409 | **43.0** | 1.771 | 14.0 [12–20] | **78.3** | **12%** |
| VWAP recross | 2637 | 29.2 | 1.090 | **6.8 [7–9]** | 58.7 | 44% |

**ETHUSDT 1h**

| exit shape | trades | win % | PF@2x | expected days | pass % | best day |
|---|---|---|---|---|---|---|
| baseline | 557 | 22.8 | **2.023** | 16.9 [15–22] | 59.2 | 85% |
| partial 1R | 535 | 22.8 | 1.543 | 17.4 [14–22] | 74.7 | 82% |
| **partial 2R** | 538 | **40.1** | 1.627 | 14.4 [13–19] | 69.5 | 59% |
| trail 2R | 595 | 38.7 | 1.607 | 16.7 [14–21] | 71.9 | 49% |
| partial 1R + trail 3R | 591 | 35.9 | 1.283 | 14.1 [12–20] | 56.9 | 61% |
| VWAP recross | 1475 | 36.6 | 1.188 | 11.0 [9–16] | 36.4 | 65% |

**Read it as three findings.**

* **Partial 2R is the win-rate answer and it holds on both markets** — 20.3 → 41.9
  and 22.8 → 40.1 — with pace bands overlapping the baseline's. Profit factor falls
  (2.872 → 2.668, 2.023 → 1.627) and stays well clear of the 1.20 gate.
* **Partial 1R + trail 3R is the payoff-shape answer on GOLD only**: best day 42% →
  **12%**, pass 59.8% → 78.3%. On ETH the same arm makes pass rate *worse* (56.9%).
  An arm that works on one market and not the other is not yet a rule.
* **The VWAP recross is the fastest number this project has produced — 6.8 expected
  days — and its profit factor is 1.090**, under the repo's own 1.20 gate, on 4.5x
  the trades. It is a cost-sensitivity accident waiting to happen and has not been
  priced at 3x.

### And the reshaped exit fixes the concentration problem

Same quarterly test as §5, on the reshaped series (`stability.py`, second table):

| cell | best-quarter share, as traded | with partial 1R + trail 3R |
|---|---|---|
| XAUUSD 1h | 57% | **39%** |
| ETHUSDT 1h | **94%** | **44%** |
| XAUUSD 4h | 67% | **28%**, 6 of 7 quarters positive |

Total R collapses (gold 188.4R → 26.0R) because the trail truncates the tail. The
trade becomes a grind instead of a lottery: fewer R, far steadier, higher pass rate,
slightly slower. **That is a decision for Kris, not a result.**

## 7. THE 20% BEST-DAY RULE SURVIVES EVERYTHING TRIED

Three independent attacks, all measured:

| attack | best day, % of net profit | payable withdrawals |
|---|---|---|
| gold alone, as traded | 42.1% | 0 of 16 |
| withdraw at 30% of the account instead of 1% | — | **0 of 5** |
| gold + ETH | 29.8% | 0 of 25 |
| all nine legs that beat their null | **20.0%** | 0 of 27 |
| gold, partial 1R + trail 3R | **12.0%** | 0 of 21 |
| the same, 4 legs, 10% withdrawals | — | **1 of 3** |

The flattest payoff this project has produced, combined with a basket and the most
patient withdrawal policy, yields **one payable withdrawal in two and a half
years**.

**Conclusion: do not take a funded account with a best-day or consistency rule.**
It is a firm-selection constraint, not a research problem. On the current shortlist
that leaves FundingPips' weekly-payout track and City Traders Imperium.

## 8. THE BASKET, MEASURED

| legs | 1 | 2 | **3** | 4 | 5 | 6 | 7 | 8 | 9 |
|---|---|---|---|---|---|---|---|---|---|
| expected days | 13.5 | 10.3 | **9.9** | 12.5 | 12.9 | 12.1 | 13.5 | 13.9 | 14.6 |
| pass % | 51.9 | 67.8 | **71.0** | 71.9 | 69.7 | 66.3 | 66.4 | 64.9 | 68.6 |
| best day | 42% | 30% | 27% | 25% | 23% | 22% | 21% | 21% | 20% |

**Three legs is the fastest and it gets slower after that** — H-012's dilution
arriving on schedule at the fourth leg. A six or seven asset basket is **safer on
the payout metric and slower to fund**. Control: 40 random baskets from all twenty
cells give a median 17–18 expected days and only half are profitable at all, so the
leg pool is doing real work.

Caveat that outranks the table: two of the top three legs (ETH 1h, SOL 1h) are
**one quarter each** (§5). A three-leg book resting on two of those is thinner than
its own numbers suggest.

## 9. SIX NEW MARKETS SCREENED, NONE BETTER THAN GOLD

NAS100, SPX500, US30, USDCHF, NZDUSD, USDCAD — cached, never tested, same window,
costs assumed and deliberately pessimistic (1.8bps round trip on the indices).

* The **indices carry the right sign** (NAS100 4h +15.8bps, SPX500 4h +9.6, US30 4h
  +2.9) — the only new class that does — but sigma/cost is 3.9–7.7 against gold's
  17.2 and every fixed-config band contains 1.0.
* The three new **FX pairs behave like the four already tested**: zero or negative
  follow-through, PF below 1.
* USDCAD 4h prints PF@2x 2.81 on 114 trades with a band of **0.60–5.60**.

Nothing here justifies a full walk-forward.

---

## What this changes

1. **Keep gold 1h as the core.** Its advantage is cost-to-sigma, which is
   structural rather than a regime that can turn.
2. **Put `partial 2R` into the candidate set** for the win rate; it holds on both
   markets. It needs the second-engine check before it can be traded.
3. **Treat the ETH leg as provisional.** 94% of its edge is 2025Q3.
4. **Never take a funded account with a best-day rule.** Measured three ways.
5. ~~Measure the crypto spread before believing any BTC or ETH number.~~ **Downgraded.**
   BTC loses at zero cost, so no spread measurement rescues it. Worth doing for ETH
   only, and it is no longer blocking.
6. **A basket of 6–7 is a safety choice, not a speed one.** Three legs is the
   fastest thing measured.
