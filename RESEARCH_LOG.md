# Research Log

Long findings. Chat stays short; detail lives here.

## Known-dead directions (inherited from ~/trading-bots, same trader)

See CLAUDE.md "Known-dead" for the list and the numbers. Summary: the whole
session-anchored breakout family (ORB, breakout+retest, Larry Williams range
breakout) failed on BTC and on Gold/Silver/Nasdaq futures. Every leg that ever
worked in that repo came from a data feed, not a price pattern.

## H-001 ORB — REJECTED (2026-08-31)

Full write-up and charts: `backtests/orb/report.html` (published artifact).
Code: `strategies/orb/`. Raw results: `backtests/orb/stage*.csv`.

**Mechanism check first.** Zarattini/Barbon/Aziz 2024 (7,000+ US stocks, 2016-23):
unfiltered 5m ORB returned Sharpe 0.48; filtered to the top-20 "stocks in play" by
opening relative volume it returned Sharpe 2.81. The edge is the *participation
filter*, not the breakout. That filter's mechanism — institutions repricing against
overnight news, compressed into a single daily auction — has no equivalent on a
24/7, continuously-arbitraged BTC book.

**What was tested.** 8,160 configurations (8 UTC session anchors x 15m/30m/1h/2h/4h
opening range x 2h/4h/8h/24h horizon x stop-at-edge vs close-beyond entry x
OR-far-side / OR-mid / 1x / 2x ATR stops x session-close/1R/1.5R/2R/3R targets x
follow vs fade), each at 0x/1x/2x/3x cost. Plus 2,160 literature variants with a
relative-volume floor, first-candle-direction entry and a daily-ATR stop. Plus a
31-quarter walk-forward, a prop-challenge simulation, and a NautilusTrader cross-check.

**Results.** Zero configurations reach the PF 1.20 gate at realistic cost (Binance
USDT-M perp taker 5bps + 2bps slip), in sample or out. Best IS was 1.045, and that
config did 0.964 OOS. Walk-forward: 2,746 trades, PF 0.781, -594R, 5/31 quarters
above breakeven.

**The decisive number is the zero-cost run: median PF 0.960.** The pattern loses
money before a single basis point is charged, so this is not a fee problem and no
cheaper venue or maker rebate rescues it. The only positive gross edge found was a
short fade with a 1x-ATR stop: +0.213R per trade against a 1R of 38.7 bps, while
round-trip cost is 0.36R. Widening the stop to 8x ATR cuts cost to 0.046R but decays
the gross edge to +1.6% — net PF never approaches 1.0 at any width.

**Relative volume did not transfer.** As the floor rises the best PF climbs (1.04 →
1.91) while the median falls (0.707 → 0.572) and median trades collapse (2,166 → 111).
That is a noisier statistic, not a filter finding signal. 75 configs clear 1.20 IS;
4 repeat OOS. Survivors trade ~0.11/day — one trade a fortnight, failing the phase
constraint independently.

**Engine cross-check.** Best config re-run in NautilusTrader (margin account on the
perp, resting stop entries, reduce-only exits) on 2022: 341 positions vs the kernel's
365, PF 0.682 vs 1.013. The independent engine is worse, so the null result is not a
kernel artefact.

**Two bugs found and fixed during this run**, both of which had inflated results:
1. Fade trades could place a stop a hair from the fill, dividing by ~0 and
   manufacturing 25R winners. Fixed with a `min_risk_bps` floor (default 10 bps);
   OR-edge stops are now skipped entirely for fades, where they are meaningless.
2. `core/data.py` incremental cache never backfilled earlier history — an earlier
   `since` was silently ignored. Fixed with a two-phase fetch.

**Where to go next, if ORB is revisited.** The literature says the edge is the
participation filter. On BTC that filter is not candle volume — it is a data feed:
funding-rate extremes, open-interest jumps, taker-delta imbalance, long/short ratio,
spot-perp basis. `~/trading-bots` reached the same conclusion independently: every leg
that ever worked there came from a feed, not a price pattern. An ORB trigger gated on
a feed is a different hypothesis and needs its own test.

### H-001 ORB — multi-asset extension (2026-08-31)

