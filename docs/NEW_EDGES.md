# Where to look next — five candidates, scored. 2026-09-17

Kris, while the demo test runs: *"we need to find new bots new edges new
indicators new way of trading i dont know how... maybe watch new coins that are
added to binance every day... maybe speculating some coins on pump.fun... maybe
we can try to trade footprint charts."*

**Nothing here is started. This is the scoring sheet so he can pick one.**

Every candidate is scored on the four things that have actually killed ideas in
this repo, in the order they kill them:

| gate | what it asks | what it has killed |
|---|---|---|
| **1. Data** | can it be tested honestly, at all? | H-030 (no gold feed), H-035 (netflow is revised after the fact) |
| **2. Pace** | ≥40 events a year inside a 3-year window? | H-034 passed this; most never get asked |
| **3. Fee** | is the gross edge bigger than the round trip? | **H-006, H-024, H-031, H-034, H-042 — five real edges, all died here** |
| **4. Null** | does a shuffled version do as well? | H-003, H-005, H-010, H-043, and the top-N result on 2026-09-17 |

Gate 3 runs before gates 1 and 4 wherever the gross number is cheap to get.
That ordering was introduced by H-043 and it saved a day.

---

## 1. GOLD FOOTPRINT — Kris's third idea, and the best one on this page

**Status: the data was believed not to exist. It does. Verified today.**

`CLAUDE.md` carried a standing prohibition — *"order flow on GOLD is not
testable and no number may be quoted for it"* — on the grounds that
`data/dukascopy_raw/XAUUSD` holds bid candles rather than ticks. That is true of
what is **on disk** and false about what is **available**.

Dukascopy publishes **hourly XAUUSD tick files carrying ask, bid, ask volume and
bid volume**, and the fetcher has been sitting in this repo the whole time:

    core/fx_spread.py:62   URL = ".../{h:02d}h_ticks.bi5"
    core/fx_spread.py:64   TICK = struct.Struct(">IIIff")   # ms, ask, bid, askvol, bidvol
    core/fx_spread.py:106  ms[i], ai, bi, _, _ = TICK.unpack_from(...)   <- volumes discarded

Measured 2026-09-17, XAUUSD 2025-05-14:

| hour UTC | ticks | ask volume | bid volume | delta |
|---|---|---|---|---|
| 09:00 | 9,589 | 1.66 | 1.55 | +0.12 |
| 13:00 | 25,274 | 4.54 | 4.27 | +0.26 |

**That is a footprint.** Two-sided volume at tick resolution, aggregatable to any
bar size, on the one market this project actually trades.

**Mechanism.** Order-flow imbalance is the only family that has ever worked here
— *"every leg that ever worked came from a data feed, not from a price pattern"*.
Five of those feed edges were real, beat their nulls, and **died to crypto's
14 bps round trip**. Gold's round trip is **1.83 bps**. This is the family that
works, on the market that can pay for it, and it has never been run.

**The honest caveats, stated before any number:**

* **It is Dukascopy's liquidity-provider volume, not a central-exchange tape.**
  Spot gold has no central exchange, so there is nothing to validate it against.
  Ask/bid volume is indicative LP size, not confirmed executions. Any result has
  to carry this sentence.
* **H-024 is the warning.** Book-depth imbalance on crypto was real, monotone,
  beat its null, was stable across years — and cleared its cost in **0 of 935
  cells**, because the effect is a *three-second* one that does not reach 15m–4h.
  The same could be true here, and the cheap way to find out is gate 3 first:
  measure the gross forward return of the imbalance before building anything.
* The repo already has a coarse version of this for crypto (`data/feeds/
  *_taker_5m.parquet`) and it powered H-006, which died. Gold is the new part,
  not the technique.

**Cost to find out:** the download is ~19k files for three years; `fx_spread.py`
already has the fetcher, the retry logic and a 24-worker pool. Gate 3 needs one
day of ticks, not three years.

**Odds:** the best on this page, and still under 50%.

---

## 2. NEW BINANCE LISTINGS — Kris's first idea. Testable, with one serious flaw

**Mechanism.** A new listing brings forced and attention-driven buying into a
constrained float. Who is on the other side: early holders and the market maker
distributing into it. The effect is well documented and also well known, which
cuts both ways.

**Pace: PASS, and comfortably.** Listing dates are exact and free — a symbol's
listing date is the timestamp of its first daily kline. Counted today across all
493 trading USDT spot pairs:

| year | listings |
|---|---|
| 2023 | 36 |
| 2024 | 58 |
| 2025 | 100 |
| 2026 (to Sep) | 103 |

**274 events inside the 3-year window**, about 91 a year, against a floor of 40.

**The serious flaw: survivorship.** `exchangeInfo` returns only what is
**currently trading**. Delisted coins are gone from it — and a new listing is
exactly the population most likely to be delisted. A study built on this list
measures "listings that went on to survive", which is not a tradeable
population. **It must be fixed before any number is read**, by reconstructing the
delisted set from Binance's own announcement archive. That is the real work in
this idea.

