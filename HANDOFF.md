# HANDOFF — read this before doing anything

You are picking up a live research project. This file tells you what it is for, what has
already been settled, and the mistakes that have already been made so you do not repeat
them. `CLAUDE.md` holds the standing rules; this file holds the state.

---

## 1. What this project is for

Kristijonas wants **working trading bots he can run with real money**, in this order:

1. Bots he can run live with his own money. Crypto first — lowest fees, easiest to automate.
2. Bots that reliably pass **prop-firm evaluations**, so he can scale to 10-20 funded accounts.
3. The best performers published as TradingView indicators.
4. Eventually sell the ones that prove out long term.

This is a real business, not a demo. Everything is built to be traded, not to look good in
a backtest.

**Kris is the trader and the only judge.** Your job is to research, propose, code and
report — not to decide. Never call a strategy good, ready, or worth real money. One good
backtest is a "maybe", never a "found it". Flag weaknesses unprompted.

**Answer in key points.** Short bullets, plain words, tables when numbers are the answer,
always include trades/day. A long reply is a bug. Detail goes in the logs, never in chat.

---

## 2. The gates a strategy has to clear

| Gate | Threshold | Why |
|---|---|---|
| Profit factor | >= 1.20 at realistic cost | the basic bar |
| Holds at 2x cost | >= 1.20 | costs are an assumption until a firm is picked |
| Beats its own null | see §5 | proves it is not just search noise |
| Survives out of sample | same config, unseen data | |
| Survives walk-forward | chosen blind each quarter | the only number with no hindsight in it |
| Max drawdown | inside the 8% cap at the risk used | else the account dies before it pays |
| **Days to resolve** | **under ~14** | the current phase constraint |

Prop targets (no firm chosen yet): **4% daily loss, 8% max loss, 8% profit target.**
"Max loss" was not specified as static or trailing, so both are enforced at 8%.
`min_trading_days` (5) and the consistency share (40%) are placeholders — confirm them when
a firm is picked. At firm selection, **prefer one on cTrader Open API** — a real REST/socket
API, far better for coded bots than MT5's GUI-only access.

**Clean PASS/FAIL only.** Fixed risk per trade, real breaches, no budget-shrinking risk
manager that sizes down to avoid ever breaching — that produces a fake 0% fail rate.

---

## 3. Where things stand

Each idea gets an ID — **H-001**, **H-002** and so on, in the order Kris brought them.
The ID tags every row in `STRATEGY_LOG.md`, so any number can be traced back to the
hypothesis it came from. Folders are named after the strategy, not the ID.

| ID | Hypothesis | Verdict |
|---|---|---|
| H-001 | Opening Range Breakout | **Rejected** — see `backtests/orb/report.html` |
| H-002 | VWAP, five model families | **Walk-forward done.** Fails as a family; one leg (BTC 4h) survives everything but the phase gate — `backtests/vwap/report.html` |

### H-001 ORB — rejected, and why it matters

65,280 configurations across 8 instruments, plus walk-forward, a prop simulation and a
NautilusTrader cross-check. Zero cleared PF 1.20 at 2x cost anywhere. Median PF was below
1.0 even with fees set to zero, so there was no edge for cheaper execution to rescue.

**Scope of the rejection**: single-symbol crypto, FX and metals. The published ORB edge is a
US-equity *cross-section* — top 20 of 7,000 stocks by opening relative volume, rebuilt daily.
No single-symbol sweep can reproduce that, so it remains untested rather than disproved.

### H-002 VWAP — where the work currently is

Best result so far, and the first thing in the project to survive a cost stress: 805 configs
clear PF 1.20 at 1x and **101 still clear at 2x**. Every challenge profile improved on the
test year it was not chosen on — the opposite of the ORB signature.

Multi-market books work: legs are near-independent (mean daily-R correlation **0.023**), so
one market to four cuts median time-to-pass from 52 days to 28, lifts CAGR from 25% to 44%,
**at a smaller drawdown**.

### H-002 walk-forward — done 2026-09-01, and it changes the picture

Quarterly folds, 12m train / 3m test, config **and filter** re-chosen blind every
fold. 44 market x timeframe combinations x 4 selection rules (two trade-count
floors x single-best vs top-ten) = 176 stitched out-of-sample series.

