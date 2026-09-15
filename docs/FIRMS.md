# Which prop firm fits this strategy — measured, not reviewed

Written 2026-09-09. Every number in the tables is **our own trade series**
(H-027 gold 1h, floor 30 / top 5, wide stop) run through each firm's published
rule set with `core/riskladder.run_accounts`. No firm's marketing number appears
anywhere on this page.

---

## THE CONSTRAINT THAT DECIDES EVERYTHING: consistency rules

Our edge is **one big winner in five**. Measured on the funded-size series, a
single day is **76-95% of all profit** at any accumulation length. Under a rule
capping the best day at 20% of a withdrawal, the strategy **never becomes payout
eligible** - not once in 2.5 years, at any risk size, on any version:

| version | trades/day | payouts in 637 trading days under a 20% best-day rule |
|---|---|---|
| floor30 / top5 | 0.93 | **0 — never eligible** |
| floor100 / top10 | 4.14 | 1 |
| floor100 / top15 | 6.42 | 2 |
| 4h floor100 / top15 | 4.74 | 3 |
| any of them, no such rule | — | one every ~11 trading days |

**This is not a tuning problem.** The lumpiness IS the edge - one winner carried
a long way is what makes the average R positive. A strategy that spreads profit
evenly across days is a different strategy, and this project has measured that
the even ones do not pay.

So: **a consistency rule, a best-day rule, or a minimum-profitable-days rule is
a disqualifier**, not a downside.

## The shortlist, priced on our trades

Best risk size per firm, chosen by fewest expected days to a funded account:

| firm | structure | risk | pass % | blown % | expected days | consistency rule | platform |
|---|---|---|---|---|---|---|---|
| **Upcomers Ash** | 1-step 2% / 3% daily / 6% trailing | 4.00% | 55.8 | 43.1 | **10.7** | **20% best day (funded)** | cTrader |
| Upcomers Thunderbolt | 1-step 5% / 3% / 6% | 3.00% | 50.9 | 44.8 | 17.7 | **20% best day (funded)** | cTrader |
| **FundingPips 1-Step Flex** | 1-step 10% / 3% / 6% static | 4.00% | 44.0 | 52.8 | **20.4** | none on the weekly-payout track | cTrader, MT5 |
| **City Traders Imperium** | 1-step 8% / no daily cap / 5% balance-based | 2.50% | 55.0 | 39.6 | **27.2** | none stated | MT5, Match-Trader |
| FundingPips 2-Step Pro | 6% + 6% / 3% / 6% static | 1.50% | 45.7 | 47.6 | 70.0 | none on the weekly track | cTrader, MT5 |
| Alpine Funded Peak | 2-step 8% + 5% / 4% / 8% | 2.00% | 45.7 | 47.6 | 70.0 | none | cTrader |
| FTMO | 2-step 10% + 5% / 5% / 10% static | 3.00% | 39.1 | 54.6 | 76.7 | none (2-step only) | cTrader, MT5 |
| The5ers Bootcamp | 3-step 6% x3 / 3% / 5% | 1.50% | 23.2 | 70.5 | 219.9 | none | cTrader, MT5 |
| FundedNext | 1-step 10% / 5% / 10% static | — | — | — | — | **40% best day — disqualified** | cTrader, MT5 |

### What the table says

1. **Every extra phase roughly quadruples the time.** 1-step 10.7-27 days;
   2-step 70-77; 3-step 220. A phase is not half the work, it is a second full
   chance to breach, and the drawdown budget is paid again.
2. **The target matters less than the number of phases.** FundingPips' 10% target
   in one step (20.4 days) beats FTMO's 10%+5% in two (76.7) by a factor of four.
3. **A daily cap costs us more than a max-drawdown cap.** Our worst single day is
   **-3.93%** of balance at 2% risk, and three days in 221 exceeded 3%. CTI has
   no daily cap at all, which is why it survives 2.5% risk where others do not.
4. **Balance-based drawdown is worth more than the headline suggests.** CTI
   measures drawdown on closed balance, not equity. Our 8-sigma stops make large
   open-equity swings that never become losses; those cannot breach a
   balance-based rule. The 27.2 days above is therefore **conservative**.

