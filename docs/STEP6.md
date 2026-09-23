# Step 6 — the re-check on longer history. Design, 2026-09-23

Kris: *"step 6 is only same check as step 3 just on 5 years?"*

Same four gates. **Different window, and the difference is the whole stage.**

`factory/recheck.py`, `tests/test_factory_steps567.py`.

---

## 1. The correction: it tests the holdout, not "five years"

The diagram said *"same rule, longer history"*. Built literally, that is a test
whose window **contains** the three years the idea was selected on. Two thirds
of the evidence would be the exam paper the idea already sat.

So the gate is the **prefix**: `cells.holdout` returns `[end − 5y, start of the
step-3 window)` — bars the idea has never touched. The full five years is
computed and printed beside it, as context, never as the gate.

A rule that clears the holdout and fails the full five years is saying the two
stretches disagree, which neither number says on its own.

---

## 2. What it is for

Steps 3 and 4 are deliberately wide: 24 cells, then up to twelve repairs on one
of them. The 2026-09-21 simulation is what pays for that width.

| junk reaching the desk, per 1,000 tested | |
|---|---|
| 3 years only | **31** |
| 3 years + this step | **0.5** |

**And the 98% is optimistic.** That simulation drew the two windows
independently. Real history is one path — the holdout and the step-3 window are
adjacent stretches of the same market, sharing its regime and its drift, and a
rule that is long gold will look similar on both for reasons unrelated to edge.
**Read a step-6 pass as "it did not fall apart", not as "it replicated".**

---

## 3. Coverage, and why a missing test is not a pass

The window ceiling is Kris's: *"maximum we need is 5 always not more then 5,
ideal 3 years"*. Five is the ceiling and the holdout is the two years in front
of the three.

```
python -m factory.recheck --coverage
```

| market | holdout | source |
|---|---|---|
| XAUUSD | ~1.9y | 11 years of raw 1-minute `.bi5` already on disk |
| BTCUSDT | 2.0y | the spot cache has 9 years |
| XAGUSD, EURUSD, GBPUSD, USDJPY | 2.0y | backfilled 2026-09-23; the caches started 2023-09 |

The four FX/metals caches were pulled to 2021-09 on 2026-09-23 and built into
`{sym}_dukascopy5y_{tf}.parquet` by `scripts/build_5y.py`.

**They are written under their own name rather than by extending
`{sym}_dukascopy_{tf}.parquet`.** Overwriting the three-year cache would
silently change the input of every board number in the repo — H-027's
walk-forward reads exactly those files — for a gain this step gets without it.

**A cell with no usable holdout is `NO DATA`, and `NO DATA` is not a pass.**
Treating a missing test as a passed one is how a pipeline quietly stops testing.
The floor is 250 trading days; below that the holdout cannot carry step 3's
100-trade gate and the gate would stop meaning what it means upstream.

---

## 4. The denominator

Trades/day on the holdout divides by the holdout's **own** trading days,
measured on that market's 1h series so all four of its cells share a
denominator — the same invariant `cells.trading_days` keeps in step 3. Measuring
it per timeframe let the 1d cell disagree with the 1h cell by 13–21% on FX,
purely from the Sunday session-open stub.

---

## 5. What it does not do

It is not a walk-forward and it is not a second search. One idea, one cell —
the cell step 3 chose — one window. If it fails, the idea is finished; there is
no repair stage after this one, by design.
