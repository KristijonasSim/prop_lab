# How this project should run — research, 2026-09-18

Kris: *"everything happens random, we do little bit of this little bit of that,
we need some kind of workflow."*

He is right, and it is measurable rather than a feeling. This page is what the
measurement says, what the outside literature says, and the operating system
proposed in response. **Nothing here is chosen. Kris picks.**

---

## The answer in six lines

1. **The search has never been priced.** 228 trials are now charged in
   `backtests/ledger.csv`. Zero were pre-registered. The history this project
   allows itself buys 13–45 trials. It has spent 228.
2. **That is the mechanism behind "random"** — with no ledger, every morning
   starts a fresh search that believes it is the first, and a dead idea can be
   re-proposed (it was, on 2026-09-14).
3. **The workflow already existed** in `~/trading-bots/research/`, built
   2026-08-07: search → test → decide, a trial ledger, deflated Sharpe, a trial
   budget. `prop_lab` started 24 days later and rebuilt none of it.
4. **The literature says the outcome so far is the expected one**, and names
   H-027's family specifically. See Part 2.
5. **"We have no API" is out of date.** cTrader's Open API has an official
   Python SDK that runs on Linux, and the prop firm the board already picked is
   on cTrader. The blocker recorded in `live/bybit_demo.py` is wrong.
6. **The honest strategic question is not "which hypothesis next"** — it is
   whether to keep searching at all, or to ship what exists. Part 5.

---

# Part 1 — What is actually wrong, from this repo's own numbers

## 1.1 The search was never counted, so it was never priced

Eighteen days, 220 commits, **48 hypotheses**, **325 files in `backtests/`**,
**176 Python files in `strategies/`**. Against that:

| machinery | present before today |
|---|---|
| paired null per candidate (`core/nulls.py`) | **yes**, and it is good |
| walk-forward with train-only selection (`core/pipeline.py`) | **yes**, and it is good |
| noise band per board cell (`core/noiseband.py`) | **yes**, and it is good |
| cheap screen, five checks (`core/screen.py`) | **yes**, built 2026-09-17 |
| **a count of how many things were tried** | **no** |
| **deflated Sharpe / multiple-testing bar** | **no** |
| **probability of backtest overfitting** | **no** |

`grep -rilE 'deflated|dsr|pbo|minbtl|stepm|trial.?ledger'` over the whole repo
returned nothing.

This is not an oversight that nobody noticed. It is written down twice:

> 2026-09-13, H-035: *"LESSON 1 — price the SEARCH, not just the test. 96 tests
> at a 95th percentile expect 4.8 false passes; 7 were observed."*

> 2026-09-17, `NEXT.md`: *"two other method debts are still open … the search is
> not priced."*

Three days apart, the second re-derived because the first had no code behind it.
**A lesson with no function to call is a lesson that gets re-learned.**

## 1.2 What the bill comes to

`core/searchcost.py` and `core/ledger.py`, both written today, and
`python -m core.ledger` says:

```
trials        228 charged, 0 pre-registered
budget        3y buys 13 (OVER BUDGET), 5y buys 45 (OVER BUDGET)
this search   needs 7.9y of history; luck alone reaches 2.81 sigma
verdicts      ? 106  FAIL 86  PASS 15  NULL 11  DEAD 9  MAYBE 1
```

Read it in order:

* **228 trials need 7.9 years of history** before an in-sample Sharpe of 1 means
  anything (Bailey–Borwein–López de Prado–Zhu; `min_backtest_years(45) = 4.998`
  against their published 5.0, pinned in `tests/test_searchcost.py`).
* **The test-window rule caps history at 3 years ideal, 5 maximum**
  (`CLAUDE.md`, set 2026-09-15). Three years buys **13** trials. Five buys
  **45**.
* So the search has been running at **five to seventeen times its budget**, and
  the best thing it has ever seen has to clear **2.81 sigma of pure luck** to be
  worth anything.

This does not retract any specific result — the paired nulls are real and they
did the killing. It sets the bar for the *next* headline, and it explains why
three headlines have already been withdrawn.

## 1.3 The two rules that follow, and they are cheap

**Pre-registration is rewarded as arithmetic, not as discipline.** At a trial
count of 1 the luck threshold is exactly zero and the deflated Sharpe collapses
to the plain probabilistic Sharpe. A pre-registered single arm faces a
dramatically lower bar than the winner of a sweep — `test_deflated_sharpe_falls_
as_the_search_widens` pins both ends. **Zero of 228 trials were pre-registered.**