Gold and FX added after Kris pointed out the first pass was BTC only. Data:
Dukascopy 1-minute candles resampled to 15m, 2023-09-01 to 2026-08-31, via the new
`core/fx_data.py`. EURUSD and XAUUSD complete (938 days, 0 gaps after a repair pass);
GBPUSD 901 of 938 days (96%). BTC re-run on the identical window for comparability.

**Results differ by market, unlike the BTC-only pass suggested.** Configs clearing
PF 1.20 at 1x cost, out of 8,160 each: Gold 2, GBPUSD 11, EURUSD 0, BTC 0. BTC is the
worst of the four — not one config even breaks even. Median PF at 1x: Gold 0.711,
GBPUSD 0.663, EURUSD 0.634, BTC 0.481. Everything collapses at 2x cost.

**IS/OOS split (fit 2023-09→2025-09, test the final year).** Gold: 2 clear the gate in
sample, 0 out, median 0.976. GBPUSD: 9 clear in sample, 5 still clear out, median 1.203
— a 129x lift over the 0.4% base rate, binomial p<0.001. That looked like a real find
until the cluster check: **all nine are the same setup** (1h range, faded, close-beyond
entry, almost all at the 20:00 anchor). They are one observation wearing nine hats, so
the significance test does not apply.

**The decisive test was the session anchor, which is what the mechanism actually
predicts.** Median PF across all 1,020 configs sharing each anchor, 1x cost:

| anchor | XAUUSD | EURUSD | GBPUSD | BTCUSDT |
|---|---|---|---|---|
| 00:00 UTC | 0.662 | 0.544 | 0.568 | 0.458 |
| 08:00 London open | 0.705 | 0.671 | 0.670 | 0.455 |
| 13:00 NY open | **0.789** | **0.734** | **0.756** | 0.518 |
| 20:00 NY close | 0.577 | **0.468** | **0.486** | 0.484 |

The NY open is the best anchor on all three FX/metal instruments and the NY close is
the worst. Best-to-worst spread is 57% on EURUSD and 56% on GBPUSD against 16% on BTC
— session structure is detected where it exists and is nearly absent where it does not,
which is a good internal validity check on the method. But the best anchor on the best
instrument still has a median PF of 0.789.

**This also disposes of the GBPUSD survivor.** Its 20:00 anchor is not a session open;
it is the NY close, and it is the single worst anchor on every FX pair by median. That
configuration is the luckiest cell of the weakest family.

**Verdict unchanged: ORB is rejected on all four instruments.** The session effect is
real and measurable and roughly 25% too small to pay for the spread.

### When is a hypothesis dead? (decision rule adopted 2026-08-31)

Kris asked how we know, given how many people trade ORB. Seven criteria, checked in
order. A "no" on criterion 2 means the test was not a test of the hypothesis.

1. A mechanism is named — why should an edge exist and who pays for it?
2. **The mechanism was present in what we tested.**
3. Clears PF 1.20 at realistic cost.
4. Not merely a cost problem — check it with fees set to zero.
5. Survives out of sample on the same configuration.
6. Survives walk-forward, chosen blind.
7. A second, independent engine agrees.

**ORB scores no on 3-6, yes on 1 and 7 — and no on 2.** That last one is the important
one and it changes the verdict's scope. The published edge is not "breakouts work"; it
is picking the 20 stocks out of 7,000+ with abnormal opening relative volume, every day,
and trading their opening range. The same paper's unfiltered single-name version scored
Sharpe 0.48 — and a single-symbol sweep like ours is the unfiltered version.

So the honest status is: **ORB is rejected for single-symbol crypto, FX and metals, and
has not been tested in the structure where its edge is claimed.** Cross-sectional
selection cannot be reproduced by sweeping parameters on one symbol, no matter how many.

Why people trade it anyway, in rough order of how much weight each deserves: the
published version is a basket strategy; equities have a daily auction and these markets
do not; live ORB is discretionary and context-filtered, which a mechanical sweep can
neither reproduce nor falsify; losing months are not posted; and a 25% shortfall
(median PF 0.789 at the best anchor) is invisible on a chart — only a few hundred
trades can distinguish 0.79 from 1.05.

**Next candidates, in priority order:**
1. US equities cross-section, top 20 daily by opening relative volume, 5m opening range.
   The actual published strategy. If it fails, ORB is dead everywhere.
