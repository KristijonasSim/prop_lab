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

### Stage 6 — walk-forward (2026-09-01)

The test every H-002 number was waiting on. Quarterly folds, train on the trailing
12 months, trade the next 3, roll. The configuration is chosen on the train slice
only and re-chosen every fold, never carried forward. **The filter is re-chosen
inside the fold too** — the H-002 filter set came from a study on overlapping
data, so holding it fixed would have left that selection bias in.

Two choices the ORB walk-forward did not have to make, both run rather than
picked in advance:

* **Trade-count floor.** ORB used 100 train trades. H-002's strongest
  configurations trade 0.09-0.28 times a day, so a 100-trade floor over twelve
  months excludes exactly what stage 3 found. Floors of 30 and 100 both run.
* **Single best vs top ten.** Taking the highest train profit factor is the
  highest-variance possible choice; trading the top ten equally weighted is the
  same information with the selection noise averaged down.

44 market x timeframe combinations x 4 selection rules = **176 stitched
out-of-sample series**.

#### The family result

| | median PF | best | cells >=1.20 | share >1.0 | combos clearing 1.20 under all 4 rules |
|---|---|---|---|---|---|
| real | **0.909** | 1.832 | 41/176 | 36.4% | **4** / 44 |
| phase-randomised | 0.756 | **2.496** | 6/176 | 11.4% | 1 / 44 |

**H-002 does not survive walk-forward as a family.** The median stitched series
loses money and only a third are above breakeven. That is the honest headline and
it is the same shape as ORB, just less severe.

The null benchmark says the survivors are not purely search noise: 41 cells clear
the gate against 6 shuffled, and 4 combinations clear under every selection rule
against 1 shuffled. But note the shuffled maximum — **2.496, higher than the real
maximum of 1.832**, and produced by a combination (XAUUSD 1h) that cleared 1.20
under all four rules on randomised data. A high walk-forward profit factor is
still not proof on its own. The count above the null is the statistic; the
headline is not.

#### The two legs that hold up

Of the four combinations clearing under all four rules, two lose money on the
recent window and are dropped:

| leg | quarters | PF | PF 2x | quarters >1 | R since 2024-09 | keep? |
|---|---|---|---|---|---|---|
| BTCUSDT 4h | 30 | 1.502 | 1.239 | 23/30 | +42.7 | yes |
| XAUUSD 5m | 7 | 1.669 | 1.466 | 6/7 | +105.6 | yes |
| BTCUSDT 30m | 30 | 1.387 | 1.006 | 19/30 | **-34.2** | no |
| BTCUSDT 1h | 30 | 1.229 | 1.005 | 19/30 | **-47.8** | no |

BTC 30m and 1h clear the gate over thirty quarters purely on pre-2024 performance.
That is worth stating plainly: **a walk-forward that passes over a long span can
still be describing a regime that has ended.** Splitting the stitched series by
recency is now part of the method.

**BTCUSDT 4h is the strongest result the project has produced.** Profit factor by
calendar year, config chosen blind every quarter:

| 2019 | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 | 2026 |
|---|---|---|---|---|---|---|---|
| 2.091 | 1.473 | 1.175 | 1.099 | 1.612 | 1.549 | 1.954 | 1.554 |

Positive in every year, through two bull markets and a bear market. 895 trades,
1.239 at 2x cost, 97th percentile of the null distribution, and its own shuffled
twin scores 0.797-0.845.

**The filter the fold picked was `rvol>1.5` in 22 of 30 folds.** Nothing forced
that; the selection was free to choose any of five filters or none. This is the
third independent time in two repos that a participation measure is the only
filter family that carries anything.

#### What it still fails

| field | BTC 4h alone | two-leg book (BTC 4h + gold 5m), 2024-09+ |
|---|---|---|
| PF 1x / 2x | 1.502 / 1.239 | 1.435 / 1.218 |
| trades/day | 0.33 | 0.65 |
| avg hold | 4.6h | — |
| win rate | 45.4% | — |
| avg R | +0.170 | — |
| max DD at 0.75% risk | **-28.9%** | **-5.6%** |
| Sharpe | 0.98 | 1.53 |
| **days to target** | **121.7** | **128** |
| prop pass rate @0.75% | 83% | 82% |
| max-loss breach rate | 8% | **0%** |

Two hard failures against the current phase:

1. **Speed.** 119-201 days to reach 8%. The phase constraint is ~14. Nothing in
   H-002 resolves inside a fortnight, and the arithmetic in stage 5 already said
   why: 2.3 trades a week cannot compound to 8% quickly at a survivable risk.
2. **Drawdown, for the single leg.** BTC 4h on its own draws down 28.9% at 0.75%
   risk — three and a half times the 8% cap. Only the two-leg book brings it
   inside, and it does so by halving the size of each leg.

#### Stage 5's diversification result does not survive

The four-leg book, rebuilt from walk-forward trades on the window every leg
shares, scores **1.018-1.222** — against 1.435 for the two legs that actually
hold. Adding the pre-2024-only BTC legs drags the book to breakeven. The 0.023
leg correlation from stage 5 was real, but correlation between legs is worthless
when two of the legs have no current edge. **Diversification improves the risk
profile of an edge; it does not create one, and it does not launder selection.**

#### Verdict

H-002 is not rejected the way H-001 was, and it is not a candidate for real money
either. One market x timeframe — BTC 4h — has a walk-forward record that beats
its own null benchmark, holds at 2x cost, and is positive in eight consecutive
calendar years. That is the first thing in this project to reach that bar. It is
also one cell out of 176, too slow for the current phase by an order of magnitude,
and too volatile to run alone under an 8% cap.

Still outstanding: a NautilusTrader cross-check of the VWAP kernel, and silver
(XAGUSD), which finished downloading overnight and has not been tested.

### Correction — the risk level was chosen badly (2026-09-01)

Kris queried the "102 expected days to pass" on the strategy board. The number was
arithmetically right but the *setup* behind it was wrong, in two ways.

**The risk level was arbitrary.** Stage 4 used 0.75% per trade, and the board
inherited it without asking whether it was the right choice. It is not. Sweeping
the two-leg walk-forward book across risk levels:

| risk | pass | breach 8% | breach 4% daily | still open at 400d | median days | expected days | peak DD |
|---|---|---|---|---|---|---|---|
| 0.50% | 75.9% | 0.0% | 0.0% | 24% | 149 | 196 | -3.6% |
| 0.75% | 85.0% | 0.0% | 0.0% | 15% | 81 | 95 | -5.5% |
| **1.00%** | **85.2%** | **0.0%** | **0.0%** | 15% | **64** | **75** | **-7.3%** |
| 1.25% | 82.8% | 2.4% | 0.0% | 15% | 53 | 64 | -9.1% |
| 1.50% | 80.8% | 4.6% | 0.0% | 15% | 43 | 53 | -10.9% |
| 2.00% | 73.7% | 20.2% | 0.0% | 6% | 30 | 41 | -14.6% |
| 3.00% | 59.6% | 28.6% | 6.6% | 5% | 17 | 28 | -21.9% |

