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

## THE ONE THING — set by Kris 2026-09-09

**H-027 (VWAP band breakout) is the project's single focus from here.** No
hypothesis-hopping. His words: *"i don't want to jump from hypothesis to
hypothesis, i want to work on one thing for a long time and make perfection, and
then post it on TradingView, gather community, also use this indicator myself."*

That sets three deliverables, in this order:

1. **A rule he trades himself.** Measured the way everything here is measured -
   blind walk-forward, paired null, costs at 1x/2x/3x, expected days with its
   noise band.
2. **A published TradingView indicator** (`strategies/vwapbreak/indicator.pine`)
   good enough to put his name on. Signals only - no orders, no equity curve.
3. **A community around it**, which means the description and the honesty of the
   claims matter as much as the numbers.

**What this changes about how to work.** A new hypothesis is now OUT OF SCOPE
unless Kris asks. Work goes into H-027's own axes - and the entry axis is close
to exhausted (thresholds, sessions, 25 filters, relative volume, fresh-cross all
tested), while **the exit axis is barely touched**: today it is a fixed sigma
stop plus a fixed bar horizon, and no trailing stop, partial exit or VWAP-recross
exit has ever been run on it.

**What has NOT changed:** the noise floor still governs. An "improvement" whose
band overlaps the baseline's is not an improvement, and a published indicator
built on one is worse than no indicator at all.

## Current phase constraint

**PACE TARGET, set by Kris 2026-09-07: evaluations that resolve in 5-14 days.**
He will run **several prop firms**, not one, so the plan does not depend on any
single firm's structure. Anything past **50 expected days is flagged TOO SLOW**
by `core/scorecard.py` and the flag OVERRIDES the score on the board.

His first instruction was to delete anything slower than 50 days. That would have
emptied the board - H-002 needs 143.6 days and H-016 needs 175.9 - so he chose to
**keep both, flagged**, as worked examples and as test targets for the
verification work in `NEXT.md`. Read the flag as "this cannot fund an account on
the timescale the business needs", not as a suggestion.

Only build hypotheses that **resolve within ~1-2 weeks of active trading**.
High trade frequency, short holds — intraday to a few days.
Named archetypes: ORB, VWAP mean reversion, breakout-retest.

Longer-hold ideas (trend following, carry, position swing) are logged as future
candidates, not built now. Say so explicitly when logging one.

## THE NOISE FLOOR — measured 2026-09-08, and it governs every comparison

Six gates carrying **no information by construction** (the MA200 slope sign,
block-shuffled at its own median run length) were run through the full blind
walk-forward on gold. At 2% risk they scored between **13.3 and 26.5 expected
days** and between **PF@2x 1.485 and 2.295**.

**The best-scoring arm of that entire day's work was one of the shuffled gates.**

Two rules follow and neither is optional:

* **An improvement smaller than that spread is not evidence of anything.** Every
  real candidate measured that day — 14.1, 16.1, 16.6, 17.2 expected days — sits
  inside the band. So did the earlier 62.6%-pass headline, which evaporated when
  the grid was widened.
* **Quote a per-cell number with its noise band or do not quote it.** No number
  in this repo's history has been reported that way, which is the mechanism
  behind every result it has had to retract.

**AS OF 2026-09-09 THE BOARD ENFORCES THIS** — `core/noiseband.py`. Every ranked
number on the page carries its own 10–90% band, computed by resampling that
cell's daily returns in blocks and re-running the same prop simulation
(`_states` is `riskladder.run_accounts` vectorised, pinned account-for-account by
`tests/test_noiseband.py`). Rows whose bands overlap share a TIER and
`core/scorecard.rank_tiers` refuses to order them — tiers are formed against the
tier LEADER, because overlap is not transitive and comparing neighbours would
chain a whole table into one tier. A band is stored per LADDER RUNG, so forcing a
different risk on the page moves the band with the number, and `core/repick.py`
carries it through a policy change.

**The one thing that is NOT subject to this: the risk ladder.** Re-simulating the
same trade series at a different position size selects nothing and searches
nothing — it is arithmetic on a fixed series. Gold 1h needs 38.0 expected days at
0.25% risk and **16.6 at 2%, 13.0 at 3%**, and that difference is real in a way
no filter result today was.

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

