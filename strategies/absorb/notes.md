# H-022 — Absorption: aggressive flow that fails to move price

Opened and closed 2026-09-05. **Status: DEAD ON COST.** Signal is real,
monotone, stable across 7 of 7 years, beats its null — and is 6.55bps against
the cheapest realistic round trip of 8bps.

## The gap this was aimed at

H-006 measured taker aggression against 8-72h forward returns and found it
flat: +10.8 / +12.5 / +10.7 / +12.0 / +12.2 bps across quintiles. H-021
measured 5m taker imbalance by clock phase against 4-12h returns and found
something real but 5x too small to pay for. Neither looked at the 15m-4h band,
and neither built the feature below.

Because "how much flow" is the wrong question — H-006 proved aggression is not
directional on its own. What should carry information is aggression measured
**against the price response it produced**:

* heavy buying that lifts price — the buyer is paying for liquidity and getting
  it. Nothing to fade.
* heavy buying that does **not** lift it — somebody passive is absorbing every
  market order, and that somebody has size and no deadline.

**Mechanism, stated before the result.** The counterparty is an institution
working a large order who wants the fill and not the tick, and who is therefore
price-insensitive in the mirror image of the aggressor: the aggressor has a
deadline, the absorber has a quantity. When the aggressor is done the passive
side is still there and price drifts back. Same class of counterparty argument
that made H-009 work, and it is the third of the three candidate edges H-006's
notes listed and never tested.

**Feature.** Both terms z-scored on a shifted trailing window, so neither the
flow nor the return is scored against itself:

    absorb_k = z(signed taker flow over k) - z(log return over k)

`absorbq` is the same thing restricted to bars where |z(flow)| > 1 — absorption
is meaningless on a quiet tape, and including quiet bars dilutes the buckets.

## Stage 1 — quintile response, BTCUSDT, 630,371 bars, 2020-09 → 2026-08

The signal is real and it is small.

| feature | horizon | q1 | q5 | spread | monotone | 7yr sign |
|---|---|---|---|---|---|---|
| `absorbq_15m` | 2h | +2.5 | +0.1 | **−2.5** | 1.00 | 7/7 |
| `flow_15m` | 2h | +2.0 | −0.3 | −2.3 | 1.00 | 7/7 |
| `flow_15m` | 30m | +1.3 | −0.7 | −2.0 | 1.00 | 7/7 |

Sign is negative throughout: absorbed buying is followed by weakness, which is
the direction the mechanism predicts. Monotone 1.00 and the same sign in 7 of 7
calendar years on the top cells, and they beat every null seed.

**Zero of 100 cells clear any cost gate** — not 14bps taker, not 28bps at 2x,
not 9bps mixed, not even an 8bps maker round trip.

## Stage 2 — the tails, on trailing thresholds

A quintile averages 20% of the sample, so a tail-concentrated signal is diluted
10:1. H-006 hit exactly this — every configuration it selected sat at the edge
of its grid at q=0.05, later extended to 0.02. So the same features were cut at
10 / 5 / 2 / 1% tails, thresholds trailing over 30 days and recomputed daily
(never full-sample).

Tail concentration is real and it is not enough:

| tail | median fade bps | best cell |
|---|---|---|
| 10% | 0.55 | 1.55 |
| 5% | 0.47 | 1.93 |
| 2% | 0.48 | 4.31 |
| **1%** | 0.31 | **6.55** |

Best cell anywhere: `absorbq_1h` at a 4h horizon, 1% tail — **6.55bps per
trade**, 4,721 trades over six years, beats its null best of 3.53.

**Still 18% short of the cheapest round trip that exists**, and the shortfall is
worse than that number looks, for two reasons.

1. **The edge is one-sided.** Of that 6.55bps, absorbed *selling* earns
   +15.95bps and absorbed *buying* earns **−2.93** — the short side is a loser.
   A symmetric strategy is not what was measured; a long-only one halves the
   trade count.
2. **Hit rate is 52.0%.** With a 6.55bps gross edge, essentially all of the
   result is a small number of large winners, which is the shape that does not
   survive a stop.

## Verdict

Third hypothesis in this project to die at exactly the same wall: H-007 (a real
10% profit-factor edge that 14bps ate whole), H-021 (2.67bps), H-022 (6.55bps).
The pattern is now specific enough to be worth stating as a rule:

> Every price/flow feature measured here lands in the 1-7bps band. That band is
> below every round trip available to a taker. The binding constraint on this
> project is not signal discovery, it is **execution cost**.

That is what sent the next block to H-023 (`strategies/vwap/stage12_queue.py`)
— measuring whether resting-limit fills are real, because a maker round trip is
4bps and would move the gate this hypothesis missed by 18%.

Do not re-propose a flow-versus-response feature without a maker execution
argument attached.

## Files

- `strategies/absorb/stage1_response.py` — quintile response, block-shuffle
  null, year-by-year sign check.
- `strategies/absorb/stage2_tails.py` — tail response on daily-anchored
  trailing thresholds.
- `backtests/absorb/stage1_response.csv`, `backtests/absorb/stage2_tails.csv`.
