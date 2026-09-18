# What to do next — rewritten 2026-09-17

The plan of record. The previous version was written 2026-09-14, before the
band-shape study finished, before H-041 to H-045, and before the top-N result was
tested. It is kept at `docs/archive/NEXT_2026-09-14.md`.

**Nothing below is chosen. Kris picks.**

---

## ADDED 2026-09-18 — the workflow question, and the one number that reframes this page

Kris: *"everything happens random ... we need some kind of workflow."* Full
research and the proposed operating system: **`docs/WORKFLOW.md`**.

The finding that changes how to read everything below:

```
trials        228 charged, 0 pre-registered
budget        3y buys 13 (OVER BUDGET), 5y buys 45 (OVER BUDGET)
this search   needs 7.9y of history; luck alone reaches 2.81 sigma
```

`core/ledger.py`, `core/searchcost.py`, `backtests/ledger.csv` — built today,
backfilled from `STRATEGY_LOG.md`. **The third method debt on this page is now
paid**; the other two (hour-matched null, accounts-consumed) have functions
behind them but are not yet wired into the board.

## THE NEXT STEP — one thing, written 2026-09-18

**Give the loop the gold order-flow feed. Everything else on this page waits.**

It is the only item that is simultaneously (a) the highest-value untested input
in the repo, (b) already half-built, and (c) the thing the loop needs in order
to keep being worth running.

**It is not a new idea and there is nothing to design.** It is **H-052**, which
was recorded INCONCLUSIVE on 2026-09-17 for one reason and one reason only:
*"the tick pull was stopped at 225 days ... finishing the three-year pull, about
fourteen unattended hours, is what settles it."* The code is written
(`core/gold_flow.py`, `strategies/goldflow/daily.py`), the schema is right, and
the verdict is waiting on bytes.

**Measured 2026-09-18, so nobody re-derives it:**

| | |
|---|---|
| days cached in `data/flow/XAUUSD/` | **245** (2023-08-01 → 2026-03-20) |
| business days in that span | 689 |
| **coverage** | **35.6%** |
| **2024** | **entirely missing — zero files** |
| on disk | 22 MB, so the full pull is ~60 MB |
| schema | `open high low close ticks askvol bidvol spread_bps vol delta imb`, 1-minute |

**Why this feed and not another macro series.** `research/` harvests eight daily
feeds; a daily feed gives ~750 rows in three years and `core.screen` is rejecting
most candidates on *event count* before cost is even considered. This one is
**minute-level on gold**, so the event problem disappears, on the one market
whose round trip is **1.83 bps**. The five feed hypotheses that died (H-006,
H-024, H-031, H-034, H-042) were all real and all died to crypto's 14 bps.

**The work, in order.**

1. **Answer `reconcile()` FIRST — it decides whether the rest is worth doing.**
   `core/gold_flow.py:120` checks the tick volumes against the cached candle
   volume to establish whether `askVolume` is size that **traded** at the ask or
   size **quoted** there. Traded ⇒ this is aggressor flow, the H-006 family.
   Quoted ⇒ it is a liquidity imbalance, the H-024 family, **which was real,
   monotone, beat its null, and cleared its cost in 0 of 935 cells.** One day of
   data answers it and it is already coded. Do not spend fourteen hours before
   running it.
2. **Finish the pull.** ~444 missing business days, 2024 first. Fourteen
   unattended hours — exactly the overnight job the loop was built for.
3. **Register it** in `research/vocab.py` with a declared `prior_sign` and its
   mechanism, so it goes through the same screen, pre-registration and ledger as
   everything else. Candidate shape: `imb = (askvol − bidvol)/(askvol + bidvol)`,
   lag 1 bar.
4. **Carry the caveat in the registry, not in a footnote.** Spot gold has no
   central exchange, so this is Dukascopy's own liquidity-provider volume —
   indicative size, not confirmed executions, and nothing to validate it
   against. It is still the same feed this project trades on and prices its
   costs from.