**THE FIRM IS CHOSEN, 2026-09-08: Thunderbolt, 1 step.** First real spec this
project has had. Everything before this date was modelled on a guessed 8%+5%
two-step and those numbers are wrong, not merely stale.

| | |
|---|---|
| Profit target | **6%** |
| Daily drawdown | **3%** |
| Max drawdown | **6%** |
| Time limit | unlimited |
| Payout | on demand, 90% split |
| Leverage | up to 10x |

**Easier on the target, harder on both caps.** The 6% max drawdown is the binding
constraint: both board picks sat at −7.5% and −7.8% under the old 8% cap and
neither fits. `core/riskladder.DD_CAP` is now 0.06 and both books re-picked a
lower risk per trade.

**What it did to the board** (nothing about the strategies changed — only the rules):

| | before, modelled 8%+5% | Thunderbolt 6% one-step |
|---|---|---|
| H-002 | 6.0/10, 143.6d, 1.00% risk | **7.7/10, 55.9d, 0.75% risk** |
| H-016 | 4.7/10, 260.1d, 2.00% risk | **6.2/10, 117.0d, 1.50% risk** |

Both still `TOO SLOW` against 5–14 days. H-002 is now 4x away rather than 10x.

**STILL UNKNOWN — ask the firm before money moves:**
* **Static or trailing max drawdown?** Worth 17 points of pass rate on a
  zero-edge strategy. Modelled as **both**, the stricter reading.
* Minimum trading days? Modelled as **0** — an unlimited time limit usually
  comes with none, and assuming one would flatter the pace.
* Any consistency rule (max share of profit from one day)?

**THE MARKET MISMATCH IS THE REAL PROBLEM.** The offer shows crypto pairs and
10x leverage. **Both surviving hypotheses are gold-only**, and every crypto price
hypothesis in this repo is dead. Confirm XAUUSD is tradeable there before reading
any board number as a plan.

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

## Test window — ALWAYS THE LAST 3 YEARS

**Kris's standing rule, 2026-09-08.** Every market in a study is trimmed to the
last three years of data, aligned to a **common end date** across the whole
universe. `core.run_hypothesis.YEARS`.

* **Three years of DATA, not three years of out-of-sample.** The first twelve
  months are the initial training window, so a study yields roughly **two years
  of blind quarterly tests**. Three years out-of-sample would need four years of
  data and the FX/metals caches only reach 2023-09.
* **It is a hard limit, not a minimum.** BTC has 9.1 years and gets the same
  three as EURUSD.
* **The common end is the EARLIEST last bar in the universe**, not the latest.
  Caches finish on different days and a fold boundary landing between two of
  them hands one market an extra quarter. That happened: crypto got 2.00 years
  of out-of-sample against FX's 1.73, so "crypto beat FX" partly meant "crypto
  was measured over a longer window".

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
- **Entry filters on H-027 gold, as a family** (2026-09-08) — 25 candidates
  screened as a paired lift per configuration on gold 1h and 4h: moving averages
  (position, slope, counter-trend), fibonacci retracement and extension zones,
  six session windows, volatility regime, day of week. **24 of 25 raise profit
  factor and LOWER R per day**, which makes the evaluation slower — the metric is
  `days = maxDD_R / R_per_day`, not PF. Every session window is slower on both
  timeframes, so "try London or NY instead" is closed by measurement. Fibonacci
  sign-flips across timeframes (fib100 beyond .618: −25.7 days on 1h, **+344.6**
  on 4h) which is H-026's signature for no effect. The one survivor, MA200 slope
  alignment, was re-run inside the kernel and then **lost to its own control**:
  a gate block-shuffled to carry no information scored PF@2x 1.968 / 54.4 days
  and 2.295 / 40.5 against the real gate's 1.840 / 75.5, and a shuffled gate on
  1h reached **60% pass in 14.5 days** — the exact target, from noise.
  `strategies/vwapbreak/research/`.
- **Order flow on GOLD is not testable and no number may be quoted for it.**
  Every file in `data/feeds/` is a Binance crypto symbol; `data/dukascopy_raw/
  XAUUSD` holds one-minute BID CANDLES, not ticks, so there is no bid/ask volume
  on disk. Gold trades naked. Backlog H-030, and it needs a download.

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

