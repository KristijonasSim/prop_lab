# Two attempts to beat H-027 — PRE-REGISTERED 2026-09-13, before any number

Kris: *"go and find something that works and beats our vwap."*

**What "beats" means, fixed now so it cannot be softened later.** The traded rule
is XAUUSD 1h, floor 30 / top 5, budget-linear sizing. To beat it an arm must
resolve an evaluation **faster in expected days**, with a **band that does not
overlap** the baseline's, scored under the **same sizing rule** and the same
walk-forward. A faster number with an overlapping band is not an improvement —
that rule killed the flat percentage band and it applies to my own work here.

Both arms live inside H-027's own axes. Neither is a new hypothesis, so neither
needs Kris to pick a direction first.

---

## Arm 1 — the fold selector, under the sizing rule that was adopted after it

### Why this is not the 2026-09-09 study

`SELECTOR OBJECTIVE (task 3)` compared what the blind fold selector maximises.
On XAUUSD 1h it measured, at **2% flat risk**:

| ranked on | expected days | pass % | trades/day |
|---|---|---|---|
| profit factor @2x (**shipped**) | 15.2 | 65.8 | 0.93 |
| R per day | 11.1 | 44.9 | 2.59 |
| **days = maxDD_R / R_per_day** | **10.9** | 54.9 | 1.52 |

Ranking on `days` was **4.3 days faster** and was left unadopted because the
pass rate fell and the bands overlapped.

**That study is dated 2026-09-09. Budget-linear sizing was adopted on
2026-09-10** and its entire effect is on the axis where the days-selector is
weak: blown accounts **29.5% → 16.9%**, pass **65.8% → 77.0%**, for 1.7 days.

Nobody has run them together — verified by grep, zero rows mention both. If the
sizing rule repairs the days-selector's pass rate while keeping its speed, that
is a genuine improvement to the thing we trade, with no new data and no new
mechanism.

`Pipeline.SELECT_ON` already accepts `"1x"`, `"2x"`, `"rday"`, `"days"`, and
`run_market` passes `pipe_kw` straight through, so this needs no new machinery.

**Arms:** `select_on` ∈ {`2x` (baseline, what is shipped), `rday`, `days`}.
**Tests: 3.** A narrow search, and it is stated up front.

---

## Arm 2 — the Asian range break, on every market

### The gap

The Asian range break is the one genuinely new signal this project found. It is
**0.114 correlated** with the VWAP break, it is second-engine clean 10/10, and
over eleven years it is the most robust arm ever measured here: **71.4% pass,
lowest quarter concentration (30.4%), smallest best-day share (23%)**.

**It has only ever been run on gold.** Verified: the three rows mentioning it are
`volume.py` (XAUUSD 1h and 4h), the second-engine check, and the eleven-year run.
No non-gold market appears in any of them. H-027 got a full nineteen-cell
cross-market screen through `assets.json`; its sibling signal never did.

`VolumeVariant(name, "asia")` is market-agnostic — `asia_range` reads only the
bar's hour, high and low — so this is a screen, not a rewrite.

### The honest problem with it

**A 00:00–07:00 UTC window is not "the Asian session" on every instrument.** On
gold and FX it is a real, low-liquidity overnight window that a London/NY move
then breaks out of. On BTC it is nothing in particular — crypto has no session.
So a hit on crypto is more likely to be noise than a hit on FX or silver, and
that expectation is written down **before** the run rather than invented to
explain a result afterwards.

**Universe:** EURUSD, GBPUSD, USDJPY, AUDUSD, XAGUSD, WTI, BTCUSDT, ETHUSDT,
SOLUSDT at 1h and 4h, with XAUUSD as the reference. **Tests: 18 (+2 reference).**

---

## KILL CRITERION — fixed before the first number

Every arm is scored the same way: blind quarterly walk-forward, paired null,
identical folds, grid and costs, then **budget-linear sizing** over the risk
ladder, best rung by expected days, with the repo's 10–90% block-resampled band
computed **under the same sizing rule as the number it wraps**. A flat-risk band
around a budget-linear number would be two different measurements and is not
allowed.

An arm survives only if **all three** hold:

1. expected days **below** the baseline's — arm 1's baseline is `select_on=2x`,
   arm 2's is XAUUSD;
2. its 10–90% band **does not overlap** the baseline's;
3. it **beats its own paired null**.

### And the search is priced, because I got this wrong today

`STRATEGY_LOG` 2026-09-13: a four-candidate screen produced 7 apparent passes
from 96 tests against 4.8 expected from pure noise, because the gate priced the
per-test null and never the width of the search. **Arm 2 runs 18 tests**, so at a
conventional threshold roughly **one apparent winner is expected from noise
alone**.

Therefore, for arm 2 specifically: **a single market clearing all three
conditions is NOT a result.** It is a candidate, and it must then show the same
sign and direction on a *related* market — another FX major, or the other metal —
before anything is claimed. One isolated winner among eighteen is what noise
looks like, and today it looked exactly like that.

**If nothing clears, both arms are closed by measurement and I will say so
plainly rather than present the best-looking row.**

## Honest prior

Arm 1 is the better bet and it is still under 50/50: the days-selector's speed
was real but its bands already overlapped once. Arm 2 is a screen of a signal
that works on one market, and the base rate for "works on a second market" in
this repo is poor — sixteen markets were screened for H-027 and none beat gold.
