# H-043 — the Fear Curve. Gate 2: a real backtest.

**Pre-registered 2026-09-15, before any number.** Gate 1 (`costgate.py`) passed:
all six standard markets clear twice their own spread, which five crypto
hypotheses could not.

## The rule being tested

`VIX3M / VIX` — three-month implied volatility over one-month. Below 1 the near
month is bid above the far month, which happens when the market is frightened
now rather than in general. **Buy the stressed bucket.**

Gate 1 established the direction is **not** risk-off. Equities, gold and BTC all
RISE after an inversion; only silver and USDJPY fall. The mechanism is the
bounce off a scare, not a flight to safety, and the biggest responses are on the
indices — which is where a VIX signal should be strongest, since VIX is built
from S&P options.

**A VIX reading dated D closes at 16:15 ET and is used from D+1.** That is the
only look-ahead this design can have and it is handled in the loader.

## Windows, per Kris's cap of 5 years

| markets | window | why |
|---|---|---|
| XAUUSD, BTCUSDT | **5 years** | the cap; doubles the event count over 3 |
| SPX500, NAS100, US30, XAGUSD, EURUSD, GBPUSD, USDJPY | **3 years** | all that is cached |

**The 3-year window flatters this signal.** Gold reports +82.6 bps at 5 days over
3 years, +96.8 over 5 and **+38.0 over 11**. Every number below is the optimistic
end of a range and is to be quoted that way.

## The grid — 12 cells per market, fixed now

| axis | values |
|---|---|
| entry bucket | bottom **1** or bottom **2** quintiles of the ratio |
| hold | **3, 5, 10** days |
| stop | **1.5** or **3.0** × ATR(14) |

Long only. Direction is not swept — gate 1 fixed it. One position at a time.
Entry at the next day's open after the signal, exit at the open after the hold
or intraday if the stop is touched. Costs from `core/markets.py`, reported at
1x / 2x / 3x.

## What counts as a win — all four, fixed now

1. **PF ≥ 1.20 at 2x cost** on gold, out of sample.
2. **Positive at 2x on at least three of the nine markets**, out of sample. One
   market is a hypothesis, not a result — the standing universe rule exists
   because the Asian range break beat its null 3.5x on gold and nowhere else.
3. **Beats a block-shuffled signal**, 25 seeds, on gold.
4. **Same sign in every calendar year** of its window.

Reported but **not** pass conditions, so they cannot select a cell: expected days
under the HOUSE spec, and `best_day_share` — the reason B was chosen over a
third crypto attempt was profit shape, and H-027's 95.5% is the number to beat.

## Out of sample: a single split, and why not the usual walk-forward

The repo's blind quarterly walk-forward is the standard and **it does not fit
here**. Three to five years of a rare signal gives 17–26 stress episodes; split
into quarters, most folds would contain zero events and the selector would pick
on noise. **First 60% selects the cell, last 40% is blind.** Stated in advance so
the weaker design cannot be presented later as the strong one.

## Kill criterion

> If gold fails condition 1 out of sample, or fewer than three markets are
> positive at 2x, H-043 is dead. A signal that only works on the window that
> contains Aug-2024 and Apr-2025 is a description of those two events.

## The trap most likely to produce a false pass

**Two V-shaped bottoms dominate the sample.** 2024-08-05 and 2025-04-03 are the
two longest inversions in the three-year window and both were followed by sharp
recoveries. "Buy the dip" was correct in that specific window in a way it was not
in 2015 or 2018. The year-by-year condition exists to catch it, and if the result
rests on those two episodes the honest verdict is that the sample is the finding.

---

# RESULT — 2026-09-15. Dead on the criterion, and the null is what kills it.

`backtests/vixterm/gate2.json`. Blind half = last 40% of each window.

## Out of sample, best in-sample cell carried forward

| market | yrs | cell | OOS n | PF@1x | PF@2x | PF@3x |
|---|---|---|---|---|---|---|
| **XAUUSD** | 5 | q2 h10 s1.5 | 37 | 1.154 | **1.140** | 1.126 |
| BTCUSDT | 5 | q2 h5 s1.5 | 50 | 1.120 | 1.065 | 1.012 |
| SPX500 | 3 | q1 h10 s3.0 | 12 | 2.487 | 2.414 | 2.337 |
| NAS100 | 3 | q2 h5 s3.0 | 29 | 2.453 | 2.387 | 2.323 |
| US30 | 3 | q1 h10 s3.0 | 12 | 2.101 | 2.044 | 1.988 |
| XAGUSD | 3 | q2 h10 s3.0 | 19 | 1.549 | 1.516 | 1.483 |
| EURUSD | 3 | q1 h10 s3.0 | 12 | 1.755 | 1.746 | 1.737 |
| GBPUSD | 3 | q1 h10 s3.0 | 11 | 2.668 | 2.638 | 2.607 |
| USDJPY | 3 | q2 h3 s1.5 | 39 | 1.069 | 1.029 | 0.990 |

**Condition 2 passes handsomely: 9 of 9 positive at 2x.** Conditions 1, 3 and 4
fail, and the failures are not marginal.

## The null settles it

| market | real PF@2x | null median | null p90 | beats? | OOS by year (R) |
|---|---|---|---|---|---|
| **XAUUSD** | **1.140** | **2.321** | **3.127** | **no** | 2025 +7.7, 2026 **−5.1** |
| SPX500 | 2.414 | 1.344 | **3.595** | **no** | 2025 +2.2, 2026 +0.6 |
| NAS100 | 2.387 | 1.152 | 1.852 | yes | 2025 +3.3, 2026 +2.4 |
| GBPUSD | 2.638 | 0.907 | 1.745 | yes | 2025 +1.0, 2026 +1.8 |

**Gold fails every condition it was the gate for.** PF@2x 1.140 against the 1.20
bar; it loses to its own shuffled signal by a wide margin (median 2.321); and its
sign flips between years, +7.7 R then −5.1 R. **A shuffled VIX series trades gold
better than the real one.**

**SPX500 — the market a VIX signal should own, since VIX is built from S&P
options — also loses to its null.** That is the tell. If the mechanism were real,
the S&P is where it would be strongest, and instead the two survivors are NAS100
and **GBPUSD**, for which no mechanism was ever proposed.

## Verdict

**Dead**, by the kill criterion written before the run: *"If gold fails condition
1 out of sample… H-043 is dead."* It failed 1, 3 and 4.

**The criterion was also mis-specified, and saying so is not a rescue.** Gold was
made the gate because it is this project's live market, not because the mechanism
pointed there — gate 1 had already shown the indices responded four times more
strongly. A better-specified test would have anchored on SPX500. **It would have
failed too**, on its own null.

## What this cost and what it bought

Half a day, because the fee gate ran first and was cheap. The thing that killed
it — the null — is the thing that killed H-003, H-005, H-010 and the MA200 gate,
and it did so again on the market with the most data.

**What survives is the method note, not the signal.** The fee-gate-first order is
correct and should stay: it took five crypto hypotheses to learn that costs
decide more than edges, and this hypothesis cleared costs on all nine markets and
still died. **Clearing costs is necessary and nowhere near sufficient.**

Nine markets, 2 of 4 nulls beaten, no mechanism behind either survivor, 11–29
trades each. That is a description of 2025–26, not an edge.