**1.00% dominates 0.75% outright** — higher pass rate, 17 fewer days, same zero
breach rate. There was no trade-off being made, just an unexamined default.
Going faster than that is possible but is genuinely paid for: 1.50% reaches a
funded account in 53 expected days but draws down 10.9%, past the cap it is
supposed to respect.

**The first automated pick was also wrong**, and the way it was wrong is worth
recording. Selecting purely on fewest expected days chose 1.50% — whose equity
curve draws down 10.9% while the simulation still reported only a 4.6% breach
rate. Those are consistent, not contradictory: each challenge account starts on
its own day and stops at a pass or a breach, so most accounts are finished before
they ever meet the worst stretch of the curve. **A low breach rate on
short-lived accounts is not evidence that the drawdown fits the cap.** The
selector now requires peak drawdown inside 8% as well, which picks 1.00%.

Board numbers are now read from `backtests/vwap/stage7_board.json`, written by
`stage7_wf_analysis.py`. Nothing on the board is hand-copied any more — the
84-day figure that prompted this was a literal in the collector, which is exactly
where a stale number survives a re-run.

Net effect: expected days to a funded account 102 -> 75, and H-002's board score
7.1 -> 7.7. It still fails the ~14-day phase gate by a factor of five.

### ORB re-scored on walk-forward output (2026-09-01)

The strategy board was scoring H-001 on a *fitted* configuration (PF 1.019 from
the stage 5 prop simulation) while scoring H-002 on walk-forward output. That is
not a comparison, and it flattered ORB: the fitted config trades ~1x/day and
produced a 9-day median time to pass, which read as "fast".

Stage 12 had already walk-forwarded the filtered ORB family but discarded the
trades, keeping only per-quarter summaries. `stage14_board.py` re-runs the
identical folds, grid and selection rule and keeps the trade series, so both
hypotheses are now scored on the same kind of evidence.

The honest ORB numbers: **PF 1.165 over 470 trades, 0.169 trades/day, 13 of 31
quarters above breakeven, PF 0.851 at 2x cost.** Across the risk ladder:

| risk | pass | killed | unresolved at 400d | median days | expected days | peak DD |
|---|---|---|---|---|---|---|
| **0.25%** | 2.6% | 0% | **97%** | 202 | 7,819 | **-7.9%** |
| 0.50% | 29.7% | 17% | 54% | 132 | 443 | -15.8% |
| 1.00% | 42.1% | 52% | 6% | 114 | 271 | -31.5% |
| 2.00% | 42.1% | 58% | 0% | 59 | 140 | -63.0% |
| 4.00% | 7.5% | 92% | 0% | 27 | 358 | -126.1% |

**0.25% is the only level whose drawdown fits inside the 8% cap, and at that size
97% of accounts never resolve at all inside 400 days.** Every level fast enough
to finish breaches the cap, most of them several times over. Board score 2.5/10.

This also corrects the earlier reading that "ORB is faster than VWAP at 25
expected days". That number came from the fitted config and was an artefact of
enormous variance — 64% of those accounts died. On walk-forward output ORB is
both slower and worse in every column.

**Infrastructure**: risk-ladder and prop simulation now live in
`core/riskladder.py`, and the board record is written by `core/board.py`. Hand
either one a stitched walk-forward trade series and a hypothesis gets the same
simulation, ladder and score as everything already on the board.
`core/build_scoreboard.py` has no per-strategy code left — it reads whatever
`backtests/*/board.json` files exist.

## H-003 EMA × VWAP cross — rejected (2026-09-01)

Kris's hypothesis, from his own gold chart: EMA200 and VWAP on the same panel,
enter when the EMA crosses the VWAP, long on a cross up and short on a cross
down. Exits open, timeframes 3m to 1d.

### Mechanism, stated before any result

VWAP is the day's volume-weighted average cost basis; the EMA is the medium-term
average price. The EMA crossing above VWAP says the recent average has moved
above what the day's participants actually paid, so the marginal holder is in
profit and dips get bought. On the other side: traders short from below VWAP,
and anyone benchmarking execution to VWAP who now has to chase.

**Honest assessment of that mechanism, recorded in advance: weak.** Both lines
are lagging averages of the same price series. The cross carries no information
the price does not already have — it is a smoothed momentum trigger. VWAP holds
the only real mechanism; the EMA contributes smoothing and lag.

Research support was thin. The EMA/VWAP combination is used almost everywhere as
a *confirmation filter* ("only long when price is above both"), not as a
standalone cross trigger. No credible profit factors published; the one
"incredibly profitable" claim found was measured on Heikin-Ashi candles, which
are not tradeable prices.

**Why it was worth testing anyway:** frequency. Every idea in this project has
died on speed. A 3-15m EMA crossing a daily-anchored VWAP looked like the first
mechanic that might trade 1-3 times a day.

### What the screen found — 284,544 backtests

All four exits, the slope filter paired on and off, seven timeframes, both VWAP
anchors, three EMA lengths, nine markets, at 1x / 2x / 3x cost.

| | configs | median PF | best | clear 1.20 |
|---|---|---|---|---|
| real | 39,927 | **0.705** | 2.512 | 1,231 |
| phase-randomised | 42,723 | **0.757** | 2.478 | 981 |

**The real markets score worse than randomised copies of themselves on the
median.** Only 16 of 52 market × timeframe combinations have a real median above
their own null.

By exit — all five variants Kris asked for:

| exit | median PF | best | clear 1.20 | trades/day |
|---|---|---|---|---|
| A — EMA crosses back through VWAP | 0.740 | 2.512 | 508 | 0.32 |
| B — price closes back through EMA | 0.619 | 2.273 | 236 | 0.32 |
| C — fixed R multiple | 0.699 | 2.298 | 378 | 0.30 |
| D — session close, flat overnight | 0.754 | 2.266 | 109 | 0.30 |

**Variant E, the slope filter, is negative**: paired across 16,909 configurations,
median 0.698 → 0.674, a lift of −0.024, with only 49.2% improving. It joins
breakeven stops and retest entries on the list of universally-recommended
improvements that lose money here.

**The frequency thesis failed, and failed backwards.** 3m does reach 0.63
trades/day, but its median profit factor is the worst of any timeframe (0.600),
and on gold specifically 3m real (0.689) sits *below* its own null (0.820). The
faster the timeframe, the worse the edge. At 2x cost, **zero** configurations
clear PF 1.20 with a trade frequency of 0.5/day or better. On 1d, no
configuration reached even 50 trades in three years.

### Walk-forward, and the null that killed it

48 combinations × 4 selection rules = 192 stitched out-of-sample series, same
shape as H-002's so the numbers are comparable.

