# prop_lab — Project Context

Auto-loaded every session. Keep current.

## RULE 0 — ANSWER IN KEY POINTS

**READ `HOW_TO_ANSWER.md` BEFORE YOUR FIRST REPLY. IT OVERRIDES YOUR DEFAULT STYLE.**

- **SHORT SENTENCES. KEY INFO ONLY. BULLETS, NOT PARAGRAPHS.**
- **ANSWER IN THE FIRST LINE, THEN STOP.**
- **MAX 10 LINES OF PROSE PER REPLY. A LONG REPLY IS A BUG.**
- **NO PREAMBLE, NO RECAP, NO "WHAT I'M ABOUT TO DO".**
- **CAVEATS: ONE LINE EACH, MAX TWO. DETAIL GOES IN FILES, NEVER IN CHAT.**
- Tables are welcome when numbers are the answer. Always include trades/day.

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
- **VWAP mean reversion / breakout on CRYPTO** (H-002 / H-009 / H-017) — killed
  2026-09-06 by the engine fix, not by a new test. Three look-aheads were found in
  `strategies/vwap/engine.py`; on the corrected kernel the walk-forward cells clearing
  PF 1.20 at 2x went **11 → 0 on BTCUSDT** (best cell 2.305 → 0.882) and the wide
  11-coin book clears **1 of 132 legs**. The board's 28.5d / 9.7d numbers came from
  the bug. **Gold and EURUSD are the only survivors.** Any pre-2026-09-06 crypto
  board number is an artifact — check `SESSION_2026-09-06.md` before quoting one.
- **Power of Three / AMD** (H-026) — accumulation, manipulation, distribution, four
  session clocks, five feed conditioners. The sweep-reversal **loses gross** on BTC
  (−3.1 to −8.5bps) and ETH (−8.2 to −17.1) and wins on SOL (+7.8 to +14.6) at
  ~1,500 events each. A sign that flips across three coins is no effect. Only 3 of
  24 conditioner cells beat a permutation null. Caveat: tested with a fixed hold to
  the session close and **no stop and no target** — a stop-and-target version is
  untested and Kris trades one.
- **Book depth imbalance** (H-024) — real, monotone, beats its null, stable across
  years, and **0 of 935 cells across 11 coins clear a 14bps taker round trip**. Best
  honest cell 7.9bps. Also settles the cap-curve question: the small-cap edge in the
  microstructure literature is a **3-second** effect and does not reach 15m-4h.

- **Order flow / fade the crowd** (H-006) — the crowd long/short ACCOUNT ratio ranks
  forward returns monotonically, beats every block-shuffle null, and holds PF 1.227
  at 2x on BTC out of sample. It still fails, on **risk shape**: no stop means R is
  a return over trailing vol, so the book draws down 63.5R against H-002's 3.8R and
  needs 548 days. Closed 2026-09-07 on a kill criterion set in advance: shortening
  the hold does NOT cut the drawdown, it raises it, monotonically — median maxDD at
  2x is 2,810R at a 2h hold against 184R at 72h, and median PF 0.41 against 0.92.
  The walk-forward at a fixed 4h hold scores **PF@2x 0.646** with **negative** R/day
  and funds zero accounts, while still beating every null seed (median 0.477). The
  edge is a slow drift that cannot pay 28bps in four hours. Adding a stop was also
  tested and reverted: the fold selector picks no stop in 37 of 52 folds.
  `strategies/orderflow/orderflow.py` is KEPT — it is the shared feed loader for
  twelve other hypotheses, not H-006's strategy.

Standing pattern from that repo: **every leg that ever worked came from a data feed
(funding, open interest, taker delta, long/short ratio), not from a price pattern.**
As of 2026-09-06 that pattern is stronger, not weaker: twelve price hypotheses have
now died here, and the one crypto book that looked alive died to a look-ahead fix.

**Measured, not assumed (2026-09-06, `strategies/depth/stage2_cost.py`):** market
impact at prop clip sizes is **0.018bps one-way on BTC** and 1.5bps on DOT for a
$50k clip — around a hundredth of the 2bps/side this repo assumes. **The 14bps round
trip is fee plus spread, not impact.** Impact only bites above ~$1M, or on thin coins
in bad minutes (DOT $50k pays 7.0bps round trip at the p99 bar). The spread itself is
still unmeasured — `bookTicker` stopped in 2024-03.

**Every feed in `data/feeds/` and what it costs to believe:** `metrics` (OI, taker,
crowd) 2020-09→; `premium` 2019-12→ (H-013, dead); `funding` 2020-01→; `depth`
2023-01→ (H-024, this session); `dvol` 2021-04→ (H-025, this session). The ±0.2%
depth band exists only from **2026-01-15**.
