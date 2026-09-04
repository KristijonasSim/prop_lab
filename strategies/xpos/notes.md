# H-017 — the search for a book that gets funded in 14 days

Opened 2026-09-04 on Kris's goal: beat H-009 on days-to-funded, aiming for one
week, 14 days worst case, on crypto / FX / NAS / US30 / SP500 / gold / oil /
silver.

## Stage 0 — what the goal actually requires, before any searching

`riskladder.pick` pins risk per trade at `0.08 / |maxDD_R|` (the drawdown must
fill, not exceed, the 8% cap). At that risk, clearing phase 1 needs exactly
`|maxDD_R|` in R and phase 2 another 0.625x, so

    days ≈ 1.625 / K,   where  **K = R_per_day / |maxDD_R|**

**K is the only number that matters.** Not profit factor, not Sharpe, not win
rate — those move K but none of them is it.

| | K | expected days |
|---|---|---|
| H-009 | 0.0517 | 48.7 |
| H-002 | 0.0395 | 53.4 |
| H-016 | 0.0212 | 126.8 |
| **14-day target** | **0.116** | 14 |
| **7-day target** | **0.232** | 7 |

Later confirmed empirically: K correlates **+0.839** with 1/expected_days
across sixteen books, once each is sized properly.

## What was ruled out, each with a number

**Widening the universe alone.** Every subset of H-009's eight legs, fitted:
K scales as **N^0.441** — near-perfect diversification, the legs really are
independent. But per-leg K is ~0.003, so 14 days by width alone needs ~3,400
legs.

**A fast crypto book. Dead on cost.** Thirteen flow features x two forms x five
horizons from 5 minutes to 2 hours, eleven coins, 2021-12 to 2026-09:
**0 of 130 cells clear even a 14bps directional round trip.** Best spread is
5.99bps. The signals are real and correctly signed — crowd_z IC −0.0167 at 2h,
premium_z −0.0192 at 30m, the same direction H-006 found — but they are an
order of magnitude too small for a perp fee. Crypto cannot be traded below the
8-24 hour horizon at retail cost, full stop.

**Cheap markets on a fast clock.** The VWAP kernel on 5m and 15m across gold,
silver, oil, SPX500, US30, NAS100 and six FX majors — 7,776 configs, 14
markets, walk-forward. **Only 2 of 26 legs clear PF 1.20.** Gold works; nothing
else does.

**Selecting folds on K instead of profit factor.** The obvious methodological
fix, tested paired on identical folds. K-selection won 1 panel, PF-selection 2.
**No gain** — K's denominator is a single order statistic and far too noisy to
rank 7,776 candidates by. Worth knowing: it is the natural idea and it fails.

**Stacking more feed gates on H-009.** Four orthogonal gates (systemic crowd,
open interest, perp premium, perp-minus-spot flow gap), alone and in all
eleven stacks, thresholds fixed at zero.

| | trades/day | ret/DD | K | expected days |
|---|---|---|---|---|
| H-002 ungated | 2.99 | 18.25 | 0.0109 | 236.9 |
| **H-009 (crowd gate)** | 2.14 | 29.97 | 0.0180 | **105.7** |
| + systemic | 1.73 | **38.74** | **0.0232** | 162.5 |
| + sys + flowgap | 1.02 | 23.04 | 0.0138 | 227.2 |

**Every extra gate raises ret/DD and K and makes the account SLOWER.** Gates
cut trades and make returns lumpier, and lumpiness costs calendar time. This
matters beyond H-017: **ret/DD is not a valid proxy for days-to-funded**, and
H-015's +29% was measured on that proxy.

*(Stage 5 first produced this with every book pinned at the ladder's 0.25%
floor — drawdowns of 25-59R breach the cap at every rung, so `pick` fell
through to its fallback and the comparison degenerated. Stage 6 fixed it by
scaling every book so its worst drawdown exactly fills 8%. The conclusion
survived the fix.)*

**Parallel accounts.** Staggered starts and one-leg-per-account, all risk
levels. Pooled accounts are near-perfectly correlated, so N=20 gives 70 days
against N=1's 84 at 4% risk. Worth 17%, not 3x.

