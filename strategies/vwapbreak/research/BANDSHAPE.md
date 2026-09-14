# H-040 — the band shape. The last untested axis on H-027.

**Pre-registered 2026-09-14, before any number was produced.**

---

## Why this axis and no other

Four axes on H-027 are closed by measurement, each in `CLAUDE.md`'s known-dead
list: entry filters (25 candidates), timeframe (5m/15m/30m and volume bars),
exit shape (partial, trailing, VWAP-recross, reversed over eleven years), and the
fold selector's objective (four of them, all on one curve).

**Every one of them changed what happens once price crosses the band.** None
changed the band itself. That is the whole of what is left, and it is backlog
items 9–12 in `docs/VWAP_BACKLOG.md`.

## What the band is today

`vwap_series` returns the volume-weighted standard deviation of price about the
session VWAP. It is used for **two** things, and both move together:

    entry   z = (close - vwap) / vwstd        threshold `thr` in sigma
    stop    risk = stop_sig * vwstd           width in sigma

So a change to the band changes the trigger AND the stop. That is deliberate
here: the question is whether sigma is the right yardstick at all, not whether
the stop should be wider (`exits.py` already swept that and ATR stops with a
sigma entry were measured there).

## The four arms, fixed now

| arm | band | what it is really asking |
|---|---|---|
| **baseline** | volume-weighted sigma about VWAP | the shipped rule |
| **atr** | ATR(14) | does a bar-range yardstick beat a dispersion one |
| **pct** | `vwap × 0.001` (10 bps) | is the volatility normalisation helping at all, or is raw distance from VWAP enough |
| **sterr** | `vwstd / sqrt(bars since anchor)` | the band should narrow as the session's estimate firms up |
| **asym** | semi-deviation above vs below VWAP, separately | gold's up-moves and down-moves are not the same size, and one symmetric band prices them as if they are |

Everything else is held identical: same entries otherwise, same grid, same folds,
same costs, same `floors 30 / top 5` selection, same blind walk-forward.

**The kernel is NOT copied.** A wrapper overrides `features()` and delegates
`grid()` and `run()` to the shipped object, so the shipped kernel is untouched
and no manifest hash moves. `exitshape.py` had to copy because it changed the
exit; nothing here does.

## What counts as a win — fixed before the run

An arm beats the baseline only if **both** hold:

1. **fewer expected days, with a band that does not overlap the baseline's.**
   Same definition `strategies/beat/` used on 2026-09-13.
2. **the blow-up rate does not rise.**

Anything else — a better profit factor, a better win rate, a nicer equity curve —
is not a win. The metric is `days = maxDD_R / R_per_day`, and 24 of 25 entry
filters raised profit factor while making the evaluation *slower*.

## What would make a pass a false one

* **Four arms is a search over four cells.** Reported as a full table, never as
  a best cell.
* **Sign-flip across timeframes is the repo's signature for no effect.** Every
  arm runs on **1h and 4h**. An arm that wins on one and loses on the other is
  read as noise, not as a timeframe-specific edge — that is what killed the
  fibonacci result and H-035's netflow.
* **Each arm carries a paired null.** A gate carrying no information by
  construction once reached 60% pass in 14.5 days on this exact data, so beating
  the baseline is not enough; the arm must also beat its own null by more than
  the baseline beats its.

## Kill criterion

> If no arm clears both conditions on **both** timeframes, the band-shape axis is
> closed, H-027 has no axis left, and the honest conclusion is that the shipped
> rule is the rule — publish it or drop it, but stop tuning it.

That is the expected outcome. Four axes have closed this way already.

---

# RESULT — 2026-09-14. Every arm dead. The axis is closed.

`backtests/vwapbreak/bandshape.json`. Gold, blind walk-forward, floors 30 /
top 5, Thunderbolt one-step, data to 2026-09-13.

| 1h | trades | tpd | PF@2x | null | days | band | pass% | blown% |
|---|---|---|---|---|---|---|---|---|
| **base** | 957 | 1.32 | **1.987** | 1.097 | **17.8** | 13.9–23.3 | 50.7 | 49.3 |
| atr | 537 | 0.74 | 1.083 | 0.843 | 49.1 | 36.3–93.5 | 61.0 | 38.6 |
| pct | 1913 | 2.63 | 1.367 | 0.873 | 19.6 | 14.2–24.2 | 35.8 | 64.2 |
| sterr | 720 | 0.99 | 1.262 | 0.600 | 28.3 | 20.5–44.8 | 31.8 | 67.8 |
| asym | 762 | 1.05 | 1.809 | 0.893 | 23.3 | 19.8–32.5 | 51.4 | 48.0 |

| 4h | trades | tpd | PF@2x | null | days | band | pass% | blown% |
|---|---|---|---|---|---|---|---|---|
| **base** | 599 | 0.82 | **1.077** | **1.711** | **34.4** | 27.5–54.5 | 29.1 | 70.5 |
| atr | 388 | 0.54 | 1.345 | 1.082 | 45.3 | 32.6–81.5 | 68.5 | 23.6 |
| pct | 621 | 0.92 | 1.428 | 0.863 | 23.5 | 18.2–33.8 | 38.3 | 61.3 |
| sterr | 663 | 0.91 | 1.238 | 1.454 | 27.1 | 21.1–43.7 | 40.6 | 59.4 |
| asym | 663 | 0.92 | 1.132 | 1.282 | 45.1 | 30.7–68.9 | 39.9 | 59.1 |

## Against the criterion fixed before the run

> Fewer expected days, **non-overlapping band**, no rise in blow-ups, on **both**
> timeframes.

**No arm clears it, and none comes close.** On 1h every arm is slower than the
baseline, three of four decisively. On 4h **every band overlaps the baseline's
27.5–54.5**, so nothing there is resolvable in either direction.

**Two arms flip sign across timeframes**, which the pre-registration named in
advance as this repo's signature for no effect:

* **atr** — 2.8x slower on 1h (49.1 vs 17.8) and the most defensive thing in the
  table on 4h (blow-ups 23.6% against 70.5%, pass 68.5% against 29.1%).
* **pct** — worse on 1h (19.6 vs 17.8), better on 4h (23.5 vs 34.4).

Neither is a timeframe-specific edge. Both are what noise looks like when it is
measured twice.

## The one thing worth carrying forward

**`pct` is the only lever ever found that raises TRADE FREQUENCY**: 2.63/day
against the baseline's 1.32 on 1h, from 1,913 trades against 957. Speed on this
hypothesis comes from frequency, and nothing else has ever moved it — the
sub-hour study found 0.93 → 1.10 going from 1h to 5m, an 18% gain for a 12x
finer bar.

It fails on **survivability, not on speed**: blow-ups 64.2% against 49.3%.

That is exactly the quantity H-041's daily-loss guard attacks, so **pct + guard**
is a real candidate where neither is one alone. It is NOT run here and must not
be run until the guard is shown to work on the baseline — otherwise it is two
failures stacked and a search over their product.

## A separate finding, not part of this study

**The 4h baseline lost to its own null seed** — PF@2x 1.077 against 1.711 — and
needs 34.4 days at 70.5% blown. That is much worse than the 4h cell has scored
before. Two candidates, untested: the window now extends to 2026-09-13 and the
Jun–Aug quarter is newly included, or one null seed is simply noisy. **One seed
is one draw and no conclusion may be hung on it.** Worth a proper multi-seed
re-run of the 4h cell before any 4h number is quoted again.

## Verdict

**The band-shape axis is closed.** Six axes now: entry filters, timeframe, exit
shape, selector objective, clock anchor, and the band itself. The shipped rule
survives all of them.