**As a family H-002 fails: median stitched PF 0.909, only 36.4% above breakeven.**
Against a phase-randomised null: 41/176 real cells clear 1.20 vs 6 shuffled, and 4
combinations clear under all four selection rules vs 1 shuffled. So the survivors
are not pure search noise — but the shuffled *maximum* was 2.496, higher than the
real maximum of 1.832, so a headline walk-forward PF still proves nothing alone.

Two of the four survivors lose money post-2024 (BTC 30m -34R, BTC 1h -48R) and are
dropped. Two hold:

| leg | quarters | PF | PF 2x | q>1 | trades/day | days to target |
|---|---|---|---|---|---|---|
| BTCUSDT 4h | 30 | 1.502 | 1.239 | 23/30 | 0.33 | 121.7 |
| XAUUSD 5m | 7 | 1.669 | 1.466 | 6/7 | 3.93 | 46.6 |
| both, equal weight, 2024-09+ | — | 1.435 | 1.218 | — | 0.65 | 128 |

**BTC 4h is the strongest thing this project has produced**: positive in every
calendar year 2019-2026 (1.099-2.091), 895 trades, 97th percentile of the null,
its own shuffled twin scores 0.80-0.85. The fold chose the `rvol>1.5` filter in 22
of 30 folds with nothing forcing it.

It still fails two gates. **Speed**: 119-201 days to reach 8% against a ~14-day
phase constraint. **Drawdown**: BTC 4h alone draws -28.9% at 0.75% risk, three and
a half times the cap; only pairing it with gold brings that to -5.6%.

**What is NOT yet done on H-002:**
1. NautilusTrader cross-check of the VWAP kernel.
2. Silver (XAGUSD) — finished downloading, `data/XAGUSD_dukascopy_15m.parquet`,
   81,984 bars 2023-09 to 2026-08. Not yet run through any stage.
3. The report page (`build_report.py`) has not been regenerated since stage 5, so
   it does not show any walk-forward result.

---

## 4. Findings that transfer — do not re-derive these

Empirically established on this data. Treat as settled unless you have new evidence.

- **Breakeven stops destroy edge.** Paired test, 5,760 configs: -0.078 median PF at 0.5R,
  -0.015 at 1.0R; only 5-8% of configs improved. Never add one by default.
- **Retest entries lose.** -0.029 median PF at every setting. This is the most commonly
  recommended breakout improvement on the internet and it is negative here.
- **The NY cash open (13:30 UTC, 14:30 in EST) is the only session anchor that carries
  anything.** Best on gold, EURUSD and GBPUSD. Asia is the worst region; the NY close is the
  worst single anchor. Test :30 anchors, not just :00.
- **Relative-volume / participation filters are the only filter family that lifts a median.**
  Consistent with the older `~/trading-bots` repo: every leg that ever worked there came from
  a data feed, not a price pattern.
- **A walk-forward that passes over a long span can still describe a regime that
  has ended.** BTC 30m and 1h both cleared PF 1.20 over thirty quarters and both
  lose money since 2024-09; the whole record was pre-2024. Always split a stitched
  series by recency before believing it.
- **Diversification does not create an edge.** Stage 5's four-leg book (leg
  correlation 0.023) fell to 1.018-1.222 when rebuilt from walk-forward trades,
  against 1.435 for the two legs that actually hold. Low correlation between legs
  is worthless when two of them have no current edge.
- **Resting-limit fills are a trap.** Every one of the 119 configs that cleared the gate in
  VWAP stage 1 did so on a limit-fill assumption; with honest fills, zero cleared and BTC's
  best fell from 2.932 to 0.876. The old repo has a strategy that backtested at PF 3.0 and
  traded live at 0.7 for exactly this reason. **Always run both fill assumptions.**

---

## 5. Method rules that were learned the hard way

**Score a filter as a paired lift on the MEDIAN**, never by whether it produced a new best.
Run the identical config family with the filter off and on and compare distributions. A
filter that only raises the maximum has shrunk the sample, not found signal.

**Always report PF at 2x and 3x cost.** The best ORB result (GBPUSD 1.439) collapsed to
0.553 at 2x — its edge was smaller than the spread difference between an ECN and a prop firm.