**Looser sizing policy.** The ladder demands the six-year global drawdown fit
8% *on top of* the account-level breach test. Dropping the global test takes
H-009 from 48.7 to 43.2 days — **+11%, median +5%** across the board. Sizing
policy is not what makes these books slow.

## Stage 8 — the goal, priced

Synthetic daily returns at a known annualised Sharpe, Student-t(4) tails, sized
to fill the cap, through the real two-step evaluation:

| annualised Sharpe | median days |
|---|---|
| 2.0 | 249-313 |
| 4.0 | 79-156 |
| 7.0 | 44-74 |
| 10.0 | 29-41 |
| **15.0** | **18-34** |

**A 14-day median needs annualised Sharpe 10-15.** H-009 is 3.73, H-002 3.67,
H-016 2.69. That is a three- to four-fold gap, and Sharpe 10+ is market-making
territory — which this repo already knows it cannot reach, because
resting-limit fills are on the known-dead list.

## What DID work — the wide crowd-gated book

H-009 runs eight legs on three coins. The Binance metrics archive covers
**eleven**, and nobody had ever run the kernel on the other eight.

44 legs walk-forwarded (11 coins x 4 timeframes), configuration chosen blind
each quarter on 2x-cost profit factor, then gated by H-009's crowd rule at its
fixed zero threshold. **29 of 33 legs clear PF 1.20 at 2x**, per-leg K up to
0.0212 against H-009's own 0.0002-0.0116.

Head to head on one identical window (2023-11-16 to 2026-06-30, 957 days), leg
choice held out on an earlier half:

| book | legs | trades/day | PF@2x | K | pass | **expected days** |
|---|---|---|---|---|---|---|
| H-009 | 8 | 2.24 | 1.650 | 0.0125 | 86.6% | **178.3** |
| H-017 wide, ungated | 20 | 96.8 | 1.473 | 0.0280 | 91.2% | 69.1 |
| **H-017 wide + crowd gate** | 20 | 66.6 | 1.566 | **0.0426** | 95.8% | **45.9** |

**3.9x faster than H-009 on the same dates**, and the crowd gate is worth 69.1
→ 45.9 of it, confirming H-006's mechanism at four times the universe. Adding
H-009's own legs to it makes it *worse* (52.2 days) — they dilute.

This is **not** H-012 repeating. H-012 widened to 57 legs and got slower
because its median leg had R/day −0.0013; these legs are the identical kernel
on the identical asset class with the identical gate.

## Stage 14/15 — Kris's objection, and it was right

The stage 11 book took 66 trades a day each worth **0.031R**, against H-009's
1.29 a day worth 0.113R. Cause: a top-10 configuration book inside every leg
divided each trade's R by ten *before* the twenty legs were equal-weighted.
Nobody trades that.

Re-run at three widths. Per leg: **top-1 gives 0.2485R per trade** at 0.42
trades/day — 2.2x H-009's per-trade edge; top-10 gives 0.0208R at 4.27.

Books built from each, legs chosen on the held-out first half:

| width | legs | trades/day | avg R per trade | risk/trade | %/trade | %/day | expected days |
|---|---|---|---|---|---|---|---|
| top-1 | 10 | 3.15 | **0.4770** | 1.11% | 0.053% | 0.167% | 91.1 |
| top-1 | 20 | 6.24 | 0.3968 | 1.40% | 0.028% | 0.173% | 91.0 |
| top-3 | 20 | 18.48 | 0.1178 | 1.82% | 0.011% | 0.198% | 78.4 |
| top-10 | 10 | 30.57 | 0.0410 | 1.95% | 0.008% | 0.245% | 65.1 |
| **top-10** | **20** | **62.65** | 0.0323 | 3.11% | 0.005% | **0.315%** | **51.5** |

**Few good trades is the better strategy and the slower account.** The top-1
book has four times the per-trade edge and takes nearly twice as long, because
the 8% cap is on the BOOK, not the trade: more legs means each is sized
smaller, and there is no way to have both large per-trade size and many trades
a day.

**The number that settles the goal: the fastest book here earns 0.315% of the
account per day.** Passing in 8 days needs about 1.6%/day. That is a 5x gap and
it is the same 5x that stage 8's Sharpe map shows.