**The known trap, from H-052's own write-up:** gold trended hard through 2025-26,
so quintile means run into hundreds of bps and the market's own move swamps the
buckets. The most coherent cell had rho 0.90 with a **mean spread of +38.3 bps
and a median of −8.4** — opposite signs, the exact skew trap `core/screen.py`
exists to catch. More data does not fix that on its own; the screen's median
check is what will.

**Do not** add more daily macro series to widen the registry instead. That is
the parameter-tuning move in feed clothing, and the arithmetic in
`docs/WORKFLOW.md` §6.1 says it buys nothing the screen can certify.

**Still open, unchanged, and still ten minutes:** the B1/B2 email below. It has
been open since 2026-09-08.

---

## ADDED 2026-09-18 (second entry) — the loop is built and running

Kris picked **"C target with B machinery"**: hunt data feeds, model-driven, with
a UI. It exists — `research/`, and `research/README.md` is the manual.

```
python -m research.loop --cycles 1        # harvest, propose, screen, publish
python -m research.loop --forever --mode llm --every 900
open backtests/research.html              # the page
```

**First run: 36 candidates screened, 0 survivors, chance expectation 1.8.** Two
seconds of compute. Three design findings are in `RESEARCH_LOG.md`; the one that
governs everything is that **at 10,000 trials on three years of data nothing
below an annual Sharpe of 2.23 is certifiable, and H-027 sits at 1.16.**

**The loop screens only.** A PASS means the idea earned a real study — it is not
a result. The walk-forward is still `core/pipeline.py` and still hours.

**It runs on the desktop, not the VM** (2 cores / 952 MB there, 28 cores / 30 GB
here). When the registry runs out, the fix is a new feed, not a new parameter —
and the next one is Dukascopy's XAUUSD **ask/bid volume**, which
`core/fx_spread.py` has been downloading and discarding on line 106.

---

Four items independent of any route, in cost order:

1. **Send the B1/B2 email.** Ten minutes, open ten days.
2. **cTrader Open API spike.** `live/bybit_demo.py`'s "no cTrader connector
   exists" is wrong — Spotware ships a Python SDK and FundingPips is on cTrader.
3. **PBO on the H-027 fold selector** (`core.searchcost.pbo_cscv`). The one gate
   never run here. Validates or invalidates `core/pipeline.py` in half a day.
4. **Gate 0** — `core/screen.py` refuses to run without a pre-registration
   (`docs/prereg/TEMPLATE.md`). Worth ~2.8 sigma of bar for thirty minutes.

---

## The state in six lines

* **H-027 is finished being tuned. Eight axes are now closed BY MEASUREMENT** —
  entry filters, timeframe, exit shape, selector objective, clock anchor, band
  shape, account overlay, and now the top-N width. That is not a failure. It is
  the answer to "how do we improve this": you don't, and you now know it with
  numbers instead of guessing.
