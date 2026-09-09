# What this needs next — data, fixes, and where else the rule works

Written 2026-09-09, after the strategy was frozen in `core/chosen.py`.
Kris's question: what else is needed, what data is missing, and does this port to
silver, oil, BTC or FX.

---

## 1. WHERE ELSE THE RULE WORKS — measured, not guessed

The traded rule (wide stop, five settings, floor 30 / top 5) run **unchanged** on
every market in the universe. Blind quarterly walk-forward, paired null, scored
at 2% risk against a 1-step 2% target. `backtests/vwapbreak/assets.json`.

| market | TF | PF @2x cost | win % | pass % | days | beats its null |
|---|---|---|---|---|---|---|
| **XAUUSD** | 1h | **2.872** | 20.3 | 65.8 | **15.2** | yes |
| **ETHUSDT** | **1h** | **2.023** | 22.8 | **65.1** | **16.9** | **yes** |
| GBPUSD | 4h | 1.268 | 18.1 | 41.7 | 21.6 | yes |
| SOLUSDT | 1h | 1.246 | 18.9 | 54.9 | 18.2 | yes |
| XAUUSD | 4h | 1.223 | 19.3 | 48.5 | 20.6 | yes |
| EURUSD | 4h | 1.188 | 15.7 | 50.5 | 19.8 | yes |
| EURUSD | 1h | 1.158 | 20.9 | 57.1 | 29.8 | yes |
| GBPUSD | 1h | 1.098 | 14.2 | 38.9 | 20.6 | yes |
| XAGUSD | 4h | 1.071 | 22.5 | 62.0 | 27.4 | yes |
| USDJPY | 1h | 0.957 | 19.9 | 45.1 | 22.2 | yes |
| ETHUSDT | 4h | 0.904 | 22.3 | 54.1 | 30.5 | yes |
| XAGUSD | 1h | 0.942 | 18.6 | 59.9 | 16.7 | **NO** |
| SOLUSDT | 4h | 0.698 | 26.3 | 56.4 | 24.8 | yes |
| BTCUSDT | 1h | 0.686 | 20.4 | 51.5 | 23.3 | **NO** |
| BTCUSDT | 4h | 0.669 | 21.9 | 32.8 | 36.6 | yes |
| WTI | 1h | 0.659 | 18.2 | 33.0 | 40.9 | yes |
| AUDUSD | 1h | 0.715 | 17.0 | 44.6 | **NO** | **NO** |
| USDJPY | 4h | 0.747 | 20.5 | 33.4 | 62.9 | **NO** |
| WTI | 4h | 0.326 | 18.2 | 24.2 | 57.9 | **NO** |

**Read it as three groups.**

* **It transfers to ETHUSDT 1h.** PF at double cost **2.02**, 65% of accounts
  pass, 16.9 days, and it beats its own phase-randomised null. That is the same
  shape as gold on a completely different market, which is the strongest evidence
  in this table that the mechanism is real rather than a gold artefact.
* **Weakly on SOL 1h, GBPUSD 4h, EURUSD 4h** - above 1.2 or near it at double
  cost, beating their nulls, but pass rates in the 40s and days in the 20s.
* **Not on silver 1h, BTC 1h, WTI, AUDUSD 1h or USDJPY 4h.** Silver 1h is the
  interesting failure: 59.9% pass and 16.7 days look fine, and it **loses to its
  own null** (1.104 against a real 1.002), which is exactly the trap the null
  exists to catch. Anyone reading the pass rate alone would have traded it.

**The caution that belongs next to ETH.** Every crypto price hypothesis in this
repo has died, including H-002's crypto book, which died to a look-ahead fix. The
kernel here is different and has been checked for that class of bug on the
decision, fill and exit paths - but H-027 has **never been run through a second
engine**, so the check that killed the last crypto result has not been applied to
this one. See item 3.1.

**The obvious next experiment: a two-market book, gold 1h + ETH 1h.** Both clear
their nulls, both at 1h, and their trades are unlikely to line up - gold's
session and ETH's are different clocks. H-012 established that widening a book
DILUTES (equal weighting divides R/day by the leg count), but that was 57 weak
legs; two strong legs is a different proposition and is untested. It is the
cheapest large gain available: if the drawdowns do not overlap, the same risk
buys twice the trades.

## 2. THE DATA WE ARE MISSING, in order of what it costs us

### 2.1 More history on gold — the single biggest lever

Everything on the board is measured on **three years** because Kris's rule says
so, and the rule exists to keep markets comparable. But the binding limit on
every number we have is the **width of the band**: 21.7 expected days with a band
of 16.8-31.4. The band is set by how few independent stretches the sample
contains, and only more data narrows it.

Dukascopy has XAUUSD back to **2003**. Ten years would give roughly three times
the folds and a band perhaps 40% narrower - enough to tell 21.7 days from the
luck zone, which nothing we currently own can do.

The cost is that a ten-year gold study is not comparable with a three-year FX
study. That is fine: keep the three-year rule for the BOARD and run a separate,
longer study for the strategy actually being traded.