**Over-charge the search rather than under-charge it.** The effective-trial
discount needs each trial's return series; guessing it from a column of summary
numbers gave 2.6 effective trials out of 228 in a first draft, which would have
handed the next result a bar near zero. The ledger charges the raw count.

## 1.4 The backlog is re-derived instead of held

* `NEXT.md` rewritten three times in ten days; each version archives the last.
* **B1 and B2 — "one email, open since 2026-09-08"** — still open on 2026-09-17,
  nine days later. `NEXT.md` itself calls B1 *"the cheapest high-value item on
  the page and it is not a research task."*
* `CLAUDE.md` carries a correction dated 2026-09-14 warning that its own text
  caused a duplicate study to be proposed on 2026-09-14.

A backlog that is rewritten is a backlog that is re-decided. That is the same
failure as the missing ledger, one level up.

## 1.5 The workflow already existed in the other repo

`~/trading-bots/research/`, built **2026-08-07**, 2,494 lines:

| file | what it does |
|---|---|
| `generator.py` | 16 mechanism families, one candidate each — a library, not a grid |
| `harness.py` | frozen evaluation; a candidate cannot reach the costs or the metrics |
| `gate.py` | PF, trades/day, sample, out-of-sample, permutation p — cheapest first |
| `stats.py` | MinBTL / DSR, bar-permutation MCPT, Romano–Wolf StepM |
| `curate.py` | re-reads the **whole** ledger and says KEEP / WATCH / DROP |
| `ledger.py` | every trial, and the budget it is spent from |

Its own result, 19 candidates, all DROP: *"price-only rules on 1h bars do not
clear 1.2 PF on this panel … every real leg came from a new data feed, never
from a new arrangement of price."*

**`prop_lab` began 2026-08-31 and imported none of it.** The trial budget, the
DSR, the KEEP/WATCH/DROP curation and the ledger were all sitting in a sibling
directory the whole time. This is the single clearest instance of the thing Kris
is complaining about.

---

# Part 2 — What the outside world says

## 2.1 The most relevant paper describes this project's exact history

*"What survives honest evaluation? Leakage-safe, search-aware assessment of
LLM-driven trading strategy discovery"* (arXiv 2608.27734).

An agent composes strategies from a validated tool registry, every evaluation
passes through one entry point into a **trial ledger**, and the results are
judged with deflated Sharpe, PBO and held-out intervals.

| their finding | this repo |
|---|---|
| 100-candidate agent search: **zero** certified at 0.95 | 48 hypotheses, 1 survivor, outside the pace target |
| best in-sample Sharpe **1.69 → 0.18** on evaluation | H-001 IS 1.907 → OOS 0.671; H-002 train 1.215 → test 0.816 |
| **five independent runs all converged on the volatility-breakout family; 0/5 survive** | H-027 is a volatility-band breakout, and it is the only survivor |
| classic factors: none survive; **PBO 0.83** flags the search as overfit | PBO has never been computed here |
| only passive benchmarks certify (buy-and-hold DSR 0.97) | — |

Their four engineering conclusions map onto Part 3 directly: make validation
structural rather than advisory; record every trial by construction; use three
different instruments for three different failure modes; and **reward
pre-registration, because at N=1 the bar collapses to the benchmark.**

## 2.2 The uncomfortable arithmetic: the test-window cap and the ambition conflict

The paper states it plainly: **a true Sharpe of 0.6 needs roughly eleven years of
out-of-sample data to reach t ≈ 2.** Four-year windows cannot certify moderate
edges. This is arithmetic, not a limitation of any particular system.

`CLAUDE.md` caps history at **3 years ideal, 5 maximum**, and its own table shows
what the cap costs — on H-043 the three-year window flattered the signal by two
to three times against eleven years.

**So the cap and the goal are in tension and one of them has to give.** The cap
is defensible for a *fast* strategy, where the sample comes from trade count
rather than from calendar time: H-027's shipped rule has 813 trades in three
years, and 3,213 over eleven. It is indefensible for a daily-feed idea, where
three years *is* ~750 events and no amount of care recovers the power. The
proposal in Part 3 is to make the cap **a function of events, not of years**.

## 2.3 The industry numbers say the simulation is optimistic

