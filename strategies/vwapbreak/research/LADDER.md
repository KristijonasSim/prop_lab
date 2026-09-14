# H-044 — does the guard's survival convert into speed on the risk ladder?

**Pre-registered 2026-09-14, before any number. The last guard study.**

Run: `.venv/bin/python strategies/vwapbreak/research/ladder.py`

---

## The question, and why it has never been asked

H-043 confirmed the daily-loss guard: blow-ups 49.3 → 42.3 on 1h and 70.5 → 50.6
on 4h, below a matched-drop null on both timeframes and holding in both halves
of the sample. And it **cost speed** — 17.8 → 20.8 expected days on 1h, 34.4 →
63.3 on 4h — so it was reported as not usable.

**Every one of those numbers is at 3% risk.** H-041 wrote `RISKS = (0.01, 0.015,
0.02, 0.03)` as a local tuple, H-042 and H-043 inherited it, and nobody looked
at it. `core/riskladder.RISK_LADDER` runs to **5%**.

That matters more here than anywhere else, because **drawdown headroom is the
guard's entire product, and headroom is what a bigger position spends.** An arm
that blows 42.3% of accounts instead of 49.3% can afford size the baseline
cannot. "The guard is slower" is, until this is run, a statement about one rung.

CLAUDE.md is explicit that this is not a search: *"Re-simulating the same trade
series at a different position size selects nothing and searches nothing — it is
arithmetic on a fixed series."* Two fixed series, twelve rungs each, no arms.

## The interaction that makes this non-obvious

**The guard's threshold is in ACCOUNT percent, so its bite scales with risk.**
At 3% risk a −0.50% guard trips on 0.17R — any loser. At 0.25% risk the same
−0.50% needs **2R of booked losses** before it stops the day, so it barely fires.

The guard therefore gets *more* aggressive exactly where the account is most
fragile, which is the right shape — but it means the trade count is a function
of the rung and cannot be quoted once. **Trades and trades/day are in the table
at every rung** so the effect is visible rather than assumed.

## The arms

Two, and only two:

| arm | |
|---|---|
| **none** | the shipped behaviour |
| **−0.50%** | the plateau of H-043, which −0.15/−0.25/−0.35% all reproduce exactly |

Cells: XAUUSD 1h and 4h. Rungs: the full `RISK_LADDER`, 0.25% → 5.00%, twelve of
them. Blind walk-forward, floors 30 / top 5, Thunderbolt one-step. Expected days
carries its 10–90 band at every rung; so does the blow-up rate.

## What counts as a win — fixed now

1. **FASTER, NOT JUST SAFER.** At some rung at or above `MIN_RISK` (2%, Kris's
   floor), the guard's expected days is **below the baseline's best expected
   days at any rung ≥2%**, and **the two days-bands do not overlap.**
2. **ON 1h**, which is the shipped timeframe. A 4h-only result is reported as
   4h-only and is not adopted — the sign-flip rule cuts both ways.
3. **NOT PAID FOR IN ACCOUNTS.** At the winning rung the guard's blow-up rate is
   no higher than the baseline's at the rung the baseline would actually be
   traded at.
4. **THE POLICY IS RESPECTED.** `riskladder.pick` takes the *lowest* rung ≥2%
   that resolves, not the fastest, and its docstring gives the measured reason —
   at 5% risk GBPUSD 1h reported 10.4 expected days on a PF@2x of **0.823**, a
   losing book funding accounts on variance. Any rung above the floor is
   reported as **"a person has to argue for this"** and never as a
   recommendation.

## Kill criterion

> **If the guard is not faster than the baseline at any rung ≥2% on 1h, the
> account-overlay axis is closed for good** and H-027's answer is
> publish-or-drop plus the demo test that finishes 2026-09-28. This is the last
> guard study either way.

## What would make a pass a false one

* **`expected_days = median_days ÷ pass_rate` flatters big positions.** At a
  large size a losing book still funds the occasional account on variance before
  it dies: short median, low pass rate, flattering ratio. That is why condition 3
  exists and why the blow-up rate is quoted at the same rung as any speed claim.
* **Twelve rungs × two arms is twenty-four cells**, but they are not twenty-four
  tests: the ladder is monotone arithmetic on one series, and a rung that wins
  with flat neighbours on both sides is read as noise here exactly as it was in
  H-042.
* **Peak drawdown of the continuous curve is reported at every rung.** Gold
  already draws −14.86% at the bottom rung against a 6% cap, so no rung clears
  it and `max_dd` cannot arbitrate — it is in the table to stop a high rung
  being read as safe rather than as merely short-lived.

---

# RESULT — 2026-09-14. The guard never buys speed. The axis is closed for good.

`backtests/vwapbreak/ladder.json`, log `ladder.log`. 48 cells: 2 arms × 12 rungs
× 2 timeframes, blind walk-forward, Thunderbolt one-step, data to 2026-09-13.

## 1h — the shipped timeframe

