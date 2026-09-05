# H-023 — Maker execution: is the resting-limit fill real?

Opened 2026-09-05. **Stage 12 complete and it is a clean result.** Stage 13
(what it is worth) running.

## Why this, and why it is not a new strategy

This project has now killed three hypotheses at the same wall, and the wall is
not signal discovery:

| hypothesis | measured edge | round trip | verdict |
|---|---|---|---|
| H-007 cross-sectional ranking | ~10% on profit factor | 14bps | eaten whole |
| H-021 quarter-hour effect | 2.67bps | 14bps | 5x too small |
| H-022 absorption | 6.55bps | 8bps (best case) | 18% short |

Every price/flow feature measured here lands in the **1-7bps band**. That band
sits below every round trip available to a taker. So the binding constraint is
**execution cost**, and the one lever nobody has priced is the one the repo's
own notes name and then decline to use.

`strategies/vwap/engine.py` states the reason in its docstring: a resting limit
at the band is the natural way to trade a fade, and it is exactly how the
previous repo produced a strategy that backtested at PF 3.0 and traded live at
0.7 — a wick touch is not a fill unless you were at the front of the queue. Its
answer was to carry two fill modes and only ever use the pessimistic one. That
choice propagated: **all 2,584 fold configurations behind H-002, H-009 and
H-017 are `fill_mode=1`**, market order on the next open, 5bps taker + 2bps
slippage each side.

Defensible, but never measured. A maker round trip on Binance USDT-M is 2bps a
side. If resting fills are real, the gate all three hypotheses above failed
moves by a factor of three.

## Stage 12 — the fill assumption, measured on ticks

103 days of BTCUSDT USDT-M `aggTrades` from the Binance archive (2026-05-01 →
2026-08-25), 11,232 15-minute bars, 124M trades. A buy limit is placed at the
bar open, d bps below it, and rests for the bar. Three criteria, weakest
assumption first:

* **touch** — the bar's low reaches the limit. This is what the optimistic
  backtest counts, and it is *not* a fill.
* **through** — price trades strictly below the limit. Every resting order at
  that price is filled whatever the queue held. Needs no book data and no
  model: a hard lower bound.
* **queue(Q)** — volume traded at or below the limit exceeds Q units resting
  ahead. Reported across a range because USDT-M `bookTicker` is not published.

| dist (bps) | touch % | through % | **through given touch** | fwd@touch | fwd@through | adverse |
|---|---|---|---|---|---|---|
| 5 | 67.46 | 67.35 | **99.8** | +0.09 | +0.06 | −0.03 |
| 10 | 45.39 | 45.31 | **99.8** | +0.27 | +0.22 | −0.06 |
| 20 | 21.15 | 21.11 | **99.8** | +2.34 | +2.26 | −0.08 |
| 40 | 5.84 | 5.84 | **100.0** | +8.07 | +8.07 | 0.00 |
| 80 | 0.90 | 0.90 | **100.0** | +26.06 | +26.06 | 0.00 |

**If a 15m bar's low reaches your limit, price traded strictly through it 99.8%
of the time.** Even assuming 10 BTC resting ahead, the fill rate given a touch
is 96-98%.

**Adverse selection is ~0.** The forward return one hour after a through-fill
is within 0.08bps of the return after a touch, at every distance. The fills you
actually get earn what the backtest thought all its fills would earn.

### Why this differs from the PF 3.0 → 0.7 disaster

A 15m bar on BTCUSDT perp carries ~1,600 trades. Price does not kiss a level
and leave; it trades through with size. The old failure was on a thinner
instrument and a finer bar, where a touch really is one print. **The scar was
real and the generalisation from it was wrong** — for this instrument at this
bar size.

### What this does NOT license

* **One market, one bar size, one regime.** BTCUSDT, 15m, May-August 2026.
  ETH, SOL and XAUUSD are not measured and must not be quoted at maker cost
  until they are. XAUUSD especially — it is two of H-002's five legs and it is
  not even the same venue.
* **Entry side only.** Stops remain market orders and keep taker cost. Only
  the entry, and a resting target exit, can be passive.
* **A limit that rests is a limit that may not fill.** The touch rate column is
  the trade count you give up: at 20bps only 21% of bars touch. The strategy
  gets fewer trades, and stage 13 has to show the net is positive.
* It says nothing about queue position at a venue with different tick size or
  a different fee tier.

## Stage 13 — what it is worth. Real, controlled, and not enough.

Same configurations priced four ways, paired so the lift is a difference and
not a new fit. BTCUSDT 1h + 4h, 5,760 configs, 8,640 paired cells.