| | published industry | this repo's simulation |
|---|---|---|
| pass rate per evaluation | **8–15%** | 39–64% |
| evaluation buyers who ever reach a payout | **~7%** | not modelled |
| funded accounts that see at least one payout | **~45%** | not modelled |
| typical spend before a payout | **~$4,270** | €96 per funded seat (`docs/FIRMS.md`) |

The board simulates a pass rate **three to eight times the published per-attempt
industry rate.** That gap may be real — an automated rule with a measured edge
should beat the median buyer of a challenge, who is a discretionary retail
trader. But **nothing in this repo has stated the gap, let alone explained it**,
and it is the largest single unexamined number in the plan.

`core/searchcost.ev_per_evaluation` now carries a `payout_rate` argument for
exactly this, and its docstring says to leave it at 1.0 only to see the
optimistic bound.

## 2.4 The API question has an answer, and the repo's note is out of date

`live/bybit_demo.py`, 2026-09-10:

> *"The two eligible firms are on MT5 and cTrader; the MetaTrader package is
> Windows-only and this box is Linux, and **no cTrader connector exists**."*

That is wrong.

* **cTrader Open API** is a first-party API to cTrader's servers — JSON or
  Protobuf, no desktop client, no Windows.
* **`pip install ctrader-open-api`** is Spotware's own Python SDK (Twisted,
  async, streaming quotes and order placement). There is a second package,
  `ctrader-api-client`. Both are plain Python and run on Linux.
* **40+ prop firms are on cTrader**, including FTMO, FundingPips, FunderPro,
  FundedNext, The5ers, Alpine, CTI.
* **FundingPips 1-Step Flex — the row `docs/FIRMS.md` already picked — is
  cTrader.** FunderPro states explicitly that Python and cTrader-API strategies
  may be deployed on evaluation and funded accounts, provided the bot is
  trader-owned rather than rented or mass-distributed.

**So the path from an H-027 signal to a filled order on a prop account exists
today, on this machine, in Python.** It is one spike, not a project. The Bybit
demo was the right call in the absence of that knowledge, and it also cost
something real: Bybit charges **5.50 bps round trip on XAUUSDT, 3.0x what
`core/markets.py` assumes for a gold CFD**, which is a cost penalty being paid
for a connector that was not needed.

**Verified today, and one caveat that matters.** The wheel downloads clean —
`ctrader_open_api-0.9.2`, Spotware's own, `github.com/spotware/openApiPy`, pure
Python, `Requires-Python >=3.8`. Its modules are `client`, `auth`, `endpoints`,
`tcpProtocol`, `protobuf`, `factory`.

But it pins **`protobuf==3.20.1`** and this venv runs **protobuf 7.36.0**. That
is a hard conflict, so:

> **Do not `pip install` it into `.venv/`.** Either give the connector its own
> virtualenv and talk to the strategy over a file or a socket, or use the Open
> API's **JSON** protocol over TLS directly and skip the SDK — the API accepts
> JSON or Protobuf, and the JSON path has no dependency at all.

The second option is a few hundred lines and leaves the research environment
untouched, which is the safer shape given `nautilus_trader` is in the same venv.

---

# Part 3 — The proposed operating system

Four things. Two are already built; two need Kris to agree before they bind.

## 3.1 One ledger, one entry point — BUILT TODAY

```
core/ledger.py           every trial, appended by the code that runs it
core/searchcost.py       MinBTL, PSR, DSR, PBO, accounts-consumed, EV
core/backfill_ledger.py  228 historical trials recovered from STRATEGY_LOG.md
tests/test_searchcost.py the paper's worked example, pinned
```

```python
from core.ledger import log
log(hypothesis="H-053", arm="dfii10_gate", market="XAUUSD", tf="1h",
    n_trades=412, pf=1.31, sharpe=0.62, verdict="FAIL",
    prereg="docs/prereg/H-053.md", note="beaten by its own null")
```

**The rule: a trial that is not logged did not happen, and a trial that is
logged is charged.** `STRATEGY_LOG.md` stays — it is the human narrative and it
is genuinely good. The ledger is its machine-readable shadow.

## 3.2 The gate order — cheapest kill first

`core/screen.py` already argues this and covers gates 1–3. The full order:

| # | gate | cost | where | status |
|---|---|---|---|---|
| 0 | **a pre-registration file exists** | 30 min | `docs/prereg/` | **proposed** |
| 1 | ≥ 40 independent events | seconds | `core.screen` | built |
| 2 | effect ≥ 2× the round trip | seconds | `core.screen` | built |
| 3 | the **median** moves, not just the mean | seconds | `core.screen` | built |
| 4 | monotone bucket response | seconds | `core.screen` | built |
| 5 | beats its own paired null | minutes | `core.nulls` | built |
| 6 | **deflated Sharpe at the ledger's trial count** | seconds | `core.searchcost` | **built today** |
| 7 | **PBO — does the SELECTOR survive?** | minutes | `core.searchcost` | **built today** |
| 8 | walk-forward, train-only selection | hours | `core.pipeline` | built |
| 9 | **€ per funded seat and accounts consumed** | seconds | `core.searchcost` | **built today** |

Gate 7 is the one never asked here. The paired null asks *is this candidate
real*; PBO asks *is the way we pick candidates any good*. This repo's selector is
`core/pipeline.py`'s train-slice profit-factor pick, and it has **never been
measured**. If its PBO is above 0.5 the selector is worse than choosing at
random and every walk-forward number in the project is affected at once.

**Suggested first use of the new code: run PBO on the H-027 fold selector.**
Either answer is worth more than another hypothesis.

*Checked today, so the estimate is honest:* it cannot be done from what is on
disk. `backtests/vwapbreak/hypothesis.json` stores 20 **cell summaries** and one
`daily` series for the chosen configuration; PBO needs every candidate
configuration's returns on a shared axis. So it means re-running the grid with
the per-config series kept — half a day, not twenty minutes. **Keeping those
series should become the default output of `core/pipeline.py`**, because without
them neither PBO nor the effective-trial discount can ever be computed after the
fact.

## 3.3 Pre-registration, one page, before any code

`docs/prereg/H-0NN.md`, and `core/screen.py` refuses to run without it:

```
mechanism      why an edge should exist, and who is on the other side
arms           the COMPLETE list. Adding one later is a new pre-registration.
null           which null, how many seeds, and what "beats it" means numerically
kill criterion the number that ends it, written before the number is known
cost bar       the round trip on the market it will be traded on
markets        the six standard, or a written reason
```

This is the item with the best ratio of cost to value on the page, because of
2.1: the deflation threshold at N=1 is zero. It is not paperwork — it is the
difference between a 2.81-sigma bar and a 0-sigma one.

**H-043's ordering already proved it in miniature** — pre-registering the fee
test first saved a day. This generalises it.

## 3.4 A weekly shape, so nothing carries over by drift

| | |
|---|---|
| **Mon** | pick ONE question. Write the pre-registration. No code. |
| **Tue** | gates 1–5. Most ideas die here in under an hour. |
| **Wed–Thu** | survivors only: gates 6–9, logged as they run. |
| **Fri** | verdict, ledger, board. Ship it or kill it. |

Anything not finished on Friday needs one written line to survive the weekend.
The point is not the days — it is that **an idea has a fixed budget and an
explicit death**, which is what "little bit of this, little bit of that" is the
absence of.

**One piece of friction found while doing this, worth fixing in a minute.**
`CLAUDE.md` says *"`pytest` is the fast run, `pytest -m slow` the engines"*, and
`pytest.ini`'s own marker help says slow is *"excluded from the fast run"* — but
`addopts` does not exclude it, so plain `pytest` runs everything and takes over
ten minutes. The documented fast run is actually **`pytest -m "not slow"`**,
which finishes in about four and passes 209 with 4 skipped. Either add
`-m "not slow"` to `addopts` or fix the sentence; right now the fast path is
slower than the docs claim and gets abandoned halfway.

## 3.5 One rule change to propose: make the window a function of events

Replace *"3 years ideal, 5 maximum"* with:

> **3 years, extended to 5 only when the study cannot otherwise reach 100
> independent events, and never beyond 5. The event count is reported with
> every result.**

Same ceiling, same intent, but it stops a daily-feed study from being run at
750 events and quoted as though the cap were the binding constraint rather than
the power. `core.screen.independent_events` already computes the number.

---

# Part 4 — Where to turn the project

Three routes. They are not exclusive; the ordering is what the evidence supports.

### Route A — Ship what exists. Stop searching.

**The case.** H-027 is the only survivor of 48 hypotheses and **eight closed
axes**. `docs/FIRMS.md`: *"22 days is the floor, not a starting point."* The
pace target is 5–14 days. The indicator is written — 424 lines — and not
published. The demo bot is alive and has never had a trade exit by its own rule.

