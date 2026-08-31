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
