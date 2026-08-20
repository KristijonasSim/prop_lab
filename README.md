# prop_lab

A research pipeline for testing many trading hypotheses honestly, and finding
the few that might survive a prop-firm evaluation.

The premise: testing lots of ideas is fine — testing them *sloppily* is not.
Everything here exists to stop a lucky result from looking like an edge.

## Ownership boundary

| Area | Owner | Rule |
|---|---|---|
| `proplab/core/*` | **you** | P&L, fills, fees, slippage, sizing math, prop rules. Marked `OWNER: kris`. Claude never edits these. |
| `proplab/strategy/library/*` | Claude writes, you approve | entry rules, exit rules, sizing choices only |
| `proplab/config.py` | you | costs, prop-firm parameters |
| everything else | shared | plumbing: data, DB, dashboard, checks |

Every run records a `core_hash`. If the core changes, older runs are no longer
comparable, and you can see that in the database.

## Install

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
```

## Workflow (per hypothesis)

```
1. hypothesis given          ->  logged as `queued`
2. research + variations     ->  `researching` / `ready_to_code`
3. you pick variations       ->  `coding`
4. code written into template->  proplab/strategy/library/<slug>.py
5. automated checks          ->  compliance, static lookahead scan, scramble test
6. backtest + prop rules     ->  `testing` -> `tested`
7. read results together     ->  `rejected` or `passed`
8. logged permanently        ->  visible in the dashboard, pass or fail
```

Statuses: `queued, researching, ready_to_code, coding, testing, tested, rejected, passed`

## Commands

```bash
# data (downloads one base timeframe; 1h/4h/1d are resampled from it)
python -m proplab.cli fetch --symbol BTCUSDT --timeframe 15m --start 2020-01-01

# strategies
python -m proplab.cli list
python -m proplab.cli run --strategy <slug> --timeframe 1h --log --variation <var-slug>

# same run, also reported at 2x and 3x assumed costs
python -m proplab.cli run --strategy <slug> --timeframe 4h --cost-sweep

# the run that actually counts: tuned on IS, judged on OOS
python -m proplab.cli oos --strategy <slug> --split-at 2024-01-01 --log

