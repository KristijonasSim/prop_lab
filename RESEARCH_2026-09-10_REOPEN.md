# H-028, the metals daily-reopen premium — proposed, measured, dead in one session

Written 2026-09-10. Kris picked Candidate 1 from `GOLD_SILVER_OPTIONS.md`.
It is dead. This file is the denominator.

**The claim.** Gold and silver stop trading for ~90 minutes a day (COMEX halt,
17:00-18:00 New York). Whoever carries metal through a window they cannot exit
is paid for it, so the first bar after the reopen should carry a premium. Payer:
the intraday crowd that flattens before the halt.

**The headline that made it worth testing:**

| | XAUUSD | XAGUSD |
|---|---|---|
| n, 3y weekday reopens | 617 | 566 |
| mean 30m return | **+4.303 bps** | **+6.516 bps** |
| t | **+5.42** | +3.69 |
| win rate | 64.7% | 65.0% |
| every other bar | +0.150 | +0.200 |
| share of the 3y move | 33.9% from 1.8% of bars | 37.0% from 1.8% of bars |

Same sign in all four calendar years on both metals.

---

## Four things killed it, and they are independent

### 1. It does not survive being the best of 48 slots

Within-day slot-shuffle null: shuffle which half-hour slot each of a day's
returns belongs to, 2,000 iterations. Preserves each day's total move and the
whole three-year trend; destroys only *which slot* the move sat in.

| | gold | silver |
|---|---|---|
| p, **that slot named in advance** | 0.0000 | 0.0000 |
| p, **best-of-48-slots** (what actually happened) | **0.187** | **0.284** |

The null's best slot averages **+2.912 bps** with a p90 of **+5.541**. Our +4.303
sits inside that. The reopen slot is not even the maximum — it ranks 2 of 48,
behind a 47-sample DST-transition slot.

**This is the noise floor doing its job.** It was found by scanning a 46-row
table for a large t, which is exactly the procedure the floor exists to price.

### 2. The effect tracks the SPREAD, not the length of the halt

| | halt | measured half-spread | reopen effect |
|---|---|---|---|
| EURUSD | 30 min (no real closure) | 0.453 bps | +0.03 |
| XAUUSD | 90 min | 1.670 bps | +4.30 |
| XAGUSD | 90 min | **10.142 bps** | **+6.52** |
| NAS100 / SPX500 / US30 | **120 min** | — | +1.55 / +1.26 / +0.92 |
| WTI | 90 min | — | **−1.00** |

A risk premium should scale with **how long the position cannot be exited**. The
indices have the longest halt and nearly the smallest effect; silver has the
widest spread and the biggest. **The ordering follows the spread.**

The five FX pairs are the placebo group — no meaningful closure, no premium,
none significant (+0.03 / −0.32 / +0.08 / −0.08 / +0.04). That part of the
cross-section is genuinely encouraging for the mechanism and it is the only part
that is.

### 3. The bar BEFORE the halt is negative, and on silver the round trip nets to zero

Dukascopy bars in this repo are **BID candles, not mid** (`core/fx_spread.py`
documents this). A spread that widens into a close pushes the last pre-halt bid
down, and a spread that normalises at the reopen lets it spring back. That is a
round trip in the quote, not a return.

| 5m bar | XAUUSD | XAGUSD |
|---|---|---|
| last before halt | **−0.725** (t −5.10, win 40.0%) | **−5.261** (t −9.17, win 32.2%) |
| reopen bar | +3.436 (t +6.51) | +4.487 (t +1.48) |
| **into the halt + out of it** | +2.651 (t +4.63) | **−0.731 (t −0.25)** |

**Silver's entire premium is a bid round trip.** Gold keeps +2.65 of it, which is
why gold needed the fourth test rather than dying here.

### 4. Priced at the real reopen spread, every fast hold is negative

`core/fx_spread.py` samples UTC hours 1, 5, 9, 13, 17, 21 — every fourth — so
**the reopen hour had never been measured**. Downloaded this session (45 days,
tick files, half-spread by minute into the reopen hour):

| minute | 0–2 | 3–5 | 6–8 | 9–11 | 21–26 | steady |
|---|---|---|---|---|---|---|
| half-spread, bps | **3.126** | 2.604 | 2.390 | 2.243 | 1.885 | ~1.87 |

The spread opens at **1.7x its own steady state** and converges over ~20 minutes.
The halt hour returned **zero ticks**, which confirms the halt timing.

Entry at the reopen bar's **open** (the first price obtainable), cost = 2 x the
minute-0 half-spread = **6.252 bps**:

| hold | bid move | **net** | t | win% |
|---|---|---|---|---|
| 5m | +3.205 | **−3.047** | −6.59 | 24.3% |
| 30m | +4.231 | **−2.021** | −2.71 | 37.1% |
| 60m | +5.328 | −0.924 | −0.94 | 38.0% |
| 120m | +7.684 | +1.432 | +1.22 | 43.7% |
| **180m** | +9.818 | **+3.566** | **+2.25** | 49.7% |
| 240m | +9.108 | +2.856 | +1.38 | 50.5% |

**Every hold that made this idea attractive is negative.** The premise was "lower
timeframe, more trades"; what survives is a three-hour hold at **0.57 trades/day**
— slower than H-027's 0.8.

**And the survivor is one year.** 180m net, by year:

| 2023 | 2024 | 2025 | 2026 |
|---|---|---|---|
| +2.05 (t 1.02) | **−0.58** (t −0.50) | +2.63 (t 1.09) | **+12.09** (t 2.07) |

**75% of the total from 22% of the trades**, and 2024 is negative. Delete 2026
and the edge is +1.16 bps, inside its own 10–90% band of [+1.15, +5.99]. It is
also the best of 7 horizons scanned, on top of the 48-slot scan.

---

## One correction to my own reasoning, for the record

I claimed mid-way that the move was an untradeable gap across the closed window.
It is not: pre-halt close → reopen **open** is **+0.231 bps, t = +0.82**. The
move happens after the open and is in principle enterable. The idea dies on the
spread and on the concentration, not on unreachability.

---

## The genuinely useful by-product

**`core/fx_spread.py` cannot download any more.** Dukascopy now returns **503**
for the User-Agent in `core/fx_data.UA`, and **429** for an unthrottled client.
Every tick and bar download path in this repo is broken until the header is
changed and a backoff added. A working fetcher is in this session's scratchpad
(`duka.py`: a current Chrome UA, no Referer, exponential backoff, ~5 workers).
Throughput is roughly 3 files/minute — the 90-file sample took ~15 minutes.

**Not fixed in-repo** — flagged for Kris, since it touches the shared data layer.

## Second by-product worth keeping

The reopen spread profile itself: **3.126 bps a side at minute 0, converging to
1.87 over 20 minutes.** Any future strategy that trades near the metals reopen —
including H-027, whose 1h bars include this window — is paying close to double
the all-hours spread there. Nobody had measured it.

## Verdict

**H-028 is dead.** Logged in `STRATEGY_LOG.md`. Nothing built, no kernel written,
no board entry. Cost: one session.

Remaining from `GOLD_SILVER_OPTIONS.md`: Candidate 2 (gold/silver ratio relative
value — but 23.6 bps a round trip and H-008 says expect a flat z-response) and
Candidate 3 (macro release — clean mechanism, one trade a week, needs a calendar
download). Neither is picked.