**The second gate is the fee, and it is where this most likely dies.** Day-one
listings are thin and violent. This project charges crypto 14 bps; a fresh
listing plausibly costs 50–100 bps in spread alone, and that is **unmeasured**.
Per H-043's ordering, measure it first.

**Odds:** moderate that something is there, low that it survives the spread.

---

## 3. PUMP.FUN MEMECOINS — Kris's second idea. I would not spend the time

Said plainly, with reasons rather than an opinion:

* **The edge that exists there is speed, and we do not have it.** The money is
  made by snipers acting within blocks of deployment. That is an infrastructure
  race against people with co-located nodes, not a strategy question.
* **There is no honest backtest.** Reconstructing this needs full Solana
  transaction history, which is a paid archive node. Free APIs serve the
  survivors and the current state — the same defect that killed **H-035**, where
  every on-chain value was `flash`, revised later, and only the latest was
  served.
* **Rugs make the returns fiction.** A large share of tokens go to zero by
  design. A backtest that does not model a deployer pulling liquidity is not
  measuring the thing you would be trading.
* **The counterparty is adversarial and knows more than you.** This project's
  standard question is "who is on the other side". Here the answer is "the person
  who created the token".

**The version I would defend.** Do not trade the memecoins — **use their launch
activity as a risk-appetite feed** and trade BTC or SOL with it. Daily count of
new launches and of tokens that reach a bonding-curve graduation is a clean
measure of crypto speculative appetite, it is a **feed** rather than a price
pattern, and it trades a liquid instrument. That version passes gate 1. It still
has to clear crypto's 14 bps, which is what killed the last five feed ideas.

---

## 4. SCHEDULED MACRO EVENTS ON GOLD — the idea nobody has proposed here

**Mechanism.** Gold's largest moves cluster on CPI, FOMC and non-farm payrolls.
The time is known in advance, the uncertainty release is known in advance, and
the volatility regime around it is structurally different from every other hour.
Nothing in this repo has ever conditioned on a scheduled event.

**Pace:** ~12 CPI + 8 FOMC + 12 NFP = **32 a year, ~96 in three years.** Thin,
and honest about it: this is the H-043 problem, where 48 inverted days turned out
to be 17 episodes and two of them were half the sample.

**Data:** free. Release dates are public and fixed.

**Fee:** gold is 1.83 bps and these are the most liquid minutes of the month.
This is the one candidate where the fee gate is not the threat.

**The real risk is the opposite one:** the event is known to everyone, so the
move is fast and the slippage at the release is nothing like the average spread.
Measure the spread **in those minutes specifically**, not on average.

---

## 5. THE FRED MACRO FEEDS — cheapest of all, verified today

Four series, no API key, plain CSV, 967 daily rows each since 2023-01:

| series | what it is | why gold |
|---|---|---|
| `DFII10` | US 10-year real yield | the single most-cited driver of gold |
| `DTWEXBGS` | broad dollar index | the other standard driver |
| `T10YIE` | 10-year breakeven | inflation expectations |
| `T10Y2Y` | 2s10s curve | recession/risk regime |

`https://fred.stlouisfed.org/graph/fredgraph.csv?id=<SERIES>&cosd=<start>`

**This is an afternoon, not a project.** Precedent is good and bad: **H-045**
found GVZ/VIX this way and it is the best filter result the project has produced
— the only one that raises profit factor *and* R per day together. **H-043**
found the VIX term structure the same way and a shuffled version traded gold
better than the real one.

**Known dead in this family, do not redo:** CFTC positioning as a gate (H-030,
every gate slower than no gate) and the VIX term structure (H-043).

---

## Ranked, with the reason

| # | candidate | data | pace | fee bar | my odds |
|---|---|---|---|---|---|
| **1** | **gold footprint** | **proven today** | tick-level | **1.83 bps** | best here |
| 2 | FRED macro feeds | proven today | daily | 1.83 bps | cheap, precedent both ways |
| 3 | scheduled macro events | free | **96 events, thin** | 1.83 bps | clean mechanism |
| 4 | Binance listings | free, **survivorship** | 274 events | **unmeasured, likely fatal** | dies on spread |
| 5 | pump.fun directly | **no honest history** | — | — | do not |

**The pattern across all five.** Four of the top choices are on gold, and that is
not a preference — it is the arithmetic. Crypto charges 14 bps and has killed
five real edges; gold charges 1.83. The same 5 bps effect is dead on one and pays
2.7x its cost on the other.

**What has to be true before any of this starts:** a pre-registered arm list, an
hour-matched null (`core/probe.py`'s does not match hour of day — owed since
2026-09-13), and the search priced (96 tests at a 95th percentile expect 4.8
false passes). Without those this produces another 60%-pass artifact.