| | cells | median | best | clear 1.20 | clear at 2x | clear under all 4 rules |
|---|---|---|---|---|---|---|
| real | 192 | 0.808 | 2.356 | 10 | 6 | **1** |
| phase-randomised | 198 | 0.791 | 1.760 | **17** | **9** | **2** |

**The null produced more gate-clearing cells than the real data, and more
survivors.** The two shuffled survivors are also stronger than the single real
one: worst-across-rules 1.659 and 1.565, against 1.271.

The one real survivor is gold at 1h, and on its own it looks excellent: stitched
PF **2.356** at floor 30 / top 10, **2.117 at 2x cost**, 7 of 7 quarters above
breakeven, 1,044 trades, 1.64 trades/day — the best trade frequency any candidate
in this project has produced. It also beats its own shuffled twin decisively
(2.356 against 0.596 at the identical rule).

**And it is still not evidence.** One survivor out of 48 combinations is what the
null gives you — the null gave two. There is no way to distinguish "gold 1h is
real" from "gold 1h is the lucky cell" with this data. Compare H-002, which found
4 real survivors against 1 shuffled, and 41 gate-clearing cells against 6. That
is a margin; this is not.

### What this changed about the scoring

H-003 initially scored **7.0/10** on the board — "Strong candidate" — off gold
1h's 2.356 profit factor and its perfect 7-of-7 quarters. That was a hole in the
rubric: the null margin was one of four equal parts of the evidence component, so
a strategy that **lost** to its null could still score 0.75 on evidence.

Two changes, both in `core/scorecard.py`:

* the null margin now carries **double** the weight of the other evidence parts;
* a **null gate**: a hypothesis that has not beaten its own null benchmark cannot
  score above 4.0, regardless of everything else. `beats_null` is stated
  explicitly by each strategy rather than inferred from a margin, because
  "measured and lost" and "never measured" both produce a margin of zero and both
  must fail.

H-003 now scores 4.0 and the board says why. H-002 is unaffected at 7.6.

### Verdict

**Rejected.** Add to the known-dead list: EMA × VWAP cross, all four exit rules,
3m to 1d, nine markets — the family scores below its own null benchmark. The
gold 1h pocket is logged as the one thing that would be worth re-testing if
genuinely fresh out-of-sample data ever exists, but nothing should be built on it.

This is the third price-geometry hypothesis to fail in this repo, after ORB and
the breakout family. The standing pattern from `~/trading-bots` now has one more
data point: **every leg that ever worked came from a data feed — funding, open
interest, taker delta, long/short ratio — not from a price pattern.** H-004
should be a data-feed idea.

## Improvement pass on H-002 and H-003 (2026-09-01)

Kris asked for both to be deep-improved with everything the repo has learned.
Two levers were worth testing, both from findings already established here rather
than from a fresh search: **participation (rvol)**, the only filter family that
has ever lifted a median in this project, and **time of day**, since H-001 found
the NY cash open was the only session anchor carrying anything and Asia the
worst region. Neither had been tested on H-002 or H-003.

Both were scored the only honest way: a paired lift on the MEDIAN, running the
identical configuration family with the lever off and on.

### The levers

| lever | H-002 lift | improved | H-003 lift | improved |
|---|---|---|---|---|
| rvol > 2.5 | **+0.063** | **64.6%** | +0.073 | 67.1% |
| rvol > 2.0 | +0.047 | 62.6% | +0.068 | 68.6% |
| rvol > 1.5 | +0.038 | 49.8% | **+0.076** | **71.7%** |
| rvol > 1.0 | +0.025 | 56.2% | +0.071 | 74.6% |
| NY 13-20 | +0.010 | 51.0% | +0.006 | 58.7% |
| London 07-16 | +0.012 | 52.0% | +0.046 | 65.9% |
| Asia only (control) | +0.002 | 49.9% | +0.003 | 52.1% |
| long only | -0.008 | 46.1% | +0.013 | 55.3% |
| short only | -0.011 | 46.6% | -0.023 | 44.2% |

**Participation confirmed for a fourth time, and we had been using it too
weakly.** H-002's walk-forward grid only offered `rvol > 1.5`, which lifts the
median but improves barely half the configurations — a coin flip. `rvol > 2.5`
improves 64.6%. Thresholds 2.0 and 2.5 were added to the grid.

**Time of day does NOT transfer from H-001.** NY windows lift +0.010 at ~51%
improved on H-002, and the Asia-only control — which ORB said should be the worst
region — is flat at +0.002. That finding is specific to ORB's mechanic, not a
property of these markets. No hour filter was added to either grid.

**Direction filters are negative on H-002**, so ORB's long/short asymmetry does
not transfer either.

### A null benchmark that was too weak, and the fix

The first re-run showed H-002's survivors going 4 → 6 while the null's went
1 → 0, which looked like a large improvement. It was partly an artefact **of my
own benchmark**.

`shuffle_market` permutes volume *independently* of returns. On real gold 1h the
correlation between |return| and volume is **+0.47**; on that null it is
**-0.003**. So the null has no volume/return relationship at all, and any
participation filter automatically looks predictive against it — while
participation was exactly the lever just added. The benchmark was rigged in the
strategy's favour without anyone intending it.

`shuffle_market_paired` permutes **(return, volume) as pairs**. Each bar keeps
its own volume, so the contemporaneous relationship survives (verified: +0.4704,
identical to real) and only the sequence is destroyed. A participation filter
that beats this null is finding something about regime and ordering, not just
"high-volume bars are bigger bars".

It is measurably harder, as expected:

| | cells >= 1.20 | at 2x | survivors under all 4 rules |
|---|---|---|---|
| real | **39** | **17** | **6** |
| null, independent volume | 6 | 2 | 0 |
| null, **paired** volume | 11 | 5 | **0** |

**H-002 clears the harder benchmark.** All scoring now uses the paired null
where it exists.

### H-002 after the improvement

| | before | after |
|---|---|---|
| survivors (all 4 selection rules) | 4 | **6** |
| cells clearing 1.20 at 2x cost | 12 | **17** |
| best stitched PF | 1.832 | **2.745** |
| book | 2 legs | **6 legs** |
| R earned per day | +0.083 | **+0.121** |
| expected days to a funded account | 75 | **59** |
| board score | 7.6 | **8.0** |

The book is now BTC 15m/30m/1h/4h + gold 5m/30m. **All six legs are positive
since 2024-09**, including BTC 30m and 1h, which were dropped last round for
losing 34R and 48R on that window — with a participation filter they are among
the strongest. The folds chose a participation filter in **498 of 536** fold
selections, `rvol > 2.5` in 332 of them, with nothing forcing it.

Still 59 days against a ~14-day phase gate.

### H-003 after the improvement — still rejected

The slope filter (variant E) was removed for being proven negative, and `min_rvol`
added in its place. The result is the textbook signature of a filter that shrinks
a sample rather than finding signal:

