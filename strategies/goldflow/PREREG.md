# H-046 — gold footprint. PRE-REGISTRATION, written before any result.

2026-09-17. Kris picked this from `docs/NEW_EDGES.md`: *"1. Footprint charts"*.

**Nothing in this file may be edited after the first number is read.** Results go
in a RESULT section appended at the end, scored against what is written here.

---

## The mechanism, stated before any number

Price is where the last trade happened. **Footprint is who had to have it.** When
buyers lift offers harder than sellers hit bids, the imbalance between the two
sides leads the price that eventually prints, because the aggressor is the one
paying the spread to get filled now.

**Who is on the other side.** Market makers and passive liquidity, who are short
the imbalance and must re-hedge. When their inventory gets one-sided they widen
or pull, and price moves to find the other side. That is the effect being
measured.

**Why gold, and why now.** The only family that has ever worked in this repo is a
data feed, not a price pattern. Five feed edges — H-006, H-024, H-031, H-034,
H-042 — were real, beat their nulls, and **all died to crypto's 14 bps round
trip**. Gold's round trip is **1.83 bps**. This is that family on the one market
that can pay for it, and it has never been run because the data was believed not
to exist.

---

## Gate 1 — WHAT IS THIS DATA, ACTUALLY? Unresolved at the time of writing.

Dukascopy tick records are `>IIIff` — ms, ask, bid, **askVolume, bidVolume**.
`core/fx_spread.py` has downloaded them since 2026-09-07 and discards both
volume fields.

**The question that decides whether this study means anything:** is
`askVolume` the size that TRADED at the ask, or the size QUOTED at the ask?

* If **traded**, the difference is aggressor delta and the mechanism above
  applies directly.
* If **quoted**, it is a liquidity imbalance and this is **H-024 on a different
  market** — which was real, monotone, beat its null, and cleared its cost in
  **0 of 935 cells**.

**The test, fixed now:** sum tick volumes within each hour and compare against
the hourly candle volume already cached in `data/XAUUSD_dukascopy_1h.parquet`.
A stable ratio with high correlation means the tick volumes decompose the candle
volume by side, and the candle volume is what every backtest in this repo already
uses. A poor correlation means they measure different things and the study needs
re-framing before it goes further.

**This gate has no pass/fail attached to the hypothesis** — it decides what the
signal is CALLED and which prior applies, and the answer is reported either way.

---

## Gate 2 — THE FEE TEST, AND IT RUNS BEFORE ANYTHING ELSE

Introduced by H-043 and it saved a day: a gross number under the spread makes
nulls and walk-forwards pointless.

**Bar: the gross forward return of the top-versus-bottom decile spread must
exceed 3.66 bps**, which is 2x gold's measured 1.83 bps round trip. This is the
same bar H-043 was held to.

No stops, no walk-forward, no selection at this gate. Decile the signal, measure
mean forward return at each horizon, read the spread.

---

## The arms. Four, fixed now, and no others without a new pre-registration.

Bar-level primitives built from tick volumes, on **15m, 1h and 4h** — the
timeframes H-027 already uses, so nothing is being searched over.

| # | arm | definition | direction |
|---|---|---|---|
| **A1** | **delta** | `(askVol − bidVol) / (askVol + bidVol)` per bar | follow: high delta → long |
| **A2** | **cumulative-delta divergence** | price makes a 20-bar high while cumulative delta does not (and the mirror) | fade the price extreme |
| **A3** | **absorption** | top-decile total volume with bottom-decile `|close − open|` | fade the move into it |
| **A4** | **exhaustion** | price extends ≥ 2 sigma while `|delta|` falls against its 20-bar average | fade the extension |

**4 arms x 3 timeframes = 12 cells. The search is priced: 12 tests at a 95th
percentile expect 0.6 false passes.** Anything at exactly one cell is noise.

---

## Gate 3 — the null, and it must be hour-matched

`core/probe.py`'s null shifts events to random positions and **does not match
hour of day** — owed since 2026-09-13. Gold's flow is strongly session-dependent,
so an unmatched null would hand any London- or NY-concentrated arm a free win.

**The null here draws its comparison population from the SAME HOUR OF DAY**, and
that is built in this study rather than deferred again.

---

## Kill criteria, fixed now

The hypothesis is **dead** if any of these holds:

