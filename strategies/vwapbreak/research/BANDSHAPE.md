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
