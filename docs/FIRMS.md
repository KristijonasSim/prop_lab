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