2. Crypto analogue: rank 50+ coins daily by relative volume, trade the top few. Tests
   whether cross-sectional selection — the part that carries the edge — transfers to a
   market we can already trade. Fits the current phase.
3. Index futures (NQ/ES) at the NY open — the instrument most retail ORB traders use,
   and the one gap left in the session-anchored test.

### H-001 ORB — upgrade attempt (2026-08-31)

Kris asked whether ORB can be made better: more session anchors including Asia, plus
filters. Four new stages.

**Stage 9 — 20 session anchors** (Sydney 21:00/22:00, Tokyo 00:00/01:00, Asia 02:00/04:00,
Frankfurt 06:00/07:00, London 07:30/08:00/08:30/09:00, NY 12:00/13:00/13:30/14:00/14:30/
15:00/16:00, NY close 20:00). The original grid only had :00 anchors and never tested the
NY cash auction at 13:30/14:30 UTC, which is the one event in this study with a documented
mechanism.

Result is a smooth, unambiguous curve. Median PF by anchor, FX+metal mean: Asia 0.62-0.68,
London 0.71, **NY cash open 13:30 UTC 0.791 (the peak, best on all three)**, decaying to
NY close 20:00 at 0.577 (the worst). Bitcoin is nearly flat (0.48-0.57). **Adding Asian
sessions makes ORB worse, not better** — they are the weakest region tested.

**Stage 10 — 29 filters, scored as paired lifts** (same configs run with the filter off
and on; a filter that only raises the maximum has just shrunk the sample). Base median
0.679. Nine filters lift, ten hurt.

| filter | median PF | lift | improved | trades kept |
|---|---|---|---|---|
| breakout-bar rvol > 2.0 | 0.768 | +0.052 | 61% | 78% |
| ATR rank > 0.7 | 0.745 | +0.050 | 75% | 36% |
| **against 20-EMA** | 0.753 | +0.039 | **77%** | **94%** |
| opening-range rvol > 2.0 | 0.723 | +0.038 | 64% | 29% |
| retest entry (4/8/16 bars) | 0.649 | **-0.029** | 37% | 86% |
| breakeven at 1.0R | 0.643 | **-0.015** | 8% | 100% |
| breakeven at 0.5R | 0.582 | **-0.078** | 5% | 100% |

Two findings worth keeping beyond ORB: **breakeven stops are the single most damaging
thing on the list**, and the **retest entry — the most commonly recommended ORB
improvement anywhere — loses on every setting tested**. "Against the 20-EMA" is the
standout because it lifts the median while keeping 94% of trades; combined with fade
beating follow earlier, the consistent message is that these markets mean-revert at the
session open and the breakout-continuation premise is backwards.

**Stage 11 — stack the three winners** (breakout rvol, high-volatility regime, counter-20EMA)
on the two NY anchors, fit 2y / test 1y. Medians rise to 0.60-0.82. Survivors: BTC 103 of
179 clear the gate again out of sample (10.6x the 5.4% base rate), EURUSD 328 of 857 (7.8x).
The best BTC config — 13:30 NY cash open, 15m range, follow the break, breakout rvol > 1.5,
counter-20EMA — is positive in 8 of 9 years and in both directions (longs PF 1.43, shorts
1.97), so it is not a bear-market artefact. But it is also the winner of an 11,583-way
search, so its year-by-year record is post-hoc.

**Stage 12 — walk-forward the filtered family**, BTC, 31 quarters, config re-chosen on the
trailing 12 months each quarter and traded blind. **PF 1.165, 470 trades, +42.4R, 13/31
quarters above breakeven** — against **0.781 / -594R / 5 of 31** for the same walk-forward
without filters. This is the only number in the whole ORB study that nobody chose after
the fact, and the filters genuinely moved it.

**It still fails, for two reasons.** PF 1.165 is below the 1.20 gate. And 470 trades over
eight years is **0.16 trades/day** — roughly +5%/year at 1% risk, so more than a year to
clear an 8% target. That fails the current phase constraint by two orders of magnitude.

