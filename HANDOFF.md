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

| ID | Hypothesis | Verdict |
|---|---|---|
| H-001 | Opening Range Breakout | **Rejected** — see `backtests/orb/report.html` |
| H-002 | VWAP, five model families | **Live candidate**, not yet validated — `backtests/vwap/report.html` |

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

**What is NOT yet done on H-002, in priority order:**
1. **Walk-forward.** The single most important missing test. It killed every ORB candidate.
2. Prop-challenge simulation on walk-forward output rather than fitted configs.
3. NautilusTrader cross-check of the VWAP kernel.
4. Silver (XAGUSD) was requested and is still downloading.

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

Run `.venv/bin/python smoke_test.py` first. Then read `RESEARCH_LOG.md` top to bottom — it is
the reasoning behind every verdict, in order. `STRATEGY_LOG.md` is the one-row-per-variation
ledger, pass and fail; the failures are the denominator that makes a winner believable.

Then run the H-002 walk-forward. Everything else is secondary.