**First run was invalid and is retracted.** It reported PF 27-95, Sharpe 15.5
and a max drawdown of 1.17R over 1,660 trades — impossible numbers. Cause: in
`engine.py`, `fill_mode=0` booked the fill on bar **i** using that same bar's
`h[i]`/`l[i]` and never advanced `entry_i`, so a trade entered at a price only
knowable after the bar had closed and then had its stop and target scanned over
that same bar. Second look-ahead of this class here after H-019. Fixed: the
band level comes off closed bar i, the order rests during bar i+1, and a gap
through it fills at the open. **No board result was affected — every one of the
2,584 fold configs behind H-002/H-009/H-017 is `fill_mode=1`.**

Corrected, at 2x cost:

| mode | n | A board | B limit@taker | C mixed | D maker | D−A | % better |
|---|---|---|---|---|---|---|---|
| **fade** | 3,888 | 0.329 | 0.340 | 0.434 | **0.587** | **+0.266** | **95.3%** |
| **pullback** | 864 | 0.468 | 0.468 | 0.607 | **0.792** | +0.317 | 100.0% |
| break (control) | 3,888 | 0.311 | 0.151 | 0.207 | 0.294 | **+0.008** | 55.1% |

**The control passes.** Maker pricing lifts the fade family by +0.266 median
profit factor and does essentially nothing for breakouts (+0.008), which is
what the mechanism predicts: you cannot rest a buy limit above the market.

**The better entry price is worth nothing.** B isolates it — same 14bps cost,
limit fill instead of next-open market — and it moves the median by **+0.011**.
The entire benefit is the fee. Resting at the band actually clears the gate
LESS often than the board's entry (1 config against 6), because a limit fills
you on every wick including the ones that keep going. So the honest claim is
narrow: *a maker fee is worth having; a maker entry price is not.*

**Pullback's number is not claimable.** `MODE_PULLBACK` has no limit path at
all — it always enters at `o[i+1]`, a market order. Its +0.317 is a maker fee
charged on an execution that cannot earn one. Reported for completeness, not as
a result.

### Why this still does not beat H-009

Even at a 4bps round trip, only **36 of 3,888** fade configs clear PF 1.20 at
2x cost. The best is PF 1.877 at **0.374 trades/day** with a −5.36R drawdown,
which by the governing identity

    days = maxDD_in_R / R_per_day x (target / cap)

is roughly **145 days to a funded account** against H-009's 45. The cost saving
is real and it does not fix the speed problem, because the fade family is slow
and thin to begin with.

## Stage 14 — the cost lever priced at its floor. The direction is closed.

Stage 13 asked what maker pricing is worth on a fresh grid. This asks the
question that decides whether the direction is worth pursuing at all, of H-009
itself: **if execution were free, how fast would the board be?** That is the
ceiling on every execution idea — maker entries, maker exits, a better fee
tier, a cheaper venue.

Cost enters an R multiple linearly, so the board's own two columns pin the
line: `r` at 1x and `r_2x` at 2x give a burden of (r − r_2x) per trade, and
r(c) = r − (c−1)(r − r_2x) is exact by construction. No re-backtest, no new fit.

| round trip | 8-leg gated book | the 5 board legs |
|---|---|---|
| 28bps (2x stress) | 130 d | 112 d |
| **14bps (board)** | **57 d** | **63 d** |
| 9bps (maker exit only) | 49 d | 54 d |
| 4bps (full maker) | 38 d | 47 d |
| **0bps (FREE)** | **32 d** | **43 d** |

**Free execution buys 33-44% of the days and lands at 32-43 median days,
against a 5-15 day target.** Every execution improvement available — and then
some, since 0bps is not purchasable — is worth about a third. The target needs
about 85%. **No amount of execution work reaches the phase goal.**

*Honesty about the reconstruction*: 57/63 days at 1x does not reproduce the
board's published 45. The board scores its 5 legs on the walk-forward window
(2024-09→2026-06) with stage-10 configs re-chosen blind each quarter; this
re-prices the full 2020-09→2026-06 trade file at fixed weights. So the ABSOLUTE
days here are not the board's and must not be quoted as such. The COMPARISON
across rows is valid — it is one book with one thing changed — and that
comparison is the finding.

## Where this leaves H-023

Not a strategy. A **correction to the cost model** that the board should
inherit, and one bug removed.

The next test is the obvious one and it was not run here: apply maker pricing
to the **existing H-002/H-009 fade-family legs** rather than to a fresh grid.
Those legs are already walk-forwarded and already beat their nulls; re-pricing
them is a paired change to a proven book, not a new search, and it is the only
version of this that could move the board. Two of H-009's five legs are XAUUSD
and must NOT be re-priced this way — different venue, fill assumption
unmeasured.

## Files

- `strategies/vwap/stage12_queue.py`, `backtests/queue/stage12_fill_realism.csv`
- `strategies/vwap/stage13_maker.py`, `backtests/queue/stage13_maker.parquet`
- `backtests/queue/stage13.log` (invalid first run), `stage13_fixed.log` (corrected)