One layer of selection remains un-removed: the filter set itself was chosen from the
29-filter study on overlapping data. A fully clean test would re-choose the filters inside
each walk-forward fold. Given the frequency problem makes the strategy unusable regardless,
that was not run.

**Verdict: ORB stays rejected, but the upgrade taught us three transferable things** —
the NY cash auction is the only anchor that carries anything; participation filters
(relative volume) are the only family that lifts a median; and breakeven stops and retest
entries actively destroy edge and should not be added to future strategies by default.

### H-001 ORB — the GBPUSD 1.439, examined properly (2026-08-31)

Kris pushed back on calling the study a failure when the table shows PF 1.439. Fair
challenge, so here is that exact configuration taken apart. 20:00 UTC anchor, 1h opening
range, faded, close-beyond entry, 2x ATR stop, 1R target.

**What is genuinely good about it:**
- 439 trades, 54.9% win rate — the right shape for a challenge, not a lottery-ticket payoff.
- It got BETTER out of sample: fit years PF 1.160 -> test year PF 1.865.
- Prop challenge sim: 52.1% pass, and it never breaches the 4% daily cap.
- +25.5R over 3 years = about +8.5%/year at 1% risk.

**What kills it, in order of severity:**
1. **The cost cliff. 1x PF 1.439 -> 2x PF 0.553 -> 3x PF 0.213.** The 1x assumption
   (0.50 fee + 0.30 slippage per side = 1.6 bps round trip) is an institutional ECN
   spread. A prop firm on GBPUSD routinely quotes 1.0-1.5 pips = 7-11 bps round trip,
   which is 4-7x the 1x column. At any realistic prop-firm cost this is PF ~0.2.
2. **Its own max drawdown is -9.4%, larger than the 8% max-loss cap.** The historical
   worst run would have failed the account outright.
3. **339 days to resolve, median 148 days to pass.** The phase constraint is 1-2 weeks.
4. Per-trade edge is +0.058R. One extra pip of spread erases it entirely.
5. The 20:00 anchor is the WORST anchor by median across every FX pair (0.486). This is
   the luckiest cell of the weakest family, which is exactly where a 8,160-way search
   puts its maximum.

The answer to "so it's not that bad?" is: it is the best thing in the study, it is not
noise in the naive sense, and it is still untradeable — because the edge is smaller than
the spread difference between a retail broker and a prop firm.

**Report fix:** the out-of-sample table had two empty cells (markets where nothing cleared
the gate in sample, so there was no median to report). Replaced with a ranking that always
resolves: top 10 by fit PF, their median test PF, and how many stayed above 1.0.
Gold 1.192 -> 1.148 (9/10), GBPUSD 1.231 -> 1.211 (8/10), EURUSD 1.106 -> 0.700 (1/10),
BTC 0.964 -> 0.710 (0/10). Also added PF-at-2x and PF-at-3x columns to the best-per-market
table, since the cost cliff is what decides every one of them.

### H-001 ORB — the FX universe test (2026-08-31)

Kris asked whether ORB might work only on FX, since GBPUSD was the one market to clear
PF 1.20. Extended the universe to eight instruments (EURUSD, GBPUSD, USDJPY, AUDUSD,
USDCAD, USDCHF, NZDUSD, XAUUSD), 8,160 configurations each, same 3-year window.
JPY crosses and silver were dropped: Dukascopy throttles hard above five parallel
downloads and they would have added another hour.

**I was wrong that GBPUSD was a lucky pair.** Six of eight instruments produce
gate-clearing configurations at 1x cost, and two of them beat GBPUSD:

| pair | clear 1.20 | best PF | best at 2x | median | top10 fit -> test | DD |
|---|---|---|---|---|---|---|
| AUDUSD | 26 | 1.698 | 0.737 | 0.675 | 1.325 -> 1.867 (10/10) | -14.1% |
| USDCHF | 19 | 1.506 | 0.614 | 0.587 | 1.108 -> 1.224 (8/10) | -28.1% |
| GBPUSD | 11 | 1.439 | 0.553 | 0.663 | 1.231 -> 1.211 (8/10) | -9.4% |
| USDJPY | 6 | 1.320 | 1.123 | 0.689 | 1.353 -> 0.858 (3/10) | -26.3% |
| NZDUSD | 5 | 1.300 | 0.584 | 0.610 | 1.037 -> 0.764 (1/10) | -27.9% |
| XAUUSD | 2 | 1.262 | 1.046 | 0.711 | 1.192 -> 1.148 (9/10) | -63.8% |
| EURUSD | 0 | 1.081 | 0.836 | 0.634 | 1.106 -> 0.700 (1/10) | -65.4% |
| USDCAD | 0 | 1.075 | 0.823 | 0.488 | 0.984 -> 0.893 (4/10) | -40.8% |

