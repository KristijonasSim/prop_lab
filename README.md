# prop_lab

Research pipeline for finding trading strategies that survive a prop-firm
evaluation. One hypothesis at a time, tested to destruction, pass or fail logged.

**New here (human or agent)? Read [`HANDOFF.md`](HANDOFF.md) first.** It covers the goal,
where the work stands, the findings that transfer between hypotheses, and the mistakes
already made. `CLAUDE.md` holds the standing rules; `RESEARCH_LOG.md` holds the reasoning
behind every verdict.

## Setting up on a new machine

```bash
git clone git@github.com:KristijonasSim/prop_lab.git
cd prop_lab
python3 -m venv .venv
.venv/bin/pip install -r requirements-lock.txt   # exact pins, verified together
.venv/bin/python smoke_test.py                   # should end with READY
```

`smoke_test.py` checks the versions, reaches Binance, loads and resamples bars,
runs a NautilusTrader backtest, and exercises the metrics and prop-rule modules.
MetaTrader5 is expected to fail on Linux — it is a Windows-only package.

**Do not upgrade pandas past 2.x.** NautilusTrader's Cython bar wrangler reads
`df.values`, which pandas 3 makes read-only under copy-on-write. vectorbt 1.x
requires pandas ≥ 3, which is why the 0.28.x line is pinned instead.

## Layout

```
core/         shared engine glue - data loaders, metrics, prop rules, Nautilus setup
strategies/   one folder per hypothesis; ORB is H-001
backtests/    results, logs and the generated report page
data/         cached bars (committed, so a clone needs no downloads)
live/         execution scripts
STRATEGY_LOG.md   one row per variation tested, pass or fail
RESEARCH_LOG.md   the long findings behind each verdict
```

## Data

- **Crypto**: Binance via ccxt. `core/data.py` — downloads 15m, resamples the rest.
  BTCUSDT from 2017-08 (316k bars).
- **FX and metals**: Dukascopy 1-minute candles via `core/fx_data.py`. Eight
  instruments, 2023-09 to 2026-08. Raw `.bi5` files are cached in
  `data/dukascopy_raw/` and committed, so nothing needs re-downloading — the
  server throttles hard and a full pull takes hours.
  `core/fx_data.build_tf(sym, "5min")` rebuilds any timeframe from that cache in
  about a minute; 5m/15m/30m/1h/4h are committed as parquet so a clone needs no
  rebuild either.

## Hypotheses

| ID | Name | Verdict | Where |
|---|---|---|---|
| H-001 | Opening Range Breakout | **Rejected** | `strategies/orb/`, `backtests/orb/report.html` |
| H-002 | VWAP (5 model families) | **Live candidate**, not yet walk-forwarded | `strategies/vwap/`, `backtests/vwap/report.html` |

H-001 was swept across 8 instruments and 65,280 configurations, in and out of
sample, walk-forward, and through a prop-challenge simulation. Open
`backtests/orb/report.html` in a browser for the full result board.

## Regenerating the report

```bash
.venv/bin/python strategies/orb/build_report.py    # rebuilds backtests/orb/report.html
.venv/bin/python strategies/vwap/build_report.py   # rebuilds backtests/vwap/report.html
```