**What it means concretely.** Publish the TradingView indicator with its band
stated honestly. Build the cTrader Open API connector (Part 2.4). Buy one
FundingPips 1-Step Flex evaluation and run it. Accept 22 days instead of 14.

**Against it.** 22 days misses the stated target, and the pass rate assumption
sits 3–8x above the published industry figure (2.3).

**For it.** It is the only route that produces a result that is not another
measurement, and two of Kris's three stated deliverables are publication and
community, neither of which needs a faster number.

### Route B — The feed hunt on gold and FX

**The case, which is the strongest piece of evidence in the repo.** Every leg
that has ever worked came from a data feed, never from a price pattern — across
two repos now. **Five feed hypotheses (H-006, H-024, H-031, H-034, H-042) were
real, beat their nulls, and died to the same 14 bps crypto round trip.** The
markets that work cost 8–50x less:

| market | taker round trip |
|---|---|
| BTCUSDT / ETHUSDT | 14.0 bps |
| XAGUSD | 9.1 |
| **XAUUSD** | **1.83** |
| **EURUSD** | **0.27** |

A 5 bps edge is dead on crypto and is 2.7x its cost on gold, 18x on EURUSD.
Exactly two feeds have ever been tried on gold — GVZ (real, the best filter
result the project has produced) and CFTC positioning (dead). `NEXT.md` lists
four free FRED series already confirmed to download.

**Against it.** `NEXT.md` states the honest prior itself: twelve price
hypotheses and five feed hypotheses have died. A daily feed gives ~750 events in
three years, which under 2.2 is close to the floor of what can be certified —
which is why 3.5 matters if this route is picked.

**Also open, and larger than any FRED series:** `CLAUDE.md`'s correction of
2026-09-17 — Dukascopy publishes **hourly XAUUSD tick files with ask, bid, ask
volume and bid volume**, and `core/fx_spread.py` has downloaded them all along
while throwing the two volume fields away on line 106. That is a real two-sided
volume series on the one market whose cost bar is low enough to pay for it. It
is the single highest-value untested input in the repo.

### Route C — Keep searching price patterns

**Against it, and the case is overwhelming.** 12 price hypotheses dead here, 19
dead in the sibling repo, 8 axes closed on H-027, and an independent paper whose
five runs all converged on H-027's own family and certified none of them.

**Recommendation: A and B together, C not at all.** A is a build and a decision,
B is research; they do not compete for the same hours. If only one: **A**,
because the project has abundant measurement and no shipped product.

---

# Part 5 — What I would do in the first week

| # | item | cost | why now |
|---|---|---|---|
| 1 | **Send the B1/B2 email.** Equity or closed-balance drawdown; is XAUUSD tradeable. | 10 min | Open 10 days. Worth 27.6% → 4.2% on which cap kills the account. Every board number assumes an answer nobody has. |
| 2 | **cTrader Open API spike** — connect, read the account, place one demo order. | half a day | Removes a blocker that has stood since 2026-09-10 and is not true. |
| 3 | **PBO on the H-027 fold selector.** | half a day | The one gate never run. Validates or invalidates the core machinery in one shot. |
| 4 | **Add gate 0** — `core/screen.py` refuses to run without a pre-registration. | 1 hour | Converts the lesson into a mechanism. Worth ~2.8 sigma of bar. |
| 5 | **Decide A / B.** | — | Kris's call. Nothing below matters until it is made. |

Items 1–4 are independent of the route and of each other.

---

# Part 6 — Two engines, running themselves — added 2026-09-18 (second entry)

Kris: *"two engines, one for registration / generating ideas, the other for
testing — we have testing and it works. I'd love it autonomous, 24/7 on a VM.
From quantity maybe we get quality."*

The split is right and the testing half genuinely is the good half. Three things
were measured before answering, and one of them changes the question.

## 6.1 Quantity is far cheaper than it feels

The luck bar grows with the **logarithm** of the trial count, so mass search is
not the catastrophe the 2.81-sigma figure suggests:

| trials | luck bar | history it would need |
|---|---|---|
| 1 | 0.00 | 0.0y |
| 228 (today) | 2.81 | 7.9y |
| 10,000 | 3.86 | 14.9y |
| 1,000,000 | 4.87 | 23.7y |

**Going from 228 trials to a million costs 2.06 sigma.** A thousand times the
search for two-thirds more bar. Kris's instinct that volume is worth having is
defensible on the arithmetic.