**Run a null benchmark on any large search.** Re-run the identical grid on a phase-randomised
copy of the market: real returns, shuffled, so the distribution survives and the sequence
does not. Any edge is destroyed by construction, so whatever maximum the search still finds
is the score to beat. On this dataset the shuffled markets produced **86 configurations above
PF 1.6, topping out at 2.412**. A high profit factor on its own proves nothing.

**Check whether a winner transfers.** ORB's best config on each market scored 0.32-0.82 on the
others, and zero of 8,160 configs cleared 1.20 on more than one market. That is what fitting
one price path looks like.

**Rank candidates on the fit window only**, then report every number on the window they were
not chosen on.

**Kris will sometimes ask for a target number** ("it must reach 1.6 PF"). Searching harder
always finds it. Say so plainly, then do the work and let the null benchmark and the
walk-forward decide whether it is real. Do not refuse, and do not quietly comply either.

---

## 6. The code

```
core/          data loaders, metrics, prop rules, NautilusTrader setup — shared
  data.py        Binance via ccxt; 15m downloaded, everything else resampled
  fx_data.py     Dukascopy 1-minute candles; build_tf() makes any timeframe from cache
  metrics.py     all mandatory reporting fields incl. resolution_estimate (the phase gate)
  prop_rules.py  4%/8%/8%, clean PASS/FAIL, no size shrinking
strategies/orb/   H-001: engine + 13 stage scripts + report builder
strategies/vwap/  H-002: engine (5 families, both fill modes) + 5 stages + report builder
backtests/        every result CSV/parquet, run logs, and the generated report pages
```

Both hypotheses follow the same shape: a numba kernel for the trade logic, a sweep driver, a
stage script per question, and a `build_report.py` that regenerates the HTML page from the
CSVs. Regenerate a page with `.venv/bin/python strategies/<name>/build_report.py`.

**Environment**: `pip install -r requirements-lock.txt`, then `.venv/bin/python smoke_test.py`
must end with READY. **Do not upgrade pandas past 2.x** — NautilusTrader's Cython bar wrangler
reads `df.values`, which pandas 3 makes read-only under copy-on-write.

**Data is committed on purpose.** Dukascopy throttles hard; a full pull takes hours. The raw
`.bi5` cache is in the repo so a clone reproduces everything with no downloads.

---

## 7. Bugs already found and fixed — the shape of them is instructive

1. **Near-zero stop distance** on fade trades divided by ~0 and manufactured 25R "winners".
   Fixed with a `min_risk_bps` floor. Any strategy that places a stop at a level price may
   have crossed needs this guard.
2. **A cache that silently skipped backfill** — an earlier `since` was ignored, so a
   "9-year" test ran on one month. Always verify the date range you actually got.
3. **A trade buffer sized by session count** segfaulted on stop-and-reverse, which can flip
   many times per session. Size by bar count.
4. **pandas reads the literal string "null" as NaN**, which silently emptied an entire null
   benchmark. The column is now written as "shuffled".
5. **An O(n^2) session rescan** dominated a sweep until it was made incremental.

Every one of these inflated results before it was caught. Assume the next one exists.

---

## 8. If you are picking this up cold

```bash
git clone git@github.com:KristijonasSim/prop_lab.git && cd prop_lab
python3 -m venv .venv
.venv/bin/pip install -r requirements-lock.txt
.venv/bin/python smoke_test.py            # must end with READY
```

Then read `RESEARCH_LOG.md` top to bottom — it is the reasoning behind every verdict, in
order. `STRATEGY_LOG.md` is the one-row-per-variation ledger, pass and fail; the failures
are the denominator that makes a winner believable.

Published result pages (private artifacts, Kris can share them):
- **Strategy board — start here** — <https://claude.ai/code/artifact/f9ac29b6-5251-4510-81d9-ef3d5b7dd3d3>
- H-001 ORB — <https://claude.ai/code/artifact/a38e8a90-fc1a-4133-afc1-da3a826ae370>
- H-002 VWAP — <https://claude.ai/code/artifact/cb748842-7d3b-45f7-9d69-827e00ba82f4>

The board is the one Kris reads. It scores every hypothesis 0-10 on the same
rubric and shows pass rate and days-to-a-funded-account first; the per-hypothesis
pages hold the workings. **When a new hypothesis gets a walk-forward, add a
`collect_<name>()` to `core/build_scoreboard.py`** and it joins the board.

