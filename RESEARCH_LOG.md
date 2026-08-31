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
