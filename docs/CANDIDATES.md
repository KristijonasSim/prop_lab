# Candidate mechanisms — written 2026-09-08

What is left to try, after reading `STRATEGY_LOG.md` end to end. Read
`core/target_profile.py` first: it says what shape a candidate must have.

---

## Two things this project already measured that I got wrong on 2026-09-08

I recommended attacking execution cost before checking the log. The log had
already answered it, twice, and both answers are recorded here so nobody spends
a week on it again.

### 1. Maker fills are SAFE on BTC perps. The queue fear was refuted.

`H-023 stage 12` measured the fill assumption on **ticks**, not bars:

* **through-given-touch is 99.8-100%** at every distance from 5 to 80bps;
* **96-98%** even assuming 10 BTC already resting ahead in the queue;
* **adverse selection ~0** — the forward return 1h after a through-fill is
  within **0.08bps** of the return after a mere touch, at every distance.

A 15m BTC perp bar carries about **1,600 trades**. Price does not kiss a level
and leave. The PF 3.0 → 0.7 scar from the previous repo was real, but the
generalisation from it was wrong *for this instrument and bar size*.

**Scope, and it matters:** one market, one bar size, one regime. ETH, SOL and
XAUUSD are unmeasured and must not be quoted at maker cost.

### 2. Cost is NOT the lever. This direction is closed.

`H-023 stage 14` re-priced a whole book from 14bps down to **zero**:

| round trip | days to funded |
|---|---|
| 14bps (board taker) | 57 |
| 4bps (full maker) | 38 |
| **0bps (free)** | **32** |

**Free execution buys 33-44% of the days. The pace target needs about 85%.**
No execution improvement — maker entries, maker exits, fee tier, cheaper venue —
reaches the goal on its own.

Cost still matters at the margin: on a 100bps stop, going 14bps → 4bps is worth
about 0.10R per trade against a required average of 0.2-0.4R. Useful. Not
sufficient. **Take the maker fill because it is free money and measured safe —
do not expect it to fix pace.**

---

## The shape a candidate must have

From `core/target_profile.py`, at Kris's 1-2 trades/day:

| win rate | reward:risk | trades/day | days |
|---|---|---|---|
| 50% | 3:1 | 1-2 | 11-12 |
| 55% | 2:1 | 2 | 9 |
| 55% | 3:1 | 1 | 6 |

**The floor is roughly 50% wins at 3:1.** For comparison the board's own
strategies average **+0.035R** and **+0.065R** per trade. This is not a tuning
gap; it is a different kind of trade. Everything tested here wins small and
often. This needs asymmetry.

**And the table is optimistic** — it assumes independent trades. Real losing
streaks cluster.

---

## What survived 26 hypotheses

| id | mechanism | state |
|---|---|---|
| **H-025** | **DVOL implied vol**. BTC `dvolz`@4h, **8.9bps**, survives 1d/1w/1mo block nulls, same sign in 5 of 5 realised-vol buckets so it is not realised vol in disguise. Direction: high implied vol → higher forward return. | **real, small** |
| **H-015** | **Systemic positioning**. Complex-wide crowd z across 11 coins. Beats every null seed; held-out **+3-6%**. | **real, small, and it is a GATE not an entry** |
| H-018 | Vol-managed sizing. Wins 3 of 4 evaluation structures. | an overlay, not a strategy |

Everything else is dead: funding fade (H-004), perp-spot premium (H-013), crowd
ratio (H-006), book depth (H-024), absorption (H-022), cross-sectional ranking
(H-007), relative volume (H-020), quarter-hour (H-021), common flow (H-019), and
every price pattern (H-001, 003, 005, 008, 010, 011, 012, 026).

**Neither survivor is a 50%@3:1 strategy.** Both are small continuous edges of
exactly the wrong shape.

---

## The observation that should drive the next round

**Every one of the 26 scored every bar and took the top N.** That design produces
many small edges — 1-9bps — which is precisely the shape that cannot pay a round
trip and cannot reach 3:1 asymmetry.

A 3:1 trade is not a slightly better continuous signal. It is a **specific,
identifiable condition that precedes a large move**, taken rarely.

Nothing in the log tests that shape.

---

## Untested candidates, in the shape the target needs

Each states the mechanism and who is on the other side, per `CLAUDE.md`.
**None is agreed work.** Kris picks.

### C-1 Liquidation cascade

**Mechanism.** Leveraged longs are force-closed by the exchange, not by choice.
Forced selling is price-insensitive, so it overshoots. The other side is anyone
willing to absorb inventory for a few minutes.

**Why it fits the shape.** Rare (tens of events a year), and the move is large
relative to a stop placed beyond the cascade low — the asymmetry is structural,
not fitted.

**Feeds we already have.** Open interest collapsing while taker delta spikes in
the same direction, 5m, from 2020-09.

**How it dies.** If the reversal is not reliably larger than the noise, or if
there are too few events to say anything. Sample size is the first thing to
check, before any strategy.

---

### C-2 Funding settlement, as an event rather than a level

**Mechanism.** Funding is paid at fixed 8-hourly moments. Positioning is
adjusted *around* those moments, which is a scheduled, observable flow.

**Not H-004.** H-004 tested funding as a **continuous** fade/carry signal scored
on every bar and it failed cleanly (0 of 12 walk-forward series clear 1.20). The
settlement *moment* is a different object and was never tested. Say so out loud,
because it looks like a re-proposal and is not.

**Fits the constraint exactly.** Three settlements a day gives at most 3 trades,
naturally 1-2 after filtering.

**How it dies.** The flow is well known and may already be arbitraged into the
minutes before settlement. Measure the move around the settlement first; if the
response is flat, stop.

---

### C-3 DVOL as a regime switch on a directional trade

**Mechanism.** H-025 established that BTC `dvolz`@4h carries real information
(8.9bps, survives every null). It was tested as a **signal to trade**. It has
never been tested as a **filter that decides when a directional trade is worth
taking** — which is how a volatility measure is normally used.

**Why it might change the shape.** A filter does not need to be big; it needs to
concentrate the same edge into fewer, better trades. That raises average R and
cuts trades per day, which is the direction the target needs.

**How it dies.** H-013 failed this exact test — as a second gate it improved PF
and drawdown but halved R/day, so return/drawdown *fell*. **Same test, same kill
criterion: return per unit of drawdown must rise, not just PF.**

---

### C-4 Power of Three with a stop and a target

**Mechanism.** Accumulation, manipulation, distribution. Kris trades it.

**Status.** H-026 killed one formalisation: a fixed hold to the session close,
**no stop and no target**, and the sweep-reversal loses gross on BTC and ETH and
wins on SOL — a sign flip across three coins at ~1,500 events each is the
signature of no effect.

**What is untested.** The version with a stop and a target, which is what Kris
actually trades, and which is a different payoff shape entirely — a stop plus a
target is how 3:1 asymmetry is created in the first place.

**Blocked on Kris:** his exact entry, stop and target rules. Without them this is
guesswork and will be killed for the wrong reason.

---

## What NOT to do

* Another continuous single-feed crypto signal at 15m-4h. Six measured, all
  1-9bps, against a spec needing far more. The band looks structural.
* Any execution-cost project as a route to pace. Closed above.
* Stacking signals. Combining nearly-independent feeds scored 3.1bps *worse*
  than the best single ingredient.
* Buying more accounts before something works. Kris's call, 2026-09-08: scale
  after a strategy is proven, not before.
