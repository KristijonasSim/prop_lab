# Building trading strategies with AI — the state of it, 2026-09-21

Written because Kris said: *"we are walking blindly."*

This is a reference, not a plan. **Nothing here is chosen.** It answers four
questions he asked — which model, how to do it properly, what test environment,
what indicators — and adds a fifth that the research kept forcing to the front:
**which market and which venue**, because that turned out to dominate all four.

Everything is sourced. Where a number is mine, it says so and shows the
arithmetic.

---

## 0. The answer in ten lines

1. **The published frontier of "AI finds alpha" is cross-sectional equity, and
   its effect sizes are tiny.** The best LLM alpha-miner on the S&P 500 reports
   an IC of **0.0056**. That is tradeable across 500 names. It is worthless on
   one gold chart.
2. **And H-027's skill per bet is about fourteen times that.** Backing the
   Fundamental Law `IR = IC × √breadth` out of this repo's own numbers gives
   H-027 an implied **IC of 0.077** on 225 bets a year. The papers take a
   signal 14× weaker and make **~43,000** bets a year with it. **The deficit
   was never signal quality — it is breadth, and a single-instrument trader
   cannot buy breadth.** §2.1, arithmetic shown, caveats stated.
3. **Direct prediction does not work.** Time-series foundation models
   (TimesFM, Chronos-2, Moirai) win forecast-accuracy leaderboards and still
   beat a random walk by a skill score of order **10⁻³**, significant in **2 of
   10** tasks. The paper's own words: not "universal engines of alpha."
4. **A systematic falsification study of OHLCV intraday signals on MNQ futures
   tested 14 signal families over 947 days. None passed.** That study is this
   repo's last eighteen months, done by someone else, published.
5. **But that study found the thing `prop_lab` is missing: positive controls.**
   Two planted signals scored T=3.11 and T=4.30, which proves the pipeline can
   see an edge when one exists. **This repo has never run one.** Every null here
   is a negative control. A pipeline that only ever returns "no" is
   indistinguishable from a broken pipeline.
6. **Where AI genuinely pays is not direction. It is sizing** — meta-labeling a
   rule you already have. That is the one technique in this document that fits
   H-027 as it stands.
7. **LLMs carry a look-ahead bias of their own.** Matched-period testing shows
   alpha decaying from **+20.7% to −1.0%** across a training cutoff, and *larger*
   models decay *worse*. Any LLM proposing hypotheses about 2023-2025 has read
   how 2023-2025 turned out.
8. **The stack is not the problem.** NautilusTrader for validation plus vectorbt
   for screening is still the right 2026 answer. What is missing is not an
   engine, it is three tests: CPCV, PBO, and a positive control.
9. **The venue is a problem.** Spot XAUUSD is a CFD. There is no central order
   book, so its "order flow" is one broker's indicative quote size. **COMEX gold
   futures have a real tape, cost about half as much, and the futures prop firms
   allow full API automation** — Topstep on evaluation *and* funded accounts.
10. **Model choice matters less than anything else here.** The best published
    automated-quant system used **o3-mini**, a small cheap model, and beat
    classical factor libraries 2× with 70% fewer factors. The gains came from
    the loop, not the brain.

---

# Part 1 — What the field actually does, and what it actually gets

## 1.1 The four things people mean by "AI trading"

They have wildly different evidence bases. Ranked by how well they hold up:

| # | approach | what it does | honest verdict |
|---|---|---|---|
| 1 | **Research automation** | LLM proposes hypotheses, writes code, runs backtests, reads the result, proposes again | **Works, and is the real story of 2025-26.** Best published result below. |
| 2 | **Meta-labeling** | ML decides *whether* to take a signal your existing rule generated, and how big | **Works, modest, and fits a one-rule trader.** The only item here that suits H-027. |
| 3 | **Alpha/factor mining** | LLM writes formulaic alphas, ranked cross-sectionally | Works in equities. **Effect sizes are minuscule and depend on breadth.** |
| 4 | **Direct prediction / end-to-end RL** | Model eats prices, emits a forecast or an action | **Does not clear costs.** Strongest evidence against. |

## 1.2 The best published result, and what it really says

**RD-Agent(Q)** (Microsoft Research, arXiv 2505.15155) is the current high-water
mark for automated quant R&D. It splits the job exactly the way `research/`
already does — a Research stage that forms hypotheses and a Development stage
(`Co-STEER`) that writes and runs the code — with the backtest result fed back
as the next prompt.

| RD-Agent(Q), CSI 300 | |
|---|---|
| IC | 0.0532 |
| Annualised return | 14.21% |
| Information ratio | 1.74 |
| vs classical factor libraries | **~2× return, 70% fewer factors** |
| LLM used | **o3-mini** |

Two things to take from this and nothing else:

* **The architecture is the product.** `prop_lab/research/` is already this
  shape. That is worth knowing: the loop Kris built on 2026-09-18 is not naive,
  it is the published design.
* **It ran on o3-mini.** Not a frontier model. The result came from the
  feedback loop and the validation, not from raw model capability. Anyone
  telling you the answer is a bigger model is selling something.

**Caveat the paper carries itself:** CSI 300 is 300 stocks, long-short,
cross-sectional. An IC of 0.053 is a *correlation of five percent* between
prediction and outcome. It is an enormous number in that setting and a
meaningless one in Kris's.

## 1.3 The alpha-mining numbers, stated plainly

**AlphaAgent** (KDD 2025, arXiv 2502.16789), whose whole contribution is
regularising against alpha decay:

| AlphaAgent, S&P 500 | |
|---|---|
| IC | **0.0056** |
| ICIR | 0.0552 |
| Annualised return | 8.74% |

**Read that IC again.** A 0.56% correlation between the signal and the next
period's return, described by the authors as "significantly ahead of
second-best performers." That is the frontier. It works because it is spread
across 500 names.

**Chain-of-Alpha** (arXiv 2508.06312) surveys the whole family and lists its
failure modes: simplified performance evaluation, weak numerical understanding,
lack of diversity and originality, weak exploration, **temporal data leakage**,
and black-box compliance risk. Every one of those is a failure mode `prop_lab`
has already hit at least once independently.

