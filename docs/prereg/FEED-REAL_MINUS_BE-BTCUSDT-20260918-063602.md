# REAL_MINUS_BE.change5.BTCUSDT.h1 — feed screen

Written 2026-09-18T06:36:02+00:00 by
`research/run.py`, BEFORE the screen ran. Auto-generated: every field below is
derivable at proposal time, which is why this costs no human minutes.

## Mechanism

Real yield minus breakeven — registry default; no mechanism written

Source: FRED (derived). Real yield minus breakeven.

## The single arm

| | |
|---|---|
| feed | `REAL_MINUS_BE` |
| transform | `change` window 5 |
| lag | 1 (Both legs are FRED daily.) |
| market | BTCUSDT |
| hold | 1 trading days, open to open |
| direction | +1 |

**This is ONE arm.** No grid, no sweep, no best-of. The trial count charged to
`backtests/ledger.csv` is 1, which is the whole reason this file exists —
`core/searchcost.sr_threshold` is exactly zero at N=1.

## Null

Block shuffle of the signal at block 20, 200 seeds
(`core/screen.py`). Beating it means p < 0.05 on the bucket-response effect.

## Cost bar

BTCUSDT round trip 9.00 bps at `mixed` execution. The effect
must clear **18.00 bps** (2.0x) between the top and bottom bucket.

## Kill criterion — fixed before the number is known

Any one of: fewer than 40 independent events; effect under
18.00 bps; mean and median disagreeing in sign; |rho| under 0.8;
p >= 0.05 against the shuffle. **First failure ends it — no second look, no
tuning of the window, no other market rescuing it.**

## Expected events

536 independent, from `core.screen.independent_events`.

## What would make this WRONG

The feed being real but unreadable at the stated lag, or the effect existing
only in the market whose cost bar is lowest. Both are checked by re-running the
identical arm on the rest of `core/universe.STANDARD`, never by widening this
one.
