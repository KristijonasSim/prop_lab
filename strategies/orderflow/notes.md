# H-006 — Order flow (open interest, taker aggression, positioning)

Opened 2026-09-02. Status: **stage 1, diagnostic only. Nothing is a strategy yet.**

## Why this hypothesis, and why now

Six price-pattern hypotheses have been rejected in this repo (H-001, H-003,
H-005, H-007, H-008) and one survives (H-002 VWAP). The standing pattern
inherited from `~/trading-bots` is blunt:

> every leg that ever worked came from a data feed (funding, open interest,
> taker delta, long/short ratio), not from a price pattern.

H-006 was reserved for exactly this and deferred to 2026-10, because
`core/feed_collector.py` only had two days of history and the REST endpoints
serve no more.

**That constraint was false.** Binance publishes the same feeds as daily files
at `data.binance.vision/data/futures/um/daily/metrics/`, 5-minute granularity,
back to **2020-09-01**, free and unauthenticated. Six years were available the
whole time. `core/binance_metrics.py` downloads them. The forward collector is
still worth running — it records the live present and the archive stops at
yesterday — but nothing has to wait for it.

## The feeds, and what each can actually say

| feed | what it measures | what it cannot say |
|---|---|---|
| `sum_open_interest` | contracts outstanding | direction |
| `sum_taker_long_short_vol_ratio` | who crossed the spread | who is positioned |
| `count_long_short_ratio` | long accounts / short accounts, **every account equal** | how much money is on each side |
| `count_toptrader_long_short_ratio` | the same headcount, largest accounts only | |
| `sum_toptrader_long_short_ratio` | large accounts weighted by **position size** | what the crowd is doing |

The count/sum split is the reason this feed is interesting and not just another
oscillator: the exchange publishes **where the crowd stands and where size
stands, separately**, and lets the two disagree.

## Mechanism, stated before any result

Three candidate edges, each with a named counterparty who is trading for a
reason other than expected return — which is the only kind of edge that has ever
survived in this repo:

1. **The open-interest quadrant.** The same price move means opposite things
   depending on whether open interest is rising or falling. Rising OI into a
   move is new risk being put on. Falling OI into a move is old risk being
   closed — short covering into a rally, longs being unwound into a fall.
   *Counterparty:* a position being closed under duress is price-insensitive and
   finite; it has to end when the position is gone. New positioning does not.

2. **Crowd-versus-size disagreement.** `count_long_short_ratio` is a headcount
   and `sum_toptrader_long_short_ratio` is money. When many small accounts are
   long while large accounts are short, the long side is leveraged retail.
   *Counterparty:* over-leveraged accounts that will be liquidated by the
   exchange, at market, regardless of price.

3. **Absorption.** Taker aggression that does not move price means a passive
   participant is absorbing it.
   *Counterparty:* an institution working a large order who wants the fill, not
   the tick.

## What stage 1 asks

Not "is it profitable" — "is there anything there". Three gates, each of which
has already killed a hypothesis here:

1. does the feature rank forward returns at all? (H-008 died on a flat response)
2. does it beat its own null? (H-003 and H-005 died here)
3. **is the best-minus-worst bucket spread worth more than a round trip?**
   (H-007 died here: a real edge of ~10% on profit factor that 14bps ate whole)

Everything is reported in basis points against 14bps at 1x cost and 28bps at 2x.

## Method notes

- Prices are **USDT-M perpetual** 5m bars from the same archive, not the repo's
  cached spot bars: the feeds describe the perp book and that is where this
  would be traded. Measuring a perp signal against spot prices would be
  comparing two different order books.
- Features are changes and deviations, never levels. Open interest in contracts
  is not comparable between 2020 and 2026, and each coin's long/short ratio
  rests at a different place.
- Z-score baselines are shifted one bar, so no bar is scored against itself.
- Forward returns are measured from the **next bar's open**, the first price a
  signal read off a closed bar could be filled at.
