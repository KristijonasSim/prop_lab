# H-0NN — <one line: what is being claimed>

Written <date>, BEFORE any code. Copy this file to `docs/prereg/H-0NN.md` and
fill it in. If a section cannot be filled, the study is not ready to run.

**Why this file exists.** At a trial count of 1 the deflation threshold is
exactly zero and the deflated Sharpe collapses to the plain probabilistic Sharpe
(`core/searchcost.sr_threshold`). The project's ledger currently charges **228
trials**, a bar of 2.81 sigma. A pre-registered single arm faces a bar of zero.
**This page is worth about 2.8 sigma and takes thirty minutes.**

---

## Mechanism

Why should an edge exist here, and **who is on the other side of the trade**?
State it before any result. A mechanism that cannot name the loser is a pattern,
not an edge.

## Arms — the COMPLETE list

Every configuration that will be run. Adding one later is a **new**
pre-registration with a new trial count, not an amendment to this one.

| # | arm | what it varies |
|---|---|---|
| 1 | | |

Raw trial count this study will charge: **N = <markets × timeframes × arms>**

## Null

Which null (`core/nulls.py`), how many seeds, and — numerically — what beating it
means. Note if the event is concentrated in an hour of the day: `core/probe.py`'s
null shifts events to random positions and does **not** match hour of day, which
gifted a short-side daily arm about 5 bps on 2026-09-13.

## Kill criterion

**The number that ends this study, written before the number is known.** One
sentence, one threshold. Example, from the top-N study that was correctly
withdrawn on 2026-09-17: *"the real speed-up survives only if the paired null's
is below 1.25x."*

## Cost bar

Round trip on the market this would actually be traded on, and the multiple of
it the effect must clear (`core.screen.COST_MULT` is 2.0).

| market | round trip (bps) |
|---|---|
| | |

## Markets

The six standard (`core/universe.STANDARD`: BTCUSDT, XAUUSD, XAGUSD, EURUSD,
GBPUSD, USDJPY), or a written reason for anything narrower.

## Window and events

Three years by default. Expected **independent** event count
(`core.screen.independent_events`) — not row count. Under 40 the study is dead
before it is run.

## What would make this WRONG

The result that would make the author abandon the mechanism rather than tune it.
If nothing would, the study is not a test.
