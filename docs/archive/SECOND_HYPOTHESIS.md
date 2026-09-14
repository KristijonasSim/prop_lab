# The second evaluation — what to build, and why

Written 2026-09-10. Kris: *"our next job is to create a separate completely
different hypothesis for a 2nd evaluation."*

H-027 is on a demo account and the entry axis is closed. This is the proposal for
what runs the second account. **Nothing is built until Kris picks one.**

---

## What "different" has to mean here

A second strategy is not worth having because it is also good. It is worth having
because **it fails at different times**. Three tests it has to pass before the
mechanism is even interesting:

| test | why |
|---|---|
| **different market** | H-027 is gold. Two gold accounts breach together. |
| **different direction of the bet** | H-027 follows a displacement. A second follow-the-move strategy is the same trade wearing a hat. |
| **different holding period** | H-027 holds a median 19h and up to a fortnight. |

And one more that only became visible today:

| **a SMOOTH payoff** | H-027 makes 23-36% of its profit on one day, so it is **never payout eligible** under a 20% best-day rule. A second strategy with many small wins is payable where the first is not, which widens the list of firms we can use rather than narrowing it. |

That last line is the strongest single argument for what to pick.

---

## CANDIDATE A — the overnight session premium on equity indices

**The mechanism, stated before any result.** Equity index returns are not spread
evenly across the day: a large share of the total accrues **between the close and
the next open**, and the intraday session carries far more of the realised
volatility than of the return. Who is on the other side is nameable - leveraged
intraday participants who will not carry overnight gap risk and flatten into the
close, and market makers who charge for warehousing it. That is a risk premium
being paid to whoever will hold the position while the market is shut, and it is
one of the few effects in this repo's history with a payer you can point at.

| | |
|---|---|
| market | NAS100, SPX500, US30 - **we have three years of 1h bars, untouched** |
| direction | long the close, flat at the open. Not a displacement trade. |
| holding | ~17 hours, once per session |
| frequency | **~250 trades a year per index** - the fastest thing proposed here |
| payoff | many small wins. **This is the one that could be paid under a consistency rule.** |
| correlation with H-027 | different asset class, different clock, opposite payoff shape |

**Why it might fail, and these are not small.** It is the most published anomaly
in equities, so the honest prior is that it is arbitraged or that the edge lives
entirely in the cash session that a CFD cannot access. Our index costs are
**assumed, not measured** (1.8bps round trip, deliberately pessimistic), and
today's screen put index sigma/cost at 3.9-7.7 against gold's 17.2. A CFD's
overnight financing charge is a direct tax on exactly this trade and it is not in
any cost model here. **It is also on the edge of the known-dead list** - session
ORB is dead in this repo - though a session RANGE breakout and a session RISK
PREMIUM are different claims.

**First thing to measure:** the overnight versus intraday return split per index,
gross, before any strategy. If the split is not there, the idea dies in an hour.

---

## CANDIDATE B — crowd positioning, rebuilt with a stop and the new sizing

**The mechanism.** Binance publishes the long/short **account** ratio - a headcount
of who is positioned which way, not a size-weighted number. Fading it works, and
this repo has already measured it properly: quintile response +25.0 / +21.8 /
+13.5 / -0.9 / -13.2 bps over 24h, **monotone**, same sign in 6 of 7 years, beats
every block-shuffle null, and PF 1.227 at 2x cost out of sample on BTC. Following
the crowd instead loses 13.35bps a trade, so the direction is not arbitrary.

**Why it is being re-proposed after being closed.** H-006 was closed on 2026-09-07
on a kill criterion set in advance, and **the signal was never what failed** - the
risk shape was. With no stop, R is a return over trailing volatility, one loser
runs the whole hold, and the book drew down 63.5R against H-002's 3.8R. Two things
have changed since:

* **Budget-linear sizing** (adopted today) cuts blown accounts 29.5% → 16.9% on
  H-027 by shrinking size as the drawdown budget is spent. It attacks precisely
  the failure that killed H-006.
* **Today's cost work** showed that a stop measured in many sigma makes the round
  trip 0.22% of a full stop, which is what makes a wide-stopped, long-held book
  affordable at all.

**Be honest about the counter-evidence.** The repo already tried adding a stop and
reverted it: the fold selector picked *no stop* in 37 of 52 folds. And shortening
the hold made drawdown **worse**, monotonically. So this is a re-open on a changed
risk framework, not on a new signal - and if the drawdown does not come down, it
dies again and stays dead.

| | |
|---|---|
| market | BTC and 16 other coins, **six years of 5m metrics on disk** |
| direction | fade the crowd - mean reversion against positioning |
| holding | 8-72h in the original work |
| correlation with H-027 | different asset class, opposite direction, feed-driven |
| the standing pattern | **every leg that has ever worked in this project came from a data feed, not a price pattern.** Twelve price hypotheses have died here. This is the family with the better base rate. |

**Practical cost:** it needs a crypto-capable prop firm, which narrows the list -
and Bybit already gives us a demo venue for it.

---

## The weaker two, for completeness

* **A gold feed layer (H-030).** COT positioning and CME volume/OI as a gate on
  gold. It serves the strategy we already trade - and that is exactly why it is
  wrong for a second account: it would make the two accounts *more* correlated.
* **Volatility risk premium on BTC (H-025 / DVOL).** Already measured into the
  1-9bps band against a spec that needs 8-20bps net. Needs a new argument, not a
  free slot.

---

## What I would pick, and why

**A first, B second** - not because A is more likely to be real, but because it is
**decidable in an afternoon**. One measurement, made before any strategy exists,
tells us whether the overnight/intraday split is there on our own data. If it is
not, we have lost an afternoon. B needs a stop grid, a walk-forward and a
drawdown study before it says anything, and it is re-opening something already
closed once.

The deciding argument for A remains the payout shape: **H-027 cannot be paid at a
firm with a consistency rule, and a many-small-wins strategy can.** Two accounts
that are both unpayable at half the firms is a worse portfolio than one of each.

**Kris picks. Nothing is built until then.**