## 1.4 Direct prediction: the cleanest negative result available

*Pretrained Time-Series Foundation Models for Financial Return Forecasting*
(arXiv 2606.27100) is the honest benchmark. Zero-shot TSFMs — TimeGPT,
TimesFM-2.5, Moirai-2.0, Chronos, Chronos-2 — against from-scratch baselines
(NBEATS, NHITS, PatchTST, iTransformer, KAN), five US equities, 20-day horizon.

* TSFMs took **8 of 10 task-level wins**. Sounds good.
* **Skill scores over a random walk were of order 10⁻³** — a 0.1% error
  reduction.
* A Diebold-Mariano test rejected equal performance in **2 of 10 tasks**.
* No Sharpe, no IC, no hit rate. It is a forecast-accuracy paper.

The authors' own conclusion: TSFMs are *"useful practical priors that reduce
model-development costs in low-data financial forecasting, but not as universal
engines of statistically reliable alpha generation or trading performance."*

Separately, independent benchmarking finds pre-training corpora overlap with
test sets, **inflating reported accuracy by 47–184%**; on clean data the edge
over strong baselines collapses to **0.3–14%**.

**Conclusion: do not build a price predictor.** Not with a foundation model, not
with an LSTM, not with a transformer. The literature's best case is a tenth of a
percent of error reduction on a 20-day horizon, and gold's round trip is a real
cost that must be paid on every trade.

## 1.5 End-to-end RL

FinRL is the reference library and it is honest about the problem: a
*"simulation-to-reality gap between testing performance and real-live market
performance."* Its mitigation is a rolling `training-testing-trading` pipeline —
retrain quarterly, pick the agent with the best validation Sharpe.

That is **fold selection by validation Sharpe**, which is exactly what
`core/pipeline.py` already does and exactly what `strategies/beat/` measured as
a dead end. RL adds an enormous parameter count and a much larger search on top
of a selection rule this repo has already established sits on a
frequency-versus-survivability curve. **Not recommended. Highest cost, weakest
evidence.**

---

# Part 2 — Breadth: the constraint that explains the last two years

## 2.1 Breadth — and the number that should change how Kris feels about this

Grinold's Fundamental Law:

```
IR  =  IC  ×  √breadth
```

`IC` is skill — the correlation between what you predict and what happens.
`breadth` is the number of **independent** bets per year.

Run it backwards on H-027, using only this repo's own numbers
(`research/README.md`: annual Sharpe **1.16**; `core/chosen.py`: five settings
at six times the 0.15 trades/day of top-1, so ~**0.9 trades/day**):

```
breadth        0.9 × 250  =  225 bets/year
√breadth                  =  15.0
implied IC     1.16 / 15.0 =  0.077
```

Now put that next to the frontier of published LLM alpha mining:

| | implied / reported IC | bets per year | → IR |
|---|---|---|---|
| **H-027 (XAUUSD 1h)** | **0.077** | 225 | 1.16 |
| AlphaAgent (S&P 500, KDD 2025) | **0.0056** | tens of thousands | — |
| ratio | **13.8×** | | |

**H-027's skill per bet is about fourteen times the best published LLM
alpha-miner's.** That is the finding. Kris has been reading "we never find an
edge" off a research programme whose one survivor carries more per-decision
predictive power than the systems in the papers he would be copying.

And the other side of it:

```
to reach IR 1.16 at IC 0.0056 you need  (1.16/0.0056)²  ≈  42,900 independent bets/year
```

**That is what the papers are actually doing.** They take a signal fourteen times
weaker than H-027's and make forty-three thousand bets a year with it. The IR
comes from breadth, not from skill — and a single-instrument trader cannot buy
breadth at any price.

**So the diagnosis flips.** The problem was never signal quality. Two years of
searching for a *better signal* was work on the axis that is already ahead of the
literature. The deficit is **225 versus 43,000**, and no new feed, indicator,
model or prompt changes that number.

**Caveat, and it is a real one.** These two ICs are not the same measurement. The
cross-sectional IC is a rank correlation across names at one point in time;
H-027's is back-solved from its Sharpe through a law that assumes independent
bets and no implementation shortfall. Real breadth is lower than the naive count
in both settings because bets are correlated. **Treat "14×" as an order of
magnitude, not a measurement** — the conclusion survives being wrong by a factor
of three in either direction, which is the only reason it is worth stating.

## 2.2 What this does and does not license

The obvious move is to buy breadth by trading more markets. It does **not** license "trade more markets." `prop_lab` already measured that
and it failed — H-012 widened the book to 57 legs and got *slower*, 15.9 days
in-window against **130.7** held out. The documented cause was **dilution, not
correlation**: equal weighting divides the book's R by the leg count, and the
median leg had R/day of −0.0013.

**H-012 failed at the weighting step, not the breadth step.** The Fundamental
Law assumes you weight bets by conviction. Equal-weighting a book where half the
legs are negative is the one way to get less from more. The literature's answer
is to weight by expected IC and size by a secondary model — which is §3.1 below.

**So breadth is not closed here. Weighting is the unsolved part of it**, and
`prop_lab`'s own note on H-012 says so in as many words: *"do not propose 'a
wider universe' as a cure for drawdown without solving the weighting first."*

## 2.3 The second structural constraint: the prop drawdown

A cross-sectional book survives a 40% hit rate because the good and bad bets
happen simultaneously and net out inside one day. A prop account with a 3% daily
cap and a 6% max cap experiences the same bets **sequentially**, and the path
kills it before the expectation arrives.

This is why `expected_days = median_days / pass_rate` behaves the way
`core/scorecard.py:85` was caught behaving — and it is why **accounts-consumed
(1/pass_rate)** is the honest companion number. That debt is already logged in
`CLAUDE.md`. It is the same issue in a different costume: **path risk is a cost
that cross-sectional research never pays, and every number borrowed from that
literature is quoted without it.**

---

# Part 3 — Where AI actually pays, ranked by evidence

## 3.1 TIER 1 — Meta-labeling. The one that fits what Kris already has.