## The recommendation

**FundingPips 1-Step Flex** or **City Traders Imperium**, in that order.

* FundingPips: cTrader (a real API for the bot), no consistency rule on the
  weekly-payout track, one step, 20.4 expected days. The cost is a 10% target and
  a 3% daily cap, which is why it needs 4% risk - and 4% risk means 53% of
  accounts blow. Two or three attempts per funded account.
* CTI: fewer accounts blown (39.6%), no daily cap, balance-based drawdown, algo
  trading explicitly supported, payouts every 7 days, up to 100% split. The cost
  is MT5 or Match-Trader - no cTrader, so the bot needs an MT5 bridge on this
  Linux box, which does not exist yet.

**Upcomers Ash is the fastest to funded by a wide margin (10.7 days) and the
weakest place to hold a funded account.** If the aim is to prove the strategy
resolves accounts, it is the cheapest test in the list. If the aim is income, its
best-day rule blocks the payout indefinitely.

## VERIFY BEFORE PAYING — all of it is third-party until you read their page

Every line above came from firm documentation or comparison sites, not from a
signed contract. Confirm on the firm's own rules page:

1. **The consistency / best-day rule, in writing, for the FUNDED stage.** This is
   the one that decides everything and it is the one most often stated only in
   the payout FAQ.
2. **XAUUSD is tradeable** and its spread. Our costs assume 1.06bps round trip -
   a wider spread moves every number on this page.
3. **Drawdown: static, trailing, or balance-based**, and whether it is measured
   on equity or closed balance.
4. **Minimum trading days**, and whether a minimum PROFITABLE day count applies -
   The5ers' ProGrowth needs three profitable days of 0.5% each, which is the
   best-day rule wearing a different hat.
5. **EAs and algorithmic trading allowed**, and whether running the same strategy
   on several accounts counts as copy trading. That one matters for the
   three-account test.

---

# Re-priced under a EUR 40 budget — 2026-09-15

Kris, 2026-09-15: *"i dont want to spend more then 40 euros on challange"*, and
*"add to research the5ers.com"*. `strategies/vwapbreak/research/firms2.py`,
`backtests/vwapbreak/firms2.json`. Same trade series, same engine (`run_phases`
is imported from `firms.py`, not re-written), budget-linear sizing.

## The correction this run makes to the page above

**The5ers Bootcamp was scored with a 3% daily cap it does not have.** The table
above gives it 219.9 expected days using `daily_loss=0.03`. The firm's own
Bootcamp page and two independent write-ups agree the **3% daily pause applies
only at the funded stage, never during the three evaluation steps**. That is the
most expensive rule in the list for this strategy — its worst single day is
−3.93% of balance at 2% risk — so the error is not small.

Corrected, Bootcamp goes **219.9 → 175.8 expected days**. It does not change the
conclusion, and that is the point: the phases were always the problem.

## The table

| firm | EUR | steps | days | pass % | blown % | risk | consistency |
|---|---|---|---|---|---|---|---|
| **FundingPips 2-Step Flex** | **29** | 2 | **75.3** | 54.4 | 21.6 | 3.00% | none stated |
| Maven 3-step | 16 | 3 | 167.0 | 29.3 | 54.9 | 1.50% | none stated |
| The5ers Bootcamp | 19 | 3 | 175.8 | 31.9 | 51.9 | 2.50% | none stated |
| Maven 2-step | 20 | 2 | 96.9 | 17.0 | 78.7 | 4.00% | **3 profitable days of 0.5% per phase — DISQUALIFIED** |
| *City Traders Imperium 1-step* | *54* | 1 | **22.8** | 56.9 | 37.1 | 4.00% | none stated |
| *Upcomers Thunderbolt (shipped)* | — | 1 | 18.3 | 54.6 | 40.2 | 4.00% | **20% best day — DISQUALIFIED** |

## What the table says, and it is one thing

**The number of steps is the whole answer, and the EUR 40 budget buys steps.**

