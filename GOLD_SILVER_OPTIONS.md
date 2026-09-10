# A second hypothesis on gold/silver — no VWAP anywhere

Rewritten 2026-09-10 after Kris: *"i dont want nothing associated with vwap, i
want completely new method and logic behind hypothesis to try."*

The earlier version of this file led with an intraday VWAP-band fade. That option
is **withdrawn** — it is the same signal H-027 already trades.

Nothing here is built. Two candidates were measured today and are dead; one
turned up that was not being looked for.

---

## Killed today, before being proposed

**1. Dollar → gold lead-lag (15m).** Synthetic USD index from EURUSD/USDJPY/
GBPUSD/USDCAD/USDCHF, DXY weights, 66,971 live gold bars, 3 years.

| lag (15m bars) | corr | R² |
|---|---|---|
| 0 | **−0.356** | 12.7% |
| 1 | −0.008 | 0.01% |
| 2–8 | ≈0.00 | 0.00% |

The repricing is complete **inside the bar**. Top-5% dollar moves predict the next
gold bar at **+0.095 bps, t = 0.26**, against a round trip of at least 1.06, and
the yearly means run −0.29 / +0.33 / −0.43 / +1.43 — a sign that flips across
years is H-026's signature for no effect.

**2. The LBMA fix auction.** The best *mechanism* on the list — two scheduled
auctions a day at a printed benchmark, dealers with fix-benchmarked client orders
forced to hedge on a clock everyone knows. It is not there:

| window (London) | n | mean | t | sign-consistency |
|---|---|---|---|---|
| AM fix 10:30 | 772 | +0.481 bps | +1.02 | 53.0% |
| PM fix 15:00 | 772 | −0.626 bps | −0.52 | 49.6% |

Most likely regulated away — the electronic auction replaced the phone fix in
2015 and our whole window is post-reform.

---

## CANDIDATE 1 — the metals daily-reopen premium

**Found while scanning the hour table for the fix, not looked for.** Report it
that way: it is an unplanned finding in a table with 46 rows, and 46 rows contain
a t > 2.5 by chance more often than people expect.

Gold and silver stop trading for roughly 90 minutes a day (COMEX daily halt,
17:00–18:00 New York). The **first 30-minute bar after the reopen** — London
23:00, UTC 22:00 or 23:00 depending on DST:

| | XAUUSD | XAGUSD |
|---|---|---|
| n (weekday reopens, 3y) | 617 | 566 |
| mean return | **+4.303 bps** | **+6.516 bps** |
| t | **+5.42** | +3.69 |
| median | +2.908 | +4.958 |
| win rate | 64.7% | 65.0% |
| every other bar | +0.150 bps | +0.200 bps |
| ratio | **28.7x** | 32.6x |
| share of the 3y move | **33.9%** from 1.8% of bars | 37.0% from 1.8% of bars |

**By year, both metals, same sign every year:**

| | 2023 | 2024 | 2025 | 2026 |
|---|---|---|---|---|
| XAUUSD | +4.51 (t 7.04) | +2.52 (t 5.31) | +3.77 (t 2.45) | +7.72 (t 2.94) |
| XAGUSD | +5.25 (t 3.91) | +6.48 (t 4.77) | +5.83 (t 2.79) | +8.56 (t 1.07) |

**The mechanism, if it is one.** This is a close-to-open risk premium: someone has
to carry metal through a window where the position cannot be exited, and whoever
will is paid for it. Same family as the equity overnight premium in
`SECOND_HYPOTHESIS.md` Candidate A, but on the instrument whose edge-to-cost
ratio is the best in this repo. Nameable payer: intraday participants who flatten
before the halt rather than hold through it.

**Checks already done.**
* *Is it just a longer bar?* The reopen bar spans 90 minutes of clock against a
  normal bar's 30, so it should mechanically carry 3x the drift. Per minute it
  carries **~10x**, not 3x. Survives.
* *Is it a high-volatility bar being rewarded?* No — |move| at the reopen is
  10.6 bps against ~10 bps for the day's other bars. It is not a wider bar.

**THE REASON THIS IS NOT YET A HYPOTHESIS, AND IT IS THE WHOLE THING.**
This repo has already killed this exact trade once, one timescale up.
`core/fx_spread_weekopen.py`: the FX **weekly** open showed +0.76 to +2.37 bps of
gross drift and died on the spread, which is 1.9x wider at the reopen than
mid-week, and whose distribution is skewed 2.3–2.7x so the **mean** cost is what
counts, not the median. The hurdle had been understated 7.6x.