* **The shipped rule is unchanged and nothing found since has beaten it.**
  `core/chosen.py`, XAUUSD 1h, floor 30 / top 5, five settings in parallel.
  **19.1 expected days, band 14–25** on the HOUSE spec at the 4% rung
  (CLAUDE.md's own table); 15.3 [13–22] at the 6% rung, which is the number the
  withdrawn top-N entry was compared against.
* **The 8.9-day top-N result is withdrawn.** It was the fastest number this
  project has ever produced and it does not survive its own null — see below.
* **The demo bot is alive, day 7 of 18.** Equity $10,130, peak $10,465, 3 legs
  open. It is the only out-of-sample evidence here that is not a simulation.
* **The pace target is 5–14 days. 15.3 with a band to 22 is outside it**, and
  there is no longer a candidate lever that closes the gap.
* **The indicator is written, not published.** 424 lines, signals only.

---

## What was settled on 2026-09-17

### The top-N result is withdrawn, and the reason matters more than the result

`strategies/vwapbreak/research/topn.py`, pre-registered in `TOPN_NULL.md`,
`backtests/vwapbreak/topn_rebuilt.json`.

**First, the study had no code.** The 2026-09-15 commits shipped JSON, logs and
a write-up and no script, so the headline of `COMPETITION.md` was not
reproducible by anybody. It is now a committed file and it reproduces the old
numbers exactly (gold 15.3 → 8.9, bands 13–22 and 8–13).

**Second, it fails the test it had never been given.** The claim was that
trading twenty configurations at a wide training floor is faster than trading
five *because the extra configurations trade the same edge*. The alternative
nobody had excluded: `expected days = median_days / pass_rate`, and more trades
a day shortens the numerator whether or not the trades are any good.

Pre-registered criterion: the real speed-up (15.3 / 8.9 = **1.72x**) survives
only if the **paired null's** speed-up is below 1.25x.

| market | real speed-up | null median | verdict |
|---|---|---|---|
| **XAUUSD** | **1.72x** | **2.45x** (2.10 / 3.97 / 2.45) | FAIL |
| XAGUSD | 1.53 | 2.69 | FAIL |
| EURUSD | 2.15 | 9.24 | FAIL |
| GBPUSD | 3.85 | 5.04 | FAIL |
| USDJPY | 1.70 | 4.11 | FAIL |
| BTCUSDT | 1.94 | 1.74 | FAIL |

**Six of six, and on four the null speeds up MORE than the real data does.**
Gold is the market the claim was about and every one of its three seeds beats
the real number. Stated against this study rather than for it: two seeds is thin
and USDJPY drew 0.99 and 7.23, so the thin cells prove nothing on their own —
gold's three seeds are what decides it.

**BTCUSDT — the sixth standard market, skipped last time — shows the mechanism
naked.** Every one of its ten cells loses money (PF@2x 0.44 to 0.80), and the
wide configuration still "resolves" an evaluation in **14.5 days against 28.2**.
A rule that loses 25 cents on the dollar reaches a verdict twice as fast when you
widen it. That is the whole effect, with the edge removed by construction.

### The method fix this exposes, and it is not small

**`expected_days = median_days / pass_rate` treats a blown account as free.**
Nothing in `core/scorecard.py` prices the evaluation fee. So any lever that
raises trade frequency can buy speed by spending accounts, and the board will
score it as an improvement.

Gold, like for like: the shipped rule passes 39.3% (**2.5 accounts per funded
seat**) and the wide one passes 33.9% (**3.0 accounts**). At €40–100 an
evaluation that is a real cost the board does not see.

**Owed:** report **accounts-consumed (1/pass_rate)** next to every expected-days
figure, and never compare expected days across configurations with different
trade frequencies without the null. Two other method debts are still open from
2026-09-13 — `core/probe.py`'s null does not match hour of day, and the search
is not priced (96 tests at a 95th percentile expect 4.8 false passes).

---

## Open, in the order the evidence favours

### A. Let the demo test finish. Cost: nothing. Ends 2026-09-28.

Day 7 of 18. Equity $10,130 (+1.3%), peak $10,464 (+4.6%), three legs open,
sizing scaled to x0.47 by the drawdown-budget rule. It cannot settle the 39%
pass rate — one account is one draw. It CAN settle what no backtest sees: whether
the fills match assumed costs (**measured: Bybit charges 5.50 bps round trip on
XAUUSDT, exactly 3.0x what `core/markets.py` assumes for a gold CFD**), and
whether the bot survives three weeks unattended.

**Read any "live validation" claim against this:** of the trades closed so far,
**not one exited by the rule's own stop or horizon** — Kris closed two by hand,
the exchange backstop took one.

### B. Answer blocker B1. One email. Open since 2026-09-08.

**Does the firm measure drawdown on EQUITY (open positions included) or on
CLOSED BALANCE?** H-039 measured what the answer is worth: pass rate and total
blow-ups are identical either way (50.0 vs 49.9), but **which cap kills the
account completely inverts** — fail-on-max 27.6% → 4.2%, fail-on-daily 22.4% →
**45.8%**, worst single day −3.10R → **−83.16R**.

Every board number silently assumes closed-balance. This is the cheapest
high-value item on the page and it is not a research task.

### C. Publish the TradingView indicator. Deliverable 2 of the three.

The code half is done. What is left is a decision, not a build: publishing puts
Kris's name on the claim, and the claim has to carry its band — 15.3 expected
days is 13–22, which overlaps the luck zone measured on 2026-09-08. His own
framing was that the honesty of the description matters as much as the numbers.
Independent of A and B.

### D. The only research direction with a live mechanism behind it

**Not another axis on H-027 — there are none left.** This is the answer to "it
seems impossible to create new ones that could have an edge", and the evidence
says the problem has been the MARKET, not the ideas.

**Five hypotheses died on cost, not on realness.** H-006, H-024, H-031, H-034
and H-042 are all real effects that beat their nulls and lose to the same
**14 bps** crypto round trip. Gross edges of 5–27 bps against a 14 bps bar.

**The bar on the markets that actually work is 8 to 50 times lower:**

| market | taker round trip |
|---|---|
| BTCUSDT / ETHUSDT | **14.0 bps** |
| XAGUSD | 9.1 |
| **XAUUSD** | **1.83** |
| GBPUSD | 0.72 |
| **EURUSD** | **0.27** |

A 5 bps edge is dead on crypto and is 2.7x its cost on gold, 18x on EURUSD.

**What blocked this before is no longer true.** CLAUDE.md records that gold
"trades naked" because every file in `data/feeds/` is a Binance crypto symbol.
H-045 disproved the general claim on 2026-09-15: **CBOE publishes GVZ free and
daily back to 2009**, and as a gate on H-027 it is the best filter result this
project has produced — the only one that raises profit factor AND R per day
together, against 24 of 25 entry filters that raised PF while lowering R/day.

**So the proposal is a feed hunt for gold and FX, where the cost bar is low and
exactly two feeds have ever been tried** (GVZ, real; CFTC positioning, dead).
Never touched here, all free and daily:

1. **US 10-year real yield — FRED `DFII10`** — the single most-cited driver of
   gold in the literature, and this repo has never loaded it.
2. **The broad dollar index — `DTWEXBGS`** (better than building DXY from the
   FX cache, and it is the series the literature uses).
3. **Breakevens — `T10YIE`** — inflation expectations, gold's other standard driver.
4. **The 2s10s curve — `T10Y2Y`.**

**All four were fetched on 2026-09-17 to confirm they exist**: no API key, plain
CSV, 967 daily rows each since 2023-01. `https://fred.stlouisfed.org/graph/
fredgraph.csv?id=<SERIES>&cosd=<start>`. This is an afternoon of work to cache,
not a project.

**The honest prior is poor and must be stated first.** Twelve price hypotheses
and five feed hypotheses have died here. A daily feed gives roughly 750 events in
three years, and the test window cap means that is the sample. Anything here
needs a pre-registered arm list, an hour-matched null and the fee test FIRST —
the order H-043 introduced and which saved a day.

---

## Blocked on Kris

| # | Question | Blocks |
|---|---|---|
| B1 | **Equity or closed-balance drawdown?** | which cap kills the account; whether a daily guard is worth building |
| B2 | **Is XAUUSD tradeable at the firm at all?** The offer shows crypto pairs; the only surviving hypothesis is gold-only. | whether the board describes a plan or a simulation |
| B3 | Any consistency rule? Current reading is **95.5% median best-day share** — any firm with one is unusable today. | which firms are even possible |
| B4 | Minimum trading days? Modelled as 0. | the 15.3-day headline |

B1 and B2 are one email and have been open since 2026-09-08.
