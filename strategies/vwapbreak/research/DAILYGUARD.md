# H-041 — a daily-loss guard. An account overlay, not a rule change.

**Pre-registered 2026-09-14, before any number.**

---

## Why this, and why it is not another filter

H-039 (`MARKTOMARKET.md`) measured which cap actually kills these accounts. Once
open positions are marked to market — which is how a firm measuring drawdown on
equity sees them — the failure mode inverts:

| | exit-booked | marked to market |
|---|---|---|
| fail on the MAX cap | 27.6% | 4.2% |
| **fail on the DAILY cap** | 22.4% | **45.8%** |

**Nothing in the rule knows what a day is.** The bot tracks equity and the peak,
sizes off the drawdown from the peak, and has no concept of a daily budget. It
will keep opening positions on a day that has already lost 2.8% against a 3% cap.

**A daily-loss guard has never been tested here.** `STRATEGY_LOG.md` has zero
mentions of one.

## Why it is allowed when entry filters are dead

Twenty-five entry filters died because they **select among signals** on market
information — and 24 of 25 raised profit factor while lowering R per day. This
does not read the market at all. It reads the **account**, and it is the same
class of thing as the risk ladder and budget-linear sizing, both of which are
adopted: a fixed trade series re-simulated under a different account policy.

That class has produced the only two improvements this hypothesis has ever kept.

## The arms

Once the day's realised R is at or below the threshold, **take no new entries
until the next UTC day**. Positions already open are left alone — closing them
would be an exit-rule change, and the exit axis is closed.

| arm | day's loss that stops new entries |
|---|---|
| **none** | baseline, the shipped behaviour |
| −1.0% | |
| −1.5% | |
| −2.0% | |
| −2.5% | just inside the 3% cap |

## What counts as a win — fixed now

1. **Fewer expected days with a band that does not overlap the baseline's**, or
2. **the same expected days (overlapping band) with a materially lower blow-up
   rate** — because under equity accounting the blow-up rate is the thing H-039
   says is mispriced, and a guard that buys survival at no cost in speed is
   worth having even if it does not make the account faster.

Condition 2 is looser than the one `strategies/beat/` used and it is stated in
advance so it cannot be invented after seeing the table. **An arm meeting only
condition 2 is reported as "survival, not speed" and never as "beats H-027".**

## What would make a pass a false one

* **Five arms is a search over five cells.** The whole curve is reported.
  **A real effect is monotone in the threshold** — tighter guard, fewer blow-ups.
  A spike at one threshold with neighbours worse is the H-038 signature and is
  read as noise.
* **It must hold on 1h and 4h.** A sign-flip across timeframes is this repo's
  signature for no effect.
* The guard can only ever *remove* trades, so it will mechanically raise profit
  factor. **Profit factor is not evidence here.** Expected days and blow-up rate
  are the only numbers that count.

## Kill criterion

> If no threshold beats the baseline on either condition, on both timeframes,
> the account-overlay axis is closed alongside the other five and H-027 is
> finished being tuned.

---

# RESULT — 2026-09-14. Survival, not speed. Promising, not proven.

`backtests/vwapbreak/dailyguard.json`. Gold, blind walk-forward, floors 30 /
top 5, Thunderbolt one-step, data to 2026-09-13.

| 1h | trades | risk | days | band | pass% | blown% | failDaily% |
|---|---|---|---|---|---|---|---|
| **none** | 957 | 3.0% | **17.8** | 13.9–23.3 | 50.7 | **49.3** | **23.3** |
| −1.0% | 595 | 3.0% | 20.3 | 15.0–24.0 | 59.2 | **40.8** | **3.2** |
| −1.5% | 694 | 3.0% | 18.6 | 14.8–24.1 | 53.9 | 46.1 | 8.5 |
| −2.0% | 844 | 2.0% | 19.1 | 15.2–24.7 | 57.6 | 42.4 | 4.3 |
| −2.5% | 813 | 3.0% | 18.5 | 14.3–23.3 | 51.2 | 48.8 | 18.6 |

| 4h | trades | risk | days | band | pass% | blown% | failDaily% |
|---|---|---|---|---|---|---|---|
| **none** | 599 | 3.0% | **34.4** | 27.5–54.5 | 29.1 | **70.5** | **52.5** |
| −1.0% | 477 | 2.0% | 51.2 | 35.2–83.1 | 50.7 | **48.3** | **0.0** |
| −1.5% | 477 | 3.0% | 39.3 | 29.3–64.0 | 28.0 | 71.6 | 34.3 |
| −2.0% | 521 | 3.0% | 39.9 | 28.3–63.4 | 27.6 | 72.0 | 42.2 |
| −2.5% | 540 | 3.0% | 35.4 | 27.3–53.6 | 29.6 | 70.0 | 40.9 |