| | before | after |
|---|---|---|
| cells clearing 1.20 | 10 | 15 |
| best stitched PF | 2.356 | **4.292** |
| **survivors under all 4 rules** | **1** | **1** |

The maximum nearly doubled; the survivor count did not move. And against the null
— the *weaker* one, which favours volume filters — the real data still loses:
**15 real cells against 17 null cells, 1 survivor each.** The paired null was not
run for H-003 because it can only be harder, and a result that already loses to
the weak benchmark cannot beat the strict one.

A separate guard was added while doing this: the board's "fewest expected days"
rule had picked a **55-trade** cell whose headline profit factor was 4.292 — the
narrowest, luckiest slice the new filter produced. Board candidates now require
at least 150 trades.

**H-003 stays rejected and is closed.**

### Correction — the improvement pass broke the cost gate (2026-09-01)

Kris pushed back on the board showing 23.66 trades/day with a 59-day time to
pass, and asked for an independent recalculation. Two things came out of it, one
a presentation failure and one a real error.

**The presentation failure.** 23.66 trades/day was never a trading plan. It was
six markets times the top TEN configurations each — sixty parallel strategies,
each risking one sixtieth of the per-trade risk. Averaging the top ten is a
legitimate way to damp selection noise in research, but putting it on the board
as the headline implied a book nobody would run. The tradeable construction is
one configuration per market.

**The real error.** Leg selection required a stitched profit factor of 1.20
under all four selection rules **at 1x cost only**. The project's gate is 1.20
at *double* cost, because costs are an assumption until a firm is picked. Checked
properly, four of the six legs collapse on their own at 2x:

| leg | PF 1x | **PF 2x** | R/day | maxDD (R) |
|---|---|---|---|---|
| BTCUSDT 15m | 1.587 | **1.067** | 0.246 | 60.3 |
| BTCUSDT 1h | 1.453 | **1.017** | 0.180 | 44.8 |
| BTCUSDT 30m | 1.386 | **0.939** | 0.133 | 21.6 |
| XAUUSD 30m | 1.297 | **1.025** | 0.118 | 47.2 |
| BTCUSDT 4h | 1.504 | 1.214 | 0.064 | 10.0 |
| XAUUSD 5m | 1.439 | 1.243 | 0.110 | 18.1 |

The six-leg book scored **1.053 at 2x** — it fails the gate outright. Searching
all 63 subsets, **only 3 hold PF 1.20 at 2x**: BTC 4h + gold 5m (1.233), BTC 4h
alone (1.214), gold 5m alone (1.243). The best of them is the same two-leg book
that existed *before* the improvement pass.

So the widened rvol grid did not find four new legs. It found four legs whose
edge is smaller than the cost assumption, and the 1x-only selection rule let them
in. The board reported a faster book that was less robust, which is the wrong
trade in this project.

**Corrected board candidate**: BTCUSDT 4h + XAUUSD 5m, one configuration each,
re-chosen blind every quarter, 1.00% risk.

| | pre-improvement | wrong 6-leg book | corrected |
|---|---|---|---|
| PF | 1.435 | 1.441 | **1.461** |
| PF at 2x | 1.218 | **1.053** | **1.233** |
| parallel strategies | 20 | 60 | **2** |
| trades/day | 6.85 | 23.66 | **0.67** |
| expected days to funded | 75 | 59 | **61** |

The rvol widening *is* a real improvement — same two legs, better configurations
chosen inside the folds, 75 days down to 61 with a slightly better 2x figure. It
is just far smaller than the six-leg book made it look.

**The governing identity**, which is what makes trades/day irrelevant:

    days to target  =  maxDD (in R) / R earned per day  x  (target / cap)

Trades per day does not appear. It enters only through R per day, and splitting
the same edge across more parallel strategies divides R per trade by exactly the
number added. For the corrected book: 13.20 R / 0.139 R per day = 95 days at
topn=1 across six legs; 7.5 R / 0.084 = 61 expected for the two-leg book after
the simulation's survivorship. Passing in 14 days needs 6.8x more R per day or
6.8x less drawdown.

`core/verify_board.py` recomputes all of this from the raw trade file with no
imports from `strategies/` or the rest of `core/`, printing every step, so the
numbers can be checked by someone who does not trust this pipeline.

**Also corrected**: the top verdict band read "Trade it" at 8.0+. That breaks the
standing rule that nothing here is called good, ready or worth real money on a
backtest. It now reads "Best evidence so far — still not proven live".

### H-002 improvement — select by 2x cost inside the fold (2026-09-01)

Kris asked to try making the three board hypotheses better. H-001 and H-003 were
already rejected for structural reasons, so the live work went into H-002. Two
changes were tested, both constrained by the same gates as the board:

1. **Silver (XAGUSD)** was added to the VWAP universe and rebuilt from the cached
   Dukascopy raw files at 5m/15m/30m/1h/4h. It did not help. Best silver rows:
   XAGUSD 1h floor 30/top 10 scored PF 1.452 and PF2x 1.221, XAGUSD 15m floor
   30/top 1 scored PF 1.365 and PF2x 1.223, but no silver timeframe cleared the
   PF 1.20 gate under all four selection rules. The high-frequency 5m rows were
   below breakeven. Silver is tested, not a board leg.
2. **The fold selector now ranks configs by train PF at double cost**, not by
   train PF at 1x cost. This directly attacks the bug that let the false six-leg
   book in: selection was happening on a cheaper market than the acceptance gate.

The 2x selector was run only on the current candidate set and the previously
tempting faster legs: BTCUSDT 15m/30m/1h/4h, XAUUSD 5m/30m, XAGUSD 15m/1h.
This is a targeted refinement, not a fresh 44-combo family search.

**Real data result:** 6 of 8 target combinations clear PF 1.20 under all four
selection rules: BTC 15m/30m/1h/4h and XAU 5m/30m. XAG still fails. Under the
same 2x selector, the paired-volume null produced **0 robust survivors and 0
cells clearing PF2x 1.20**. The improvement is not explained by the stricter
null.

Best tradeable subset, one configuration per leg, common 2024-09+ window:

| | previous corrected | 2x-selector |
|---|---|---|
| legs | BTC 4h + XAU 5m | BTC 30m + BTC 4h + XAU 30m + XAU 5m |
| PF | 1.461 | **1.646** |
| PF at 2x | 1.233 | **1.313** |
| trades/day | 0.67 | **1.58** |
| R/day | +0.084 | **+0.146** |
| max DD at picked risk | -7.5% | -7.6% |
| pass rate | 85.2% | 85.8% |
| median days | 52 | **45** |
| expected days to funded | 61.1 | **52.5** |
| board score | 8.0 | **8.5** |

This is a real improvement: more R/day at the same drawdown envelope, better
2x-cost robustness, and a strict paired-volume null that does not reproduce it.