So the pattern is FX-wide at institutional spreads, not one pair's accident. That is a
real correction to the earlier read.

**But two things are universal across all eight, and they are what settle it.**

1. **Zero of 65,280 configurations clear PF 1.20 at 2x cost.** Not one, on any
   instrument. The break-even spread by pair: EURUSD and USDCAD die at 1.0x, GBPUSD and
   NZDUSD at 1.2x, USDCHF and XAUUSD at 1.3x, AUDUSD at 1.5x, USDJPY at 1.6x. 1x here is
   an institutional ECN spread; a prop firm is routinely 4-6x that. The edge is
   systematically about the width of one extra spread, on every pair independently.
2. **Every single best configuration has a max drawdown that breaches the 8% cap** —
   from -9.4% (GBPUSD, the mildest) to -65% (EURUSD). All at a fixed 1% risk per trade.

And only two of eight resolve fast enough for the current phase (XAUUSD 11 days,
EURUSD 14); the rest run 19 to 339 days.

The transfer test says the same thing from the other direction: each market's winning
configuration scores 0.32-0.82 on the other markets, and of 8,160 configs scored on
EURUSD, GBPUSD and XAUUSD together, **zero clear 1.20 on more than one**. The gate
clearers are broad as a phenomenon but individually pair-specific — which is what an
edge that sits just under the noise floor looks like when you search 8,160 ways.

**Verdict unchanged, reasoning upgraded.** ORB is not dead because GBPUSD got lucky. It
is dead because the effect is real, small, present across FX, and uniformly smaller than
the cost of trading it anywhere a retail account can actually trade.

## H-002 VWAP — in progress (opened 2026-08-31)

Mechanism, literature and the model families are written up in
`strategies/vwap/notes.md`. Short version: VWAP is the benchmark institutional
execution is graded against, so there is continuous flow tied to the line all
session — a much better fit for 24h markets than ORB's once-a-day auction.

### Stage 1 — five families, 9 markets, 287,712 backtests

Families: trend/stop-and-reverse, band fade, band breakout, VWAP reclaim, first
pullback. Three session anchors, band widths 1.0-3.0 sigma, both fill assumptions,
0x/1x/2x/3x cost.

**The headline was PF 2.932 on BTC and it was an artefact.** All 119 configurations
clearing PF 1.20 were `fill_mode=0` — a resting limit at the band, which assumes a
wick touch fills you. That is precisely the failure `~/trading-bots` documented
(band fade backtested 3.0, traded live 0.7). With honest fills — close beyond the
band, entry at the next open — **zero** configurations cleared 1.20 anywhere, and
BTC's best fell from 2.932 to 0.876.

Building both fill assumptions into the engine from the start caught this on the
first pass. Every band result from here reports the honest number.

Partial corroboration of the old repo: in the trend family the top two markets are
XAUUSD (0.871) and USDJPY (0.842), with BTC last at 0.554 — exactly the ordering
`~/trading-bots` recorded. The ranking replicates; the level does not clear breakeven.

### Stage 2 — paper-faithful trend, rolling VWAP, ORB's surviving filters

Three gaps closed: the Zarattini trend variant has no stop (only the VWAP cross),
stage 1 always carried one; rolling-window VWAP was untested; and the two filters
that lifted a median on ORB (relative volume, volatility regime) were untested here.
18,816 configs per market, honest fills only.

**This is materially better than anything ORB produced.** 805 configurations clear
PF 1.20 at 1x cost, and **101 still clear it at 2x cost** — ORB had zero at 2x on any
market. Median 2x profit factor of the gate-clearers is 1.034. 23 configurations reach
PF 1.6. Best: XAUUSD 2.087 (break, 4-day rolling anchor), BTC 1.730 (reclaim).