### 2.2 The prop firm's own spreads

Every cost in this repo is Dukascopy's. FundingPips, CTI and Upcomers each quote
their own gold spread, and gold spreads vary between 1 and 4 bps between brokers.
Our whole result is priced at **1.06bps round trip**. At 3bps the picture changes
and nobody has checked. One evening of tick capture from a demo account settles
it.

### 2.3 A data refresh that runs itself

The settings expire on **2026-12-01** and re-ranking needs the twelve months
ending then. Right now the caches end 2026-08-30 and nothing updates them. A
scheduled download plus the ranking script is an afternoon of work, and without
it the quarterly refresh silently does not happen.

### 2.4 Feeds we have and have not used on this hypothesis

`data/feeds/` holds funding, open interest, taker delta and the crowd long/short
ratio for BTC/ETH/SOL from 2020. The standing pattern in `CLAUDE.md` is that
**every leg that ever worked in the prior project came from a data feed, not a
price pattern** - and H-027 is a pure price pattern. If ETH 1h is real, the
feeds are the obvious thing to condition it on, and they exist already. For gold
there is nothing equivalent on disk: COT positioning and the ETF flow series
would be the analogues, and neither is downloaded.

## 3. WHAT WOULD MAKE THE STRATEGY BETTER, in order

### 3.1 Run H-027 through the second engine — do this first

`strategies/vwap/stage17_goldnautilus.py` streams the older kernel through
NautilusTrader bar by bar and has caught **three real bugs**, including the one
that killed the crypto book. H-027's kernel has never been through it. It is a
day of work and it is the cheapest thing that could invalidate everything above.

### 3.2 Fix what the fold selector optimises

The selector ranks configurations on **profit factor at double cost**. Profit
factor is maximised by a very tight stop that wins 5% of the time and pays
hugely - and a prop evaluation does not pay for profit factor, it pays for
reaching a target before a drawdown. That mismatch is why the traded settings had
to be pinned by hand instead of derived: given every stop width from 0.75 to 20
sigma, the blind selector picks 0.75.

Rank on **R per day**, or on the drawdown-to-R ratio that actually sets
days-to-funded, and the pipeline would select the thing we want without a human
overriding it. Everything downstream inherits the fix.

### 3.3 Cap concurrent positions — measured, +9 points of pass rate

The five settings pile into gold in the same direction, so they lose together.
Capping open positions at **two** moves Upcomers Ash from 65.8% to **75.1%** pass
and cuts blown accounts from 29.5% to 17.5%, at 0.46 trades a day instead of
0.93. At 3% risk with the cap: 68.5% pass in **14.6** days, better than the
uncapped book on both counts. Not yet applied - it is a change to the frozen
strategy and needs Kris's sign-off.

### 3.4 The rest of the exit axis

Stop WIDTH is now swept. Untested: a trailing stop (H-016's entire edge is one),
a partial exit at +1R with the remainder running, and a time-of-day exit. The
exit is where this strategy's money is - 79% of trades stop out, and the whole
result comes from the 10% that survive fifty bars.

### 3.5 Per-firm risk policy

Risk is currently one number. It should be a function of the firm's rules: no
daily cap means a larger size is safe, a trailing drawdown means a smaller one.
`core/riskladder.pick` already has the machinery; it needs the firm's spec as an
input instead of a constant.

## 4. WHAT IS MISSING OPERATIONALLY

* **Execution.** There is no bot. cTrader Open API is the documented preference
  and FundingPips supports it; CTI is MT5-only, and this Linux box has no MT5
  bridge. Nothing can be traded automatically today.
* **A daily-loss circuit breaker.** Three days in 221 broke the 3% daily cap at
  2% risk. A rule that stops trading for the day at -2% would have saved those
  accounts, and it cannot be simulated from daily data - it needs the intraday
  sequence, which we have in the trade list but have not wired up.
* **Monitoring.** At 0.93 trades a day nobody watches a chart. Alerts exist in
  the Pine; nothing watches the account, the drawdown or whether the bot is
  alive.
* **Multi-account tracking.** The plan is several accounts. Staggering start
  dates is what makes them independent samples rather than one sample copied
  three times, and there is nothing to track which account started when.

## 5. WHAT I WOULD DO NEXT, in order

1. **Second engine check on H-027** (3.1). Everything else is worthless if this
   fails.
2. **Ten years of gold** (2.1). It is the only thing that can narrow the band,
   and the band is what stops us calling any of this proven.
3. **Selector objective** (3.2), then re-run. If it picks the wide stop by
   itself, the pin in `core/chosen.py` can go and the pipeline is trustworthy
   again.
4. **Gold + ETH two-market book** (1). The cheapest large gain if the drawdowns
   do not overlap.
5. **Concurrency cap** (3.3) - decided by Kris, since it changes the frozen
   strategy.
6. Execution and the circuit breaker (4), once a firm is chosen.