**The technique.** López de Prado, 2017. Split the decision in two:

* A **primary model** decides the *side*. That is H-027. Unchanged. No ML.
* A **secondary model** — ML — looks at each signal the primary fires and
  predicts only **"will this one work?"**, a binary label. Its output sizes the
  bet, or vetoes it.

**Why it fits here and almost nothing else does:**

* It does not need breadth. It runs on one instrument.
* It does not replace the rule Kris trades, it filters it. The mechanism stays
  the one he can explain.
* It targets **precision**, and precision is what a prop drawdown cap pays for.
  A rule that takes the same winners and skips a third of the losers does not
  need a higher PF to pass an evaluation — it needs a shallower path.
* The label is binary, so it is far easier to learn than a return.

**Reported effects** (treat as upper bounds; these are demo-grade):
precision 0.48 → 0.54 and accuracy 48% → 55% in one test; a mean-reverting
baseline's accuracy 17% → 63% in another. Hudson & Thames' own paper —
*Does Meta-Labeling Add to Signal Efficacy?* — and QuantConnect's
*Why Meta-Labeling Is Not a Silver Bullet* are both worth reading before
believing any of it.

**What it needs, all of which `prop_lab` has:**

| ingredient | status |
|---|---|
| a primary model with high recall | H-027 — takes many signals, PF@2x 2.209 on gold 30/5 |
| triple-barrier labels (stop, target, time) | the kernel already computes all three |
| features at decision time | the entry bar's own state, plus the feed |
| purged, embargoed CV | **missing — see §5.2** |
| a trial budget | `core/ledger.py`, `core/searchcost.py` |

**The honest risk**, and it is the standard one: meta-labeling is a second
search over the same 3 years. It must be charged to the ledger like anything
else, and the features must be pre-registered before it runs, or it will find a
0.06 lift that is the noise floor wearing a hat.

## 3.2 TIER 2 — Research automation. Already built; three upgrades available.

`research/` is the RD-Agent shape and its four safety rules are better than the
published systems':

1. a candidate never writes code, so look-ahead is *inexpressible*
2. every feed declares its knowable lag
3. every feed declares one direction, from the mechanism
4. every trial is charged

Rule 1 is stronger than anything in the RD-Agent line, which lets a code agent
write arbitrary factor code and catches leakage only by backtest inspection.
Chain-of-Alpha lists **temporal data leakage** as an open failure mode for the
whole family. `prop_lab` closed it by construction.

**The three upgrades, in value order:**

**(a) Positive controls — §5.1. Cheapest and most important thing in this
document.**

**(b) Point-in-time discipline on the proposer — §4.1.** The LLM knows how
2023-2025 turned out.

**(c) Hypothesis quality over hypothesis count.** HypoAgents (arXiv 2508.01746)
runs a Bayesian-entropy loop that scores hypotheses against each other and
refines them — **+116.3 ELO over 12 iterations with uncertainty down 0.92**.
The lesson transfers: a proposer that ranks and refines its own candidates
beats one that enumerates. `research/propose.py` currently enumerates.

Given the log-N luck bar this is not urgent. **264 trials → 1,000,000 costs two
sigma.** Volume is cheap; what volume cannot buy is a *larger effect*, and only
better hypotheses do that.

## 3.3 TIER 3 — Alpha/factor mining. Mostly not applicable.

Works, small, and cross-sectional. The one transferable idea is **AlphaAgent's
regularisation against factor homogenisation** — it penalises a new factor for
correlating with existing ones, on the grounds that crowded signals decay
faster. `research/propose.py` refuses *already-tried* candidates; it does not
refuse *correlated* ones. Cheap upgrade, real: two feeds that produce the same
series are one trial's worth of information charged as two.

## 3.4 TIER 4 — Direct prediction, end-to-end RL. Do not build.

§1.4 and §1.5. The single strongest empirical claim in this document is that
these do not clear costs.

---

# Part 4 — The three AI-specific traps

These are not the classical backtest traps. They are new, they are specific to
using models in the loop, and two of them are invisible to every test currently
in this repo.

## 4.1 The LLM knows the future

**Look-Ahead-Bench** (Benhenda, 2026) compared LLM trading signals across two
matched six-month windows with near-identical market returns (~25%): April–Sept
**2021** (inside training data) and July–Dec **2024** (after cutoff).

| model | in-training alpha | post-cutoff alpha | decay |
|---|---|---|---|
| DeepSeek 3.2 | **+20.73%** | **−1.04%** | −21.77 |
| Llama 3.1 8B | +13.81% | −3.42% | −17.23 |
| Pitinf-Large (point-in-time trained) | +6.02% | **+7.32%** | **+1.30** |

Two findings, both bad for the naive approach:

* **The alpha was memory.** Twenty points of it evaporated across the cutoff.
* **The scaling paradox: bigger models decayed worse.** More memorisation
  capacity, more fake alpha. Upgrading the model makes this trap *deeper*.

**What it means for `research/propose.py`.** The proposer's LLM has read that
gold ran hard through 2025, that crypto funding regimes shifted, and which
factors published well. When it "reasons" about a feed's prior sign, some of
that is recall, not mechanism. Mitigations, in order of cost:

1. **Demand the mechanism, not the direction.** Rule 3 already requires a
   declared sign *from the mechanism*. Make the prompt output the causal story
   and *derive* the sign from it, so a sign with no story is rejected
   structurally rather than by a reader's judgement.
2. **Hold out a window the model cannot have seen.** Reserve the most recent
   months as a true post-cutoff slice and report survivors on it separately.
3. **Blind the proposer to the market.** Let it propose over an anonymised feed
   description, so it cannot recall *that instrument's* history.
4. Accept the residual and say so in the write-up.

## 4.2 Deflation does not catch leakage

This is already in `research/README.md` and deserves repeating because it is the
most counter-intuitive item here: **arXiv 2608.27734 planted an oracle with
Sharpe 34.7 and the deflation machinery scored it a perfect 1.00.**

Deflated Sharpe, PBO and the luck bar all correct for **multiple testing**. None
of them detect **a leak**. A leaking strategy is not overfit — it is genuinely
predictive, of data it should not have. The statistics are working correctly and
reporting exactly what they are asked.