| steps | expected days |
|---|---|
| 1 | 18–23 |
| 2 | 75 |
| 3 | 167–176 |

Nothing else in the rule set moves the number as much. Bootcamp has the friendly
structure — no daily cap on any step, no minimum days, EAs allowed, unlimited
time, gold on MT5 and cTrader — and still needs 176 days, because a phase is not
half the work: it is a second and third full chance to breach, and the drawdown
budget is paid again each time.

**The budget is therefore the binding constraint, not the firm.** The fastest
eligible thing under EUR 40 is 75.3 days. **EUR 25 more buys City Traders
Imperium at 22.8 days** — a factor of 3.3 on time, for less than the price of one
extra Bootcamp step. Whether that trade is worth taking is Kris's call, but it
should be made knowingly.

**Maven 2-step is disqualified on the same rule The5ers ProGrowth was**: three
profitable days of 0.5% each, per phase. This strategy takes 0.93 trades a day
and one winner in five carries it. That is the best-day rule wearing a hat.

## VERIFY BEFORE PAYING — new items, on top of the five above

7. **Every price here is third-party.** FundingPips 2-Step Flex is quoted at $32
   for the 5K size (≈EUR 29) and 1-Step Flex at $66; Bootcamp is EUR 19 for step
   1 **plus EUR 43 to activate the funded account**, which the table does not
   include.
8. **Bootcamp's stop-loss rule is a hard constraint on the bot.** A mandatory
   stop-loss on every position, **max 2% risk per position**, and **5 violations
   terminates the account**. The shipped book runs five settings at 0.4% each,
   so each position is inside it — but a netting venue that holds one position
   with one stop, which is what the Bybit bot does today, is not obviously
   compliant. Check before arming anything there.
9. **Is Bootcamp's 5% max loss static or trailing?** Modelled static. Trailing
   would make it worse.
10. **CTI is MT5 / Match-Trader, no cTrader.** The bot has no MT5 bridge on this
    Linux box and building one is unscoped work. FundingPips has cTrader, which
    is a real API.

## CORRECTION, same day — Maven 2-step was priced off a review site, not the firm

Kris asked about Maven 2-step directly. Reading **Maven's own challenge page**
rather than the review that fed the table above changes it:

| | review site (what I used) | Maven's own page |
|---|---|---|
| targets | 8% + 5% | 8% + 5% |
| daily loss | 2% | **4%** |
| max loss | 5% | **8%** |
| consistency | 3 profitable days of 0.5% per phase | **"Consistency score: Not required"** |

Corrected, Maven 2-step is **67.4 days, not 96.9, and not disqualified**. It is
the fastest thing under EUR 40. **It is still not the pick**: it blows **60.9%**
of accounts against FundingPips' **21.6%**, for eight days saved.

**The profitable-days rule is priced rather than deleted.** Two review sites
state it; the firm's page is silent on minimum days rather than denying them.
What it would cost is measurable on our own series, and this is what the rule
means: a day counts only if the account closes it up **0.5% or more**, and three
separate such days are needed before a phase can be passed.

| at 2% risk | |
|---|---|
| days closing ≥ +0.5% | **45 of 634 — 7.1% of all days** |
| calendar days to collect three, from a random start | median **34**, p90 **77**, worst **105** |

**Per phase.** If the rule exists, it roughly doubles the evaluation and Maven is
disqualified. If it does not, 67.4 days stands. **This is the same shape of rule
as a best-day cap**: it does not care what the account made, only that the profit
arrived spread out. This strategy takes 0.93 trades a day and one winner in five
carries it, so it produces a qualifying day one week in two.

Maven's page also shows **"Sorry, this product is not available in your region"**.
Check that before planning on it at all.

---

# TWENTY-TWO FIRMS, two axes — 2026-09-15

Kris: *"research of at least 20 best prop firms and give me table of results what
would suit best"*. `strategies/vwapbreak/research/firms3.py`,
`backtests/vwapbreak/firms3.json`. Same trade series, same engine.

## AXIS B FIRST, because it eliminates half the table before speed matters

