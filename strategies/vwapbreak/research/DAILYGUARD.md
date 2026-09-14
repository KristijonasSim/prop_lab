# H-041 — a daily-loss guard. An account overlay, not a rule change.

**Pre-registered 2026-09-14, before any number.**

---

## Why this, and why it is not another filter

H-039 (`MARKTOMARKET.md`) measured which cap actually kills these accounts. Once
open positions are marked to market — which is how a firm measuring drawdown on
equity sees them — the failure mode inverts:

| | exit-booked | marked to market |
|---|---|---|
| fail on the MAX cap | 27.6% | 4.2% |
| **fail on the DAILY cap** | 22.4% | **45.8%** |

**Nothing in the rule knows what a day is.** The bot tracks equity and the peak,
sizes off the drawdown from the peak, and has no concept of a daily budget. It
will keep opening positions on a day that has already lost 2.8% against a 3% cap.

**A daily-loss guard has never been tested here.** `STRATEGY_LOG.md` has zero
mentions of one.

## Why it is allowed when entry filters are dead

Twenty-five entry filters died because they **select among signals** on market
information — and 24 of 25 raised profit factor while lowering R per day. This
does not read the market at all. It reads the **account**, and it is the same
class of thing as the risk ladder and budget-linear sizing, both of which are
adopted: a fixed trade series re-simulated under a different account policy.

That class has produced the only two improvements this hypothesis has ever kept.

## The arms

Once the day's realised R is at or below the threshold, **take no new entries
until the next UTC day**. Positions already open are left alone — closing them
would be an exit-rule change, and the exit axis is closed.

| arm | day's loss that stops new entries |
|---|---|
| **none** | baseline, the shipped behaviour |
| −1.0% | |
| −1.5% | |
| −2.0% | |
| −2.5% | just inside the 3% cap |

## What counts as a win — fixed now

1. **Fewer expected days with a band that does not overlap the baseline's**, or
2. **the same expected days (overlapping band) with a materially lower blow-up
   rate** — because under equity accounting the blow-up rate is the thing H-039
   says is mispriced, and a guard that buys survival at no cost in speed is
   worth having even if it does not make the account faster.

Condition 2 is looser than the one `strategies/beat/` used and it is stated in
advance so it cannot be invented after seeing the table. **An arm meeting only
condition 2 is reported as "survival, not speed" and never as "beats H-027".**

## What would make a pass a false one

* **Five arms is a search over five cells.** The whole curve is reported.
  **A real effect is monotone in the threshold** — tighter guard, fewer blow-ups.
  A spike at one threshold with neighbours worse is the H-038 signature and is
  read as noise.
* **It must hold on 1h and 4h.** A sign-flip across timeframes is this repo's
  signature for no effect.
* The guard can only ever *remove* trades, so it will mechanically raise profit
  factor. **Profit factor is not evidence here.** Expected days and blow-up rate
  are the only numbers that count.

## Kill criterion

> If no threshold beats the baseline on either condition, on both timeframes,
> the account-overlay axis is closed alongside the other five and H-027 is
> finished being tuned.
