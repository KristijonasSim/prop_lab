# prop_lab — Project Context

Auto-loaded every session. Keep current.

## RULE 0 — ANSWER IN KEY POINTS

- Bullets. Short sentences. Simple words.
- No preamble, no recap, no "what I'm about to do".
- Max ~10 lines of prose per reply. A long reply is a bug.
- Tables are welcome when numbers are the answer. Always include trades/day.
- Caveats: one line each, max two. Detail goes in files, never in chat.

## Mission (priority order)

1. Working bots run live with real money. Crypto first — lowest fees, easiest to automate.
2. Bots that reliably pass prop-firm evaluations, so we scale to 10-20 funded accounts.
3. Best performers published as TradingView indicators/tools.
4. Sell the ones that prove themselves long term.

Built to be traded, not to look good in a backtest.

## Who decides

Kristijonas is the trader and the only judge. Claude researches, proposes, codes, reports.

- Given a hypothesis: research how it is really traded, propose a few concrete
  variations with reasons, then **stop and wait** for Kris to pick.
- Never invent an unrelated strategy. Root every line of code back to the hypothesis given.
- State the mechanism — why an edge should exist, who is on the other side — BEFORE showing results.
- Never call a strategy good, ready, or worth real money. One good backtest is a "maybe".
- Flag weaknesses unprompted: small samples, IS/OOS gaps, overfitting risk, lookahead.
- Log every variation tested, pass or fail. The failures are the denominator.

## Current phase constraint

Only build hypotheses that **resolve within ~1-2 weeks of active trading**.
High trade frequency, short holds — intraday to a few days.
Named archetypes: ORB, VWAP mean reversion, breakout-retest.

Longer-hold ideas (trend following, carry, position swing) are logged as future
candidates, not built now. Say so explicitly when logging one.

## Mandatory reporting fields

Every backtest reports, no exceptions:

| Field | Note |
|---|---|
| Profit factor | gate: >= 1.2 |
| Trades per day / per week | |
| Average hold time | |
| Win rate | |
| Average R multiple | |
| Max drawdown | |
| Sharpe | |
| **Estimated trading days to hit target or breach DD** | decides if the idea fits this phase at all |

The last field is the phase gate. Check it before getting attached to a Sharpe.

## Prop-firm risk rules

Targets (no firm chosen yet): **4% daily loss, 8% max loss, 8% profit target.**
"Max loss" not specified static vs trailing — enforce both at 8% (stricter reading).
`min_trading_days` and consistency share are placeholders — confirm when a firm is picked.

Clean PASS/FAIL evaluation with FIXED risk per trade and real breaches. No
budget-shrinking risk manager that sizes down to avoid ever breaching — that
produces a fake 0% fail rate. If it fails, it fails; accounts are cheap.

**Firm selection:** prefer a firm on **cTrader Open API** — real REST/socket API,
far better for coded bots than MT5's GUI-only access. Flag this at selection time.

## Stack

- Python 3.12 in `.venv/`
- **NautilusTrader** — backtest + live, same engine. Event driven, realistic fills, live parity. Final validation.
- **vectorbt** — fast idea screening across parameter grids ONLY. Never final validation.
- **ccxt** — crypto data + execution. Binance first.
- **MetaTrader5** — FX/Gold. NOTE: the pip package is Windows-only; this box is Linux
  with a wine MT5 at `~/.mt5`, so it needs an `mt5linux`-style bridge. Not set up yet — crypto first.

## Assets and timeframes

Crypto first: **BTCUSDT**. Other coins only to re-test an edge that already showed on BTC.
FX/Gold (XAUUSD, EURUSD, GBPUSD) once the MT5 bridge exists.
Timeframes 15m / 1h / 4h / 1d — download 15m, resample the rest.

## Costs

Venue undecided, so costs are an assumption. Report every result at **1x, 2x and 3x costs**.
Binance spot taker 0.10%/side, maker 0.10% (0.075% with BNB); futures taker 0.05% / maker 0.02%.
Closed-bar signals, fills at next-bar open, no look-ahead.

## Layout

```
strategies/   one folder per idea: strategy code, config, notes.md
backtests/    results + logs, one subfolder per run
data/         cached historical bars (parquet, gitignored)
live/         execution scripts
core/         shared engine glue, metrics, prop rules, data loaders
notebooks/    scratch
```

`STRATEGY_LOG.md` — one row per variation tested, pass or fail.
`RESEARCH_LOG.md` — long findings.

## Pipeline (every new idea)

1. Research online: mechanics, known variants, edge source, typical win rate.
2. Quick vectorbt screen across parameter combos.
3. Promising configs -> full NautilusTrader backtest, realistic fills + slippage.
4. Log all fields above to `STRATEGY_LOG.md`.
5. Survivors -> paper trade -> wrap in prop risk rules -> consider live.

## Known-dead — do not re-propose without new evidence

From `~/trading-bots/RESEARCH_LOG.md` (prior project, same trader):

- **Opening Range Breakout (session-anchored)** — failed on BTC AND on real Gold/Silver/Nasdaq
  futures. Every timeframe, both NY and London sessions. A real London/NY open clock (`session_orb`)
  scored PF 0.986 and did not beat a plain UTC one.
- **Breakout + retest** — failed on BTC at every timeframe 3m-4h, even with volume/order-flow/
  squeeze/body-strength filters. Best robust PF ~0.85. The INVERSE (fade the breakout,
  `liquidity_sweep`) is what worked.
- **Larry Williams daily volatility-range breakout** — PF 0.88-1.00 everywhere at taker. Same family.
- **VWAP trend-following / stop-and-reverse on BTC** — PF ~0.99-1.02 at ZERO fee. Asset-specific:
  the same mechanic worked on Gold/USDJPY/NAS100.
- **VWAP std-band fade** — backtest PF 3.0, live ~0.7. Resting-limit backtests assume a fill on
  any wick touch. Any limit-fill strategy needs a queue-priority check before the backtest is trusted.

Standing pattern from that repo: **every leg that ever worked came from a data feed
(funding, open interest, taker delta, long/short ratio), not from a price pattern.**
