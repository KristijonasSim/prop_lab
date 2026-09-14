# Deliverable 2 — publishing the indicator. The description IS the work.

Written 2026-09-14, after H-044 closed the last axis. `NEXT.md` section C has
said since 2026-09-07 that the code half is done and *"what is left is not a
build, it is a decision"*, and CLAUDE.md's third deliverable says the honesty of
the claims matters as much as the numbers.

**This file is the description, the register of every claim in it, and the list
of things we could say and deliberately do not. It is not the decision — Kris
publishes or does not.**

---

## 1. The one rule that shapes the whole description

**The indicator is signals only.** No orders, no equity curve, no profit factor,
no pass rate, no expected days. That was decided when the Pine file was written
and the reasons are in its header: another vendor's volume on a volume-weighted
rule, different fills, no costs, no blind re-selection. A number from this
project quoted next to a TradingView chart would be compared against a strategy
tester that measures something else.

**So the description carries NO performance claim of any kind.** Not a hedged
one, not a backtested one, not one in a screenshot. That is a stricter line than
TradingView's house rules require, and it is the line because of what
`RESEARCH_LOG.md` is full of: every number this project has had to retract was
retracted because it was quoted without its band.

## 2. The description, as it would be pasted

> ### VWAP Band Breakout — the five-setting book
>
> A VWAP band breakout, drawn the way it is actually traded: **five
> configurations of one rule running side by side**, rather than one setting
> anyone has to guess at.
>
> **The rule, for one setting.** VWAP is anchored to the UTC day. Sigma is the
> volume-weighted spread of price about that VWAP. On every closed bar it takes
> `z = (close − vwap) / sigma`. A long fires when z rises to the setting's
> threshold, a short when it falls to minus that. Entry is the **next** bar's
> open — never the signal bar's close. The stop is a multiple of the same sigma,
> measured on the signal bar. There is **no profit target**: the trade ends at
> the stop or at a fixed horizon.
>
> **One position at a time per setting.** A setting already in a trade ignores
> its own signals until it is out. A mark on the chart is therefore a trade, not
> merely a bar where the condition held — which is the difference between an
> indicator you can count and one you cannot.
>
> **Why five settings and not one.** A single setting fires about once a week.
> Anything you conclude from a handful of trades is a conclusion about luck.
> Five thresholds and stop widths side by side produce several times the signals
> from the same rule, and they disagree often enough to be worth watching: a bar
> where all five fire is a different event from a bar where one does.
>
> **What is drawn.** The anchored VWAP and its bands; the bar each setting
> fires on; the stop that setting would use; and a running count of how each
> setting's marks resolved on your chart, your feed, your market.
>
> **A second, deliberately different signal is included.** The Asian-range break
> — the 00:00–07:00 UTC high and low used as a level during the European and US
> day — on the same kernel and the same stop shape. It is drawn in its own
> colours. It is there because it is a genuinely different trade, not a
> confirmation of the first one, and seeing them disagree is the point.
>
> **What this is not.**
> * It places no orders, shows no equity curve and reports no profit. If you
>   want to know whether it makes money on your market, you have to test that
>   yourself, with your costs.
> * The settings shipped here were ranked on gold, on one timeframe, on twelve
>   months of data, and they are refreshed quarterly. **On any other market or
>   timeframe they are an arbitrary starting point, not a recommendation.**
> * Volume is the vendor's. This rule is volume-weighted, so a different data
>   feed gives different bands. That is not a bug and it cannot be fixed.
> * Gaps and untraded bars are drawn differently by different feeds, and the
>   rule is sensitive to them.
>
> **How to judge it.** Count the marks over a period long enough to matter, on
> the market you actually trade, with the spread you actually pay. If that
> sample is small, so is what you have learned.

## 3. Claims register — every factual statement above, and what backs it

| claim in the description | source | safe? |
|---|---|---|
| VWAP anchored to the UTC day, sigma = volume-weighted spread about it | `strategies/vwapbreak/hypothesis.py`, `indicator.pine` | yes — a description of the code |
| entry at the next bar's open, never the signal bar's close | the look-ahead fix of 2026-09-05; `tests/test_no_lookahead.py` | yes |
| stop = multiple of sigma on the signal bar, no target | `core/chosen.py` SETTINGS: `stop_sig` 3.0–4.0, no target field | yes |
| one position at a time per setting | kernel behaviour, stated in the Pine header | yes |
| "a single setting fires about once a week" | 0.15 trades/day, `core/chosen.py` docstring | yes — a **frequency**, not a performance number |
| "five give several times the signals" | 0.15/day → 0.93/day on the shipped book | yes |
| Asian-range correlation to the core signal | 0.114, `core/chosen.py` | **cut from the description** — a correlation invites a portfolio claim |
| settings ranked on 12 months to 2026-08-30, refreshed quarterly | `core/chosen.py`, `refresh_on` 2026-12-01 | yes |

## 4. What we could say and deliberately do not

| number we have | why it stays off the page |
|---|---|
| 59.8% of simulated accounts pass | a performance claim, and its band overlaps the measured luck zone |
| 21.7 expected days, band 16.8–31.4 | same, and the band is the honest part — a reader takes the point estimate |
| PF@2x 2.872 on the 1h cell | a profit factor next to a chart will be read as *this indicator's* profit factor |
| the rule beats its paired null by 2.6× | true, the part most worth trusting, and **meaningless without three paragraphs of method** — which is a paper, not a description |
| seven axes closed by measurement | interesting to us, noise to a reader, and it advertises how much searching was done |
| 16.8 expected days is the ladder's floor | a performance claim about a prop evaluation, which is not what is being published |

**The pattern: everything we know that is favourable is inseparable from a
method the reader cannot check on their own chart.** That is the argument for
publishing a description with no numbers in it at all, and it is why the draft
above has none.

## 5. What Kris is actually deciding

**Not "is the strategy good enough to publish".** The indicator makes no claim,
so it cannot be wrong about performance. The decision is narrower and it is
about his name:

1. **Does the rule deserve his name on it?** It is measured, look-ahead-tested,
   second-engine-verified against NautilusTrader bar for bar, and it is trading
   a demo account. It has also never met the pace target at any position size
   (H-044) — which is a statement about *funding a prop account in 5–14 days*,
   not about whether the signal is worth watching.
2. **Is a description with no numbers in it publishable, or does it read as
   evasive?** The honest answer to "does it work" is *we measured it carefully,
   the result is a range that overlaps noise, and you cannot verify our method
   from a chart*. That is the truth, and it is not a marketing sentence.
3. **Does the demo test change either answer?** It finishes **2026-09-28** and
   is the only out-of-sample, non-simulated evidence this project has ever had.
   **Publishing before it finishes buys nothing and costs the one clean read.**

**The recommendation, and it is a recommendation, not a decision: wait for
2026-09-28.** Nothing about the description improves in the meantime, the code
is done, and the only new information in the project's history arrives on that
date. If the demo test embarrasses the rule, this file is why we did not
publish first.
