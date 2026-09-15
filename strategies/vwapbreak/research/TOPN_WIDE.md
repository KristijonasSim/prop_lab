# The shipped configuration is not the fastest one. 2026-09-15.

`backtests/vwapbreak/topn_wide.json`, `topn_wide.log`. Gold 1h, blind quarterly
walk-forward, HOUSE spec (8% / 3% / 6%), identical folds and costs throughout.

## What was never tested

`core/chosen.py` records the choice of **floor 30 / top 5** and the comparison it
was made against: *"`top 1` at 4% risk reaches 60.1% pass in 18.3 days - three
days quicker - and it takes 0.15 trades a day, which is two or three trades
inside a whole evaluation."* **The comparison was top5 against top1.** It was
never made against top10, top15 or top20, and never at a wider floor.

## The sweep

| config | trades | per day | PF@2x | risk | days | band | pass% | blown% |
|---|---|---|---|---|---|---|---|---|
| floor30/top1 | 107 | 0.15 | 1.429 | 6.0% | 25.6 | 22–40 | 42.9 | 56.7 |
| **floor30/top5 (shipped)** | 957 | 1.32 | **1.987** | 6.0% | **15.4** | 13–20 | 38.8 | 61.2 |
| floor30/top10 | 2103 | 2.89 | 1.790 | 6.0% | 15.5 | 14–22 | 38.7 | 61.3 |
| floor30/top15 | 3270 | 4.49 | 1.959 | 6.0% | 16.5 | 13–22 | 36.4 | 63.6 |
| floor30/top20 | 4384 | 6.01 | 1.888 | 5.0% | 15.8 | 14–22 | 38.1 | 61.9 |
| floor100/top1 | 305 | 0.42 | 1.607 | 6.0% | 22.7 | 21–36 | 39.6 | 60.4 |
| floor100/top5 | 1570 | 2.15 | 1.682 | 3.0% | 16.0 | 14–23 | 37.5 | 62.5 |
| floor100/top10 | 3149 | 4.32 | 1.708 | 6.0% | 12.2 | 11–17 | 32.9 | 67.1 |
| floor100/top15 | 4816 | 6.61 | 1.735 | 6.0% | 11.4 | 9–15 | 35.1 | 64.9 |
| **floor100/top20** | **6657** | **9.13** | 1.755 | 4.0% | **10.6** | **10–15** | 37.8 | 62.2 |

## Why this is not another day's noise

**It is monotone in N at the wide floor, across five levels:** 22.7 → 16.0 →
12.2 → 11.4 → 10.6. Every result killed today failed on the opposite pattern —
a number that jumps one way at one setting and back at the next (EMA 0.877 on
1h and 3.005 on 4h; H-041's blow-ups flat then stepping). **A clean monotone
trend across five levels is the shape a real effect has.**

It also has the trade count to support it: 6,657 trades at 9.13 a day against
the shipped rule's 957 at 1.32.

## What it does NOT clear

**The bands overlap.** floor100/top20 is 10–15 and the shipped rule is 13–20.
By this project's own standard, overlapping bands mean the difference is not
resolvable, and **10.6 against 15.4 is therefore a point estimate, not a proof**.

**Profit factor falls**, 1.987 → 1.755, and blow-ups are unchanged at ~62%. The
gain is pace and nothing else.

**The best-day share does not improve** — 100.4% against 102.4% — so this does
nothing for the consistency-rule problem that rules out most firms.

**The top-N choice is now a 10-cell search** made by looking at this table. The
monotonicity is what protects it, not the ranking.

## Why it matters anyway

**10.6 days is inside the 5–14 day pace target. 15.4 is not.** That is the
target this project has failed to reach for six weeks, and the thing that
reaches it is a parameter of the strategy already being traded.

## What has to happen before it is traded

1. **An out-of-sample split on the top-N choice itself.** Per-fold selection is
   already blind; the choice of N is not.
2. **The paired null.** Every arm here is real-data only.
3. **The operational question.** Twenty settings in parallel is twenty positions
   at 1/20th risk each; the live bot runs five and its netting, backstop and leg
   book were built for that. `live/bybit_demo.py` would need work.
4. **The other markets**, per the standing universe rule.