**Leakage needs a structural guarantee, not a statistical test.** `research/`
has one (rule 1). `core/pipeline.py` does not — it has a history of
look-ahead bugs found by hand, and three of them are documented in `CLAUDE.md`.

The formal version is *Look-Ahead-Freedom as Temporal Non-Interference*
(arXiv 2607.04958): treat look-ahead as an information-flow property, where
no decision at time *t* may depend on data from any *t' > t*, and verify it with
type-and-effect tracking rather than by inspection. The implementable subset:

1. tag every series with the timestamp at which it became knowable
2. make the kernel read through an accessor that refuses a read of index > *t*
3. **replay**: stream the same data event-by-event and require identical trades

`prop_lab` does (3) already and calls it second-engine verification. It does not
do (1) or (2), and the dead-bar and gap-fill bugs are exactly what (2) catches
automatically.

## 4.3 The search is the experiment

Already this repo's own lesson, restated because it is the one the outside
literature agrees with most loudly. Harvey, Liu & Zhu — *…and the Cross-Section
of Expected Returns* — is the canonical statement: after decades of factor
mining, **a newly discovered factor needs t > 3.0**, not 2.0, and *"most claimed
research findings in financial economics are likely false."*

`backtests/ledger.csv` currently holds **457 trials**. The bar that implies is
already computed by `core/searchcost.py` and it is the reason the board is empty.
**That is the machinery working.**

---

# Part 5 — The test environment

## 5.1 The missing test: positive controls

**This is the recommendation in this document with the best ratio of value to
cost, and it came from a paper that otherwise reads as a eulogy for this whole
approach.**

*Structural Limits of OHLCV-Based Intraday Signals in MNQ Futures: A Systematic
Falsification Study* (arXiv 2605.04004):

| | |
|---|---|
| signal families tested | **14** |
| trading days | 947, 5-minute bars, 2021-2025 |
| validation | expanding-window walk-forward |
| criteria, all five required | T ≥ 2.0 OOS · ≥30 trades/fold · positive net of costs · consistent 2023-2025 · permutation p < 0.001 |
| **passed** | **none** |
| failure mode 1 | **11 of 14 never cleared the friction threshold** — gross 0.07–1.50 points against a 2.0-point cost |
| failure mode 2 | 3 cleared costs, failed on weak T and year-to-year inconsistency |
| **positive controls** | **RTH Confluence T=3.11 · London Session B T=4.30** |

Read those last two rows together. **Eleven of fourteen signals died to costs
before statistics were even relevant** — which is the exact shape of this
repo's five dead feed edges. And the two planted signals passed, which is what
makes the fourteen failures *mean* something.

**`prop_lab` has an extensive negative-control apparatus and zero positive
controls.** Every null here is designed to answer "could noise have done this?"
Nothing answers **"could this pipeline see a real edge if one were there?"**

After 457 trials and no survivors, those two hypotheses are observationally
identical:

* the market has no edge at this size, **or**
* the pipeline cannot detect one — too few events, too coarse a screen, a
  bug, a cost model that is too harsh, a fold selector that discards winners.

**How to run one, concretely.** Take gold 1h. Inject a synthetic signal of known
strength into a copy of the series — for example, add *k* basis points of drift
to the bar after a chosen marker fires, with *k* swept across a range. Run the
**entire unmodified pipeline**: screen, walk-forward, null, noise band,
scorecard. Then report the smallest *k* the pipeline reliably recovers.

That number is the **detection floor**, and it converts every past failure from
"nothing there" into "nothing there *above X bps*." It also prices the whole
research programme in one figure: if the floor is 40 bps and realistic edges are
10, the search was never going to work and no amount of new feeds changes that.

A day of work. It should have been the first thing built.

## 5.2 The two validation gates that exist but have never been run

**Combinatorial Purged Cross-Validation (CPCV).** Standard k-fold violates
temporal dependence and leaks through overlapping labels. CPCV builds many
train/test splits, **purges** overlapping samples and **embargoes** a gap around
each test set, producing a *distribution* of out-of-sample results rather than
one path. Comparative work in a synthetic controlled environment finds CPCV
best at mitigating overfitting, on both lower PBO and better Deflated Sharpe.

`prop_lab` runs expanding-window walk-forward — one path. Its noise bands are
built by block-resampling *daily returns*, which prices the noise in the
**result** but not the noise in the **fold selection**. CPCV prices both.

**Probability of Backtest Overfitting (PBO).** `core.searchcost.pbo_cscv` is
written and has never been run. `NEXT.md` has had it at item 3 for four days. It
is the single test that can invalidate `core/pipeline.py`'s fold selector, which
every board number depends on. **Half a day.**

## 5.3 Many paths, not one

Single-path walk-forward answers "did this work on the one history we got." It
cannot answer "would it have worked on a history we plausibly could have got."
The standard fixes, cheapest first:

| method | cost | what it buys | what it cannot do |
|---|---|---|---|
| **block bootstrap** | free, already in `core/noiseband.py` | resampled paths preserving short autocorrelation | breaks long-range structure; weak on small samples |
| **stationary / circular bootstrap** | hours | variable block length, fewer edge artifacts | same |
| **agent-based simulators** | weeks | ABM-generated data improves model performance across statistical and economic metrics, robust across architectures and frequencies | calibration is its own research project |
| **GANs / TradeFM** | weeks-months | macro-conditioned generators with faithful cross-instrument and macro correlation | can hallucinate structure that then gets traded |

**Recommendation: extend the existing bootstrap, do not build a GAN.** The
noise-band machinery already resamples. Applying the same resampling to the
*whole pipeline* — refitting the fold selector on each resampled path — is the
cheap 80%, and it is nearly the same code as the positive control in §5.1.

## 5.4 The engines — no change needed

The 2026 consensus matches what is already installed:

| need | tool | status |
|---|---|---|
| parameter sweeps, hypothesis screening | **vectorbt** — millions of trades in under a second | installed, used correctly |
| event-driven validation, live parity | **NautilusTrader** — *"no serious alternative"* for intraday crypto/FX with order-book behaviour | installed, used correctly |
| end-to-end managed platform | QuantConnect / LEAN | not needed |
| avoid | **Backtrader** — *"starting fresh in 2026 on a frozen framework"* | not used |

**Do not spend a day changing engines.** The split — vectorised for search,
event-driven for truth — is the recommended architecture and it is already the
one in `CLAUDE.md`.

---

# Part 6 — Which model for which job

## 6.1 The benchmarks, September 2026

| job | leader | number | note |
|---|---|---|---|
| agentic coding | **Claude Opus 5** | SWE-bench Verified **97.0%** | GPT-5.6 Sol 96.2, Grok 4.6 95.6, Fable 5 95.0 — **read the top as a tie**, all inside combined error |
| coding (BenchAlign) | Claude Fable 5.1 | 83.8 | Fable 5 76.9, Opus 5 75.6 |
| research-level maths | **GPT-5.5 Pro** | FrontierMath **52.4** | GPT-5.5 51.7 |
| competition maths | GPT-5.4 / GPT-5.2 Pro | AIME saturated (100%) | not a discriminator any more |
| open-weight coding | GLM-5.3 | tops DeepSWE, Terminal-Bench 2.1 | for a self-hosted loop |

## 6.2 The assignment that actually makes sense

| role in the loop | model | why |
|---|---|---|
| **building and fixing the repo** | Claude Opus 5 | agentic coding, long-horizon edits, tool use |
| **hypothesis proposal, bulk** | a small cheap reasoner (o3-mini class) | **RD-Agent(Q) got its 2× on o3-mini.** Proposals are cheap and mostly discarded; frontier tokens are wasted here, and §4.1 says a bigger model memorises *more* |
| **hypothesis critique / ranking** | a strong reasoner, sparingly | this is where quality beats quantity (§3.2c) |
| **the meta-labeling model** | **not an LLM at all** | gradient boosting on tabular features. An LLM is the wrong tool for a binary label on 30 numeric features |
| **anything touching prices directly** | none | §1.4 |

**The single most useful sentence in this section:** the best published result in
this field ran on a small model. If `research/` feels weak, the fix is not a
bigger model — it is a positive control (§5.1), better hypotheses (§3.2c), and a
cheaper market (Part 8).

---

# Part 7 — Indicators and features

## 7.1 What the evidence supports

Mostafavi & Hooman (2025) evaluated **88 technical indicators** on the S&P 500,
reduced to 35 features by PCA, tested with XGBoost, Random Forest, SVR and LSTM
under a rolling window. Feature groups that survived selection:

* **volatility** — ATR, price distance, Bollinger width
* **volume** — MFI, OBV, PVT, accumulation/distribution
* **trend** — SMA/EMA position and slope
* **momentum** — RSI, MACD

Their headline is the useful part: **models with selected features beat models
using the full set**, on both accuracy and stability. More indicators is worse.

## 7.2 The three caveats that matter more than the list

1. **Frequency kills it.** At one-minute frequency, technical indicators add
   **no out-of-sample predictive power** to random-forest SPY models. The
   feature set that works on daily equity data does not survive intraday.
2. **Importance rankings disagree across models** for algorithmic reasons — so
   "RSI ranked high" is a statement about the model, not the market.
3. **`prop_lab` already measured this directly and got the same answer.** The
   H-027 entry-filter family: 25 candidates — moving averages, fibonacci,
   sessions, volatility regime, day of week — and **24 of 25 raised profit
   factor and lowered R per day**. The one survivor lost to a block-shuffled
   version of itself.

**The indicator axis is closed, here and in the literature.** Kris does not need
a better indicator list.

## 7.3 The feature class with the best evidence: order flow

Cont, Kukanov & Stoikov, *The Price Impact of Order Book Events*: over short
intervals price changes are driven mainly by **order flow imbalance** — the
imbalance between supply and demand at the best bid and ask — with a **linear**
relation to price change whose slope is inversely proportional to market depth.
Trade *volume* gives the noisy square-root relation; **imbalance gives a straight
line**, robust to intraday seasonality and stable across stocks.

It is the cleanest microstructure result in finance. **And the honest reading for
this project is a warning, not an invitation:**

* the effect is strongest at **50–100 millisecond** windows and "within tens of
  seconds"
* `prop_lab` already found this independently in H-024: *"the small-cap edge in
  the microstructure literature is a 3-second effect and does not reach
  15m-4h"*, with **0 of 935 cells clearing a 14 bps round trip**

**So H-052 — gold ask/bid volume at 1-minute bars — is not the OFI result.** It
is a *different, weaker* claim: that flow imbalance **aggregated over minutes**
predicts returns **over hours**. That claim has far less support, and it should
be pre-registered as its own hypothesis with that stated, not sold on Cont &
Kukanov's authority.

**The aggregation is also where the cost problem inverts in Kris's favour**, and
that is the real argument for it: OFI at 3 seconds needs an HFT cost structure
nobody here has. At a 1-hour hold, a 1.8 bps round trip is payable. The edge is
smaller *and* the cost is 8× smaller. That trade is the only reason this feed is
worth the fourteen hours.

---

# Part 8 — The venue, which turned out to dominate everything

**This is the part of this research that was not asked for and matters most.**

## 8.1 Spot gold has no tape

`CLAUDE.md` already carries the caveat: Dukascopy's ask/bid volume is *"the
liquidity-provider's own volume, not a central-exchange tape."* The outside
sources are blunter — authentic order flow comes only from exchange DOM/Level 2
feeds, while **decentralised forex and most CFDs offer no actual order book**;
MT4/MT5 "volume" is tick count, not volume.

**COMEX gold futures do have one**: one centralised order book, one public tape,
central clearing, and *"nobody can adjust the reference price that marks your
P&L."*

## 8.2 The cost arithmetic