Every firm caps the share of a payout that may come from one trading day. This
strategy's profit arrives in single days, and the numbers are worse than the
"76–95%" this page quoted in September:

| payout window | windows | median best-day share | windows under a 20% cap | under 50% |
|---|---|---|---|---|
| 14d | 284 | **103.2%** | 0.0% | 0.7% |
| 30d | 337 | **95.5%** | **0.0%** | **0.9%** |
| 60d | 413 | 89.9% | 0.0% | 5.3% |
| 90d | 444 | 90.0% | 0.0% | 11.7% |

**One day is 95.5% of a typical month's profit.** Over 103% at two weeks — the
best day is larger than the whole fortnight, because the rest of it is a net
loss. A firm capping the best day at **50% can pay us in 0.9% of months. At 20%,
never.**

**Eleven of the twenty-two firms below are therefore unpayable at any speed**,
including the two fastest things in the entire table. This is not a reason to
prefer them and lose later; it is a reason to strike them now.

## The table

`payable%` is the share of 30-day windows whose best day falls under that firm's
cap. `days` is expected days to a funded account on our own blind walk-forward.

| firm | € | steps | days | pass% | blown% | best-day cap | payable% | platform |
|---|---|---|---|---|---|---|---|---|
| **City Traders Imperium 1-step** | **36** | 1 | **24.7** | 56.8 | 37.2 | none found | **100** | MT5, Match-Trader |
| **Aqua Funded 2-Step Std** | **14** | 2 | 58.9 | 44.2 | 39.7 | none found | **100** | MT5, **cTrader**, Match-Trader |
| **FundingPips 2-Step Std** | **27** | 2 | 58.9 | 44.2 | 39.7 | none found | **100** | **cTrader**, MT5 |
| Maven 2-step | 20 | 2 | 67.4 | 32.6 | 60.9 | none found | 100 | MT5, Match-Trader |
| FXIFY 2-step | 36 | 2 | 67.4 | 32.6 | 60.9 | none found | 100 | MT5, DXtrade |
| FundingPips 2-Step Flex | 29 | 2 | 75.3 | 54.4 | **21.6** | none found | 100 | **cTrader**, MT5 |
| Maven 3-step | 16 | 3 | 167.0 | 29.3 | 54.9 | none found | 100 | MT5, Match-Trader |
| The5ers Bootcamp 3-step | 20 | 3 | 175.8 | 31.9 | 51.9 | none found | 100 | MT5, cTrader |
| The5ers Hyper Growth 3-step | 36 | 3 | 191.3 | 28.2 | 18.8 | none found | 100 | MT5, cTrader |
| FundingPips 1-Step Flex | 61 | 1 | **22.0** | 63.7 | **24.3** | none found | 100 | cTrader, MT5 |
| FTMO 2-step | 143 | 2 | 70.3 | 58.4 | 16.6 | discretionary review | 100 | cTrader, MT5 |
| Alpine Funded Peak 2-step | 45 | 2 | 67.4 | 32.6 | 60.9 | none found | 100 | cTrader |
| ~~Upcomers Ash 1-step~~ | — | 1 | *11.3* | 62.0 | 34.9 | 20% | **0.0** | cTrader |
| ~~Upcomers Thunderbolt~~ | — | 1 | *18.2* | 55.0 | 39.7 | 20% | **0.0** | cTrader |
| ~~Goat Funded 1-step~~ | 16 | 1 | *23.3* | 51.4 | 43.4 | 4 days × +0.5% | **0.9** | MT5, cTrader |
| ~~FundedNext 1-step~~ | 61 | 1 | 23.3 | 51.4 | 43.4 | 40% | 0.0 | MT4, MT5, cTrader |
| ~~Atlas Funded 1-step~~ | 63 | 1 | 23.9 | 58.7 | 35.0 | 40% + 1%/day | 0.0 | MT5, TradeLocker |
| ~~PipFarm 1-step~~ | 41 | 1 | 26.5 | 64.2 | 27.6 | 20% + 5 winning days | 0.0 | cTrader |
| ~~Goat Funded 2-step~~ | 20 | 2 | 67.9 | 53.0 | **11.5** | 50% | 0.9 | MT5, cTrader |
| ~~Aqua Funded 2-Step Pro~~ | 18 | 2 | 68.9 | 56.6 | 21.1 | 50% | 0.9 | MT5, cTrader |
| ~~Funded Trading Plus~~ | 73 | 2 | 67.4 | 51.9 | 16.7 | 35% / 50% | 0.9 | MT4, MT5, cTrader |
| ~~FundedNext 2-step~~ | 29 | 2 | 103.3 | 21.3 | 73.5 | 40% | 0.0 | MT4, MT5, cTrader |