- The null shuffles day-long blocks of the feature against untouched returns,
  five seeds, read as a distribution. Shuffling bar-by-bar would destroy the
  feature's own autocorrelation and make it trivially easy to beat.
- Rows where either feed is missing are dropped, never forward-filled: a
  forward-filled order-flow reading is a number nobody could have seen.

## Log

- **2026-09-02** — found the archive, wrote `core/binance_metrics.py`, built the
  feed kernel and the stage-1 diagnostic. No results yet.

## Stage 1 result — BTCUSDT, 624k observations, 2020-09 → 2026-08

**The feed ranks forward returns, monotonically, and it is the CROWD feed doing
it — not open interest.**

Mean forward return by feature quintile, in basis points:

| feature | horizon | q1 | q2 | q3 | q4 | q5 | spread |
|---|---|---|---|---|---|---|---|
| `dcrowd_4h` | 24h | **+25.0** | +21.8 | +13.5 | −0.9 | **−13.2** | **−38.1** |
| `dcrowd_1h` | 24h | +23.8 | +16.4 | +8.3 | +3.1 | −5.3 | −29.0 |
| `crowd_z` | 12h | +19.6 | +17.1 | +2.1 | −5.0 | −10.8 | −30.5 |
| `doi_4h` | 24h | +17.1 | +2.8 | +1.6 | +3.2 | +17.3 | +0.2 |
| `taker_z` | 24h | +10.8 | +12.5 | +10.7 | +12.0 | +12.2 | +1.4 |

Read the first row: when the long/short **account** ratio has been rising over
four hours — the crowd getting longer — the next 24 hours average −13bps; when
it has been falling, +25bps. Monotone across all five buckets, not a tail
artefact.

Read the last two rows the same way and they say nothing. Open interest on its
own is a **V** — both tails positive, which is a volatility reading, not a
direction. Taker aggression is flat, +11 to +12bps in every bucket.

**So the edge is positioning, not aggression and not leverage.** That is worth
stating plainly because "open interest" is the feed everyone quotes, and on this
evidence it carries no directional information by itself.

Five feature × horizon combinations clear all three gates: beat every null seed,
spread over 28bps (2x cost), monotone, and the same sign in 6 or 7 of 7 calendar
years. `dcrowd_1h` at 24h is the same sign in **7 of 7**.

Caveats, unprompted:
- IC is about 0.04. Small, as any real one is.
- 24h forward returns on 5m bars overlap heavily, so the effective sample is
  about 2,190 independent days, not 624k. The block-shuffle null and the
  year-by-year sign check are the defence; a t-statistic on 624k rows would be
  a lie.
- Stage 1 cuts buckets on full-sample quantiles. That is hindsight about the
  distribution, not about the returns, and stage 2 replaces it with trailing
  quantiles.
- One coin. ETH and SOL are the confirmation that matters.

## Stage 2, first pass — BTC + ETH, 336 configurations

| | real | null (3 seeds/config) |
|---|---|---|
| PF > 1.0 at 0x cost | 50.0% | 50.0% |
| PF > 1.0 at 1x | **24.7%** | 2.7% |
| PF > 1.0 at 2x | **3.6%** | 0.0% |
| clears PF 1.20 at 1x | **10** | 0 |
| clears PF 1.20 at 2x | **1** | 0 |

**The control.** Every configuration was also run following the crowd instead of
fading it: median PF at 2x cost 0.628 against 0.826, mean −9.18bps per trade
against +9.18. The direction is not arbitrary and the entry filter is not just
selecting volatile bars.

**But it is cost-limited.** Median PF at 2x is 0.826 and exactly one
configuration of 336 clears the 1.20 gate there. Gross edge on the best
configurations is 30-60bps per trade against a 28bps round trip at 2x. That is
the H-007 disease — a real signal that the spread eats — though less severe:
H-007 could not beat its null after costs at all, and this beats it at every
cost level.

