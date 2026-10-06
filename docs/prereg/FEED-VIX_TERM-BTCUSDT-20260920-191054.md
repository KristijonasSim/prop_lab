# VIX_TERM.zscore60.BTCUSDT.h5 — feed screen

Written 2026-09-20T19:10:54+00:00 by
`research/run.py`, BEFORE the screen ran. Auto-generated: every field below is
derivable at proposal time, which is why this costs no human minutes.

## Mechanism

A low term-structure slope (inversion) marks forced de-risking by vol-targeting and levered funds, which sell liquid risk assets regardless of price. They are the loser. Bitcoin trades 24/7, so it absorbs this selling first, and liquidity providers who buy the overshoot are paid as the stress fades. High values (calm contango) predict weaker follow-through, which matches direction -1.

Source: CBOE (derived). VIX3M minus VIX (term structure slope).

## The single arm

| | |
|---|---|
| feed | `VIX_TERM` |
| transform | `zscore` window 60 |
| lag | 1 (Both legs are settlement values.) |
| market | BTCUSDT |
| hold | 5 trading days, open to open |
| direction | -1 |

**This is ONE arm.** No grid, no sweep, no best-of. The trial count charged to
`backtests/ledger.csv` is 1, which is the whole reason this file exists —
`core/searchcost.sr_threshold` is exactly zero at N=1.

## Null

Block shuffle of the signal at block 20, 200 seeds
(`core/screen.py`). Beating it means p < 0.05 on the bucket-response effect.

## Cost bar

BTCUSDT round trip 7.05 bps at `mixed` execution. The effect
must clear **14.10 bps** (2.0x) between the top and bottom bucket.

## Kill criterion — fixed before the number is known

Any one of: fewer than 40 independent events; effect under
14.10 bps; mean and median disagreeing in sign; |rho| under 0.8;
the 5 best decisions carrying more than 50% of the
profit; a seat not fundable inside 90 days at the risk that
survives the worst stretch; p >= 0.05 against the shuffle. **First failure ends
it — no second look, no tuning of the window, no other market rescuing it.**

The last two are the shape gates added 2026-09-20. They exist because H-027 —
this project's only survivor of 48 hypotheses — clears all five of the others
while earning 65% of its profit on two days out of 634, which is unpayable at
any firm carrying a consistency rule and kills a funded seat in a median of 29
days at the traded risk. `docs/DIAGNOSIS_2026-09-20.md` has the measurement.

## Expected events

265 independent, from `core.screen.independent_events`.

## What would make this WRONG

The feed being real but unreadable at the stated lag, or the effect existing
only in the market whose cost bar is lowest. Both are checked by re-running the
identical arm on the rest of `core/universe.STANDARD`, never by widening this
one.