- **Liquidation-pressure fade** (H-031, 2026-09-11) — a 30m OI collapse with price
  down, long 24h. Real but small: **+26.7bps gross per trade against +11.8 for a
  block-shuffled null and +20.5 for a same-fall/stable-OI control**, 10 coins, 3y.
  PF@2x **0.924** with no stop and **worse with every stop** (0.667–0.889, monotone
  in stop width); R/day negative on all eight arms. 10 of 10 coins fire together
  in a cascade. Killed on a criterion written before the run. It also closes
  **H-006-R**: a stop does not repair a slow-drift feed signal, it harms it.
  `strategies/liqflush/`.

- **Four candidates screened at gate 2** (H-035/036/037/038, 2026-09-13) — all
  dead, and the two METHOD lessons are worth more than the four deaths.
  * **H-035 on-chain exchange flows** (CoinMetrics netflow, free, daily). The
    only arm with a coherent shape — pctile 99.2/100.0 at the same h=4 on both
    markets — and it **alternates when the knowable-lag is pushed out a day**:
    D+2 +19.4/+30.9, D+3 **−2.7/−15.8**, D+4 +14.8/+32.6. An edge that inverts on
    alternate days is not information. Also never honestly testable: every value
    is `flash`, revised later, and only the current value is served.
  * **H-036 funding settlement as an EVENT** (not H-004's continuous level) —
    fails cross-market, 96.0 on BTC and 67.2 on ETH.
  * **H-037 variance risk premium** (implied − realised; not H-025's level) —
    fails cross-market, 96.2 on ETH and 93.2 on BTC.
  * **H-038 fair value gaps**, the first SMC primitive tested here, every
    parameter fixed in advance — **the gap-size filter WEAKENS it 3 of 4**
    (96.8→87.2, 97.0→91.8, 97.2→75.0), the opposite of a real effect.
  * **LESSON 1 — price the SEARCH, not just the test.** 96 tests at a 95th
    percentile expect **4.8 false passes**; 7 were observed, `P(≥7)=0.205`. This
    is the H-028 distinction (`p=0.0000` one slot vs `p=0.187` best-of-48) and it
    was rebuilt without the correction three days after being written down.
  * **LESSON 2 — `core/probe.py`'s null does not match HOUR OF DAY.** It shifts
    events to random positions; an event that always fires at 00:00 UTC is then
    compared against a population drawn from every hour. At h=4 the 00:00 bar
    means −3.15/−2.90 against an all-bar +1.56/+2.29, so any short-side daily arm
    is gifted about **5 bps**. **An hour-concentrated event needs an
    hour-matched null.** `strategies/screen/`.

- **The term structure of leverage** (H-034, 2026-09-13) — dated quarterly
  futures against the perp, `basis_ann = (front − perp)/perp × 365/days`. The
  first feed here with a HARD arbitrage anchor: it must converge on a known date,
  and it does (153 → 8.6 bps into settlement). Free, 22 of 22 quarterly cycles,
  48,837 hourly rows per market 2021-02→2026-08, and genuinely NOT funding —
  correlation **0.306 in levels, 0.004 in changes**, so H-004 and H-013 do not
  cover it. **Pace passed** (57–243 events/year, against a floor of 40 fixed in
  advance) and the edge test killed it. The level reading is absent (best pctile
  78.2). The best arm, ETH curve-steepening at h=72, scored 205.13bps at pctile
  95.2 and died on the year split (3 of 4, 2023 at −49.35); the same arm on BTC
  scored 139.22 against a **null p95 of 171.46**, and K flips sign between BTC
  (+35.15) and ETH (−11.26). At a 72h horizon the null is the same size as the
  finding. **The dated contract is a feed, never a trade** — it turns over one
  thousandth of the perp. `strategies/termstruct/`.

- **CFTC positioning as a gate on H-027** (H-030, 2026-09-11) — eight gates from
  the weekly COT report (managed-money crowding, 1w/4w flow, total OI), used only
  from release time. **Every gate is slower than no gate**: 26.3–64.1 expected
  days against 21.7. Refusing the side managed money is crowded on cuts PF@2x
  2.872 → 1.766 — gold breakouts WITH the crowd are the good ones. Free CME GC
  volume/OI history does not exist; SPDR's GLD archive is now a PDF. So gold
  still trades naked, and the one free feed that exists does not help it.
  `strategies/goldfeed/`.

Standing pattern from that repo: **every leg that ever worked came from a data feed
(funding, open interest, taker delta, long/short ratio), not from a price pattern.**
As of 2026-09-06 that pattern is stronger, not weaker: twelve price hypotheses have
now died here, and the one crypto book that looked alive died to a look-ahead fix.

**THE DEAD-BAR FIX WAS INCOMPLETE UNTIL 2026-09-08. THE EXIT PATH WAS NEVER
GUARDED.** The 2026-09-07 work guarded the DECISION bar and the FILL bar and
stopped there, so a stop, target or trail could still be "hit" by a padded
weekend bar. Measured on the boards' own walk-forwards: **H-002 1,079 of 17,432
exits (6.2%)** and **H-016 1,532 of 8,610 (17.8%)**. Both are now zero.

* **Which field of the bar the exit rule touches decides how much it matters.**
  A trailing stop reads every bar's `high`/`low`, and a padded bar has
  `hi == lo ==` the frozen price, so it sits on the trail and force-closes a live
  trade. H-016's walk-forward went **12 of 16 cells clearing PF 1.20 at 2x to 14
  of 16**, median cell **1.275 → 1.430**, and the board record **175.9 → 127.6
  expected days**. A session-horizon time exit reads only the `close`, and a
  padded bar's close IS the last real close - so H-002 did not move at all
  (PF 2.016, **143.6 days**, unchanged). Same bug, opposite magnitude.
* **Never estimate this by subtracting the affected trades' R.** On H-016 that
  arithmetic said dead-bar exits contributed +59.03R of +127.08R, i.e. that
  fixing it would halve the edge. Re-running showed the opposite: they were
  premature stop-outs on a price nobody traded. **The counterfactual has to be
  re-run, not subtracted.**

**A STOP THE BAR GAPPED PAST FILLS AT THE OPEN, NOT AT THE LEVEL (2026-09-08).**
A stop is a stop-market order. Filling at the level assumes price walked down to
it; on a gap it did not. This became material the moment the kernels started
holding through the closed weekend, which is exactly where gold gaps — the two
2026-09-08 changes belong together and **the second undoes the first's gain**.

| | before either fix | after the exit fix | after the gap fix |
|---|---|---|---|
| H-016 expected days | 175.9 | 127.6 | **260.1** |
| H-016 cells clearing PF 1.20 at 2x | 12/16 | 14/16 | 13/16 |
| H-016 vs its paired null | 12 vs 5.0 | 14 vs 3.3 | 13 vs 3.0 |
| H-002 expected days | 143.6 | 143.6 | **143.6** |

**H-002 is immune and H-016 is not, structurally.** H-002 is session-bound and
rarely holds across a weekend (1 gapped stop in 5,382); H-016's whole exit is a
multi-day trailing stop (168 gapped of 2,027, median 13.9–27.2bps through, worst
216bps). **H-016's pace headline was resting on a fill nobody could have got.**
The edge survives — 13 of 16 against a null's 3.0 — the speed never existed.
**A TARGET keeps its level**: it is a limit order, a gap through it fills better,
and taking that bonus would be optimism in the other direction.

**RESOLVED 2026-09-09 — and neither was a look-ahead.** Both were diagnosed by
dumping each engine's state at the disputed bar; the workings are in
`SESSION_2026-09-09.md`.

* **30m, MODE_PULLBACK / MODE_RECLAIM, anchor 13:30 — the RULE was ill-posed,
  not either engine.** Both modes ask whether the PREVIOUS bar closed above or
  below its VWAP. Over the padded weekend every bar is O=H=L=C at one frozen
  price, so the session VWAP *is* that price and the true answer is neither. What
  decided it was the last bit of the accumulation - pandas `cumsum` in the kernel
  against an incremental sum in the port, one ulp apart (4.5e-13 on gold) in
  whichever direction. `engine.PX_EPS_FRAC = 1e-9` now gives the comparison a
  tolerance in price terms: a strict test must beat the floor, a non-strict one
  absorbs it. 3,095 of 45,024 30m bars are ties at that anchor and all but 2 are
  padded bars, so the blast radius is the weekend open and nothing else.
* **15m, MODE_BREAK, rolling 384-bar anchor — the PORT's bookkeeping.** The
  kernel caps a hold at the end of the session (`horizon = stop_bar`) and books
  the trade at the last usable bar; the port left the horizon uncapped and then
  dropped whatever was still open when the stream stopped. One trade of 416, the
  last one, entered seven bars from the end. The port now caps at `n_bars - 1`.

**The lesson generalises: an entry-bar disagreement is not automatically a
causality bug.** One of these was a rule that had no answer and one was a
convention at the end of the data. Both were found by printing both engines'
state at the bar, which took minutes; both had been carried as unresolved for a
day because the disagreement was reported as a count rather than as a mechanism.

**The original entry, kept for the record:**

**OPEN, 2026-09-08: two configurations disagree with the vwap NautilusTrader
port on entry bars.** Found the moment 15m and 30m were added to the port's `TFS`
map, which had listed only 5m/1h/4h — **two of the board book's four legs had
never been cross-checked at all** and nothing said so. Both are localised, both
sit at a boundary, and on every shared trade exit bars match 1.0000 and
`max |dR|` is 2e-7 (float noise), so **neither looks like a look-ahead**:

| | disagreement | where | reaches the board? |
|---|---|---|---|
| 30m, MODE_PULLBACK, `min_rvol` 2.0, anchor 13:30 | 4 of 330 trades | all four are the **first live bar after the weekend** (Sunday 22:00 UTC decision, 22:30 entry) | **No.** The config is fold-selected only for the 2025-12 quarter and all four dates (2024-04-07, 2025-04-06, 2025-05-18, 2025-06-15) fall outside it. |
| 15m, MODE_BREAK, rolling 384-bar anchor, hold 48 | 1 of 416 trades | bar **90041 of 90048** — 7 bars from the end of the series, in the last rolling window | Possibly one trade in the final fold. |

Which side is right is **unresolved**. Do not quote H-002's 30m or 15m legs as
second-engine verified until it is. The slow suite fails on this deliberately —
`pytest -m slow`.

**BOTH KERNELS ARE NOW SECOND-ENGINE CHECKED (2026-09-08).** `strategies/ribbon/
stage12_nautilus.py` streams the ribbon kernel through NautilusTrader one bar at
a time and matches **108 of 108 rule shapes exactly** across 15m/30m/1h/4h -
every entry bar, every exit bar, `max |dR| = 0`. It covers the TRADE LOGIC; the
twenty moving averages are covered separately by `test_parity.py` against a
literal reading of the Pine. With that gap closed H-016 went **3.0 → 6.0** on the
board, having been capped by `core/verification.py` for exactly this.

**FX/METALS DATA CARRIES A CLOSED MARKET (2026-09-07, `stage20_deadfix.py`).**
Dukascopy pads the closed FX weekend with synthetic bars: zero volume, O=H=L=C at
the last traded price. **21.5% of the XAUUSD series is these.** Two rules now hold
in every engine that touches FX or metals, and any new one must carry them:
1. **Never decide or fill on a zero-volume bar.** Both kernels (`vwap`, `ribbon`)
   take a `live` array. Before the fix H-016's XAUUSD 1h leg took **25.19R of
   54.25R** from dead-bar entries and its 4h leg **11.87R of 2.15R** — that leg
   was negative without them.
2. **A volatility guard needs a tolerance in price terms, not `<= 0.0`** - and
   so does any comparison against a VWAP (`PX_EPS_FRAC`, 2026-09-09). A
   quantity like `vwstd = sqrt(p2v/v − vwap²)` is a difference of near-equal
   accumulated sums, so its cancellation floor is `price·sqrt(eps)` ≈ 3e-5 on
   gold. `sd <= 0.0` let that noise act as a real band on sessions that never
   traded. Use `sd <= price · 1e-6`.
Applying both left the signal intact (gold cells clearing PF 1.20 at 2x: 15/20
before and after, median cell 1.395 → **1.485**) and **cost the pace headline**:
the best book went 100.2 → 143.6 expected days, because the old book's drawdown
sat at 8.00R against an 8.00R cap. Crypto has **zero** zero-volume bars and did
not move.

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
