# prop_lab

**Read this file completely before doing anything. It is the entry point for
every AI agent and every human who opens this repository.**

---

## 0. The four files that matter, and the order to read them

| file | what it is | when to read |
|---|---|---|
| **`README.md`** (this) | the mission, the system, the rules of evidence | **first, always** |
| **`HOW_TO_ANSWER.md`** | how to talk to Kris. Overrides your default style. | **before your first reply** |
| **`CLAUDE.md`** | standing rules + the known-dead list | before proposing anything |
| **`NEXT.md`** | the current plan, and what is blocked on Kris | before starting work |

Then, as needed: `SESSION_<date>.md` for why the last session did what it did,
`STRATEGY_LOG.md` for every variation ever tested, `RESEARCH_LOG.md` for the
reasoning behind each verdict.

`HANDOFF.md` and `START_HERE.md` are **historical**. They contain real findings
but their "current state" sections are stale. Do not take a number from them.

---

## 1. What this project is actually for

Kristijonas is building a **trading business**, in this priority order:

1. **Bots he runs live with his own money.** Crypto first — lowest fees, easiest
   to automate.
2. **Bots that reliably pass prop-firm evaluations**, so he can scale to 10–20
   funded accounts.
3. The best performers published as **TradingView indicators**.
4. Eventually **sell** the ones that prove out long term.

**This is not a research exercise and not a portfolio piece.** Everything is
built to be traded. A strategy that looks good in a backtest and cannot be traded
is worth nothing here.

### Why prop firms, and what that actually demands

A prop firm gives you a funded account if you pass an **evaluation** — hit a
profit target without breaching a drawdown limit. You pay a fee per attempt.
Accounts are cheap, so **failing is acceptable; lying to yourself about the
failure rate is not.**

Working targets (no firm signed yet):

| rule | value | note |
|---|---|---|
| profit target | **8%** | two-step firms then ask for a further 5% |
| daily loss limit | **4%** | breach = account dead |
| max loss limit | **8%** | static vs trailing unspecified → **both enforced**, the stricter reading |
| min trading days | 5 | placeholder, confirm with the firm |
| consistency share | 40% | placeholder, confirm with the firm |

**Two facts that dominate every decision:**

* **A coin flip funds an account.** With zero edge, one account passes **40.2%**
  of the time (57.1% if max loss is static rather than trailing). **Pass rate
  alone means almost nothing.** What matters is the lift over that line, and
  keeping the account afterwards.
* **The firm's structure is worth more than any strategy improvement measured in
  this project.** One-step vs two-step is worth ~2.7x on time-to-funded. Raising
  the target from 5% to 8% costs 1.7 days; adding a second phase costs 19.
  **When shopping firms: one-step beats a lower target, and both beat a slightly
  better spread.** Prefer a firm on **cTrader Open API** — a real REST/socket
  API. MT5 is GUI-only and hostile to coded bots.

### The metric that actually decides everything

Not profit factor. Not Sharpe. **Expected days to a funded account**:

```
days = maxDD_in_R / R_per_day × (target / cap)
expected_days = median_days ÷ pass_rate
```

Note what is **absent**: trades per day. Frequency only ever enters through
R per day. **Splitting the same edge across more parallel strategies divides
R per trade by exactly the number you add** — this is why "add more legs" made
a book slower, not faster (H-012).

`expected_days` divides by pass rate on purpose: median-days-to-pass only counts
accounts that passed, which flatters a strategy that blows most of them up.

---

## 2. Who decides

**Kris is the trader and the only judge.** Your job is to research, propose, code
and report. Not to decide.

* Given a hypothesis: research how it is really traded, propose a few concrete
  variations with reasons, then **stop and wait** for him to pick.
* **Never invent an unrelated strategy.** Root every line of code back to the
  hypothesis you were given.
* **State the mechanism first** — why an edge should exist, who is on the other
  side — *before* showing results.
* **Never call a strategy good, ready, or worth real money.** One good backtest
  is a "maybe".
* **Flag weaknesses unprompted**: small samples, IS/OOS gaps, overfitting risk,
  look-ahead.
* **Log every variation, pass or fail.** The failures are the denominator. A
  rejected hypothesis that is invisible is not part of the denominator.