1. **Gate 2 fails** — no arm's decile spread clears 3.66 bps gross at any horizon.
2. **The response is flat in the signal.** If the decile means do not order
   monotonically, the size of an imbalance says nothing about what follows and
   there is no mechanism to repair. This is what killed **H-008** and it is
   decisive on its own.
3. **It survives at one cell out of twelve.** With 0.6 false passes expected,
   one is not a result.
4. **It flips sign across timeframes.** Recorded four times now — H-026's
   fibonacci, H-035's netflow, H-040's atr/pct, H-044's EMA/SMA. Two arms moving
   opposite ways at 1h and 4h is this repo's signature for no effect.
5. **It loses to the hour-matched null.**

## What would make a pass a FALSE one

* **H-024 is the precedent and it is not encouraging.** Book-depth imbalance was
  real, monotone, beat its null and was stable across years, and the edge was a
  **three-second** effect that never reached 15m–4h. A monotone decile response
  here is necessary and nowhere near sufficient.
* **The measured-cost trap.** Gold's 1.83 bps is Dukascopy's own spread, and the
  live demo measured **Bybit charging 5.50 bps round trip on XAUUSDT — exactly
  3.0x**. Any arm that clears 3.66 but not ~11 bps is not tradeable at the only
  venue this project has actually touched. **Report at 1x, 2x and 3x.**
* **Dukascopy volume is its own liquidity-provider volume, not a central-exchange
  tape.** Spot gold has no central exchange; there is nothing to validate it
  against. Every result carries this sentence.

## Scope

**Gold first**, then the standing universe minus BTC (`XAGUSD`, `EURUSD`,
`GBPUSD`, `USDJPY` — all have Dukascopy ticks). The written reason for starting
on one market: gate 2 is a screen, and if gold cannot pay at 1.83 bps nothing
cheaper exists in the universe to rescue it.

**Test window: 3 years**, per the standing rule.


---

# GATE 1 — RESULT. 2026-09-17. Passed, and it answered more than it was asked.

`core/gold_flow.py`. Tick volumes summed per hour and compared against the
cached hourly candle volume, on three days in three different years.

| day | hours | `max abs(volume − bidvol)` | `max abs(volume − askvol)` | corr(total, volume) |
|---|---|---|---|---|
| 2025-05-14 | 17 | **0.000000** | 2.7709 | 0.912 |
| 2024-11-06 | 23 | **0.000000** | 4.3741 | 0.932 |
| 2026-03-12 | 23 | **0.000000** | 0.7458 | 0.991 |

## What it says

**The cached candle volume IS the bid-side tick volume, exactly.** Not close —
zero to floating-point precision, on every hour of three days years apart. The
two fields in the tick file reconcile perfectly against data this project has
been running on for weeks.

**The cause is in `core/fx_data.py:47`**, which downloads
`BID_candles_min_1.bi5`. Dukascopy's bid candles carry the bid-side volume, so
every `volume` figure in `data/XAUUSD_dukascopy_*.parquet` is one side of the
book.

## Three consequences, and none of them was known this morning

1. **Gate 1 passes in the strongest possible form.** The tick volumes are not a
   different measurement that has to be reconciled — they are the same
   measurement, and the file simply carries the other half of it.
2. **The ask side is genuinely new information.** Nothing in this repo has ever
   seen it. Every volume feature ever computed here — including H-027's own
   `min_rvol` filter, which reads `df.volume` — has been a bid-side quantity.
   That is not an error, and it was not written down anywhere.
3. **What the signal should be called.** These are two-sided sizes published
   with each tick, so `delta` here is a **liquidity imbalance**, not confirmed
   aggressor flow. That places it in the **H-024 family** — which was real,
   monotone, beat its null, was stable across years, and cleared its cost in
   **0 of 935 cells**. That is the prior this study carries into gate 2, and it
   is not a friendly one.

**The caveat that travels with every number from here:** this is Dukascopy's own
liquidity-provider size, not a consolidated tape, and spot gold has no central
exchange to validate it against.

## Status

**Gate 2 (the fee test) is blocked on data.** The three-year hourly tick pull is
running; Dukascopy rate-limits hard enough that it is an overnight job, so
`core/gold_flow.py download` caches one day per file and skips what it already
has, and can be killed and restarted without losing work.