It still fails the phase. Fifty-two expected days is materially better than
sixty-one, but still nearly four times the 14-day target. Getting from here to
14 days requires another ~3.75x improvement in R/day at the same drawdown, or a
firm/challenge structure that accepts a slower resolution. The next honest work
is not another price-only filter; it is either a NautilusTrader execution
cross-check of this VWAP kernel or new data-feed inputs (open interest, taker
delta, basis) collected prospectively.

## H-004 funding-rate fade — rejected (2026-09-01)

First data-feed hypothesis, chosen because the standing pattern across both repos
is that every leg that ever worked came from a feed rather than a price pattern.

**Mechanism, stated before results.** Perpetual funding is a cash transfer every
8 hours between longs and shorts. Strongly positive funding means leveraged longs
are paying shorts to stay in: the book is crowded and impatient. Fading it means
being paid to take the other side of stretched positioning and collecting the
funding while waiting. Unlike a price pattern, the counterparty is named and the
flow is observable.

**Data**: BTC/ETH/SOL perps, 7,645 funding settlements from 2019-09, 61k hourly
bars. No look-ahead — a settlement is visible only after it lands, and the
z-score baseline is shifted so a settlement is not part of its own reference.
Funding payments are credited into the R multiple, since ignoring them would
understate a carry trade.

**The null was built for this hypothesis specifically.** The claim is that
*funding predicts price*, so the null permutes the funding series against real,
untouched price: same funding distribution, same price path, relationship
destroyed. Shuffling price instead would have been the wrong test — it would
have destroyed the price autocorrelation the exits depend on as well.

**Stage 1 — the widest margin any hypothesis here has produced:**

| | configs | median PF | best | clear 1.20 |
|---|---|---|---|---|
| real | 34,524 | 0.827 | **1.893** | **828** |
| null | 34,560 | 0.775 | 1.205 | **2** |

828 against 2. For comparison H-002's stage 1 was 290 against 86. Cost stress
also held better than expected: 828 at 1x, 262 at 2x, 60 at 3x.

Two warnings visible even there: **826 of the 828 are BTC alone** (ETH 2, SOL 0),
and the trade rate is 0.20/day, with **zero** configurations clearing 1.20 at 2x
cost with a usable frequency.

**Walk-forward killed it.**

| | cells | median | best | clear 1.20 | at 2x | survivors |
|---|---|---|---|---|---|---|
| real | 12 | 0.873 | **1.126** | **0** | 0 | 0 |
| null | 12 | 0.790 | 1.005 | 0 | 0 | 0 |

Nothing clears the gate under any selection rule. The best cell is BTC 1h at
floor 100 / top 1: PF 1.126, 14 of 23 quarters above breakeven, 0.41 trades/day.
The real data still beats the null on both median and maximum, so there is
*something* there — it is simply too small to trade after costs.

**The lesson worth keeping: a large in-sample margin over a null is necessary but
not sufficient.** H-004 had by far the best stage-1 null separation in the project
and still failed the moment configurations had to be chosen blind. Walk-forward
remains the only test that decides, and no amount of stage-1 evidence substitutes
for it.

**Verdict: rejected.** The mechanism remains the most credible one tested — which
is the argument for collecting **open interest and taker delta** forward. Both are
capped at roughly two days of history on Binance's public endpoint, so they cannot
be backtested today and need a collector running before they become testable.


**H-004 code deleted 2026-09-01** at Kris's request — the strategy, its backtests
and the funding/perp data files are gone. The finding stays logged here and in
`STRATEGY_LOG.md`: funding fade produced the widest stage-1 null margin in the
project (828 gate-clearing configs against 2) and still failed walk-forward with
0 of 12 series clearing PF 1.20. Re-downloadable in minutes from ccxt if ever
revisited. The forward collector for open interest and taker delta is NOT part of
this deletion and is still running.

## H-005 liquidity sweep / stop-run fade — rejected at stage 1 (2026-09-01)

Tested because the prior repo (`~/trading-bots`) recorded that the INVERSE of
breakout-retest worked, and breakout-retest itself failed here at every
timeframe. That prior was the strongest reason to test anything new.

**Mechanism**: stops cluster beyond obvious swing highs and lows. Price pushing
through one fires them as market orders — forced, price-insensitive flow. If the
push was only the stop run and not information, price returns inside the range,
and whoever absorbed the forced flow is paid for it. Same property that made
funding worth testing: a compelled counterparty.

Grid: 4 lookbacks, 4 pierce depths, wick-rejection required or not, 5 stop
placements, 5 target types, 4 hold caps, 3 participation thresholds — 9,600
configurations across 12 markets and 5 timeframes at 1x/2x/3x cost, 541,474
backtests, each against a paired-shuffle null.

| | configs | median PF | best | clear 1.20 |
|---|---|---|---|---|
| real | 541,474 | 0.718 | 1.929 | **1,702** |
| paired null | 510,197 | 0.781 | **3.858** | **19,062** |

**The null produced eleven times more gate-clearing configurations than the real
markets, and its best result was twice as good.** Only 2 of 57 market x timeframe
combinations beat their own null on the count. Cost stress is academic at that
point: 1,702 at 1x, 465 at 2x, 114 at 3x, and exactly **one** configuration
anywhere clears 1.20 at 1x with a trade rate of 0.5/day or better.

The reason the null is so strong here is worth recording: a paired shuffle
destroys sequence while keeping each bar's volume with its own return, and a
shuffled series mean-reverts around its extremes more readily than a real
trending one. A "sweep and reversion" rule is therefore *easier* to satisfy on
randomised data than on real data. That is exactly the comparison the null exists
to make, and this hypothesis fails it as clearly as any tested.

**Verdict: rejected, no walk-forward run.** Nothing that loses to its null by a
factor of eleven at stage 1 justifies the compute.

**This also revises the prior repo's finding.** `liquidity_sweep` was recorded
there as the thing that worked where breakout-retest failed. On this data, with a
null benchmark the older work did not run, it does not reproduce. Treat the old
result as unverified rather than as evidence.

### H-007 Cross-sectional crypto ranking — rejected (2026-09-01)

Requested by Kris and never started; `HANDOFF.md` predicted failure on the grounds
that time-series momentum beats cross-sectional in crypto and that coins are too
correlated. It failed, but not for that reason, and the way it failed is worth
keeping.

**The ranking carries real information.** Before costs, 95.0% of the 360 real
configurations beat PF 1.0 against 59.4% of the paired-null ones, median 1.096
against 1.009. That is a clean separation from the null — cleaner than H-003 or
H-005 ever managed. The cross-sectional ordering of five coins is not noise.