Every best configuration sat at the EDGE of the grid (`q = 0.05`, 24h hold), so
the grid was cutting off the region where the edge lives. Extended once, in one
direction: `q` down to 0.02, holds out to 72h.

## Stage 2, extended grid — 3 coins, 700 configurations each

| cost | real PF > 1.0 | real clears 1.20 | null PF > 1.0 | null clears 1.20 |
|---|---|---|---|---|
| 0x | 50.0% | 396 | 50.0% | 219 |
| 1x | 31.2% | 102 | 14.5% | 53 |
| 2x | **14.2%** | **37** | 5.4% | 16 |
| 3x | 6.7% | 12 | 2.2% | 5 |

Real beats null at every cost level — the opposite of H-005, and better than
H-007, which only beat its null before costs. The control holds: fading the
crowd averages **+13.35bps a trade**, following it **−13.35bps**.

Longer holds are monotonically better (median PF at 2x: 0.786 at 8h → 0.996 at
72h) and the tightest entry tail is best. Both say the same thing: the edge is a
slow drift, not a fast reaction, so it needs a long hold to outrun the spread.

## Stage 3 — the walk-forward, and why this does NOT beat H-002

Configuration re-chosen blind every quarter on 2x-cost train profit factor, 53
folds, 1,271 out-of-sample trades.

| book | PF | PF@2x | max DD | R/day | days to a funded account |
|---|---|---|---|---|---|
| BTC + ETH + SOL | 1.143 | 1.050 | 49.8R | +0.045 | 1,119 |
| BTC + SOL | 1.307 | 1.195 | 30.8R | +0.082 | 375 |
| BTC only | 1.363 | **1.227** | 63.5R | +0.116 | 548 |
| **H-002 for comparison** | **1.772** | **1.418** | **3.8R** | **+0.149** | **25 (53 two-step)** |

Per market: BTC clears the gate out of sample (PF@2x 1.227 over 462 trades),
SOL is close (1.146), ETH fails outright (0.854, −57.9R). Median train PF at 2x
was 1.808 against a median test of 1.117 — the usual collapse.

**The reason it loses is drawdown, not profit factor.** BTC-only holds PF 1.227
at double cost, which is a pass. It still needs ~548 days because its equity
curve draws down **63.5R** against H-002's 3.8R, and

    days = maxDD_in_R / R_per_day x (target / cap)

is the governing identity. The cause is structural and was a deliberate choice:
**there is no stop**, so R is return divided by trailing volatility and a single
loser can run the whole hold. H-002's R is bounded near 1 because it stops out.
The edge here is real; the risk shape is unusable.

That makes the next test obvious rather than exploratory: **add a stop**. It was
left out on purpose — a stop needs an intrabar ordering assumption and this repo
has been burned by a fill assumption once — but it is now the specific thing
standing between a measured edge and a tradeable one, not a knob to turn.

### Where this leaves H-006

Not a VWAP-beater. It is the second-best-evidenced hypothesis in the project:
the only one besides H-002 to beat its own null after costs, with a monotone
rank response, a working direction control, and stability across six years. It
fails the phase gate on drawdown.

Three levers, none of them tried, in the order they deserve testing:

1. **A stop.** Bounds R, which is the whole problem. Needs a fill-assumption
   argument first.
2. **A wider universe.** The archive carries every USDT-M perp; eight more coins
   are downloading. More coins is more trades from *different* crowds, which
   diversifies the drawdown rather than splitting one edge — the opposite of
   adding configurations on the same market.
3. **Maker entries.** A 24-72 hour hold does not need to cross the spread. That
   halves the cost the edge has to clear — but this repo's own rule is that any
   limit-fill result needs a queue-priority check before it is believed.

## Stage 4 — the stop. It helps. It is not enough.

540 configurations over the region stages 2 and 3 actually selected, stop at a
multiple of the same trailing sigma that defines R.