## Against the two conditions fixed before the run

**Condition 1 — fewer expected days with a non-overlapping band: FAILED
everywhere.** Not one arm is faster than no guard on either timeframe. Every
band overlaps. The guard does not make the evaluation quicker and nothing here
may be read as if it does.

**Condition 2 — same expected days with a materially lower blow-up rate: MET by
−1.0% on both timeframes.** Bands overlap the baseline's in both cases, and:

* 1h: blow-ups **49.3% → 40.8%**, pass 50.7 → 59.2
* 4h: blow-ups **70.5% → 48.3%**, pass 29.1 → 50.7

Per the pre-registration this is reported as **"survival, not speed"** and is
**not** a claim that anything beats H-027.

## Why this is weaker than the table looks — three reasons, all pre-registered

**1. The curve is NOT monotone, and monotonicity was the stated test.** On 4h,
blow-ups at −2.5/−2.0/−1.5 are 70.0/72.0/71.6 — indistinguishable from the
baseline's 70.5 — and then −1.0% drops to 48.3. **That is a step at one
threshold with its neighbours flat, which the pre-registration named as the
H-038 signature for noise.** 1h wobbles too: 48.8 → 42.4 → 46.1 → 40.8 is
broadly falling but not clean.

There is a plausible mechanism for a threshold effect — a guard only helps if it
triggers *before* the account is already dead, and the loose ones rarely do —
but a mechanism invented after seeing the table is not evidence. **A finer
sweep (−0.5, −0.75, −1.0, −1.25) is what would settle whether this is a curve
or a spike, and it has not been run.**

**2. The falling daily-failure rate is arithmetic, not evidence.** A guard that
stops trading on bad days *must* cut daily-cap breaches; 23.3% → 3.2% is the
mechanism working, not the edge being real. Only the TOTAL blow-up rate counts,
and that moved far less.

**3. The risk rung is a confound.** `score` picks the fastest rung per arm, and
the −1.0% arm landed on **2.0% risk on 4h against the baseline's 3.0%**. Lower
risk cuts blow-ups on its own. That comparison is not clean and the arm should
be re-read at a rung held fixed.

## Verdict

**Not a win, and the first thing on this hypothesis in weeks that is not simply
dead.** The direction is consistent across both timeframes and the mechanism is
the one H-039 predicted. It is held back by a non-monotone curve and a risk-rung
confound, either of which could explain the whole result.

**Next, in order, and neither is optional before this is believed:**

1. the finer threshold sweep, to tell a curve from a spike;
2. every arm re-scored at a **fixed** risk rung, to remove the confound.

Only if it survives both does **pct + guard** become worth running — `pct` is
the only lever that has ever raised trade frequency (2.63/day against 1.32) and
it died on exactly the quantity this guard moves.

---

# H-041b — the two runs H-041 said were owed. Pre-registered 2026-09-15, before any number.

Kris, 2026-09-15: *"lets do 2 + 3"*. This is 2. It settles nothing new — it
decides whether the H-041 result above survives the two objections its own
write-up raised against it.

## What is being fixed, and why each matters

**1. The risk rung was a confound.** `score()` above picks the fastest rung per
arm independently, and the −1.0% arm landed on **2.0% risk on 4h against the
baseline's 3.0%**. A lower rung cuts blow-ups by itself, so part or all of
70.5% → 48.3% may be the rung, not the guard.

**2. The curve was not monotone, and monotonicity was the stated test.** On 4h,
−2.5/−2.0/−1.5 gave 70.0/72.0/71.6 against a baseline 70.5 — flat — and then
−1.0% dropped to 48.3. A step at one threshold with flat neighbours is the
H-038 signature for noise. Only a finer sweep can tell a curve from a spike.

**3. NEW, and not in H-041 at all: the guard has never been run against a
control.** The guard can only remove trades. Removing trades cuts blow-ups on
its own, because a smaller book breaches less. **Nothing so far separates "the
account signal is informative" from "trading less is safer."** That is the same
omission that made the 62.6%-pass headline and the MA200 gate evaporate, and it
is the single most likely way this result is wrong.

## The three changes

| | H-041 | H-041b |
|---|---|---|
| thresholds | 4 (−1.0 to −2.5) | **8**: none, −0.5, −0.75, −1.0, −1.25, −1.5, −2.0, −2.5 |
| rung | best per arm — the confound | **full 4×8 matrix reported**; primary readout at a rung fixed in advance |
| control | none | **day-shuffled guard**, 25 seeds |

**The fixed rung is 3.0%**, chosen because it is the rung the BASELINE selected
on both timeframes in the table above. It is fixed now, before the matrix is
seen, so it cannot be picked to suit an arm.

## The control, stated precisely