**The edge is worth about 10% on profit factor and a round trip costs more.**
Median PF by cost level: 1.096 (0x) → 0.825 (1x) → 0.618 (2x). At 14bps round
trip on a signal this weak, the only configurations that survive are the ones
that amortise the cost over a long hold — and sure enough, all 23 cells clearing
PF 1.20 at 2x are 1d bars held 7 days, 0.14 trades/day, time-to-target 400–875
days against H-002's 25. Quarterly walk-forward stitched to PF 1.168, 1.063 at
2x, under the gate, with the best of five null seeds at 1.065 — beating it.

**The generalisable finding: this hypothesis was cost-limited, not signal-limited,
and that is a different failure from every other rejected hypothesis in this
repo.** H-001, H-003, H-004 and H-005 all failed because the signal did not beat
its null. H-007 beats its null before costs and loses to the spread. Those two
failures have different cures. A signal that loses to its null is dead. A signal
that loses to costs gets better with a wider universe, because cross-sectional
dispersion grows with the number of names ranked while the cost per trade does
not — which is exactly why the published versions rank 500–7,000 names and not
five.

**What was not tested, and is the only open route:** a 50–100 coin universe.
Five high-beta majors with pairwise correlation above 0.7 is not a cross-section;
"top 1 vs bottom 1" of five names is closer to a coin-flip on dispersion than to
the published mechanic, and the long-only variant is close to a leveraged bet on
whichever alt is hottest. Testing it properly needs a data download, which
`START_HERE.md` currently forbids. Recorded here as the decision point rather
than taken unilaterally.

Caveat on the null: the spread across five shuffle seeds was wide — 0, 1, 2, 9
and 14 gate-clearing cells against the real 23. Read as a distribution, 23 is not
the clean win the mean of 5.2 suggests.

Code: `strategies/xsec/`. Results: `backtests/xsec/`. Notes:
`strategies/xsec/notes.md`.

### H-008 Beta-residual reversion — rejected at stage 1 (2026-09-01)

Built to beat H-002, on the argument that VWAP mean reversion cannot distinguish
a liquidity move from an informed one. Strip the BTC factor out of an alt, fade
what is left, and you fade only the part of the move with no reason to persist.
Four alts throwing signals is also more R per day than five single-asset legs,
and `days = maxDD_in_R / R_per_day`.

It failed as completely as anything in this repo. 1,152 configurations, **0 clear
PF 1.20 at 2x cost**, and the paired-shuffle null beats the real data on every
single cut — more configurations profitable before costs (55.4% vs 51.6%), higher
median before costs (1.005 vs 1.002), higher best at 2x (1.496 vs 0.940), more
gate-clearing cells (2 vs 0). This is the H-005 result exactly: a fade rule is
*easier* to satisfy on phase-randomised data, because shuffled series revert
around their extremes more readily than real trending ones. The risk was named in
the kernel docstring before the run and it is what happened.

**The diagnostic worth keeping is the z-response.** Median profit factor before
any costs, by entry threshold: z≥1.5 → 1.000, z≥2.0 → 0.997, z≥2.5 → 1.006,
z≥3.0 → 1.013. Flat. A three-sigma residual reverts no harder than a 1.5-sigma
one. **The size of the deviation carries no information about what happens next.**

That flat z-response is a cheap test and it should be run on every future
reversion idea before anything else is built. It costs one grid and it answers
the only question that matters — is there a mechanism — without any reference to
costs, fills, position sizing or walk-forward discipline. Had it been run first
here it would have killed H-008 in ten minutes.

**The hedge is real and far too small.** Hedged median PF before costs is 1.021
against naked 0.985, so removing BTC genuinely does leave a more mean-reverting
series. It is a 3.6% effect, and hedging crosses two spreads instead of one, so
after costs the hedged variant is the worse of the two (0.142 vs 0.482 at 2x).

**Taken with H-007, this closes a family.** H-007 ranked the majors and traded
the spread; H-008 hedged out the factor and faded the residual — continuation and
reversion on the same relative structure, in opposite directions. H-007 found a
real but tiny edge, beaten by a 14bps round trip. H-008 found nothing. Between
them they say **the relative structure of the crypto majors is not tradeable at
retail cost**, and that should not be reopened without either a much wider
universe or a much cheaper venue.

Note what this does NOT contradict. The repo's standing pattern is that every leg
that ever worked came from a data feed — funding, open interest, taker delta,
long/short ratio — and not from a price pattern. H-007 and H-008 are both derived
from price. They are the fourth and fifth price-derived hypotheses to fail here,
against zero successes. The order-flow hypothesis (H-006) is still the best
untested mechanism in the project and its recorder is now finally on cron.

Code: `strategies/resid/`. Results: `backtests/resid/`. Notes:
`strategies/resid/notes.md`.

### Prop-firm structure: two-step, and what it costs (2026-09-01)

`core/prop_rules.py` modelled a single 8% step. HANDOFF flagged that most
no-time-limit firms are two-step (8% then 5%). `core/riskladder.run_accounts_two_step`
now models the real structure: phase 2 starts the day after phase 1 clears, on
the same live series, with a fresh equity, peak and drawdown budget, and a breach
in either phase kills the account outright.

H-002's board book, 5 legs, 2024-09 → 2026-08:

| risk | one-step pass | one-step days | two-step pass | two-step days |
|---|---|---|---|---|
| 1.000% | 85.5% | 57.3 | 81.7% | 113.8 |
| 1.500% | 89.8% | 36.7 | 85.2% | 74.0 |
| 2.000% | 93.1% | 23.6 | 88.0% | 53.4 |
| 2.125% | 93.9% | 21.3 | 88.3% | **49.8** |
| 2.500% | 94.8% | 19.0 | 89.2% | 43.7 |

**Two-step roughly doubles time-to-funded.** The second 5% step is not half the
work of the first 8% one — it is a whole second chance to breach, and the
drawdown has to be survived twice. The board's headline "24 expected days" was a
one-step number and should be read as ~50.

Firm choice: **two-step on cTrader**. `CLAUDE.md` prefers cTrader outright
(Open API is real REST/WebSocket; MT5 is GUI-only with a Windows-only Python
package), this box is Linux with no working MT5 bridge, and cTrader carries both
crypto and XAUUSD — so it is the one choice that unblocks the whole book rather
than half of it. The exact percentages, minimum trading days and consistency
rules are NOT verified against any specific firm's current spec and must be
confirmed before money moves; what is modelled here is the structure.

## Every null in this project was drawn on an unreproducible seed (found 2026-09-02)

Eleven call sites seeded their shuffle with `abs(hash((sym, tf, tag))) % 2**31`.
Python randomises the hash of a **string** per process unless `PYTHONHASHSEED`
is set, so that expression returns a different number on every run. The nulls
were therefore a different random draw each time, and nothing derived from one
could be reproduced or checked.

How it surfaced: H-007 was re-run twice today on identical code and identical
data. The first run printed `beats every null seed: True` and scored 3.0; the
second printed `False` and scored 2.9. The real walk-forward was 1.063 both
times; the null's best seed moved across it.

Sites affected — every hypothesis on the board:

| file | null |
|---|---|
| `strategies/vwap/stage3_timeframes.py` | timeframe sweep |
| `strategies/vwap/stage6_walkforward.py` | walk-forward, plain and paired |
| `strategies/vwap/stage9_cost_robust.py` | cost-robust selection |
| `strategies/vwap/stage10_universe.py` | twelve-market universe |
| `strategies/ema_vwap/stage1_grid.py`, `stage2_walkforward.py` | H-003 grid and walk-forward |
| `strategies/sweep_fade/stage1_grid.py` | H-005 grid |
| `strategies/xsec/stage1_grid.py` | H-007 panels |
| `strategies/resid/stage1_grid.py` | H-008 panels |

**Fixed** with `stage3_timeframes.null_seed(*parts)` — CRC32 over the joined
parts, stable across processes and machines. Verified: two separate interpreters
now return the same seed.

**What this does and does not invalidate.** A randomly-seeded shuffle is still a
valid null draw, so no conclusion here is known to be wrong: H-002 beat its null
by a wide margin (52 gate-clearing cells against 3) and H-005 lost to its null by
a wider one (19,062 against 1,702). Neither verdict turns on a single seed.
What is lost is **auditability** — none of those figures can be regenerated, so
none can be checked. The margin that mattered is H-007's, which was inside the
noise all along; that it flipped is the finding, not a new result.

**Regenerated on deterministic seeds:** the H-007 and H-008 board records, which
draw their nulls at board time. **Not regenerated:** every stage-1 grid null
(H-002 stage 3/6/9/10, H-003, H-005). Those figures stand as reported but are
not reproducible until their grids are re-run, which is hours of compute for
H-005 and H-002. Treat any stage-1 null count in this log as provisional.

## H-006 order flow — the data was never the blocker (2026-09-02)

**The finding that unblocks this.** `core/feed_collector.py` exists because
Binance's REST endpoints serve about two days of open interest and taker ratio,
and on that basis HANDOFF deferred the order-flow hypothesis to 2026-10 while the
collector slowly accumulated history. That was wrong.

Binance publishes the same feeds as daily files at

    data.binance.vision/data/futures/um/daily/metrics/<SYMBOL>/

at the same 5-minute granularity, back to **2020-09-01**, free and
unauthenticated. BTCUSDT alone is **630,659 rows covering 2020-09-01 to
2026-09-01** — six years, downloaded in about ten minutes. The same bucket
carries funding rate (monthly, from 2020-01) and USDT-M perpetual klines
(monthly plus a daily tail), and the klines include
`taker_buy_base_asset_volume`, which is a true signed taker flow rather than the
summarised ratio.

`core/binance_metrics.py` downloads all of it. The forward collector is still
worth running — it records the live present and the archive stops at yesterday —
but nothing has to wait for it, and H-006 is open now rather than in October.

**Columns, and why they are not the same thing five times:**

| column | measures | |
|---|---|---|
| `sum_open_interest` | contracts outstanding | is a move new risk or old risk closing? |
| `sum_taker_long_short_vol_ratio` | who crossed the spread | aggression, not positioning |
| `count_long_short_ratio` | long accounts / short accounts, every account equal | a headcount — a crowd gauge |
| `count_toptrader_long_short_ratio` | the same headcount, largest accounts only | |
| `sum_toptrader_long_short_ratio` | large accounts weighted by **position size** | money, not headcount |

The count/sum split is why this feed is worth more than another oscillator: the
exchange publishes **where the crowd stands and where size stands, separately**,
and lets the two disagree.

**Prices are the perpetual, not spot.** The repo's cached crypto bars are spot
15m. These feeds describe the USDT-M perpetual book and that is where this would
be traded, so the diagnostic uses matching perp 5m bars from the same archive.
Measuring a perp signal against spot prices compares two different order books.

**Two bugs found while building the loader**, both of the silent kind:

1. Monthly kline files are published weeks in arrears — the newest was 2026-07
   on 2026-09-02 — so a monthly-only fetch ends the series two months early and
   every backtest built on it is quietly truncated. Fixed by taking the tail
   from the daily files, with the boundary read from the data returned rather
   than from the calendar.
2. The resume logic skipped ahead to the end of whatever was cached. A stray
   two-month test file therefore made a "full history" fetch return two months,
   with the six-year hole in front of it left forever. Now a cache that starts
   later than the requested start is refetched from the beginning.

Mechanism, gates and results: `strategies/orderflow/notes.md`.

## H-009 — the crowd feed makes H-002 better (2026-09-02)

The synthesis that had not been tried. H-002 is the one price strategy that
survived here; H-006 established that Binance's long/short **account** ratio
carries real directional information but cannot carry a book on its own. Putting
the feed on top of H-002 as a veto rather than a signal is the most direct route
to "better than H-002" available, because it starts from H-002.

**The rule, fixed before the run:** keep a long only when `crowd_z <= 0` and a
short only when `crowd_z >= 0` — that is, only take H-002's trade when retail
positioning is on the other side of it. `crowd_z` is the account ratio z-scored
against a shifted one-day trailing baseline, so it is point in time.

**Nothing on the VWAP side is refitted.** Every configuration is the one stage 10
chose blind for that quarter. The gate is a global rule on top, not something the
walk-forward was allowed to select, which is stricter than letting it choose.

| same selection rule as stage 11 | gate off | gate on |
|---|---|---|
| profit factor | 1.768 | **2.047** |
| at 2x cost | 1.458 | **1.651** |
| max drawdown | −3.66R | **−2.82R** |
| return / drawdown | 24.6 | **34.4** |
| two-step pass rate | 88.0% | **92.4%** |
| expected days to funded | 53.4 | **48.7** |

The gate keeps 55% of trades and total R rises. **It improves six of six crypto
legs on both profit factor and drawdown, with no exception** — ETHUSDT 30m goes
from 1.177 to 1.657 with its drawdown halved, which is what lets the book carry a
fifth leg.

**The control is what makes it a mechanism.** Inverting the gate — keeping only
the trades the crowd agrees with — gives PF 1.137 and return/drawdown 2.9, and
goes outright negative at a tighter threshold. Almost the whole of H-002's edge
lives in the trades that run against retail positioning. That is a statement
about who is on the other side, not about a filter that fit.

**The null:** a block-shuffled feed driving the same gate scores 1.288 to 1.464
at 2x against the real 1.651, and its median lift is negative. The real gate
lifts; a shuffled one hurts.

**Why the board still shows 8.3 against H-002's 8.6.** H-009 wins five of the six
scored components and loses `evidence`, entirely on `null_margin` — and those two
margins are not the same measurement. H-002's null phase-randomises the market, so
its null book has no edge at all (survivors 8 against 0, margin 1.0). H-009's null
shuffles only the feed, leaving H-002's price edge intact, so it measures the
increment alone. The survivor-count version confirms it is the wrong statistic
here: 229 real against a null median of 198, because most subsets clear PF 1.20
with a shuffled gate too, carried by H-002's own edge. Settling it means re-running
stage 10's universe sweep with the gate in the kernel against a phase-randomised
market null — hours of compute, and the next thing to do.