Computed here from this repo's own data. Gold at **$4,490** (`data/flow/XAUUSD/
20260320.parquet`, last bar 2026-03-20).

| | XAUUSD CFD (Dukascopy) | MGC (micro, 10 oz) | GC (full, 100 oz) |
|---|---|---|---|
| notional / contract | — | $44,900 | $449,000 |
| measured mean spread | **1.64 bps** (this repo's own cache) | — | — |
| spread, 1–2 ticks | — | $1–2 = **0.22–0.45 bps** | $10–20 = 0.22–0.45 bps |
| commission, all-in round turn | in the spread | ~$1.60–1.90 = **0.36–0.42 bps** | ~$4 = **0.09 bps** |
| **round-trip total** | **~1.8 bps** (repo's figure) | **~0.6–0.9 bps** | **~0.3–0.5 bps** |

**Gold futures cost roughly half to a third of the CFD, and come with a real
tape.** Commission figures are from public 2026 broker comparisons and must be
confirmed against an actual account before any of it is believed. The spread
figure for the CFD is measured from this repo's own cache and is solid.

**What that does to the dead work.** Five feed edges died to crypto's 14 bps.
`prop_lab`'s own note: *"Gold's round trip is 1.83 bps. This is that family on
the one market that can pay for it."* At 0.6 bps the same sentence is twice as
true — and the feed stops being a broker's estimate.

## 8.3 The prop-firm rules, which are the decisive part

| | Topstep | Apex | CFD firms (FundingPips etc.) |
|---|---|---|---|
| market | CME futures | CME futures | CFD / OTC |
| **automation, evaluation** | **allowed** | allowed | varies |
| **automation, funded** | **allowed** | **banned** — bots, algorithms, copy trading and AI prohibited on PA/live | varies |
| API | **TopstepX / ProjectX, official** | Project X, NinjaTrader/Rithmic, Tradovate | MT5 GUI, or cTrader |
| accounts per trader | — | **up to 20 funded** | varies |
| restriction | no HFT, no scalping algorithms | copier waives nothing — every rule applies per account | — |

**Topstep permits full automation on evaluation *and* funded accounts through an
official API.** That is the single rule that decides whether any of this can be
a business, and it points at futures, not CFDs.

**Apex's 20 funded accounts is precisely Kris's stated goal** — and automation is
banned on exactly the accounts that would matter. Worth knowing before building
toward it.

## 8.4 What to check before believing any of this

1. **Topstep's trailing drawdown.** The MLL trails the **highest end-of-day
   balance** and never moves back down; on XFA it breaches on *unrealised* P&L.
   That is materially harsher than `core/prop_rules.HOUSE`'s static 6%, and
   every board number would have to be re-simulated against it. `CLAUDE.md`
   already flags trailing-vs-static as worth **17 points of pass rate**.
2. **Topstep's consistency rule.** 50% best-day, Combine phase only, and it
   **raises the profit target rather than failing you**. H-027's median best-day
   share is **95.5%** and only 0.9% of windows sit under a 50% cap. So it does
   not disqualify, but it lengthens the evaluation — and `research/consistency.py`
   already measured that gating on consistency costs **316 expected days**.
3. **"No scalping algorithms."** Undefined, and H-027 holds for hours, so
   probably fine — but it is a written rule and it needs an answer in writing.
4. **Contract granularity.** MGC is 10 oz. On a $50k account at $4,490 gold,
   one contract is $44,900 notional. Position sizing becomes **integer**, and
   every risk-ladder number in this repo assumes a continuous size. That is a
   real modelling change, not a detail.
5. **Session hours.** Futures are ~23/5 with a daily break; the CFD is 24/5.
   H-027 is session-anchored and the anchor may move.

---

# Part 9 — Prompts

What the literature actually supports, stripped of vendor copy.

## 9.1 The loop shape

Every working system — RD-Agent(Q), AlphaAgent, HypoAgents, AI Scientist-v2 —
has the same four stages. There is no sign that a cleverer single prompt
substitutes for the loop.

```
  PROPOSE  →  IMPLEMENT  →  VALIDATE  →  CRITIQUE
     ↑                                       │
     └───────── memory of what died ─────────┘