## What suits best

**1. City Traders Imperium 1-step — EUR 36, 24.7 days.** The only thing in the
table that is one step, inside budget, and has no best-day rule. It also has **no
daily cap at all** and measures drawdown on **closed balance**, which is the
single most favourable combination for a strategy whose risk shape is large open
swings that mostly come back. H-039 showed that accounting choice is worth more
than any strategy lever measured this year. **Its cost is the platform: MT5 or
Match-Trader, no cTrader, and this box has no MT5 bridge.**

**2. Aqua Funded 2-Step Standard — EUR 14, 58.9 days.** Cheapest credible entry
in the table, has cTrader, static drawdown, no rule found. Two steps is 2.4x the
time.

**3. FundingPips 2-Step Standard — EUR 27, 58.9 days.** Identical speed to Aqua
on our series, twice the price, but the better-known firm and cTrader.

**If the budget moves to EUR 61, FundingPips 1-Step Flex is the best row in the
whole table**: 22.0 days at 63.7% pass and **24.3% blown**, the lowest blow-up
rate of any fast arm, with cTrader. It is EUR 25 over the ceiling.

## THE CAVEAT THAT MATTERS MOST

**"None found" is not "none exists."** Consistency rules are usually published in
the payout FAQ, not the challenge page, and this table's `payable%` treats an
unfound rule as no rule. The measured profit shape means **any** cap at or below
50% takes a firm to ~0% payable. So the first question to ask every shortlisted
firm, in writing, before paying:

> *What is the maximum share of a payout that may come from a single trading day,
> and is there a minimum number of profitable days?*

If the answer is anything at or under 50%, that firm is off the list no matter
what the table above says about its speed.

Prices, targets and drawdowns here are third-party as of 2026-09-15 and several
firms changed rules mid-2026 — Goat's 1-step daily cap went 4% → 3% in August and
its funded payout gained a 4-day 0.5% requirement in July. CTI is listed at $39
here against $59 in the September table; confirm which is current.

---

# THE WIDE SWEEP — 44 products, 2026-09-15

Kris: *"please do bigger research i know its not best ones"*. Correct — the
twenty-two above came largely off cheap-challenge listicles and missed most of
the established names. `strategies/vwapbreak/research/firms4.py`,
`backtests/vwapbreak/firms4.json`.

**36 products scored, 14 named without an obtainable rule set, 5 groups excluded
outright.** Futures firms (Topstep, Apex, MyFundedFutures, Bulenox, Earn2Trade,
Tradeify, TradeDay, Leeloo, BluSky, Elite Trader, Alpha Futures, FFN, Legends)
cannot hold XAUUSD and are excluded by construction, not by score.

## What the wider sweep changed

**Three firms now beat City Traders Imperium inside the budget, and one of them
has cTrader.**

| firm | € | steps | DD | days | pass% | blown% | cap | platform |
|---|---|---|---|---|---|---|---|---|
| **Blue Guardian 1-Step Std** | **29** | 1 | trailing | **23.2** | 56.2 | 37.5 | none found | MT5, Match-Trader, **cTrader** |
| **Alpha Capital Alpha One** | 36 | 1 | trailing | 23.3 | 55.7 | 38.0 | none found | MT4, MT5, **cTrader** |
| City Traders Imperium 1-step | 36 | 1 | static | 24.7 | 56.8 | 37.2 | none found | MT5, DXtrade |
| Aqua Funded 2-Step Std | 14 | 2 | static | 58.9 | 44.2 | 39.7 | none found | MT5, **cTrader** |
| FundingPips 2-Step Std | 27 | 2 | static | 58.9 | 44.2 | 39.7 | none found | **cTrader**, MT5 |
| FundingPips 2-Step Flex | 29 | 2 | static | 75.3 | 54.4 | **21.6** | none found | **cTrader**, MT5 |
| *FundingPips 1-Step Flex* | *61* | 1 | static | **22.0** | 63.7 | **24.3** | none found | cTrader, MT5 |