Caveat carried forward: the PF>=1.6 group trades 0.13-0.29 times a day, which fails
the phase constraint the same way ORB's winners did. The trend family at the 00:00
anchor is the only high-frequency group (1.6 trades/day, best 1.426).

### Stage 3 — timeframes and a null benchmark (running)

FX and metals rebuilt from the cached 1-minute files at 5m/15m/30m/1h/4h via
`core/fx_data.build_tf`; BTC resampled from 15m. Hold horizons specified in hours and
converted per timeframe so they mean the same thing everywhere.

**Method addition: every grid is also run on a phase-randomised copy of the same
market** — real returns, shuffled, so the distribution survives and the sequence does
not. Any edge is destroyed by construction, so whatever maximum profit factor the
search still produces is the score a live result has to beat. Early readings:

| market | tf | real best | real >=1.6 | null best | null >=1.6 |
|---|---|---|---|---|---|
| BTCUSDT | 1h | 1.952 | 13 | 1.254 | 0 |
| BTCUSDT | 4h | 2.777 | 105 | 1.701 | 2 |
| XAUUSD | 5m | 1.864 | 32 | 1.310 | 0 |
| XAUUSD | 1h | 2.392 | 37 | 2.038 | 3 |
| XAUUSD | 4h | 1.920 | 44 | 1.877 | 7 |
| EURUSD | 15m | 1.309 | 0 | 1.804 | 2 |

### Stage 3 complete — 44 market x timeframe combinations, real vs shuffled

Two conclusions. **A PF of 1.6 is reachable by pure search noise on this
dataset** — shuffled gold at 1h produced 2.038 and shuffled EURUSD 15m produced 1.804,
beating the real data. A single high profit factor is therefore not evidence of
anything on its own. **But some combinations separate cleanly**: gold at 5m has 32
real configurations above 1.6 against zero in the null, and BTC at 1h has 13 against
zero. The count above the null, not the headline maximum, is the statistic to chase.

Final stage 3 numbers: the shuffled markets produced **86 configurations above PF 1.6**,
topping out at **2.412**. The real markets produced 290. **16 of 44 market x timeframe
combinations beat their own null** on both the maximum and the count above 1.6.

Ranked by how far the real maximum exceeds its null:

| market | tf | real best | real >=1.6 | null best | null >=1.6 | edge | trades/day |
|---|---|---|---|---|---|---|---|
| Bitcoin | 4h | 2.777 | 105 | 1.701 | 2 | +1.076 | 0.10 |
| Bitcoin | 1h | 1.952 | 13 | 1.254 | 0 | +0.698 | 0.14 |
| Bitcoin | 15m | 1.730 | 2 | 1.031 | 0 | +0.699 | 0.16 |
| Gold | 5m | 1.864 | 32 | 1.310 | 0 | +0.554 | 0.10 |
| USDCHF | 1h | 1.694 | 4 | 1.187 | 0 | +0.507 | 0.13 |
| Gold | 30m | 2.014 | 15 | 1.579 | 0 | +0.435 | 0.14 |
| Gold | 1h | 2.392 | 37 | 2.038 | 3 | +0.354 | 0.09 |

**A caution that applies to every row: trades per day is 0.09-0.28.** The strongest
configurations in this whole study trade roughly once a week. That is the same defect
that disqualified every ORB winner, and it is present here before out-of-sample testing
has even started. A 2.777 profit factor on 0.10 trades a day cannot clear an 8% target
inside the current phase window no matter how real it is.

Also note Gold at 4h: real 1.920 against a null of 1.877. The gap is +0.043 — that
combination is indistinguishable from noise despite a headline near 2.0.

**Nothing here is a result yet.** Fill realism, cost stress and the null benchmark are
passed. Out-of-sample, walk-forward, the prop-challenge simulation and the NautilusTrader
cross-check are all still to run, and those are the four tests that killed every ORB
candidate.

### Stage 4 — three challenge profiles (2026-08-31)

Kris asked for a safest / moderate / riskiest configuration with PF, CAGR, drawdown and
time to pass. Method: candidates ranked on the FIT window only (2023-09 -> 2025-09), then
every number measured on the test year and the full period. Prop simulation opens a fresh
account every trading day, fixed risk, real breaches, 400-day limit.