For an arm that blocks entries on **B** distinct UTC days, the control blocks
entries on **B days drawn at random** from the days that have entries, with no
reference to the account. Same number of blocked days, same day-level clustering,
no information. 25 seeds, reported as a median and a 10–90 spread.

**This is the decisive test.** A guard that reads the account must beat a guard
that reads nothing.

## What counts as a win — all three required, on BOTH timeframes

1. **At the fixed 3.0% rung**, the arm's blow-up rate is materially below the
   baseline's — the confound removed.
2. **The curve is monotone**: Spearman rho between the threshold value and the
   blow-up rate is **≥ +0.7** (tighter guard → fewer blow-ups, smoothly). A
   single step with flat neighbours fails this by construction.
3. **The arm beats its day-shuffled control** by more than the control's own
   10–90 spread.

Speed is not part of this. H-041 already failed condition 1 of its own
pre-registration everywhere, and nothing here is expected to change that. This
asks only whether the SURVIVAL result is real.

## Kill criterion

> If the blow-up reduction does not survive a fixed rung, or is not monotone, or
> does not beat the day-shuffled control, **H-041 is dead, the account-overlay
> axis closes with the other six, and `pct + guard` is never run** — it was only
> ever justified by this guard working.

If it survives all three, run 3 (`pct + guard`) next and nothing else.

---

# RESULT H-041b — 2026-09-15. FAILED the criterion. H-041's headline was the risk rung.

`backtests/vwapbreak/dailyguard2.json`, `dailyguard2.log`. Same data, same folds,
same costs as H-041.

## The three conditions, scored as written

| condition | 1h | 4h |
|---|---|---|
| 1. beats baseline at the FIXED 3.0% rung | **yes** (−0.50%: 42.3 vs 49.3) | **yes** (−0.50%: 50.6 vs 70.5) |
| 2. Spearman ≥ +0.700 | **+0.883 PASS** | **+0.450 FAIL** |
| 3. beats the day-shuffled control below its p10 | **yes** (42.3 vs p10 46.6) | **yes** (50.6 vs p10 57.2) |

**Condition 2 fails on 4h, so the criterion fails.** By the kill criterion fixed
before the run, H-041 is dead, the account-overlay axis closes, and **`pct` +
guard does not run.**

## What actually happened — the rung was doing the work

H-041 reported 4h blow-ups **70.5% → 48.3%** at a −1.0% guard. The full matrix
shows where that came from:

| 4h, blown% | 1.00% | 1.50% | 2.00% | **3.00%** |
|---|---|---|---|---|
| none | 38.0 | 52.5 | 55.6 | **70.5** |
| −1.00% | 33.1 | 46.0 | **48.3** | **70.8** |

**The 48.3 is at the 2.0% rung and the 70.5 is at the 3.0% rung.** Compared
like with like the guard is worth **55.6 → 48.3, seven points**, not twenty-two.
At the rung the baseline actually selected it is worth **nothing**: 70.8 against
70.5, slightly the wrong way.

**The winning threshold also moved.** H-041 named −1.0%; at a fixed rung the best
arm is −0.50% on both timeframes and −1.0% is inert on 4h. A result whose optimum
relocates when a confound is removed was not measuring what it claimed.

## The one thing that is real, and it is not enough

**The guard beats its day-shuffled control on both timeframes, below the p10 of
25 seeds.** 1h 42.3 against 54.7 (46.6–64.5); 4h 50.6 against 72.8 (57.2–85.6).

That is the first evidence on this hypothesis that an account overlay carries
information beyond "trading less is safer" — the control removes the same number
of days and does materially worse. It is a real signal.

**It does not rescue the arm.** The criterion required all three conditions and
was written precisely so that one surviving leg could not be promoted into a
result after the fact. The 4h curve is a step at −0.50% with every other
threshold flat at ~70 — the H-038 signature named in the pre-registration.

## Verdict

**Dead, and more informative than most deaths here.**

* **H-041's table should not be quoted.** Its 4h headline is a rung comparison
  wearing a guard's name. The 1h figure (49.3 → 40.8, both already at 3.0%) was
  clean but is the smaller claim and fails condition 2 on the other timeframe.
* **`pct` + guard is closed** without being run, per the pre-registration.
* **Seven axes are now closed on H-027.** Entry filters, timeframe, exit shape,
  selector objective, clock anchor, band shape, account overlay.
* **What survives is a method note, not a lever:** the day-shuffled control is
  the right instrument for any future account-policy test, and it should have
  existed before H-041 was ever written up.

**The honest state of H-027: it is finished being tuned.** The remaining open
question is not a strategy question — it is whether the firm measures drawdown
on equity or on closed balance (blocker B1), which H-039 says changes which cap
kills the account.
