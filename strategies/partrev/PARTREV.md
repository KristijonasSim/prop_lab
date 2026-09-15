# H-047 — participation decides whether a move reverses. REAL, AND TOO SMALL.

Pre-registered in `PREREG.md`, including the addendum, each before the stage it
governs. Run: `stage1_response.py`, `stage2_tail.py`.
Records: `backtests/partrev/stage1.json`, `stage2.json`.

**Window** 2023-09 → 2026-07, 15m bars, all six of `core/universe.STANDARD`.
72 cells at stage 1 (6 markets × 3 participation terciles × 4 horizons).

---

## The claim

A move carrying volume is information and stays. A move carrying none is a
liquidity provider's inventory and comes back. So the reversal should be
**strongest in thin participation and weakest in heavy** — an interaction, not a
fade.

## 1. The signal is real, and this is the strongest part of the result

| | |
|---|---|
| cells | 72 |
| false passes expected at p < 0.05 | 3.6 |
| **observed at p < 0.05** | **28** |
| best cell | GBPUSD, h = 1 bar, **thin** tercile, t = 6.12 |
| **best cell vs the best-of-72 block-permutation null** | **p = 0.000** |

**The five most significant cells in the table are all the thin tercile.** That
is the hypothesis's own shape appearing in the data rather than a market being
noisy, and it clears a search correction that killed H-046 the same day.

The direction is right too. USDJPY at h = 12 reads **+1.00 / +0.47 / −0.41** bps
across thin / mid / heavy: reversal when nobody traded, **continuation** when
everybody did, which is the mechanism stated as a sentence.

## 2. And it is between two and four times too small to trade

Per-trade edge is half the quintile spread. The bar is the round trip at 2x.

| h = 12 bars, thin tercile | spread (bps) | edge | 2x round trip | edge / bar | p |
|---|---|---|---|---|---|
| GBPUSD | +1.06 | 0.53 | 0.82 | **0.64** | 0.000 |
| EURUSD | +0.43 | 0.22 | 0.37 | 0.57 | 0.028 |
| USDJPY | +1.00 | 0.50 | 1.10 | 0.46 | 0.006 |
| XAGUSD | +5.00 | 2.50 | 9.40 | 0.27 | 0.006 |
| BTCUSDT | +0.38 | 0.19 | 18.00 | 0.01 | 0.384 |
| XAUUSD | −0.45 | −0.22 | 2.13 | −0.11 | 0.698 |

**0 of 6 markets clear the bar.** The best is 64% of the way there, and it does
not clear at 1x cost either. Gold, the market this project actually trades, has
the wrong sign.

## 3. The interaction is only half there

Monotone thin > mid > heavy on **3 of 6** markets at h = 6 and again at h = 12,
against a criterion of 4. The three that hold are the three FX majors; both
metals and BTC do not.

## 4. The tail is flat, and then it inverts — this is what kills it

The addendum asked H-008's question: does a bigger move revert harder? Deciles of
|z| inside the thin tercile, fade return in bps, h = 12:

| market | decile 1 → 10 | top 1% | 2x bar |
|---|---|---|---|
| GBPUSD | +0.30 −0.03 −0.04 +0.20 +0.18 +0.58 +0.41 +0.29 +0.35 **+1.08** | **+1.13** | 0.82 |
| USDJPY | +0.48 +0.04 +0.36 −0.85 +0.70 +0.18 +0.56 +0.07 +0.87 +0.59 | +1.31 | 1.10 |
| EURUSD | +0.14 −0.22 +0.37 −0.03 −0.24 +0.33 +0.42 +0.33 +0.05 +0.09 | **−0.85** | 0.37 |
| XAUUSD | +0.44 +1.20 −0.78 +0.41 +1.49 −0.09 −1.01 −1.13 +0.58 +0.08 | **−1.52** | 2.13 |
| XAGUSD | +2.04 −1.03 −1.88 +1.50 −1.68 +0.06 +0.03 +3.97 +4.49 +2.63 | **−0.53** | 9.40 |
| BTCUSDT | +1.54 +3.03 +0.70 +1.48 +0.48 +2.10 +0.10 +1.18 −0.68 +0.02 | **−2.60** | 18.00 |

Rising on 3 of 6, clearing the bar on 2 of 6, against a criterion of 4 and 4.

**And the top 1% is NEGATIVE on four of the six markets.** The largest thin-volume
moves do not revert at all — they continue. That is not a failure of the
mechanism, it is the mechanism's own limit: past some size a move is information
whatever the volume looked like. It also removes the last way this could have
been rescued, because the tail is where a tradeable version would have had to
live.

## Verdict

**Dead at gate 1, on cost, with the mechanism confirmed.** Both are worth saying
in the same sentence: this is the first hypothesis in this session that beat a
priced search, and it still cannot pay a 0.4–2.1bps round trip.

**What it closes.** Short-horizon reversal on 15m bars as a standalone rule, on
all six standard markets, conditioned on the one variable this repo has evidence
for. Do not re-open it with a different lookback, a stop or a target: a stop
changes R, not bps, and the gross edge is the thing that is short.

**What it establishes for the next hypothesis.** The gap between a real signal
and a tradeable one here is a **factor of two to four in cost**, not a factor of
ten in edge — the same distance H-024's depth imbalance failed by (7.9bps against
14) and H-011 failed by ("real edge, too small for 28bps"). Three independent
signals now sit inside one factor-of-four band below the bar. That is a statement
about the bar, and it is the strongest argument this session produced about what
to do next.