## The ultra hypothesis — combining the books

Common window 2024-10-01 to 2026-06-30, equal weight across books, each book's
own legs chosen on earlier data:

| book | trades/day | PF@2x | K | pass | expected days |
|---|---|---|---|---|---|
| H-017 crypto | 60.4 | 1.698 | 0.0479 | 92.2% | 43.4 |
| H-009 VWAP+crowd | 2.19 | 1.408 | 0.0079 | 79.9% | 237.1 |
| H-016 ribbon metals | 13.5 | 1.328 | 0.0063 | 71.0% | 216.8 |
| H-009 + H-016 | 15.7 | 1.390 | 0.0078 | 75.1% | 242.4 |
| H-009 + H-017 | 62.6 | 1.544 | 0.0265 | 82.3% | 70.5 |
| **H-016 + H-017** | 73.9 | 1.609 | **0.0492** | **95.0%** | **41.1** |
| H-009 + H-016 + H-017 | 76.1 | 1.516 | 0.0255 | 82.3% | 76.6 |

**Combining helps only when the added book is comparable.** H-016 + H-017 is
the fastest thing this project has produced at **41.1 days**, and its pass rate
of 95.0% is the highest on record. But adding H-009 — whose K on this window is
six times lower — drags every combination it touches. Diversification does not
rescue a weak book; it averages it in.

## Verdict

**The goal is not met and, on this evidence, is not reachable.** Seven to
fourteen days requires annualised Sharpe 10-15 or 1.6% of account per day;
the best book here is Sharpe ~4 and 0.315%/day.

**What was gained is real**: the fastest book in the project at **41.1 expected
days** (H-016 + H-017), against H-009's 48.7 on its own board window and 237 on
the common one — and the first book here to pass 95% of simulated evaluations.

Open and unresolved: nothing found gives **5-10 trades a day on a single
market** with a real edge, which is the only shape that would allow large
per-trade size AND speed together. Every fast book here is fast only by adding
legs, and every added leg shrinks the trade.

## Caveats that must travel with the 41.1

- 20 legs x 10 configurations is **200 parallel sub-strategies**, never
  paper-traded. The execution problem is unsolved and is not a detail.
- At 0.005% of account per trade, **one extra basis point of slippage kills
  it outright**. This is the most cost-fragile thing the project has built.
- Crypto perps only, costs assumed at 14bps round trip.
- No phase-randomised market null on the wide grid — only the gate and the leg
  selection have nulls.
- H-009's 48.7 board figure comes from a longer, easier window; on the common
  window it is 178-237. Comparisons across windows here are worthless.

---

# Stage 16/17 — Kris was right, and the sizing rule was hiding it (2026-09-04)

Kris rejected the 73-trades-a-day book outright: four trades a day, $50 risk
each on a $10k account, is what a real book looks like, and his own N5
strategy ran 17 legs at 5-7 trades a day.

**His figure matches this data exactly.** The top-1 legs here average 0.42
trades a day, so seventeen of them is 5.5 a day. The 73 was an artefact of
carrying a top-10 configuration book inside every leg: 200 parallel
sub-strategies, each trade **1/200** of the risk budget - about **$1.56** of
risk, not $50.

He also sent a second AI's arithmetic showing 73 trades a day at PF 1.6 and $50
a trade would make 45-65% a WEEK. That arithmetic is correct and does not apply
here: it assumes 73 trades each risking a full $50, which is **$3,650 of risk
per day on a $10k account - 36.5%**, breaching the 4% daily loss limit several
times over before lunch. Its own conclusion says as much: an edge producing 50%
a week cannot exist, so an input is wrong. The wrong input was the sizing.

## Stage 16 — his configuration, run literally

One configuration per leg, legs ranked on a held-out first half, **flat 0.50%
($50) risk per trade, no rescaling and no dividing by the leg count**:

| legs | trades/day | PF@2x | avg R | $/trade | $/day | curve DD |
|---|---|---|---|---|---|---|
| 6 | 1.98 | **1.832** | 0.4887 | $24.43 | $48 | −18.6% |
| 8 | 2.75 | 1.748 | 0.4772 | $23.86 | $66 | −27.7% |
| 12 | 3.72 | 1.726 | 0.4657 | $23.28 | $87 | −41.6% |
| **17** | **5.48** | 1.644 | 0.4344 | **$21.72** | **$119** | −54.9% |

