# H-011 — previous day/week high-low reversal

Opened 2026-09-02.

## The hypothesis, and how it differs from the rejected H-005

Price takes out the previous day's high or low, the stops sitting there fire, and
once they are gone the forced flow is finished — so the move gives back.

**H-005 is already rejected and this is adjacent to it.** H-005 faded the extreme
of the last 10 to 100 **bars**: a rolling level, moving every bar, depending on a
lookback nobody agreed on, and watched by nobody. Its paired null cleared the
1.20 gate 19,062 times against the real market's 1,702.

The previous day's and week's extremes are a different kind of object. They are a
**schelling point** — printed identically on every platform, fixed for the whole
session. The claim is not "price reverts from extremes", which is dead; it is
that a level everyone agrees on collects resting orders in a way an arbitrary
one does not.

Two things H-005 had no way to check are in the grid:

- **open interest across the sweep.** Contracts *closing* while the level is
  taken is the fingerprint of stops running. Contracts *opening* is a real
  breakout wearing the same clothes. H-006 showed open interest carries nothing
  directional on its own — conditioned on a level being taken out, it separates
  two events that look identical on price.
- **the H-009 crowd gate.**

Plus, always: a **control** that takes every setup the other way for the same
risk, and a **paired-shuffle null**, five seeds.

## Stage 1 — 3 coins x 4 timeframes x 3,840 configurations

| cost | revert (the hypothesis) | continue (control) | paired null |
|---|---|---|---|
| 0x | **1.052** (60.9% > 1.0) | 0.867 (24.8%) | 0.926 (36.2%) |
| 1x | **0.872** (25.7%) | 0.707 (9.5%) | 0.774 (13.8%) |
| 2x | **0.739** (12.2%) | 0.592 (5.5%) | 0.658 (6.7%) |
| 3x | **0.627** (6.8%) | 0.500 (3.8%) | 0.567 (3.7%) |
| clears 1.20 at 2x | **952** | 469 | **436 per seed** |

**The real market beats its null at every cost level, and the fade beats its own
control at every cost level.** That is the first time any fade hypothesis in this
project has managed it — H-005's null beat it elevenfold, H-010's null had a
higher median than the real market. Something about the schelling-point version
is genuinely different from the rolling-lookback version.

It is still a median of 0.739 at double cost. Only 12.2% of configurations are
above 1.0 there. A real edge that costs mostly eat — the H-007 shape.

## What the levers say

Median profit factor at 2x cost, by choice:

| lever | values |
|---|---|
| confirmation | none 0.708 · flow 0.718 · **oi 0.741** · **crowd 0.772** · crowd+oi 0.767 |
| exit | revert to the mid **0.576** · fixed R 0.766 · **time only 0.862** |
| minimum stop | 25bps 0.661 · **100bps 0.794** |
| level | previous day 0.730 · **previous week 0.755** |
| timeframe | 15m 0.684 · 30m 0.723 · 1h 0.738 · **4h 0.818** |
| sweep depth | ≥0 0.732 · ≥0.25 ATR 0.740 · ≥0.5 ATR 0.744 |

Four things worth reading off that table:

1. **The crowd gate lifts it again** (0.708 to 0.772) — a fourth independent
   confirmation of H-009, now on a fourth unrelated strategy.
2. **Open interest earns its place here** (0.708 to 0.741), which it did not in
   H-006. Conditioned on a level being taken out, "were contracts closed?" is
   informative in a way that the raw series is not.
3. **Targeting the reversion is the worst exit again**, exactly as in H-010.
   Exiting on time beats exiting at the level's midpoint by a wide margin. Both
   of these hypotheses are named after a target that hurts them.
4. **The weekly level beats the daily one**, and the deeper the sweep the better,
   and the higher the timeframe the better — all three point the same way the
   mechanism does: the bigger and more widely watched the pool, the more there is
   to be had.

## Stage 2 — the walk-forward, and where it fails

Configuration re-chosen blind every quarter on 2x-cost train profit factor,
12 market/timeframe panels, 2,241 out-of-sample trades.

| | |
|---|---|
| profit factor | 1.008 |
| **at 2x cost** | **0.897** |
| max drawdown | −13.2R |
| panels holding PF 1.20 at 2x on their own | **0 of 12** |

Best single panel is BTCUSDT 15m at 1.126. Nothing reaches the gate.

**So the verdict is: real, and too small.** The stage-1 null margin is not an
artefact — it is consistent across cost levels, it is mirrored by the control,
and it points the way the mechanism does. It is simply not worth 28bps a round
trip. That is the same shape as H-007, which also carried genuine information
that the spread ate.

## What to carry forward

1. **A schelling point is not the same as an arbitrary level.** H-005 fading a
   rolling extreme lost to its null elevenfold; this, fading a level everyone
   sees identically, beats its null at every cost level. That is a result about
   H-005 as much as about H-011, and it says the family died for the right
   reason but not quite the reason recorded.
2. **Open interest becomes informative once a level has been taken.** Raw open
   interest carried nothing directional in H-006 — both tails of its quintile
   response were positive, a volatility reading. Conditioned on a sweep it lifts
   the median from 0.708 to 0.741, because "were contracts closed?" separates a
   stop run from a breakout, and those look identical on price alone.
3. **The reversion is real enough to enter on and not reliable enough to exit
   on.** Exiting at the level's midpoint is the worst choice in this grid (0.576)
   against exiting on time (0.862) — the identical pattern H-010 found with the
   VWAP target. Two mean-reversion hypotheses in a row have been hurt most by the
   target they are named after.
4. **The crowd gate lifts a fourth unrelated strategy** (0.708 to 0.772). It has
   now improved a VWAP book, a dead band fade, an order-flow book and a level
   sweep. That is the most reliable single finding in this project.