Now look at what we have measured for gold (`backtests/propfirms/
fx_spread_measured.csv`, 478 sampled hours):

| UTC hour | 1 | 5 | 9 | 13 | 17 | 21 | **22** | **23** |
|---|---|---|---|---|---|---|---|---|
| mean half-spread, bps | 1.738 | 1.713 | 1.605 | 1.659 | 1.617 | 1.712 | **never sampled** | **never sampled** |

The sampler takes every fourth hour. **The two hours the entire candidate lives in
are the two it has never measured** — structurally the same blind spot as the
`dayofweek < 5` line that meant Sunday was never sampled.

All-hours mean half-spread is 1.670 bps → **round trip 3.34 bps** against a gross
edge of **+4.30**. The trade is 1.29x its cost *at the average hour*. At the FX
weekly open's 1.9x widening it is **under water**. This is decided by one
measurement and no strategy code.

**Silver is already out.** Its measured all-hours round trip is **20.3 bps**
against a +6.52 bps gross edge. Cost is 3x the edge. Trade this on gold or not at
all.

> **Open discrepancy, flagged not resolved:** `RESEARCH_2026-09-10_WHY.md` quotes
> gold at 1.06 bps and silver at 4.70 bps round trip; this file's measured
> spreads give 3.34 and 20.3. Both cannot be right and the gap decides silver
> entirely. Worth an hour before any number here is quoted onward.

| | |
|---|---|
| market | XAUUSD only |
| direction | long into the reopen, flat 30–60 min later. Not a breakout, not a fade. |
| holding | 30–60 minutes |
| trades/day | ~1 (≈250/yr) |
| correlation with H-027 | different clock, 30min vs 19h hold, no band, no VWAP |
| payoff shape | many small wins — **payable under a 20% best-day rule, which H-027 is not** |
| **decided by** | **sampling UTC hours 22 and 23 with the existing tick sampler. One download, about an hour.** |

**What would still have to survive after that:** a block-shuffle null (this is
long-only in a window where gold nearly doubled), the 2x/3x cost ladder, a blind
walk-forward, and the noise band. The spread measurement only decides whether it
is worth starting.

---

## CANDIDATE 2 — the gold/silver ratio, as relative value

**The mechanism.** XAU and XAG are one macro factor with two liquidities. Silver
has roughly a fifth the book, so identical flow displaces it further, and the
ratio overshoots on impulse and closes as the cross-asset arbitrage works. The
only candidate here that is **not a directional metals bet at all** — a gold
crash takes out a directional account and leaves a ratio position alone.

| | |
|---|---|
| market | long/short XAUUSD vs XAGUSD, beta-matched, 30m or 1h |
| trades/day | set by the z-threshold, ~0.5–2 |
| correlation with H-027 | structurally the lowest of anything proposed |
| decided by | the z-response: forward move by z-quintile, gross, plus a block-shuffle null. A day. |

**The hard number against it.** You pay **both** legs, and if the measured
spreads above are the right ones that is 3.34 + 20.3 = **23.6 bps** a round trip,
which is worse than crypto. It is also *fading an extreme*, the family this repo
has killed twice, and its closest precedent is H-008 — strip out the beta, fade
the residual — which died on a **flat** z-response (PF 1.000 / 0.997 / 1.006 /
1.013 as entry went 1.5σ to 3.0σ). Check the z-response first; H-008 says expect
it flat.

---

## CANDIDATE 3 — the scheduled macro release

**The mechanism.** Gold is the most macro-sensitive metal on the board — CPI,
NFP, FOMC reprice real rates, and real rates are gold's discount rate. Large
institutional orders are worked over hours rather than at the print, so
information diffuses slowly and a post-release drift is the standard story. The
payer is whoever must transact immediately at the print.

**Why it is third.** ~100–150 events in three years is **one trade a week**,
which is the opposite of what Kris asked for, and it needs an economic-calendar
download we do not have. Clean mechanism, wrong frequency for this phase.

---

## What I would pick

**Candidate 1, and it is one download from being decided.**

It is the only thing on the page that is new logic, high frequency, on the one
instrument whose cost the repo can defend, with a payoff shape that is payable
where H-027 is not. It is also the one most likely to be an artifact — the FX
version of it died on exactly the spread number we are missing, and the hours it
lives in are the hours the sampler skipped.

**So the honest order is: measure the reopen spread first, and only then decide
whether there is a hypothesis here at all.** If UTC 22–23 comes back near 1.7 bps
a side, this is a candidate. If it comes back at the FX weekly open's 1.9x, it is
dead and cost us an hour.

**Kris picks. Nothing is built until then.**