He moves fast and asks for outcomes ("make it 1.6 PF", "pass in a week").
**Give him the number he asked for *and* the number that says whether it is
real.** Do not refuse, and do not quietly comply either — searching harder always
finds the target, so say that plainly, then let the null benchmark and the
walk-forward decide.

---

## 3. The rules of evidence — this is the important section

This project has repeatedly produced a result, published it, and invalidated it
weeks later. Every rule below exists because something went wrong without it.

### 3.1 The gates a strategy must clear

| gate | threshold | why |
|---|---|---|
| profit factor | ≥ 1.20 at realistic cost | the basic bar |
| holds at 2x cost | ≥ 1.20 | costs are an assumption until a firm is signed |
| beats its own null | see 3.2 | proves it is not search noise |
| survives out of sample | same config, unseen data | |
| survives walk-forward | config chosen blind each quarter | **the only number with no hindsight in it** |
| max drawdown | inside the 8% cap at the risk used | else the account dies before it pays |
| days to resolve | the phase constraint | |

**Score a hypothesis on walk-forward output, never on a fitted configuration.**
H-001 was briefly scored on a fitted config and read as "25 expected days"; the
real figure on blind-chosen configs was **7,819**.

### 3.2 Run a null benchmark on any large search

Re-run the identical grid on a **phase-randomised** copy of the market: real
returns, shuffled, so the distribution survives and the sequence does not. Any
edge is destroyed by construction, so whatever maximum the search still finds is
**the score to beat**.

On this dataset shuffled markets produced 86 configurations above PF 1.6, topping
out at 2.412. **A high profit factor on its own proves nothing.**

* Use the **paired** null (`shuffle_market_paired`). The original permuted volume
  independently of returns, destroying a +0.47 correlation and handing every
  participation filter a free win.
* **One shuffle seed is a sample of size one.** Read the null as a distribution.

### 3.3 The method rules learned the hard way

* **Score a filter as a paired lift on the MEDIAN**, never by whether it produced
  a new best. A filter that only raises the maximum has shrunk the sample.
* **Always report PF at 2x and 3x cost.** The best ORB result (1.439) collapsed
  to 0.553 at 2x — its edge was smaller than the spread difference between an ECN
  and a prop firm.
* **Select configurations on 2x-cost profit factor inside the fold**, not on 1x
  with a 2x check afterwards.
* **Check whether a winner transfers.** ORB's best config on each market scored
  0.32–0.82 on the others. That is what fitting one price path looks like.
* **Rank on the fit window only**, then report every number on the window it was
  not chosen on.
* **A walk-forward that passes over a long span can still describe a regime that
  has ended.** Always split a stitched series by recency before believing it.
* **Diversification does not create an edge.** Low correlation between legs is
  worthless when two of them have no current edge.
* **Resting-limit fills are a trap.** Every config that cleared the gate in VWAP
  stage 1 did so on a limit-fill assumption; with honest fills, zero cleared. The
  old repo has a strategy that backtested at PF 3.0 and traded live at 0.7 for
  exactly this reason. **Always run both fill assumptions.**
* **Shift a feed forward one bar before joining it to a trade.** A plain backward
  search returns the bar the trade *enters* on, and that bar has not closed.
* **Trades per day is not a plan.** Report R earned per day.
* **Clean PASS/FAIL only.** Fixed risk per trade, real breaches, no
  budget-shrinking risk manager that sizes down to avoid ever breaching — that
  produces a fake 0% fail rate.

### 3.4 Bugs already found, and the shape of them

Every one inflated results before it was caught. **Assume the next one exists.**

| bug | how it was found |
|---|---|
| three look-aheads in the VWAP kernel — killed every crypto result | reading the code by hand |
| near-zero stop distance manufacturing 25R "winners" | inspecting outliers |
| a cache silently skipping backfill — a "9-year" test ran on one month | checking the date range |
| a trade buffer sized by session count — segfault on stop-and-reverse | crash |
| pandas reading the literal string `"null"` as NaN — emptied a whole null benchmark | disbelief at the result |
| an O(n²) session rescan dominating a sweep | profiling |
| volume-weighted sigma resolving trades on float noise in a **closed** market | porting the kernel to a second engine |
| the kernel deciding and filling on padded weekend bars (21.5% of gold) | chasing that disagreement |

