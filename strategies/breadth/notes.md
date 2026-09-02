# H-015 — systemic crowd positioning

Opened 2026-09-02 after H-013 was rejected. The transferable finding from that
rejection pointed here: **pricing does not pay in this project, positioning
does.** Every attempt to trade what the crowd is *charged* has failed (H-004
funding, H-013 premium); the one thing that works reads where the crowd *is*.

## The claim, and it is an estimator claim

H-009 keeps only the trades the crowd is positioned against, reading Binance's
long/short account ratio **one coin at a time**. But a single coin's account
ratio is one noisy measurement of something that is not really per-coin: the
same retail is long everything, margined against the same collateral.

> If what pays is "the crowd is offside", then the crowd's position across
> eleven coins estimates it better than the position in one.

Falsifiable, and falsified or not on the same coins over the same bars with the
same construction — `own` is built identically to H-006's `crowd_z`, so any
difference is the aggregation and nothing else.

Eleven coins of metrics have been on disk since the archive pull. Nothing had
ever aggregated them.

## Stage 1 — the estimator claim holds, at one horizon only

Mean |IC| across all 11 coins, hourly-thinned:

| horizon | own | **sys** | breadth | idio |
|---|---|---|---|---|
| 1h | 0.0082 | 0.0044 | 0.0041 | 0.0081 |
| 4h | 0.0132 | 0.0121 | 0.0101 | 0.0095 |
| **8h** | 0.0159 | **0.0207** | 0.0186 | 0.0087 |
| 24h | 0.0132 | 0.0102 | 0.0117 | 0.0108 |

At 8h the complex beats the coin's own on every measure — IC 0.0207 vs 0.0159,
beats its block-shuffle null in **82%** of cells vs 55%, quintile spread 24bps
vs 16bps. At 1h, 4h and 24h it does not. **The advantage is real and narrow.**

**`idio` is the weakest feature in the table** (IC 0.0093, beats null in 36%).
That is the mechanism surviving its own test: crowding in *this* coin beyond the
complex predicts nothing, so the crowding that pays is systemic. It also implies
H-009's per-coin gate has been reading a noisy proxy for a market-wide quantity.

## Stage 2 — stacking beats replacing

Common window 2021-12 → 2026-06 (the systemic reading needs ≥6 coins listed),
5,035 trades of H-002's book. **Threshold fixed at zero, never searched.**

| book | PF@2x | maxDD | R/day | **ret/DD** | days proxy |
|---|---|---|---|---|---|
| H-002, no gate | 1.487 | −86.1R | 1.020 | 19.78 | 84.5 |
| **H-009, per-coin gate** | 1.767 | −59.0R | 1.060 | **29.97** | 55.7 |
| H-009 **+ sys** | 1.724 | −34.2R | 0.792 | **38.74** | **43.1** |
| H-009 + dsys_144 | 1.912 | −30.8R | 0.784 | **42.53** | **39.3** |

R per day falls, and it does not matter: drawdown falls faster, and
`days = maxDD_R / R_per_day` is what the board scores. This is precisely where
H-013 failed — it raised profit factor and made this number worse.

Replacing H-009's gate rather than stacking on it gives only +8.2% (`sys` alone,
32.43), so the two gates are measuring different components, not the same one
twice.

## Stage 3 — the null and the control both pass; the held-out split is the catch

| | real | null median | null best | verdict |
|---|---|---|---|---|
| H-009 + sys | **38.74** | 19.25 | 22.06 | beats every seed |
| H-009 + dsys_144 | **42.53** | 25.66 | 26.77 | beats every seed |

The control — keeping the trades the complex *agrees* with — collapses to 13.85
and 13.02 against a 29.97 baseline. So direction carries the result; the gate is
not selecting calm periods. H-013 never got past its control.

**And then the split, which is why the headline should not be quoted:**

| gate | first half | second half |
|---|---|---|
| sys | +5.5% | +2.8% |
| dsys_144 | **−6.4%** | +74.9% |

Neither half reproduces the full-window figure, because maximum drawdown is not
additive: much of the full-window lift comes from the gate cutting **one** large
drawdown that spans the split. `dsys_144`'s +41.9% is mostly one episode, and it
*hurt* in the first half.

**So the defensible reading is `sys`, not `dsys_144`** — positive in both halves,
beats every null seed, fails its control correctly, and it is the parameter-free
feature (a plain cross-sectional mean, no lookback to choose). Preferring it is a
prior, not a fit. Its honest held-out effect is **+3 to +6%**, not +29%.

## Weaknesses, unprompted

- **The full-window numbers are a best-of-nine.** Six gates × two placements,
  winner chosen after seeing all of them. The null and the control were run
  because of that, and they pass — but the held-out split is the test that
  matters and it cuts the effect by roughly 5x.
- **Short window.** 2021-12 on, because only BTC's metrics reach back to
  2020-09. Four and a half years, and the two halves behave very differently
  (H-009 itself does ret/DD 27.19 then 11.35).
- **Not a new strategy.** Stage 1's quintile spread at 8h is 24bps against a
  28bps round trip at 2x cost, so systemic crowding does not clear the gate as a
  standalone entry signal. Its value here is as a filter on a book that already
  works — the same shape as H-006/H-009, and it inherits H-009's post-filter
  limitation: it can only remove trades, never add the ones freed capacity
  would have allowed.
- **No walk-forward.** The feature is chosen once over the whole window. Until
  it is re-chosen blind each quarter this is not a board-eligible result, and
  H-004 is the standing reminder that nothing before a walk-forward decides.
- **One venue, one feed.** Binance's account ratio, same single point of failure
  H-009 already has, now across eleven coins instead of three.