What it costs is stated in Sharpe terms, under this project's own window cap:

| trials | annual Sharpe 3y can certify | 5y |
|---|---|---|
| 1 | 0.00 | 0.00 |
| 228 | **1.62** | 1.26 |
| 10,000 | 2.23 | 1.73 |
| 1,000,000 | 2.81 | 2.18 |

So a 24/7 farm is legitimate **if and only if it hunts large effects.** At ten
thousand trials on three years of data, nothing below an annual Sharpe of 2.23
can ever be certified, no matter how real it is. **Mass search and marginal
edges are incompatible by construction** — not as a matter of taste.

## 6.2 The measurement that has to be said out loud

H-027, XAUUSD 1h, its own stored daily series — 638 observations, per-day Sharpe
0.0609, annual 1.16, skew 15.2, kurtosis 287. Trial-Sharpe variance measured
from the 20 board cells.

| charged at | luck bar (per day) | deflated Sharpe |
|---|---|---|
| **N=1 — pre-registered single arm** | 0.0000 | **0.996** |
| N=38 — H-027's own ledger trials | 0.1434 | **0.000** |
| N=228 — the whole project | 0.1856 | **0.000** |
| N=10,000 — a 24/7 farm | 0.2552 | **0.000** |

**The same series, the same edge, scores 0.996 declared in advance and 0.000
found by searching.** The result is robust — halving or doubling the assumed
trial-Sharpe variance does not move it.

**What this does and does not mean.** It does **not** say H-027 is fake. The
paired null is a different question and H-027 passes it; the noise-floor work of
2026-09-08 said the same thing empirically when shuffled gates scored inside the
real candidates' band. Deflated Sharpe says only: *given how much was searched,
a Sharpe of 1.16 is inside what the search alone would have produced.*

Two honest caveats. Charging H-027 for H-001's ORB trials is arguably harsh —
except that the project-wide search is precisely what selected H-027 as the
survivor out of 48. And **N=38 fails on its own**, so the choice of trial count
does not rescue it.

**The conclusion that matters for Kris's question: the cheapest speed-up
available is not compute. It is writing the arm down before running it.** That
is worth more than any farm, and he is right that it does not take a Monday — it
takes twenty minutes, and `docs/prereg/TEMPLATE.md` is the twenty minutes.

## 6.3 The VM cannot do this, and the box that can is idle

Measured today:

| | cores | RAM | python |
|---|---|---|---|
| Oracle VM (89.168.78.138) | 2 | **952 MB** | 3.8 |
| this desktop | **28** | **30 GB** | 3.12 |

The VM is a free-tier box with 545 MB available and a load average of 0.08. It
is a perfectly good **order router** — which is what it is doing, hourly, and it
has been up 56 days. It is not a research machine and will not become one.

**So invert the plan: the VM keeps routing orders, and the 28-core desktop runs
the research loop.** It has 28 cores sitting at idle and that is where the
quantity is. "Autonomous" should mean unattended, not remote.

## 6.4 What Engine 1 has to be, and the one rule that makes it work

The literature converged on the same shape: QuantaAlpha, XALPHA and **AlphaMemo**
all wrap the generator in a *structured memory of the search process* — what was
tried, what failed, and why — specifically so the agent stops re-exploring dead
space. AlphaMemo's whole finding is that memoried agents beat memoryless ones on
both discovery rate and survival rate.

**This repo now has that memory: `backtests/ledger.csv`.** It is the missing
half of Engine 1, and it was the missing half of Engine 2's honesty too.

The rule that decides whether the loop is worth building:

> **Quantity spent on new MECHANISMS is affordable. Quantity spent on new
> PARAMETERS of an old mechanism is pure cost.**

Both raise the bar by the same log(N). Only the first opens space that was never
searched. Eight closed axes on H-027 are 38 trials of the second kind. The
sibling repo's `generator.py` already enforces this — it emits one candidate per
mechanism family and **refuses to re-emit a family already in the ledger** —
and its README draws the same conclusion: *"the fix is a new data feed in
`vocab.py`, not more shapes of the same 24 columns."*

## 6.5 Three ways to build it — Kris picks

### Option A — Mechanism library on a timer. Free, deterministic, dumb.

A library of mechanism families; a nightly job proposes the next untested one,
runs gates 1–5, logs the verdict. No model calls, no network, runs on the
desktop under cron.

