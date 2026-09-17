> **SUPERSEDED 2026-09-17 — the claim in this file is withdrawn.** It was
> never run against a null. When it was, the paired null's speed-up beat the
> real one on every market tested (gold real 1.72x vs null 2.45x; silver
> 1.53x vs 2.69x). The monotone trend this file cites as proof of a real
> effect is reproduced by a series with its sequence shuffled out. Kept for
> the workings. See `TOPN_NULL.md` and `topn.py`.

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

---

# VALIDATED OUT OF SAMPLE — 2026-09-15

The objection to the table above was that the top-N choice is a 10-cell search
made by looking at it. So the choice was made on the FIRST half of the window and
scored on the SECOND, which the selection never saw. Split at **2025-09-01**.

## The whole ladder, both halves

| topN (floor 100) | first half | **blind half** | blind band | pass % |
|---|---|---|---|---|
| 1 | 19.8 | 28.3 | 21–52 | 35.3 |
| 5 | 14.1 | 18.7 | 15–31 | 37.5 |
| 10 | 14.1 | 12.4 | 10–18 | 40.3 |
| **15** | 11.7 | **10.3** | **9–16** | 38.9 |
| 20 | 11.0 | 10.4 | 9–16 | 38.6 |

**The trend replicates on data the choice never saw.** 28.3 → 18.7 → 12.4 → 10.3
→ 10.4. The only break is the last step, 10.3 against 10.4, which is a tenth of a
day and below any resolution this study has.

## Against the shipped rule, selection held out

Config AND risk rung fixed on the first half, scored on the second only:

| | blind days | band | pass % | blown % |
|---|---|---|---|---|
| **floor30/top5 (shipped)** | **15.8** | 12–24 | 38.1 | 61.9 |
| **floor100/top20** | **10.4** | 9–16 | 38.6 | 61.4 |

**10.4 against 15.8 out of sample — 34% faster, at the same pass rate and the
same blow-up rate.** The bands (9–16 and 12–24) overlap only across 12–16, which
is the narrowest overlap this project has produced on a pace comparison.

## What this is and is not

**It is:** a validated improvement to the configuration currently traded, chosen
on one half of the data and confirmed on the other, monotone across five levels
in both halves.

**It is not a new edge.** It is the same VWAP band breakout on the same market;
only the number of parallel settings changes. `core/chosen.py` compared top5
against top1 and stopped there — this is the comparison that was never made.

**Still owed:** the other markets per the universe rule, a paired null, and the
operational work — twenty settings is twenty positions at a twentieth risk each,
and `live/bybit_demo.py`'s netting, backstop and leg book were built for five.

---

# THE UNIVERSE TEST — 2026-09-15. Five markets, five wins, three of them clean.

`backtests/vwapbreak/topn_universe.json`, `.log`. The standing rule set this
morning says every finding runs on all six standard markets. This one had not.

| market | shipped floor30/top5 | band | **floor100/top20** | band | bands disjoint? |
|---|---|---|---|---|---|
| **XAUUSD** | 15.3 | 13–22 | **8.9** | **8–13** | **YES** |
| XAGUSD | 22.1 | 17–30 | 14.4 | 11–18 | no (17–18) |
| **EURUSD** | 25.4 | 20–37 | **11.8** | **10–15** | **YES** |
| **GBPUSD** | 43.9 | 29–71 | **11.4** | **11–16** | **YES** |
| USDJPY | 26.8 | 20–40 | 15.8 | 13–22 | no (20–22) |

**Five markets, five faster. Three with bands that do not overlap** — which is
this project's own definition of a real improvement, written into the H-040 and
`strategies/beat/` pre-registrations long before this study existed.

**Gold reaches 8.9 expected days with a band of 8–13.** The shipped rule is 15.3
with a band of 13–22. They do not touch. That is the first clean pace improvement
this project has recorded on gold.

**And it rescues two markets that were dead.** At top5, GBPUSD scored PF@2x 0.684
with negative R per day and USDJPY 0.874 — both losing money. At top20 they fund
accounts in 11.4 and 15.8 days. The rule was never broken on those markets; it
was starved of trades.

## What it costs, stated plainly

**Blow-ups rise and pass rates fall on every market.** Gold 60.7% → 66.1%, EURUSD
64.5% → 74.3%, GBPUSD 86.3% → 73.6% (the one that improves). The trade is more
attempts that resolve faster, not more attempts that succeed. On a EUR 27–61
challenge fee that is a real cost and it belongs in the decision.

## Still owed

* **A paired null.** Every arm here is real-data only.
* **The operational rebuild.** Twenty settings is twenty positions at a twentieth
  risk each; `live/bybit_demo.py`'s netting, backstop and leg book were built for
  five, and the Bybit account holds ONE netted position.
* **BTCUSDT**, the sixth standard market, not run here.