**Known weakness:** this is a post-filter, so it can only remove trades, never add
the ones freed capacity would have allowed. Every trade it keeps is real at a real
price, so the book is achievable; the in-kernel version would take extra trades
this one cannot see. Also: no TradingView port is possible, because Pine cannot
fetch the account-ratio feed.

## H-010 VWAP band rejection — rejected (2026-09-02)

From a published TradingView indicator: anchored VWAP with three
standard-deviation bands, a bar reaches a band and closes back against the move,
and the trade fades it toward the VWAP with volume-delta confirmation.

**This family was already on the dead list.** `CLAUDE.md` records `VWAP std-band
fade` at profit factor 3.0 in backtest and about 0.7 live, on a backtest that
filled a resting limit on any wick touch. It was worth re-testing only because
the rejection formulation can be made fill-honest. A second warning was already
in the data: H-002's 105 blind fold choices land on **trend** and **break** and
essentially never on **fade**, and all of them use market fills.

Five things were changed from the indicator, none cosmetic: market fills at the
next open instead of a resting limit; the exchange's real `taker_buy_base` split
instead of `volume * sign(close - open)`; actual exits with a stop so R is
bounded; the H-009 crowd gate; and a direction control that takes every setup
the other way.

**Result — 3 coins x 4 timeframes x 2,592 configurations, 5 null seeds:**

| cost | revert | continue (control) | **paired null** |
|---|---|---|---|
| 0x | 0.946 | 0.991 | **0.965** |
| 1x | 0.792 | 0.818 | **0.845** |
| 2x | 0.681 | 0.686 | **0.747** |
| 3x | 0.585 | 0.577 | **0.660** |
| clears 1.20 at 2x | 280 | 785 | **637 per seed** |

The null beats the real market at every cost level and clears the gate more than
twice as often. The control scores no worse than the hypothesis. Walk-forward for
board parity: 2,487 out-of-sample trades, PF 1.031, **0.892 at 2x**, no risk
level passes. Board 2.5/10.

**The lever table refutes the mechanism outright.** Median profit factor at 2x by
choice of exit: revert to the VWAP **0.500**, fixed R multiple 0.679, ignore the
VWAP and exit on time **0.816**. Exiting at the VWAP — the entire idea — is the
most harmful choice in the grid. Deeper bands are worse, not better (1σ 0.713,
3σ 0.573), which is the opposite of the "75-80% reversion from the 2nd or 3rd
band" claim made for it. The delta filter moves nothing (0.679 to 0.682) despite
being the indicator's headline feature, and that is a fair test of the idea
rather than of the approximation, because the crude proxy was replaced by the
real taker split.

Best-looking configurations trade **0.018 times a day** — one every two months
over six years. Search noise, and it fails the phase constraint independently.

**Two bugs were found while building it, both flattering:** the VWAP target could
sit behind the entry and book losses as target hits (2,096 of them, averaging
−0.8R), and the minimum stop distance was 10bps against a 14bps round trip, so
cost alone was 1.4R on the tightest trades. Both are fixed; the second became a
swept dimension, and it is worth remembering generally — early in a session the
volume-weighted sigma is tiny and any band-relative stop can be narrower than
the spread.

**One thing worth keeping.** The H-009 crowd gate lifts even this dead strategy,
0.659 to 0.712. A third independent confirmation, in the cleanest possible
setting: a strategy with no edge of its own.

## H-011 previous day/week high-low reversal (2026-09-02)

Price takes out the previous day's high or low, the stops resting there fire, and
once they are gone the forced flow is finished — so the move gives back.

**This is adjacent to the rejected H-005, and the difference is the point.**
H-005 faded the extreme of the last 10 to 100 **bars**: a rolling level, moving
every bar, on a lookback nobody agreed on, watched by nobody. Its paired null
cleared the 1.20 gate 19,062 times against the real market's 1,702. The previous
day's and week's extremes are a **schelling point** — printed identically on
every platform, fixed for the session. The claim is not "price reverts from
extremes", which is dead; it is that a level everyone agrees on collects resting
orders in a way an arbitrary one does not.

Two things H-005 could not check were added: **open interest across the sweep**
(contracts closing means stops ran; contracts opening means a real breakout wearing
the same clothes) and the **H-009 crowd gate**. Plus a direction control and a
paired null throughout.

**Stage 1, 3 coins x 4 timeframes x 3,840 configurations:**

| cost | revert | continue (control) | paired null |
|---|---|---|---|
| 0x | **1.052** | 0.867 | 0.926 |
| 1x | **0.872** | 0.707 | 0.774 |
| 2x | **0.739** | 0.592 | 0.658 |
| 3x | **0.627** | 0.500 | 0.567 |
| clears 1.20 at 2x | **952** | 469 | 436 per seed |

**The real market beats its null at every cost level and beats its own control at
every cost level.** No other fade hypothesis in this project has managed either.
The schelling-point version is measurably a different object from the
rolling-lookback version, which is a result about H-005 as much as about this.

**But it does not survive blind selection.** Walk-forward, configuration chosen
blind each quarter on 2x-cost train profit factor: 2,241 out-of-sample trades,
PF 1.008, **0.897 at 2x**, and **0 of 12 panels hold the 1.20 gate on their own**
(best is BTC 15m at 1.126). Median across the grid is 0.739 at double cost and
only 12.2% of configurations are above 1.0 there. The edge is real and too small
to pay a 28bps round trip — the H-007 shape.

**Four things the lever table says, all of which travel beyond this hypothesis:**

1. The **crowd gate lifts it**, 0.708 to 0.772. That is the **fourth** independent
   confirmation of H-009, now on a fourth unrelated strategy. It has now improved
   a VWAP book, a dead band-fade, an order-flow book and a level sweep.
2. **Open interest earns its place here**, 0.708 to 0.741, where the raw series
   did nothing directional in H-006. Conditioned on a level being taken out,
   "were contracts closed?" is informative in a way the series alone is not.
   That is a genuinely new reading of the feed.
3. **Targeting the reversion is the worst exit, again.** Exit at the level's
   midpoint 0.576 against exit on time 0.862 — the identical pattern H-010 showed,
   where exiting at the VWAP was the most harmful lever in its grid. Two
   mean-reversion hypotheses in a row are named after a target that hurts them.
   Worth carrying forward: **the reversion is real enough to enter on and not
   reliable enough to exit on.**
4. The **weekly level beats the daily one** (0.755 vs 0.730), deeper sweeps beat
   shallow ones, and higher timeframes beat lower ones. All three point the way
   the mechanism does — the bigger and more widely watched the pool, the more
   there is in it.