**Notice the pattern: none of these was caught by a test.** They were caught by
cross-checks, code reading, and someone refusing to believe a number.

### 3.5 The current state of testing — be honest about this

| exists | covers |
|---|---|
| `smoke_test.py` | environment only |
| `strategies/ribbon/test_parity.py` | ribbon's indicators only |
| pytest / hypothesis / CI | **none** |

**The VWAP kernel, which produced every board number this project has ever
published, has zero tests.** Fixing this is items 1–3 in `NEXT.md` and it takes
priority over new hypotheses.

**Until it is fixed, the trust rule is:** believe a number only when it has
beaten a paired null **and** been reproduced by a second engine.

---

## 4. How work actually flows

```
1. Research online     mechanics, known variants, edge source, typical win rate
2. vectorbt screen     fast parameter sweep — SCREENING ONLY, never validation
3. NautilusTrader      realistic fills + slippage, the same engine used live
4. Null benchmark      the identical search on phase-randomised data
5. Walk-forward        config re-chosen blind each quarter
6. Log everything      STRATEGY_LOG.md, pass or fail
7. Board               core/board.py::write_board — walk-forward output only
8. Survivors           paper trade -> prop risk rules -> consider live
```

Every hypothesis gets an ID — **H-001, H-002, …** in the order Kris brought it.
The ID tags every row in `STRATEGY_LOG.md`, so any number traces back.

**Adding a hypothesis to the board is one call.** `core/board.py::write_board`
takes a stitched walk-forward trade series and produces the whole record — prop
simulation across twelve risk levels, the mandatory reporting fields, the scoring
inputs. `core/build_scoreboard.py` picks up any `backtests/*/board.json`
automatically and has no per-strategy code in it.

### Mandatory reporting fields — every backtest, no exceptions

Profit factor (gate ≥ 1.20) · trades per day and per week · average hold time ·
win rate · average R multiple · max drawdown · Sharpe · **estimated trading days
to hit target or breach**.

The last one is the phase gate. Check it before getting attached to a Sharpe.

---

## 5. The stack, and the pins that must not move

* **Python 3.12** in `.venv/`
* **NautilusTrader 1.231** — backtest *and* live, same engine. Final validation.
* **vectorbt 0.28.5** — fast idea screening across parameter grids **only**.
* **ccxt** — crypto data and execution. Binance first.
* **numba** — the strategy kernels are hand-written njit loops.
* **MetaTrader5** — the pip package is **Windows-only**; this box is Linux. Not
  set up. The route out is a **cTrader Open API** connector, not an MT5 bridge.

```bash
git clone git@github.com:KristijonasSim/prop_lab.git && cd prop_lab
python3 -m venv .venv
.venv/bin/pip install -r requirements-lock.txt
.venv/bin/python smoke_test.py            # must end with READY
```

**Do not upgrade pandas past 2.x.** NautilusTrader's Cython bar wrangler reads
`df.values`, which pandas 3 makes read-only under copy-on-write. vectorbt 1.x
requires pandas ≥ 3, which is why the 0.28.x line is pinned instead.

---

## 6. Data

* **Crypto**: Binance via ccxt. `core/data.py` downloads 15m and resamples the
  rest. BTCUSDT from 2017-08.
* **FX and metals**: Dukascopy 1-minute candles via `core/fx_data.py`. 2023-09 to
  2026-08. Raw `.bi5` cached **and committed** — the server throttles hard and a
  full pull takes hours, so a clone reproduces everything with no downloads.
  * **Dukascopy pads the closed weekend with synthetic bars** — zero volume,
    O=H=L=C at the last price. **21.5% of XAUUSD is these.** Never decide or fill
    on one. Crypto has none.
* **Feeds** in `data/feeds/` — open interest, taker delta, crowd long/short
  ratio, funding, depth, DVOL. Collected by `core/feed_collector.py` on a
  15-minute cron.
  * **Binance serves ~2 days of history on these endpoints.** The collector
    self-heals gaps under ~41h. **Longer is unrecoverable forever.** This is the
    one part of the project that genuinely needs a server rather than a laptop.

### Assets and timeframes

