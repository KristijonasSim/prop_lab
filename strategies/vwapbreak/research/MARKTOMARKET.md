# H-039 — the prop simulation has never marked open positions to market

**Pre-registered 2026-09-14, before any number was produced.** Written because
the last two studies in this repo were proposed after their answers already
existed, and because the thing being questioned here is the number on the board.

---

## What prompted it

Kris, 2026-09-14, holding a six-leg gold short **+$406 unrealised** on the demo
account, equity +4.65% against a 6% target: *"we already 355 dollars in profit
we should still wait? maybe i need to add manual trailing stop loss?"*

Answering that meant asking what the simulation does with an open position. It
does nothing. The daily series every board number rests on is built one way, in
two places:

    core/board.py:45                daily = pd.Series(r * risk, index=exit_ts)
                                            .resample("1D").sum()
    research/exitshape.py:266       the same line

**A trade's entire R is booked on the day it EXITS.** A position opened on the
2nd and closed on the 18th contributes nothing on the 3rd through the 17th and
its whole result on the 18th.

## Why that is not a detail on this hypothesis

A real evaluation measures both caps on **equity, which includes open profit and
loss**. H-027 is the worst possible shape for the difference:

* the horizon is **384 bars — 16 days**, so positions are open a long time;
* the stop is **8 sigma**, so a trade can travel a long way against you without
  being closed;
* the shipped book runs **five settings plus the Asian leg in parallel**, which
  on gold are usually the same direction, so the unrealised swings add up rather
  than netting off.

Every one of those makes the invisible part bigger.

## The claim, stated so it can be wrong

**Marking the same trade series to market will raise breach rates and lower pass
rates, because losses that a real account experiences daily are currently
collapsed onto a single exit day where they may be netted against gains.**

Direction is predicted. **Magnitude is not** — that is the measurement.

It is also possible the effect runs the other way for the daily cap
specifically: booking 16 days of accumulated loss as one -4R day is a *worse*
single day than the same loss spread over 16 days, and the daily cap is checked
per day. **So the two caps may move in opposite directions**, and both are
reported separately rather than as one "blown" number.

## Kill criterion, fixed now

> If the mark-to-market series produces pass and blow-up rates **inside the
> noise band** of the exit-booked series, the concern is closed, the board
> numbers stand, and this file is the record that it was checked.

If they fall outside it, no board number may be quoted until the pipeline is
fixed — that is a bigger claim than any strategy result in this repo, so the
bar for believing it is correspondingly higher, and the arithmetic below is
checked twice before anything is republished.

## Method

1. Re-run the shipped configuration through the ordinary blind walk-forward
   (`core.run_hypothesis.run_market`, floors 30 / top 5), changing nothing.
2. Record every trade array the kernel returns, with its bars. Match each row of
   the selected trade series back to a recorded trade **on entry timestamp, exit
   timestamp and R together**, and require a 100% match. A partial match stops
   the study — a reconstruction that has to guess is how this repo has produced
   results it later withdrew.
3. From the matched trades take `entry_i`, `exit_i`, `dir`, `entry_px` and the
   per-trade risk in price terms, and mark the book to market on every bar:
   `unrealised_R = (px - entry_px) * dir / risk_px`, summed over open trades.
4. Difference that equity path to daily steps. Dead bars are excluded exactly as
   the kernel excludes them — a padded weekend bar is not a day on which an
   account can breach.
5. Run the identical account simulation (`core.riskladder.run_accounts`,
   Thunderbolt one-step) on both series and report both, each with its band.

**The trade series is identical in both arms.** Nothing is re-selected, no
configuration changes, no grid is searched. This is the same distinction the
risk ladder has: it is arithmetic on a fixed series, not a search. The only
thing that changes is which day a given R is attributed to.

## The second arm, only if the first survives

The question Kris actually asked: **close the book when the account is within X
of the target.** It is meaningless on the exit-booked series, where open profit
does not exist, which is why it is second and not first.

* arms: X = 0.5%, 1.0%, 1.5%, 2.0% of account, against no rule at all
* the whole curve in X is reported, not the best cell. **A real effect should be
  smooth in X.** A spike at one value is the H-038 signature — the gap-size
  filter that weakened its own result on 3 of 4 cuts — and is read as noise.
* it must beat the baseline on expected days with a band that **does not
  overlap**, and must not raise the blow-up rate. That is the same definition of
  "beats" that `strategies/beat/` used on 2026-09-13.

**Four values of X is a search over four cells.** At a 10-90% band that is not
severe, but it is not free either, and the curve requirement above is what pays
for it.