**Unpayable regardless of speed** — best-day cap at or under 50%, which this
strategy clears in under 1% of months: Upcomers Ash (11.3d) and Thunderbolt
(18.2d), E8 One (18.3d), Goat Funded 1-step (23.3d), Hola Prime (23.3d),
FundedNext both models, Atlas Funded, DNA Funded, PipFarm, Fintokei all three,
Funded Trading Plus, E8 2-phase, Aqua Pro, Goat 2-step. **Fifteen of thirty-six.**

## Three rule shapes the narrow sweep never met

**1. Trailing drawdown.** Almost everything in `firms3` was static. Blue
Guardian, Alpha One, ThinkCapital, E8 One, Aqua Pro and DNA all trail off the
equity high. On this strategy that is normally punitive — H-039 measured trades
reaching **+286.6 R unrealised** before giving it all back — yet the trailing
1-step arms score the same as the static ones (23.2–23.5 vs 24.7). **The reason
is that the evaluation resolves before the giveback matters**; the trailing cap
would bite on a *funded* account held for months, which this table does not
simulate. Treat the trailing rows as flattered.

**2. A hard exclusion, not a slow row.** **Alpha Capital's qualified Pro accounts
forbid holding over the weekend.** The shipped rule holds up to 384 hours —
sixteen days. It cannot be traded there at all, at any speed. Alpha **One** is
fine; Alpha **Pro** is out.

**3. The loosest caps in the industry answer a question we could not otherwise
ask.** Finotive Funding runs **8% daily / 16% max** — nearly triple Thunderbolt's
budget. Result: **51.0 days at 15.6% blown**, the lowest blow-up rate of any
two-step row, and **still not fast**.

> **That settles something.** Tripling the drawdown budget cuts blow-ups 2.5x and
> barely moves expected days. **The pace problem is the edge, not the caps.** No
> firm choice fixes 5–14 days; only a faster rule would, and seven axes of
> tuning have now failed to produce one.

## What suits best

**Blue Guardian 1-Step Standard, EUR 29.** Fastest payable thing under budget
(23.2 days), one step, **and it has cTrader** — the only one of the three fast
arms that does, which matters because the bot has no MT5 bridge on this box.
Its 6% cap trails, which is the thing to verify hardest.

**Second: City Traders Imperium, EUR 36.** Slower by 1.5 days and no cTrader, but
**static, balance-based, and no daily cap at all** — structurally the safest
accounting for a rule whose risk is large open swings that mostly come back.

**Do not buy on speed alone.** The two fastest products in the entire sweep
(Upcomers Ash at 11.3 days, E8 One at 18.3) are both unpayable.

## Still to verify, and now the list is short

1. **The best-day question, in writing, for Blue Guardian and CTI.** "None found"
   is not "none exists" — it is the single assumption the whole ranking rests on.
2. **Blue Guardian: is the 6% trailing cap intraday or end-of-day?** Intraday
   trailing against 286 R of open swing is a different product.
3. **Gold spread at each firm.** Bybit charges 2.750 bps/side on XAUUSD against
   the 0.915 `core/markets.py` assumes — exactly 3x. Assume 3x until measured.
4. **14 gold-capable firms have no rule set here** — SabioTrade, Audacity,
   Lark, MyFundedFX, EverFunded, AscendX, For Traders, The Trading Pit, FTUK,
   Instant Funding, Crypto Fund Trader, Velotrade, RebelsFunding, Smart Prop
   Trader. They are listed rather than guessed, because a guessed rule set
   produces a real-looking number.