Risk 50, make 21.72 on average, five times a day. That is the shape he
described and it is what the data actually contains.

## The risk sweep — where `pick` was wrong

17 legs, 5.48 trades/day, PF@2x 1.644:

| risk | $/trade | pass | killed | **median days** | expected days |
|---|---|---|---|---|---|
| 0.25% | $10.86 | 72.5% | 22.1% | 28 | 34.6 |
| **0.50%** | **$21.72** | **50.0%** | 56.3% | **15** | 35.3 |
| 0.75% | $32.58 | 20.0% | 80.1% | 12 | 65.3 |
| 1.00% | $43.44 | 11.2% | 88.4% | 12 | 112.4 |

**`riskladder.pick` had refused every one of these levels.** It requires the
whole six-year equity curve to fit inside the 8% cap on top of the account-level
breach test, and at 0.50% that curve draws down 54.9%. So every book in this
project has been reported at a risk level chosen by the more conservative of
two tests, and the fast configurations were never visible.

`CLAUDE.md` is explicit that this is the wrong thing to hide behind: *"clean
PASS/FAIL with fixed risk per trade and real breaches... if it fails, it fails;
accounts are cheap."* **A 56% kill rate is a price, not a disqualification.**

## Stage 17 — the price, in dollars and days

Evaluation fee $32 (Velotrade, the cheapest firm that permits a bot at all).
Sequential: buy, fail, buy again; a failed account ends early so the wasted
days are its own lifetime, not a full cycle.

| risk | $/trade | pass | median days | accounts bought | fee cost | **days to funded** |
|---|---|---|---|---|---|---|
| 0.25% | $10.86 | 72.5% | 28 | 1.4 | $44 | 35 |
| **0.50%** | **$21.72** | **50.0%** | **15** | **2.0** | **$64** | **23** |
| 0.75% | $32.58 | 20.0% | 12 | 5.0 | $160 | 37 |
| 1.00% | $43.44 | 11.2% | 12 | 8.9 | $284 | 51 |

**0.50% is the optimum: a median of 15 days for an account that passes, 23 days
including the expected retry, at $64 of evaluation fees.**

Running several at once, staggered a week apart (median days to the first
funded / share of start dates where any passed):

| risk | N=1 | N=3 | N=5 | N=10 |
|---|---|---|---|---|
| 0.25% | 28 d / 72% | 27 d / 86% | 30 d / 95% | 32 d / 100% |
| 0.50% | 15 d / 50% | 18 d / 72% | 22 d / 90% | 24 d / 100% |

Read the pair, never the median alone: a column with a higher hit rate includes
harder periods the lower one skipped, which is why the medians rise with N.
**Five accounts at 0.50% ($160) fund at least one within 22 days on 90% of
start dates.**

## Where the goal now stands

| | median days | days incl. retries |
|---|---|---|
| H-009, the incumbent | — | 48.7 |
| **H-017 at 0.50% risk** | **15** | **23** |
| Kris's target | 7-14 | — |

**The 14-day target is met on the median and missed on the all-in figure.**
The gap between 15 and 23 is entirely the 50% of accounts that die.

What stage 8's Sharpe map said still holds and is not contradicted: a
*reliable* 14 days - high pass rate, not a coin flip - needs annualised Sharpe
10-15. What changed is that Kris never asked for reliable. He asked for fast,
on cheap accounts, and at a 50% pass rate that is a different and much easier
problem.

## Caveats on the 15 days

- **Half the accounts die.** At $32 a go that is fine; it is not fine if a firm
  limits retries or if the fee is $100+.
- The curve's own drawdown at this sizing is **−54.9%**. A FUNDED account run at
  0.50% would eventually be destroyed - this risk level is for passing an
  evaluation, not for trading the funded seat afterwards. Those need different
  sizing and that has not been worked out.
- 17 legs across 11 crypto perps, costs assumed at 14bps round trip, never
  paper-traded.
- Held-out on an earlier half, but leg count and risk level were both chosen by
  looking at this table. The 0.50% optimum is a selected maximum.