```

`research/` has all four. The critique stage is the thin one.

## 9.2 What goes in the proposal prompt

Not a request for "a trading strategy." A **structured object**, because the
value is in what the schema refuses:

| field | why it is there |
|---|---|
| `mechanism` | who is on the other side, and why they lose. **No mechanism, no candidate.** |
| `prior_sign` | **derived from the mechanism, stated before the data is touched.** Rule 3. Halved the search space from 5,590 to 2,795. |
| `knowable_lag` + reason | when the value could actually have been read |
| `expected_effect_bps` | forces a size claim ahead of the result — the thing that makes a 7 bps "win" against a 14 bps cost visibly a loss |
| `kill_criterion` | what result ends it, written first |
| `correlation to existing feeds` | AlphaAgent's anti-homogenisation regulariser (§3.3) |

## 9.3 What goes in the critique prompt

The gap in `research/`. Two jobs, and only two:

1. **Rank candidates against each other** before any is charged, on mechanism
   plausibility and expected effect size — the HypoAgents move, worth 116 ELO
   over 12 iterations in their setting.
2. **Read a dead result and say which family it kills**, so the next proposal
   avoids the whole neighbourhood rather than the one cell. `prop_lab`'s
   best-documented lessons are family-level — *"fading an extreme, as a
   family"*, *"the objective axis is closed"* — and they were all written by
   hand.

## 9.4 The three rules the proposer must be held to

1. **Refuse a proposal with no mechanism.** Structurally, in the schema, not in
   the prompt text.
2. **Never let the model see prices.** It picks from enumerated sets; the runner
   builds the signal. Rule 1 of `research/`, and it is stronger than anything
   published.
3. **Never ask it "did this work?"** It has read the answer (§4.1).

---

# Part 10 — What I would change in `prop_lab`, ranked

Cost is my estimate. **Nothing here is chosen — Kris picks.**

| # | change | cost | why it ranks here |
|---|---|---|---|
| **1** | **Positive control — inject a known edge of swept size, run the whole pipeline, report the detection floor** | **1 day** | Converts 457 failed trials from "no edge" into "no edge above X bps". Without it, "the market is efficient" and "our pipeline is broken" are the same observation. §5.1 |
| **2** | **Run PBO on the H-027 fold selector** | half a day | `core.searchcost.pbo_cscv` is written and unrun. Validates or invalidates every board number. Already item 3 on `NEXT.md`. §5.2 |
| **3** | **Answer `reconcile()` on the gold flow** | **minutes** | Decides whether H-052 is aggressor flow (H-006 family) or quoted liquidity (H-024 family, 0 of 935). Already coded. Do it before the 14-hour pull. |
| **4** | **Price COMEX gold futures properly, and email Topstep** | half a day | ~0.6-0.9 bps vs 1.8, a real tape, and **automation allowed on funded accounts**. The only item that changes the ceiling rather than the measurement. Part 8 |
| **5** | **Meta-label H-027** | 3-5 days | The one ML technique that fits one instrument and a drawdown cap — **and the missing half of H-012**: a conviction score is exactly the weighting that equal-weighting lacked. Pre-register the features. §3.1, §2.2 |
| **5b** | **Re-run H-012's wide book, weighted by the §5 meta-model instead of equally** | +2 days | Only after #5 works. The one route to breadth this repo has not tried, and §2.1 says breadth is the actual deficit. Failure mode is known and measured: dilution. |
| **6** | **Point-in-time holdout for the proposer** | 1 day | The LLM has read 2023-2025. §4.1 |
| **7** | **Critique stage in `research/`** | 2 days | Quality of hypothesis is the only thing volume cannot buy. §9.3 |
| **8** | **CPCV alongside walk-forward** | 3 days | Prices fold-selection noise, which noise bands currently do not. §5.2 |
| **9** | **Bigger model anywhere** | — | **Do not.** RD-Agent(Q) ran on o3-mini, and §4.1 says bigger memorises more. |
| **10** | **A price predictor, TSFM or RL** | — | **Do not.** §1.4, §1.5 |

**Two things to hold on to before picking.** §2.1 says the signal axis is
already ahead of the published frontier, so more searching for a better feed is
the lowest-value work on this page — which is the opposite of what `NEXT.md`
currently says. And **if only one thing is done, it is #1.** It is the cheapest, it is the only one
that reprices all past work rather than adding new work, and the paper that
supplied the idea is the same paper that ran this exact search on MNQ futures
and found nothing — with two planted controls proving its own machinery worked.
`prop_lab` has the eighteen months of nothing. It does not have the proof that
the machinery works.

---

# Part 11 — Data, and what this costs to run

## 11.1 Where the data comes from

| need | source | cost | note |
|---|---|---|---|
| **FX / metals tick** | **Dukascopy** | free | what `prop_lab` already uses. Community-standard for FX tick continuity. **Carries the synthetic weekend bars** this repo found the hard way — 21.5% of the XAUUSD series |
| FX tick, alternative | TrueFX | free | second source, useful as a cross-check |
| **crypto depth** | Binance / Coinbase / OKX WebSocket | free | already in `data/feeds/` |
| crypto L2/L3 replay | Tardis.dev | paid | only if depth research restarts |
| **CME futures historical** | **Databento** (GLBX.MDP3) | **$179/mo** standard, or pay-as-you-go metered by bytes | covers GC and MGC, full book, L1/L2/L3, nanosecond stamps. **$125 free credits** |
| CME futures, cheaper history | FirstRate Data | one-off | 15 years intraday GC |
| **CME real-time, to trade** | broker / platform, non-professional | **~$10-15/mo per exchange** top-of-book (COMEX is its own exchange); L2 more | professional rate is **$140/exchange/mo** — misclassification is expensive |

**The important one:** a Databento pay-as-you-go pull of MGC/GC trades and quotes
for three years is the honest test of Part 8, and it costs tens of dollars, not
$179/mo. **It also answers H-052 properly** — a real tape to compare Dukascopy's
LP volume against, which `CLAUDE.md` currently records as impossible because
*"spot gold has no central exchange."* True for spot. Not true for the futures
that price it.

## 11.2 What the research loop costs

| item | cost | note |
|---|---|---|
| the screen | seconds | 30 candidates in ~2s, measured |
| a full walk-forward | hours | the real throughput bound: 5-20 studies/day |
| the VM | already paid | 2 cores / 952 MB — fine for the loop, not for a walk-forward |
| **LLM tokens for proposals** | **small, if a small model is used** | §6.2. RD-Agent(Q)'s result came on o3-mini |
| **the real cost** | **the trial budget** | 457 charged. Every trial raises the bar for all the others whether or not it was informative |

**The binding constraint on this project is not compute or money. It is the
statistical budget**, and `core/ledger.py` is the only thing that meters it.

## 11.3 Point-in-time, the discipline that cuts across all of it

Three separate incidents in this repo trace to the same root — data that was not
what it would have been at decision time:

* FRED **revises**, and the cache keeps only the latest vintage. H-035 died on
  this. Any survivor from a FRED feed needs re-checking against ALFRED.
* Dukascopy **pads the closed weekend** with synthetic O=H=L=C bars. 21.5% of
  the XAUUSD series; two engine rules now exist because of it.
* LLMs **are** a revised vintage — they have read the outcome (§4.1).

**One rule covers all three: nothing enters a backtest unless it carries the
timestamp at which it became knowable, and the runner applies the lag.**
`research/` enforces this for feeds (rule 2). `core/pipeline.py` does not enforce
it structurally. §4.2 has the formal version.

---

# Sources

**LLM-driven quant research**
- [R&D-Agent-Quant: A Multi-Agent Framework for Data-Centric Factors and Model Joint Optimization](https://arxiv.org/pdf/2505.15155) · [overview](https://www.alphaxiv.org/overview/2505.15155) · [microsoft/RD-Agent](https://github.com/microsoft/rd-agent)
- [AlphaAgent: LLM-Driven Alpha Mining with Regularized Exploration to Counteract Alpha Decay](https://arxiv.org/html/2502.16789v2)
- [Chain-of-Alpha: Unleashing the Power of LLMs for Alpha Mining](https://arxiv.org/pdf/2508.06312)
- [Automate Strategy Finding with LLM in Quant Investment](https://arxiv.org/abs/2409.06289)
- [Bayes-Entropy Collaborative Driven Agents for Research Hypotheses Generation (HypoAgents)](https://arxiv.org/pdf/2508.01746)
- [The AI Scientist-v2: Workshop-Level Automated Scientific Discovery via Agentic Tree Search](https://arxiv.org/abs/2504.08066)
- [Awesome-LLM-Quantitative-Trading-Papers](https://github.com/Tom-roujiang/Awesome-LLM-Quantitative-Trading-Papers)

**Negative results and validation**
- [Structural Limits of OHLCV-Based Intraday Signals in MNQ Futures: A Systematic Falsification Study](https://arxiv.org/abs/2605.04004) — the positive-control idea
- [Pretrained Time-Series Foundation Models for Financial Return Forecasting](https://arxiv.org/html/2606.27100)
- [Your LLM's Alpha Might Be Mere Memorization](https://hedgefundalpha.com/education/your-llms-alpha-might-be-mere-memorization/) — Look-Ahead-Bench
- [Look-Ahead-Freedom as Temporal Non-Interference](https://arxiv.org/pdf/2607.04958)
- [Backtest overfitting in the machine learning era: a comparison of out-of-sample testing methods](https://www.sciencedirect.com/science/article/abs/pii/S0950705124011110) — CPCV vs alternatives
- […and the Cross-Section of Expected Returns](https://www.nber.org/system/files/working_papers/w20592/w20592.pdf) — Harvey, Liu & Zhu, t > 3.0
- [Purged cross-validation](https://en.wikipedia.org/wiki/Purged_cross-validation)

**Meta-labeling**
- [Does Meta-Labeling Add to Signal Efficacy?](https://hudsonthames.org/wp-content/uploads/2022/04/Does-Meta-Labeling-Add-to-Signal-Efficacy.pdf) — Singh & Joubert
- [Why Meta-Labeling Is Not a Silver Bullet](https://www.quantconnect.com/forum/discussion/14706/why-meta-labeling-is-not-a-silver-bullet/)
- [Meta-Labeling](https://en.wikipedia.org/wiki/Meta-Labeling)

**Breadth and microstructure**
- [Fundamental Law of Active Management](https://www.fe.training/free-resources/portfolio-management/fundamental-law-of-active-management/) · [Redux](https://www.sciencedirect.com/science/article/pii/S0927539817300543)
- [The Price Impact of Order Book Events](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=1712822) — Cont, Kukanov & Stoikov · [summary](https://quantmemo.com/writing/paper-cont-kukanov-stoikov-order-flow-imbalance)

**Features**
- [Key technical indicators for stock market prediction](https://www.sciencedirect.com/science/article/pii/S2666827025000143)
- [Comparing model-specific and model-agnostic feature importance methods](https://www.sciencedirect.com/science/article/pii/S2666827025001823)

**Engines, synthetic data, RL**
- [Python Backtesting Frameworks (2026): 7 Compared Honestly](https://quanttradingtools.com/python-backtesting-frameworks/) · [Best Python Backtest Engines in 2026](https://bullalert.ai/blog/best-python-backtest-engines-2026/)
- [Bayesian Robust Financial Trading with Adversarial Synthetic Market Data](https://arxiv.org/html/2601.17008)
- [TradeFM: A Generative Foundation Model for Trade-flow and Market Microstructure](https://arxiv.org/pdf/2602.23784)
- [FinRL: Deep Reinforcement Learning Framework to Automate Trading](https://arxiv.org/pdf/2111.09395)

**Models**
- [Best LLM for Coding (September 2026): SWE-bench & LiveCodeBench Ranked](https://benchlm.ai/coding)
- [LLM Coding Benchmarks: The Complete Guide September 2026](https://www.openlayer.com/blog/llm-coding-benchmarks-complete-guide)
- [Best LLM for Math 2026](https://benchlm.ai/blog/posts/best-llm-math)

**Venue and prop firms**
- [Prop Firm Automation: FTMO vs Apex vs TopStep Rules Compared](https://clearedge.trading/post/prop-firm-automation-ftmo-apex-topstep-rules) · [Topstep vs Apex bot comparison](https://clearedge.trading/post/topstep-vs-apex-automated-trading-rules-bot-comparison)
- [Apex Funded Automation Rules 2026: Allowed vs Banned](https://blog.pickmytrade.trade/apex-funded-automation-rules-2026/)
- [Topstep Rules 2026 — Complete Guide](https://propjournal.net/prop-firms/topstep/rules)
- [Futures Prop Trading: Why Prop Firms are Moving Beyond CFDs](https://dx.trade/news/articles/futures-prop-trading-why-prop-firms-are-moving-beyond-cfds/)
- [MGC Tick Value: Micro Gold Futures Contract Specs](https://damnpropfirms.com/trading-guides/mgc-tick-value-micro-gold-futures-contract-specs/) · [Futures Commissions Explained](https://damnpropfirms.com/trading-guides/futures-commissions-explained-what-you-actually-pay/)
- [XAUUSD vs Gold Futures: Cost, Margin & Roll Compared](https://fxnx.com/en/blog/xauusd-vs-gold-futures-cost-leverage-roll-compared)
- [Databento CME pricing](https://databento.com/blog/introducing-new-cme-pricing-plans) — $179/mo standard, pay-as-you-go historical

**Data sources and fees**
- [Best Sources for Tick & Aggregated Futures Data in 2026](https://www.quantvps.com/blog/best-sources-for-tick-aggregated-futures-data)
- [Quant Data Provider Comparison: Databento, Massive, Wind, EODHD, Barchart](https://waylandz.com/quant-book-en/Data-Provider-Comparison/) · [Level 2 order book data sources](https://waylandz.com/quant-book-en/Tick-and-L2-Order-Book-Data-Sources/)
- [CME January 2026 market data fee list](https://www.cmegroup.com/market-data/files/january-2026-market-data-fee-list.pdf) · [CME market data pricing explained](https://tick-stream.xyz/blog/cme-market-data-pricing-affordable-feeds)