| stop | PF@1x | PF@2x | median maxDD | median total R | return / drawdown |
|---|---|---|---|---|---|
| none | 1.130 | 1.042 | −104.9R | +32.3 | 0.28 |
| 1.0σ | 1.134 | 0.970 | −110.1R | −21.7 | −0.22 |
| 1.5σ | 1.168 | 1.033 | −97.4R | +31.0 | 0.29 |
| 2.0σ | 1.186 | 1.066 | −84.3R | +61.9 | 0.67 |
| **3.0σ** | **1.193** | **1.079** | **−81.3R** | **+73.4** | **0.87** |

Wider is better, monotonically. A 1σ stop is actively harmful — it cuts the win
rate to 27% and turns the median configuration into a loser — which is itself
informative: the edge is a slow drift that has to be given room, not a quick
reaction that can be tightly protected.

The best single configuration (SOL, `crowd_z`, q 0.02, 48h hold, 3σ stop) reaches
**PF 1.427 at 2x cost with a −22.7R drawdown and return/drawdown 7.48**.

**H-002's return over drawdown is 26.4.** That is the entire remaining gap, and
it is not a profit-factor gap — H-006's best configurations match H-002's 1.42 at
double cost. It is that H-002 stops out at a bounded R and holds five markets
that do not draw down together, while this is three correlated crypto legs whose
losers still run for hours.

So the ranking of what is left to try changes: **decorrelation, not the stop.**
Which is the same conclusion H-007's rejection reached from the other direction,
and the reason eight more coins were queued for download while this ran.

## Stage 5 — two attempts to raise the 1.3, both of which made it worse

Asked whether H-006 can be improved, the two obvious levers were tried and both
failed out of sample. Recording them so neither is tried again.

**The gap that looked real.** Stage 3 — the walk-forward that produced the board
record — ran with **no stop at all**. Stage 4 then showed a stop helps
monotonically in sample (median PF at 2x 1.042 with none against 1.079 at 3
sigma, return over drawdown 0.31 against 0.90), and that result was never folded
back into the board record. So the board appeared to be scoring a version already
known to be inferior.

**Attempt 1 — let the walk-forward choose a stop.** Added `stop_k` to the grid,
700 configurations to 2,800.

The fold selector chose **no stop in 45 of 53 folds**, because it ranks on profit
factor and a stop converts some winners into losses — it costs profit factor
while cutting drawdown by far more. The book got worse: PF at 2x 1.050 → 1.007.

**Attempt 2 — rank folds on return over drawdown instead.** Principled rather
than fitted: the board judges this on `days = maxDD_in_R / R_per_day`, so a
selector blind to drawdown optimises the one quantity that is not binding, and
stage 11 already chooses H-002's book on a drawdown-aware objective.

It did change the choices — stops in 29 of 52 folds instead of 8 of 53 — and the
book still got worse on **every** measure:

| | board record | + stop, PF selector | + stop, return/DD selector |
|---|---|---|---|
| PF at 2x | **1.050** | 1.007 | 0.990 |
| max drawdown | **49.8R** | — | 57.1R |
| return / drawdown | **1.69** | — | 1.02 |
| R per day | **+0.0445** | — | +0.0309 |

**Why.** Stage 4's stop benefit was measured in sample across a focused grid.
Which stop to use is not stable quarter to quarter, so the selector cannot pick
it reliably, and quadrupling the configuration count mostly bought four times as
many chances to fit the training quarter. Both changes were reverted; the code
keeps the machinery so the test can be repeated rather than redone.

**What this leaves.** H-006's value has already been extracted — as H-009, which
takes the same signal, uses it to veto H-002's trades rather than to generate its
own, and is the top of the board at 8.9. A signal with the wrong risk shape is
worth more as a filter on a strategy with the right one than as a strategy.

The one untried lever is the **wider universe**: the archive carries every USDT-M
perpetual, and more coins means more trades from different crowds, which
diversifies the drawdown rather than splitting one edge. That is the same cure
H-007's rejection identified, and it is the only thing left that attacks the
49.8R directly.