Scoring lives in `core/scorecard.py`, weights stated at the top of the file:
speed 30, pass rate 18, breach safety 12, drawdown 10, evidence 20, raw profit 10.
Two design points worth keeping: speed is scored on **expected days per funded
account** (median days ÷ pass rate), because median-days-to-pass only counts
accounts that passed and flatters a strategy that blows most of them up; and an
**evidence gate** caps the total at 3.0 when the walk-forward record is
effectively absent, so churn cannot buy the speed weight. Kris set the priority
(everything counts, speed heaviest) — the exact curves are Claude's and he can
change any of them.

Rebuild the board with `.venv/bin/python core/build_scoreboard.py`.

**Every hypothesis on the board has an interactive risk ladder**: the trader picks
risk per trade and the score, verdict and headline numbers all re-compute. Each
level's scorecard is calculated in Python and embedded, so the page never scores
anything itself and cannot drift from `core/scorecard.py`.

**Adding a hypothesis is one call.** `core/board.py::write_board` takes a stitched
walk-forward trade series (R multiples, entry and exit timestamps, optionally the
2x-cost series) and produces the whole board record — prop simulation across
`core/riskladder.py`'s twelve risk levels, the mandatory reporting fields, and the
scoring inputs. `build_scoreboard.py` then picks up any `backtests/*/board.json`
automatically; it has no per-strategy code in it. `strategies/orb/stage14_board.py`
is the shortest worked example.

**Score a hypothesis on walk-forward output, never on a fitted configuration.**
H-001 was briefly scored on a fitted config while H-002 was scored on walk-forward,
which flattered ORB badly — it read as "25 expected days to a funded account" when
the real figure on blind-chosen configs is 7,819.

Rebuild either locally with `.venv/bin/python strategies/<orb|vwap>/build_report.py`.

### STATE AT HANDOFF — 2026-09-01 evening

Read this first; it supersedes the older "next job" section below.

**The board is the entry point**: <https://claude.ai/code/artifact/f9ac29b6-5251-4510-81d9-ef3d5b7dd3d3>
Rebuild it with `.venv/bin/python core/build_scoreboard.py`. It reads whatever
`backtests/*/board.json` files exist and has no per-strategy code in it.

| ID | hypothesis | score | state |
|---|---|---|---|
| H-002 | VWAP | **8.5** | the only survivor. Beats a paired-shuffle null 6 combos to 0 |
| H-003 | EMA x VWAP cross | 4.0 | rejected, loses to its own null |
| H-005 | Liquidity sweep fade | 4.0 | rejected, null clears the gate 19,062 times to 1,702 |
| H-001 | ORB | 2.4 | rejected |
| H-004 | Funding fade | — | tested, rejected, code deleted at Kris's request. Finding in `RESEARCH_LOG.md` |

**Work in flight when this was written:**

1. **`stage10_universe.py --shuffled-paired` was still running.** Stage 10 widened
   the H-002 universe to twelve markets (added ETHUSDT, SOLUSDT, XAGUSD) and found
   **8 combinations clearing PF 1.20 at 2x cost under all four selection rules**,
   up from 6 — and **ETH is stronger than BTC** (ETHUSDT 1h worst-of-four 1.825 at
   2x; best cell PF 2.835, 2.232 at 2x, 24 of 26 quarters positive). That result is
   NOT yet on the board because its null had not finished. **Finish that run, check
   the margin, then rebuild the board.** Do not put stage 10 on the board until the
   null is in — comparing a new result against an old null is the exact mistake
   this repo has already made once.
2. **`core/feed_collector.py` is running** and should stay running. It records open
   interest and taker buy/sell delta, which Binance only serves for ~2 days. There
   is no way to recover missed hours. Cron line:
   `*/15 * * * * .venv/bin/python core/feed_collector.py --once >> data/feeds/collector.log 2>&1`
   Around 2026-10 there will be enough to test an order-flow hypothesis (H-006).
3. **Cross-sectional crypto ranking was requested and not started.** Note the
   research argues against it: time-series momentum beats cross-sectional in
   crypto, and cross-sectional carries ~55% drawdowns because coins are too
   correlated. Test it anyway — Kris asked — but expect it to fail.

**Two firm-level findings that change the goalposts:**