*For:* free, reproducible, ships in a day, cannot hallucinate.
*Against:* **the library is finite and runs out.** The sibling repo's ran out at
16 families and returned 0 of 19. That is the honest expected outcome.

### Option B — LLM generator with a frozen action surface. What Kris described.

Claude proposes mechanisms, reads the ledger to avoid duplicates, writes the
candidate against a harness it cannot modify, and the loop runs continuously.

*For:* the search space is not finite, and it is the shape the 2026 literature
settled on.
*Against, and it is the whole risk:* a model with a broad action surface writes
look-ahead. arXiv 2608.27734's answer is that look-ahead features must be
**structurally inexpressible** — a validated tool registry, not a code review —
and their planted-oracle test showed deflation does **not** catch leakage (a
Sharpe of 34.7 sailed through with DSR 1.00). So Option B needs the registry
first, and their own 100-candidate run certified zero.

### Option C — Point the loop at FEEDS instead of at rules.

The generator's job becomes finding, downloading, caching and screening **new
data**, each tested with the same fixed strategy template.

*For:* it is the only thing that has ever worked here — every real leg in two
repos came from a feed, never a price arrangement. It is also the only option
where quantity does not decay, because each new feed resets the search space.
The nearest target is already on disk: `core/fx_spread.py` has been downloading
**hourly XAUUSD tick files with ask/bid volume** and discarding the two volume
fields on line 106.
*Against:* feed discovery is slower and lumpier than rule generation, and it does
not feel like 24/7 throughput.

**Recommendation, stated as a preference and not a decision: C's target with B's
machinery, A as the fallback if the model budget matters.** And whichever is
picked, the loop must write a pre-registration per candidate *before* it runs —
6.2 says that is worth more than the rest of the design combined.

## 6.6 What must be true before any of it is switched on

1. **Every candidate pre-registered by the generator**, automatically. Arms,
   null, kill criterion, cost bar — all derivable at proposal time.
2. **Gate 0 enforced in code**: `core/screen.py` refuses to run without one.
3. **The generator reads the ledger and refuses duplicates**, including the
   known-dead list in `CLAUDE.md`.
4. **`core/pipeline.py` keeps per-configuration return series.** Without them
   neither PBO nor the effective-trial discount can ever be computed — the
   reason 6.2 had to assume the trial-Sharpe variance rather than measure it
   properly.
5. **A throughput ceiling that is honest.** The cheap screen is seconds, so
   thousands a day are possible; a full walk-forward is hours, so the real
   number is 5–20 a day on 28 cores. The loop must be allowed to kill 95% at the
   screen, or it will be slow no matter how many cores it gets.

---

## What this page does not claim

It does not claim H-027 is good, ready, or worth real money. It does not retract
any specific result — the paired nulls did their job and killed what they should
have. It claims one thing: **the project has been measuring carefully and
searching carelessly, and the second half now has code behind it.**

---

## Sources

* [What survives honest evaluation? Leakage-safe, search-aware assessment of LLM-driven trading strategy discovery](https://arxiv.org/html/2608.27734)
* [Bailey & López de Prado, The Deflated Sharpe Ratio](https://www.davidhbailey.com/dhbpapers/deflated-sharpe.pdf)
* [Bailey, Borwein, López de Prado & Zhu, The Probability of Backtest Overfitting](https://www.davidhbailey.com/dhbpapers/backtest-prob.pdf)
* [cTrader Open API — getting started](https://help.ctrader.com/open-api/)
* [cTrader Open API Python SDK](https://help.ctrader.com/open-api/python-SDK/python-sdk-index/)
* [ctrader-open-api on PyPI](https://pypi.org/project/ctrader_open_api/)
* [Prop firms on cTrader](https://ctrader.com/prop-firms)
* [FunderPro — EA and API policy](https://funderpro.com/blog/ea-friendly-prop-firms-in-2025-why-funderpro-leads-the-way/)
* [Prop firm pass-rate statistics 2026](https://track360.io/blog/prop-trading-industry-statistics-2026)
* [Prop firm statistics — payouts and funded-account data](https://www.quantvps.com/blog/prop-firm-statistics)
* [QuantaAlpha: an evolutionary framework for LLM-driven alpha mining](https://ar5iv.labs.arxiv.org/html/2602.07085)
* [XALPHA: a memory-driven AI quant researcher](https://arxiv.org/pdf/2607.08332)