| risk% | | none: days [band] | blown% | | −0.50%: days [band] | blown% | tpd |
|---|---|---|---|---|---|---|---|
| 0.25 | | 84.4 [57.9–180.4] | 37.7 | | 84.1 [57.9–177.1] | 37.6 | 1.30 |
| 0.50 | | 47.8 [35.5–76.9] | 22.3 | | **44.0** [35.1–78.3] | **20.8** | 1.16 |
| 0.75 | | 39.2 [29.7–58.1] | 31.8 | | **38.9** [30.2–59.5] | **28.6** | 1.05 |
| 1.00 | | 30.1 [23.4–45.2] | 36.4 | | 31.0 [25.1–50.2] | **28.6** | 0.95 |
| 1.25 | | 25.6 [19.9–37.1] | 37.5 | | 27.2 [22.0–40.3] | **30.0** | 0.82 |
| 1.50 | | 23.0 [18.3–31.5] | 39.1 | | 24.4 [19.5–32.9] | **30.4** | 0.82 |
| 1.75 | | 21.3 [16.6–27.7] | 43.5 | | 23.6 [18.0–30.6] | **32.1** | 0.82 |
| **2.00** ← floor | | **19.5** [15.5–26.1] | 43.5 | | 21.3 [16.8–26.9] | **38.8** | 0.82 |
| 2.50 | | 18.0 [14.2–24.1] | 44.5 | | 21.1 [17.5–29.1] | 43.2 | 0.65 |
| 3.00 | | 17.8 [13.9–23.3] | 49.3 | | 20.8 [16.5–26.4] | 42.3 | 0.65 |
| 4.00 | | **16.8** [12.7–20.9] | 52.5 | | 19.0 [14.6–23.6] | 47.2 | 0.65 |
| 5.00 | | **16.8** [12.6–19.7] | 58.3 | | 18.2 [14.3–23.6] | 56.1 | 0.64 |

## 4h

Baseline runs 43.7 → 38.4 → 34.4 → 28.7 → **25.0** days from 2.00% to 5.00%;
the guard runs 63.6 → 58.7 → 63.3 → 47.1 → **35.6**. **The guard is slower at
every rung on 4h**, by 10 to 20 days.

## The four conditions

| | condition | verdict |
|---|---|---|
| 1 | faster at some rung ≥2%, non-overlapping days band | **FAIL** — guard's best ≥2% is **18.2** days against the baseline's **16.8**, and every band overlaps |
| 2 | on 1h | **FAIL** — 1h is where it fails; 4h is worse |
| 3 | not paid for in accounts | not reached |
| 4 | policy respected | n/a |

**The kill criterion is triggered. The account-overlay axis is closed for good.
This was the last guard study.**

## What the ladder does show, and it is worth more than the guard was

**At a MATCHED blow-up rate the guard is the better trade below ~42% blown, and
the baseline is better above it.** Reading the two columns across rather than
down:

| blow-up ≈ | baseline | guard | who wins |
|---|---|---|---|
| 30% | 0.75% risk → **39.2** days | 1.50% risk → **24.4** days | **guard, by 14.8 days AND safer** |
| 38% | 1.25% risk → **25.6** days | 2.00% risk → **21.3** days | **guard, by 4.3 days** |
| 43% | 2.00% risk → **19.5** days | 2.50% risk → **21.1** days | baseline, by 1.6 |
| 52–56% | 4.00% risk → **16.8** days | 5.00% risk → **18.2** days | baseline, by 1.4 |

The guard converts drawdown headroom into position size, exactly as predicted —
it just runs out of conversion before it catches the baseline's top speed.
**Kris's 2% floor lands the shipped rule at 43.5% blown, which is the crossover
itself**, so at the rung actually traded the two are indistinguishable: 19.5 vs
21.3 days, bands [15.5–26.1] against [16.8–26.9], blow-ups 43.5 vs 38.8 with
bands [37.4–59.8] against [24.2–50.1]. **Nothing at the shipped rung is
resolvable and nothing here changes what is traded.**

## Two things about the BASELINE that nobody had looked at

**1. The ladder is exhausted as a speed lever.** 1h expected days by rung:
18.0 → 17.8 → **16.8 → 16.8**. Above 4% risk there is no speed left at all,
while blow-ups climb 44.5 → 58.3 and the continuous curve's drawdown goes
−82.8% → **−165.5%**. The last 1.2 days cost 13.8 points of accounts.

**2. H-027 HAS NEVER MET THE PACE TARGET AT ANY POSITION SIZE.** The fastest of
all 48 cells is **16.8 expected days** — 1h, no guard, 4–5% risk — against a
pace target of **5–14 days** set 2026-09-07. The shipped rule at 2% needs 19.5.
The gap is not a tuning problem: the ladder is the one lever CLAUDE.md exempts
from the noise floor, it has now been run end to end, and its floor is 16.8.

## Verdict

**Seven axes closed. The eighth, the ladder, is arithmetic and it bottoms out
above the pace target.** There is nothing left to tune on H-027.

The honest read for Kris:

* **The rule is what it is** — ~17–20 expected days on 1h gold, 40–50% of
  accounts blown, and no setting of any dial moves it into 5–14.
* **The decision is publish-or-drop**, plus the demo test that finishes
  **2026-09-28** and is the only out-of-sample evidence this project has.
* **If accounts ever get expensive, the guard comes back** — at any blow-up rate
  under ~40% it is strictly the better curve, and that is a business input, not
  a research one.