# tracking
python -m proplab.cli status
python -m proplab.cli failed
python -m proplab.cli dashboard
```

## Execution model (deliberately pessimistic)

- `on_bar` is called **after** a bar closes; the strategy sees bars `0..i` only.
- Orders fill at the **open of the next bar**, plus slippage. No same-bar-close entries.
- Gapping through a stop fills at the **open**, not the stop price.
- If one bar contains both the stop and the target, the **stop** is assumed first.
- Fees, slippage and 8-hourly perp funding are charged on every position.
- Position size is computed at fill time from the real fill price, so `risk_pct`
  is exact rather than approximate.

## How lookahead is prevented

1. **Structural** — a strategy only sees `Context`, whose every accessor slices
   at the current bar. Future data is unreachable, not merely discouraged.
2. **Multi-timeframe** — a 4h bar becomes visible only once its close time has
   passed. Partial higher-timeframe bars are dropped entirely.
3. **Static scan** — flags private-attribute access, negative shifts, self-loaded
   data, network calls, wall-clock time.
4. **Future-scramble test** — the backtest is re-run with all data after a cutoff
   replaced by noise. Every pre-cutoff decision must be bit-identical. A
   strategy that peeks fails this, and `tests/test_checks.py` proves the
   detector catches a deliberate cheater.

## Prop-firm rules

Checked inside every run, not bolted on afterwards. Hard breaches (daily loss,
static max DD, trailing DD) kill the account at a specific timestamp — after
that point the equity curve is reported as fiction. Qualification rules (profit
target, minimum trading days, consistency, no martingale sizing) can still be
met later.

Current targets (`proplab/config.py::PropFirmRules`), set before a firm was
chosen:

| rule | value |
|---|---|
| daily loss limit | 4% |
| max loss, static (from start) | 8% |
| max loss, trailing (from peak) | 8% |
| profit target | 8% |
| minimum trading days | 5 *(not specified — placeholder)* |
| consistency, max single-day share of profit | 40% *(not specified — placeholder)* |

"Max loss" was not specified as static or trailing, so **both** are enforced at
8%. That is the stricter reading: anything surviving it passes either style of
firm. Once a firm is picked, relax whichever rule does not apply and re-run —
results can only improve.

## Costs

The venue is undecided (Binance vs a prop platform on MT4 / Match-Trader /
cTrader, and FX rather than crypto would change the data source entirely).
Defaults model Binance USDT-M perps: 4.5bps taker, 2bps slippage, 5bps stop
slippage, 8-hourly funding.

Because that is an assumption rather than a fact, `--cost-sweep` re-runs any
strategy at 2x and 3x costs. A strategy that only works at 1x is a bet on a fee
schedule, not an edge.

## Dashboard

Three levels of drill-down:

1. **Hypothesis library** — every idea ever tried, with how many strategies came
   out of it, how many were rejected, best out-of-sample Sharpe, prop passes.
2. **Open a hypothesis** — the idea, the mechanism, the research notes, then
   every strategy built from it side by side (IS vs OOS Sharpe, OOS return,
   expectancy, trades, max DD, prop pass/fail), each expandable for its
   rationale, exact rules, params, verdict and code.
3. **Open a variation** — all its runs, with equity curve against the drawdown
   floor and breach marker, per-rule prop-firm results, automated checks, full
   metrics and the trade list.

## Current research phase

Only hypotheses that can **resolve within roughly 1-2 weeks of active trading**
are being built right now: high trade frequency, short holds (intraday to a few
days) - ORB, VWAP mean reversion, breakout-retest and similar.

This is a phase constraint, not a permanent one. Longer-holding ideas (trend
following, carry) are still researched and logged as future candidates; they are
just not built as a priority. The trend-following hypothesis was rejected partly
on this basis - its estimated time to resolve was ~2,374 trading days.

## Reported on every backtest

Beyond the usual return/Sharpe/drawdown:

| field | why |
|---|---|
| profit factor | gross win / gross loss |
| trades per day and per week | does it generate enough opportunities |
| average hold time | intraday, days, or weeks |
| win rate | with average R, describes the shape of the edge |
| average R multiple | expectancy per unit risked |
| **estimated days to resolution** | trading days until the profit target is hit or the drawdown limit is breached |

The last one (`metrics.resolution`) models daily P&L as a random walk with drift
between two barriers - the profit target above, the drawdown limit below - and
reports the probability of reaching the target first plus the expected days to
either. Total return says nothing about how long an evaluation takes; a strategy
needing two years to clear 8% is useless however good its Sharpe. Validated
against a brute-force Monte Carlo simulation in `tests/test_resolution.py`.

## The one-look rule on out-of-sample data

Out-of-sample data is a one-shot resource: look at it twice and the second look
is tuning, whether or not it feels like it. This is enforced by the tooling, not
by memory.

- `run --split oos` refuses to run if that variation already has a logged OOS
  run, and names the run that spent it.
- An OOS run is always logged. An unrecorded look is a free peek.
- Changed the strategy? Make it a **new variation slug** — that is what
  variations are for, and it keeps the trial count honest.
- `--burn-oos "<reason>"` overrides, and records the reason permanently.
- `python -m proplab.cli oos-ledger` shows who has spent their look.

In-sample tuning stays unlimited; that is what in-sample is for.

## Guarding against false positives

Every run is logged, pass or fail. That count is the denominator:

- `expected_max_sharpe(n_trials, years)` — the Sharpe pure noise would produce
  across that many tries.
- `deflated_sharpe(...)` — probability the result beats that noise benchmark.
- IS/OOS comparison with an explicit Sharpe-decay figure.
- Bonferroni-adjusted t-tests on per-trade R multiples.

A single good backtest is a "maybe", never a "found it".

## Timeframes

15m is downloaded; 1h, 4h and 1d are resampled from it, so all four agree
bar-for-bar. Days are anchored to 00:00 UTC as exactly 24h from the epoch —
crypto has no calendar close, and calendar-day resampling would silently move
the boundaries.

## Layout

```
proplab/
  config.py          costs, prop-firm rules, backtest settings
  runner.py          load -> check -> run -> score -> prop-check -> log
  cli.py
  core/              OWNER-FIXED: engine, metrics, prop_rules, context, types
  data/              binance downloader, loader, resampling, synthetic
  strategy/
    base.py          the template contract
    TEMPLATE.py      copy this per variation
    library/         one file per variation
  checks/            lookahead + template compliance
  db/                schema.sql, store.py
  research/          multiple-testing corrections
dashboard/app.py     Streamlit (hypothesis library -> hypothesis -> variation runs)
tests/               engine arithmetic, prop rules, lookahead detectors
proplab.db           the permanent record
```
