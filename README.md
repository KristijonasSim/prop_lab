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
# data (downloads one base timeframe; 1h/4h are resampled from it)
python -m proplab.cli fetch --symbol BTCUSDT --timeframe 15m --start 2020-01-01

# strategies
python -m proplab.cli list
python -m proplab.cli run --strategy <slug> --timeframe 1h --log --variation <var-slug>

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

Defaults are in `proplab/config.py::PropFirmRules`. **Change them to match the
actual firm before trusting any pass/fail.**

## Guarding against false positives

Every run is logged, pass or fail. That count is the denominator:

- `expected_max_sharpe(n_trials, years)` — the Sharpe pure noise would produce
  across that many tries.
- `deflated_sharpe(...)` — probability the result beats that noise benchmark.
- IS/OOS comparison with an explicit Sharpe-decay figure.
- Bonferroni-adjusted t-tests on per-trade R multiples.

A single good backtest is a "maybe", never a "found it".

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
dashboard/app.py     Streamlit
tests/               engine arithmetic, prop rules, lookahead detectors
proplab.db           the permanent record
```