Crypto first: **BTCUSDT**. Other coins only to re-test an edge that already
showed on BTC. FX/gold: XAUUSD, EURUSD, GBPUSD. Timeframes 15m / 1h / 4h / 1d —
download 15m, resample the rest.

### Costs

Venue undecided, so costs are an assumption. **Report every result at 1x, 2x and
3x.** Binance spot taker 0.10%/side; futures taker 0.05% / maker 0.02%.
Closed-bar signals, fills at next-bar open, no look-ahead.

**Measured, not assumed:** market impact at prop clip sizes is 0.018bps one-way
on BTC — about a hundredth of what this repo assumes. **The 14bps crypto round
trip is fee plus spread, not impact.** XAUUSD measures **1.83bps round trip**
against 3.00 assumed.

---

## 7. Layout

```
core/          shared engine glue — data loaders, metrics, prop rules, board,
               risk ladder, Nautilus setup, scoring
  data.py         Binance via ccxt
  fx_data.py      Dukascopy; build_tf() makes any timeframe from cache
  metrics.py      all mandatory reporting fields
  prop_rules.py   4%/8%/8%, one-step and TWO_STEP, clean PASS/FAIL
  riskladder.py   twelve risk levels, account simulation, expected days
  board.py        write_board() — the single entry point to the board
  scorecard.py    the 0–10 rubric, weights stated at the top of the file
  verify_board.py INDEPENDENT audit — imports nothing from the pipeline
strategies/    one folder per hypothesis: engine (numba kernel), sweep driver,
               one stageN_*.py per question asked, notes.md
backtests/     results, logs, board.json per hypothesis, the scoreboard page
data/          cached bars and feeds (committed on purpose)
live/          execution scripts
```

**Every strategy folder follows the same shape**: a numba kernel for the trade
logic, a sweep driver, a stage script per question, and `notes.md` as the
running record. Read a hypothesis's `notes.md` before touching its code.

### The board

`.venv/bin/python core/build_scoreboard.py` rebuilds `backtests/scoreboard.html`.
Serve it with `python -m http.server` from `backtests/`.

Scoring weights: speed 30, pass rate 18, breach safety 12, drawdown 10,
evidence 20, raw profit 10. Speed is scored on **expected days per funded
account**. An **evidence gate** caps the total at 3.0 when the walk-forward
record is effectively absent, so churn cannot buy the speed weight.

Every board entry has an interactive risk ladder — pick risk per trade and the
score, verdict and headline numbers all recompute. Each level is calculated in
Python and embedded, so the page never scores anything itself.

**`core/verify_board.py` recomputes every headline number from the raw trade
file importing nothing from the pipeline.** Hand it to anyone who wants to audit
this. If it disagrees with the board, one of them is wrong.

---

## 8. Where things stand right now (2026-09-07)

| ID | hypothesis | score | PF | trades/day | expected days | state |
|---|---|---|---|---|---|---|
| H-009 | VWAP gated by crowd | 8.9 | 2.05 | — | 48.7 | **DEAD — scored on a broken kernel** |
| H-017 | VWAP MR / breakout | 7.8 | 2.06 | — | 28.5 | **DEAD — scored on a broken kernel** |
| **H-002** | **VWAP — gold only** | **6.0** | **2.02** | **4.41** | **143.6** (55.9 one-step) | alive |
| **H-016** | **MA ribbon — gold only** | **5.0** | **1.81** | **0.53** | **175.9** | alive |

**A `SUPERSEDED` note on a board record means the number came from a bug, not
from the market. Never quote one.**

* **One market is left: gold.** Every crypto price hypothesis is dead — twelve of
  them, plus the entire VWAP crypto book, which died to a look-ahead fix.
* **The problem is no longer edge. It is speed.** Both survivors beat their nulls
  and both are 3–4x slower than target.
* **The biggest lever is the firm, not research.**

**The standing pattern from both this repo and the previous one: every leg that
ever worked came from a data feed — funding, open interest, taker delta,
long/short ratio — not from a price pattern.** Twelve price hypotheses have died
here. Weigh that before proposing another price geometry.

**Read `CLAUDE.md`'s known-dead list before proposing anything.** Re-proposing a
dead idea without new evidence wastes the one resource this project is short of.