* Prop firms with **no time limit** are now standard (FundedNext, Crypto Fund
  Trader, FundingPips, Bitfunded). The ~14-day phase constraint in `CLAUDE.md` is
  self-imposed, not a firm rule. H-002 at ~50 days with 85% pass and 0% breach is
  a viable business if the firm has no deadline.
* Most are **two-step** (8% then 5%), while `core/prop_rules.py` models one step
  at 8%. That needs updating once a firm is chosen.

**Blocker for going live**: two of H-002's legs are XAUUSD and this box has no
working MT5 bridge, so `live/paper_trade.py` runs gold in signal-only mode off
cached data. Half the book cannot be paper-traded until that bridge exists.

**Method rules added today — do not regress on these:**

* **Use the paired null** (`shuffle_market_paired`). The original null permuted
  volume independently of returns, destroying a +0.47 correlation and handing
  every participation filter a free win.
* **Select configurations on 2x-cost profit factor inside the fold**, not on 1x
  with a 2x check afterwards. Selecting on 1x let four legs into the book that
  collapse at 2x.
* **One shuffle seed is a sample of size one.** Read the null as a distribution.
* **Trades per day is not a plan.** A "top 10 configs x 6 legs" book is 60
  parallel strategies. Report R earned per day, which is what sets time to pass:
  `days = maxDD_in_R / R_per_day x (target / cap)`.
* **Everything goes on the board as soon as it exists, pass or fail.** A rejected
  hypothesis that is invisible is not part of the denominator.

`core/verify_board.py` recomputes every headline number from the raw trade file
importing nothing from the pipeline — hand it to anyone who wants to audit this.

---

### The next job, concretely (rewritten 2026-09-01 — the walk-forward is done)

The walk-forward, the null benchmark on it, and the prop simulation on its output
all exist now (`strategies/vwap/stage6_walkforward.py`, `stage7_wf_analysis.py`;
results in `backtests/vwap/stage6_*` and `stage7_*`). Re-run either with
`.venv/bin/python strategies/vwap/stage6_walkforward.py [--shuffled]`, about four
minutes each on 14 workers.

**Latest H-002 state:** the best board candidate is now the stage 9 2x-cost
selector: BTCUSDT 30m + BTCUSDT 4h + XAUUSD 30m + XAUUSD 5m, one configuration
per leg, equal weight, common 2024-09+ window. It scores PF 1.646, PF 1.313 at
2x cost, 1.58 trades/day, 0.146 R/day, -7.6% max drawdown at 1.00% risk, 85.8%
pass rate, 45 median days and 52.5 expected days to a funded account. Board score
8.5. The paired-volume null for the same 2x selector produced 0 robust survivors.

This is better than the older two-leg candidate (61 expected days) but still far
too slow for the current phase. The genuine options are

1. **Chase frequency on the BTC 4h mechanic.** It is the only thing with a real
   long record, but stage 9 showed BTC 30m can join the book when configs are
   chosen by 2x-cost train PF. Getting to 14 expected days still needs roughly
   another 3.75x R/day at the same drawdown, so this is not a small tweak.
2. **Accept a slower challenge.** The four-leg book passes 85.8% of the time with
   a 0% breach rate at a 45-day median / 52.5-day expectation. That breaks the
   ~14-day phase constraint but is a real, tested result; whether the phase
   constraint or the result gives way is Kris's call, not yours.
3. **Log H-002 as a keeper and move to the next hypothesis.** The standing pattern
   from both repos — every leg that ever worked came from a data feed, not a price
   pattern — argues for spending the next block on funding, open interest or taker
   delta rather than another price geometry.

Whatever he picks, two pieces of unfinished work stand regardless: the
NautilusTrader cross-check of the VWAP kernel (`core/nautilus_setup.py` and
`strategies/orb/stage6_nautilus.py` show the pattern), and the VWAP report page:
`build_report.py` predates stages 6-9, so the published VWAP page still shows
only the fitted numbers. XAGUSD is no longer outstanding for H-002; it was tested
in stage 9 and did not produce a robust leg.

### What Kris will ask you

He moves fast and asks for outcomes ("make it 1.6 PF", "pass in a week"). Give him the
number he asked for **and** the number that says whether it is real — the null benchmark and
the walk-forward exist for exactly that. He responds well to being shown the arithmetic
before the simulation; he pushed back correctly on a result once and was right to.
