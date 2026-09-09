# The three-account demo test — H-027 gold 1h

Kris, 2026-09-09: *"I will launch 3 demo accounts with the same strategy and in
18 days we should know for all 3 if they passed or not."*

**UPDATED 2026-09-09 evening.** The single-setting version below was replaced:
Kris chose **floor 30 / top 5 at 2% risk** after the top-N study. One setting
takes 0.15 trades a day - two or three inside a whole evaluation - so the account
resolves on luck either way. Five settings give the same pass rate on six times
the trades and blow up less often.

**The live specification now lives in `core/chosen.py`**, is rendered at the top
of the board, and fills the Pine indicator automatically. What follows is kept
because the reasoning about the test itself has not changed.

| | chosen | what it replaced |
|---|---|---|
| rule | floor 30 / **top 5** | floor 30 / top 1 |
| risk | **2%** total, 0.4% per setting | 4% |
| pass rate | **59.8%** | 60.1% |
| expected days | 21.7 (band 16.8-31.4) | 18.3 (band 15.9-25.4) |
| blown | **33.9%** | 39.6% |
| trades | **0.93/day**, ~17 in 18 days | 0.15/day, ~3 in 18 days |

---

## The rule

| | |
|---|---|
| market | **XAUUSD**, 1-hour bars |
| VWAP | anchored to the **UTC day** (resets 00:00 UTC) |
| sigma | volume-weighted standard deviation of price about that VWAP |
| **entry** | close **≥ 1.25 sigma above** the VWAP → **long**; **≤ 1.25 below** → **short** |
| decision bar | a **closed** bar. Fill at the **next bar's open** |
| session filter | signal bar must be **00:00–07:00 UTC** |
| **stop** | **8 × sigma** measured on the signal bar |
| target | **none** |
| horizon | close after **384 bars** (16 days) if the stop has not been hit |
| positions | **one at a time**. No new entry while a trade is open |
| **risk per trade** | **4% of the account** |

At 4% risk the firm's 6% target is **1.5R** — one good trade passes the account.

## What to expect

| | |
|---|---|
| trades | ~**0.15/day** — one every 6-7 days, so **2-3 trades** in 18 days |
| median days to pass | **11** |
| expected days per funded account | **18.3** (band 15.9-25.4) |
| pass rate | **60.1%** |
| blown | 39.6%, nearly all on the **3% daily cap** |
| never finished | 0.3% |
| win rate | roughly one trade in four to one in ten, depending on the stretch |

**An account is decided by one or two trades.** That is the honest shape of it,
and it is why three accounts is a weak test even though it is a real one.

## THE ONE THING THAT WOULD MAKE THE TEST WORTHLESS

**Do not start three identical accounts on the same day.** They would take the
same trades in the same order and produce the same outcome - three copies of one
sample, not three samples. The result would be "all three passed" or "all three
failed", and neither would mean anything.

Stagger them. Any of these works:

1. **Start dates one week apart.** Simplest, and it is exactly what the
   simulation does - it opens a fresh account on every trading day.
2. **Three selection rules** on the same market: top 1 (4% risk), top 3 (2%),
   top 5 (1.75%). Different trade streams, all three reach 60% pass.
3. **Three markets**, if the firm offers them - though gold is the only one this
   hypothesis has evidence for.

What three staggered accounts can tell you, at a 60% pass rate: **3 of 3 happens
22% of the time by chance, 2 of 3 happens 43%, 0 of 3 happens 6%.** So all three
failing is real evidence against; two of three passing is consistent with the
number and proves little on its own. It is a sanity check, not a validation.

## The indicator

The **Copy Pine indicator** button on the board now ships these settings pinned
(`core/pine.PINNED`). Paste it into TradingView on XAUUSD 1h and it draws the
signal, the entry bar, the 8-sigma stop and the trade count.

Set an alert on **"H-027 long signal" / "H-027 short signal"** - at one trade a
week, watching the chart is not a plan.

## What is NOT settled, and would still be true if all three pass

* The blind selector does **not** choose this configuration when it is free to
  choose - given every stop width it picks 0.75 sigma, because it ranks on
  profit factor and the tight-stop lottery wins on profit factor. The wide stop
  is here because it was **forced** and then measured. Fixing what the selector
  aims at is the open work.
* The 18.3-day figure's band (15.9-25.4) sits inside the measured luck zone
  (13.3-26.5 expected days). The edge beats its null; the *speed* has not been
  shown to differ from noise.
* **H-027's kernel has never been checked against a second engine.** H-002 and
  H-016 both were, and that check has caught three real bugs in this repo. It is
  the cheapest remaining thing that could still invalidate all of this.
