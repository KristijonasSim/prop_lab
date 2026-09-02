# H-010 — VWAP band rejection (from the TradingView "VWAP MR Scalper")

Opened and rejected 2026-09-02.

## The hypothesis

From a published indicator: anchored VWAP with three standard-deviation bands.
A bar reaches a band, then closes back against the move — a "rejection" — and
the trade fades it back toward the VWAP. Volume delta must agree.

**Mechanism, stated before results.** At two or three sigma from the session's
volume-weighted consensus, the price is far from where the day's volume actually
traded. Reversion is paid by the market makers quoting around VWAP; the
counterparty is whoever chased. The rejection candle is evidence the push
failed, and the delta agreeing is evidence aggressive flow has turned.

## Why this needed care before it was worth running at all

`CLAUDE.md` already lists **VWAP std-band fade** as dead: backtest profit factor
3.0, live about 0.7. The cause was a backtest that filled a resting limit on any
wick touch. So this family is not new here — it is the one that burned the trader
before. It was worth re-testing only because the rejection formulation can be
made fill-honest, which the original could not.

A second warning was already in the data: H-002's 105 blind fold choices land on
**trend** and **break** modes and essentially never on **fade**, and every one of
them uses market fills rather than the limit fill. The one VWAP strategy that
works here is not a mean-reversion strategy.

## What was changed from the indicator, and why each change is not cosmetic

1. **Honest fills.** Entry at the next bar's open after a closed rejection bar.
   Never a resting limit at the band.
2. **Real signed flow.** The indicator estimates delta as
   `volume * sign(close - open)` — a guess about a bar it can already see.
   Binance publishes `taker_buy_base_asset_volume`, so the true split is used.
3. **Exits**, which the indicator has none of: revert to the VWAP, a fixed R
   multiple, or time — always with a stop beyond the band so R is bounded.
4. **The H-009 crowd gate**, optional: take the trade only when the long/short
   account ratio is on the other side of it.
5. **A direction control**: every setup also taken the other way.

## Two real bugs found while building it, both of which flattered the result

1. The VWAP "target" could sit **behind** the entry. If the rejection bar closed
   back through the VWAP, a long entered above it had nowhere to revert to, and
   the exit booked a loss as a target hit — 2,096 target hits averaging −0.8R.
   Fixed by refusing the trade when there is no room, and by only honouring the
   target while it is still on the profitable side.
2. The minimum stop distance was 10bps against a **14bps round trip**, so cost
   alone was 1.4R on the tightest trades. Early in a session the volume-weighted
   sigma is tiny and the bands sit almost on top of each other. It became a swept
   dimension rather than a hygiene constant.

## The result — 3 coins x 4 timeframes x 2,592 configurations, 5 null seeds

| cost | revert (the hypothesis) | continue (control) | **paired null** |
|---|---|---|---|
| 0x | 0.946 | 0.991 | **0.965** |
| 1x | 0.792 | 0.818 | **0.845** |
| 2x | 0.681 | 0.686 | **0.747** |
| 3x | 0.585 | 0.577 | **0.660** |
| clears 1.20 at 2x | 280 | 785 | **637 per seed** |

**The null is better than the real market at every cost level**, and clears the
gate more than twice as often as the hypothesis. This is the H-005 verdict again:
a phase-randomised copy of the market satisfies these rules more easily than the
market does, which is what a fade rule does on shuffled data.

The control is equally damning — taking every setup the other way scores no worse.
Neither side carries information.

## The lever table refutes the mechanism directly

Median profit factor at 2x cost, by choice:

| lever | values |
|---|---|
| **target** | **revert to VWAP 0.500** · fixed R 0.679 · **time only 0.816** |
| anchor | daily 0.581 · weekly 0.661 · rolling 0.759 |
| entry band | 1σ 0.713 · 2σ 0.688 · 3σ 0.573 |
| min stop | 25bps 0.592 · 50bps 0.671 · 100bps 0.737 |
| flow filter | off 0.679 · on 0.682 |
| crowd gate | off 0.659 · **on 0.712** |

**Exiting at the VWAP — the whole idea — is the single most harmful choice in the
grid, and ignoring the VWAP entirely is the best.** Deeper bands are worse, not
better, which is the opposite of the "75-80% reversion from the 2nd or 3rd band"
claim the indicator's write-up makes. The delta filter does nothing (0.679 to
0.682), which is notable given it is the indicator's headline feature — though
that is the crude `sign(close-open)` proxy replaced by the real thing, so this is
a fair test of the idea rather than of the approximation.

The best-looking configurations trade **0.018 times a day** — one every two
months over six years, 40-46 trades. That is search noise and it fails the phase
constraint on its own.

## What is worth keeping

The crowd gate lifts even this dead strategy, 0.659 to 0.712. That is a third
independent confirmation of H-009, on a strategy with no edge of its own, which
is the cleanest possible setting to see a filter work in.