| profile | market | tf | risk | PF fit | PF test | CAGR | max DD | pass | breach 8% | median days |
|---|---|---|---|---|---|---|---|---|---|---|
| Conservative | XAUUSD | 15m | 0.50% | 1.570 | 2.489 | 24.0% | -5.9% | 96% | 0% | 127 |
| Moderate | XAUUSD | 5m | 0.75% | 1.554 | 1.915 | 34.4% | -7.6% | 82% | 13% | 50 |
| Aggressive | XAUUSD | 5m | 2.00% | 1.554 | 1.915 | 68.8% | -13.2% | 44% | 23% | 18 |
| Diversifier | BTCUSDT | 1h | 0.75% | 2.403 | 1.355 | 24.6% | -7.8% | 54% | 25% | 51 |

Moderate and Aggressive are the SAME configuration at different risk — sizing is the lever,
not the strategy. All are band-break on a rolling VWAP anchor, honest fills, no breakeven
stop and no retest entry (H-001 proved both destroy edge).

**Every profile improved on the test year it was not chosen on** (1.570->2.489,
1.554->1.915), which is the opposite of the ORB signature. The BTC diversifier decayed
(2.403->1.355) and is the weakest of the four.

**Three reasons these are candidates and not a plan:**
1. No walk-forward yet. That is the only test with no hindsight in it and the one that
   killed every ORB candidate.
2. Frequency: 0.14-0.36 trades/day, so 18-127 days to pass against a phase target of ~14.
   Only the Aggressive profile fits the window, and it passes only 44% of the time.
3. Three of four are gold. Running them together is one bet, not a book.

Selection bias remains despite the fit/test split: the top three per market/timeframe were
carried forward on fit-window profit factor, but the final three were chosen using
full-period pass rates. A clean version would choose the profile inside each walk-forward
fold.

### Stage 5 — combining markets (2026-08-31)

Kris asked whether trading two or more assets on different timeframes would speed up a
challenge, aiming to pass in a week. Nine legs, one per market, best config per market as
ranked on the fit window. 255 books, six risk levels, 8% and 5% targets.

**The legs are effectively independent: mean pairwise correlation of daily R is 0.023.**
Only one pair exceeds 0.25 (NZDUSD 4h / GBPUSD 4h at 0.29). That is what makes combining
work — the drawdowns do not stack, so the same risk budget can be spread across more
trades.

**Scaling, 8% target, drawdown held inside the 8% cap:**

| legs | risk | CAGR | max DD | pass rate | median days | pass in 14d |
|---|---|---|---|---|---|---|
| 1 | 0.75% | 24.8% | -7.8% | 55% | 52 | 1.0% |
| 2 | 1.00% | 35.3% | -8.0% | 59% | 39 | 4.1% |
| 3 | 1.00% | 40.7% | -7.4% | 67% | 30 | 8.6% |
| 4 | 1.00% | 44.3% | -7.2% | 62% | 28 | 12.0% |

Going from one market to four nearly halves the median time to pass, raises CAGR from 25%
to 44%, and does it at a **smaller** drawdown. That is the diversification working exactly
as intended, and it is the strongest structural result in the project so far.

**On the one-week goal: no.** The arithmetic first. Gold 5m alone trades 2.5 times a week,
so hitting 8% inside a week needs 12.9% risk per trade — one loser ends the account. Four
combined legs trade ~10 times a week, which brings the requirement down to 3.2% per trade;
still enough that three losers breach the 8% cap.

The simulation agrees. On the easier **5% target** the best four-leg book passes within
seven days **1.6% of the time**, with a median of 24 days and 46% through inside thirty.
Best case found anywhere for a seven-day pass was 2.8%.

**Honest expectation: three to four weeks per challenge, ~60-75% pass rate.** One week is
the tail of the distribution, not a plan. Note also that a book of four best-of-market legs
carries four times the selection bias of one leg — combining improves the risk profile, it
does not launder the selection.

Silver (XAGUSD) was requested for a gold/silver pair and is still downloading; the best
metal+crypto book found so far is BTCUSDT 1h + XAUUSD 1h + NZDUSD 4h + USDCAD 1h.
