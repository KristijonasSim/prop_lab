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
- **EMA × VWAP cross** (H-003) — all four exits (cross-back, price/EMA, fixed R, session
  close), 3m-1d, 9 markets, 284k backtests. Real median PF 0.705 vs a phase-randomised
  **0.757** — worse than noise. Walk-forward: the null produced MORE gate-clearing cells
  than the real data (17 vs 10). An EMA slope filter was negative (-0.024 paired lift).
  Gold 1h reached walk-forward PF 2.356 but is 1 survivor in 48 where the null gave 2.
- **Liquidity sweep / stop-run fade** (H-005) — 541k backtests, 12 markets, 5m-4h. Real
  clears PF 1.20 on 1,702 configs; the paired-shuffle null clears **19,062**. Null best
  3.858 vs real 1.929. Only 2 of 57 combos beat their own null. NOTE: this contradicts the
  prior repo's `liquidity_sweep` result, which was never run against a null — treat that
  older finding as unverified.
- **Beta-residual reversion** (H-008) — strip BTC's beta out of ETH/SOL/BNB/XRP and
  fade the residual. 1,152 configs x 6 panels: ZERO clear PF 1.20 at 2x, and the
  null beats the real data on every cut. The decisive number is the z-response and
  it is FLAT — PF before costs runs 1.000/0.997/1.006/1.013 as entry goes 1.5 to
  3.0 sigma, so the size of a deviation says nothing about what follows. There is
  no mechanism here to repair.
- **Fading an extreme, as a family** — it has now failed twice on two different
  definitions of "extreme": a rolling 10-100 bar high/low (H-005) and the previous
  day/week high/low (H-011), which is the strongest level in the family. Do not
  re-propose fading an extreme without a genuinely new ingredient.
- **VWAP band rejection / mean-reversion scalper** (H-010) — the TradingView
  "VWAP MR Scalper" idea rebuilt with honest fills, real taker delta and exits.
  2,592 configs x 3 coins x 4 TFs: the paired null's median PF is HIGHER than the
  real market's at 0x/1x/2x/3x, and it clears the gate 637 times per seed against
  280. The control (take every setup the other way) scores no worse. Exiting at
  the VWAP — the whole idea — is the most harmful lever in the grid (0.500 vs
  0.816 for a time exit). Walk-forward 0.892 at 2x.
- **Previous day/week high-low reversal** (H-011) — NOT fully dead, but not
  tradeable: it is the only fade here that beats its paired null at every cost
  level and beats its own control, yet walk-forward is 0.897 at 2x and 0 of 12
  panels hold the gate. Real edge, too small for 28bps. Code kept.
- **Widening a book with more legs** (H-012 / "hypothesis X") — adding legs to cut
  drawdown makes the book SLOWER, not faster. All 57 walk-forwarded legs, gated,
  book chosen greedily for fewest days with the selection held out: in-window
  15.9 days, held out **130.7** against H-009's 16.7. Every variant lost — capped
  at 5 legs 62.5d, plus silver 39.5d, plus three FX majors 23.0d, inverse-vol
  weighting 29.2d. Cause is DILUTION not correlation: the median leg has R/day
  −0.0013, and equal weighting divides the book's R by the leg count, so a weak
  leg costs more R per day than it saves in drawdown. Do not propose "a wider
  universe" as a cure for drawdown without solving the weighting first.
- **VWAP std-band fade** — backtest PF 3.0, live ~0.7. Resting-limit backtests assume a fill on
  any wick touch. Any limit-fill strategy needs a queue-priority check before the backtest is trusted.

Standing pattern from that repo: **every leg that ever worked came from a data feed
(funding, open interest, taker delta, long/short ratio), not from a price pattern.**
