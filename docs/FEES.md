# What trading actually costs — venues and assets ranked, 2026-09-22

Kris: *"is there a way we could make our fees lower? compare trading gold on
Interactive Brokers vs prop firms. does it depend that much on a broker? rank
brokers top 10, and rank assets by fees."*

**Everything below is one number: the ROUND-TRIP cost of a $50,000 position, in
basis points of notional.** That is the bar an edge has to clear, and it is the
only cost measure that compares a gold futures contract to a Bitcoin perp.

Arithmetic: `/tmp/.../fees.py`, reproduced in §6. Gold $4,353, EURUSD 1.08,
ES 6,900 (2026-09-22).

---

## 1. The answer in four lines

1. **The asset matters ~30x. The broker matters ~2x.** Crypto costs 11–21 bps
   round trip; gold futures cost 0.67. Switching venue inside an asset class
   saves tens of percent; switching asset class saves an order of magnitude.
2. **Interactive Brokers and the futures prop firms charge almost exactly the
   same** on micro gold — $1.90 vs $1.92 per round turn. **Fees are not the
   reason to choose between them.** Capital and rules are.
3. **Gold futures (MGC) at ~0.67 bps against the CFD we model at 1.83 bps.**
   That is a **2.7x** cut in the cost bar, and it comes with a real tape.
4. **Crypto was never going to work here and now we can say by how much.** Five
   dead feed hypotheses had gross edges of 5–27 bps against a 14 bps bar. The
   same edges on gold futures face **0.67**.

---

## 2. Assets ranked by cost — cheapest first

| # | asset | instrument | round trip | notional needed |
|---|---|---|---|---|
| 1 | **FX majors** | EURUSD, raw broker | **0.27–0.57 bps** | any |
| 2 | **Large ETFs** | SPY-type, $700 share | **0.28 bps** | any |
| 3 | **Gold, full futures** | GC, 100 oz | **0.33 bps** | **$435,000** |
| 4 | **Index, full futures** | ES | **0.49 bps** | **$345,000** |
| 5 | **Index, micro futures** | MES | **0.65 bps** | $34,500 |
| 6 | **Gold, micro futures** | **MGC, 10 oz** | **0.67 bps** | **$43,530** |
| 7 | **Gold CFD** | XAUUSD | **0.6–1.8 bps** | any |
| 8 | **Silver CFD** | XAGUSD | **9.1 bps** (measured here) | any |
| 9 | **Crypto perps** | BTC, best tier | **8.5–12 bps** | any |
| 10 | **Crypto spot** | BTC | **16–21 bps** | any |
| — | *cheap shares* | $20 share | *8.5 bps* | any |

**Two things fall out of this table that are not obvious.**

* **The big contracts are the cheap ones, and we cannot afford them.** GC at
  0.33 bps is half the price of MGC at 0.67, purely because the commission is a
  fixed dollar amount spread over 10x the notional. A $50k prop account cannot
  hold one GC contract. **Cost per bp is bought with account size.**
* **Cheap shares are expensive.** Stock commission is per SHARE, so a $20 stock
  costs 10x a $200 stock for the same dollars traded. Anyone screening equities
  here must price by share count, not by notional.

---

## 3. Venues ranked — best to worst, for what we actually trade

| # | venue | best use | round trip | automation |
|---|---|---|---|---|
| 1 | **Interactive Brokers** | gold + index futures, FX, equities, all in one account | **0.33–0.89 bps** | full API, no restrictions |
| 2 | **Topstep** (futures prop) | gold futures on someone else's capital | **0.67 bps** (MGC) | **allowed on funded accounts**, official API |
| 3 | **Apex** (futures prop) | up to 20 funded accounts | ~0.6 bps (MGC) | **BANNED on funded accounts** |
| 4 | **IC Markets Raw** (cTrader) | FX, if not using IBKR | 0.57 bps | cTrader Open API |
| 5 | **Dukascopy** | FX + metals, and it is our data source | 0.27 bps FX / 1.64 gold, **commission not measured** | JForex API |
| 6 | **Pepperstone Razor** | FX | 0.74 bps | cTrader / MT5 |
| 7 | **FundingPips / CFD props** | gold CFD, high leverage, cheap entry | 0.6–1.8 bps | cTrader, varies by firm |
| 8 | **Binance futures** | crypto, if crypto at all | 11 bps | full API |
| 9 | **OKX futures** | crypto | 11 bps | full API |
| 10 | **Bybit futures** | crypto — and **what the demo bot is on** | 12 bps | full API |

**Bybit is last on this list and it is where our live bot is.** Measured on the
actual account: **5.50 bps round trip on XAUUSDT, 3.0x what `core/markets.py`
assumes for gold.** That was a connector decision, not a cost decision, and it
is costing 8x what Topstep would.

---

## 4. IBKR vs prop firms — the comparison Kris asked for

Micro gold, one contract, $43,530 notional:

| | commission, round turn | spread, 1 tick | **total** |
|---|---|---|---|
| **Interactive Brokers** | ~$1.90 ($0.25 comm + ~$0.70/side fees) | $1.00 | **~0.67 bps** |
| **Topstep** | **$1.92** ($0.50 comm + $1.40 exch + $0.02 NFA, per side) | $1.00 | **0.67 bps** |

**Identical.** The futures prop firms are not marking up the trade; they pass
through CME's fees and add about fifty cents a side. So the choice is not about
cost at all:

| | Interactive Brokers | Topstep |
|---|---|---|
| **whose money** | **yours** | theirs — ~$50k buying power for ~$150 |
| **drawdown rules** | none | **trailing max loss, and it never moves back down** |
| **profit split** | 100% | 90% after the first $10k |
| **failure cost** | your capital | the evaluation fee |
| **automation** | unrestricted | allowed, evaluation **and** funded, official API |
| **scaling to 10–20 accounts** | needs 10–20x the capital | buy 10–20 evaluations |

**This is the real trade.** IBKR is cheaper in rules and identical in fees, but
it needs Kris's own money. The prop route buys size for a fee and pays for it in
constraints. Kris's stated goal — 10–20 funded accounts — only works on the prop
route, and **Topstep is the only firm found so far that permits a bot on the
funded account**. Apex allows 20 accounts and bans the bot on all of them.

**Where CFD prop firms are genuinely more expensive:** they quote a marked-up
spread instead of a commission. Advertised gold spreads are 10–30 cents raw and
20–50 cents on standard accounts (0.23–1.15 bps), and those are **peak-liquidity
advertised numbers**. Our own all-hours measured Dukascopy mean is 71 cents
(1.64 bps). The two are not comparable and the marketing number is the
optimistic one.

---

## 5. What this changes here

**Nothing is chosen. These are the consequences if Kris wants them.**

1. **The cost bar for any gold study could drop from 1.83 bps to 0.67.** That is
   the single biggest lever on this project's hit rate that does not involve
   finding a new edge — it makes a 1.5 bps effect go from *marginal* to *2.2x
   its cost*.
2. **It is not free.** MGC is **$43,530 of notional in one indivisible
   contract**. Every risk number in this repo assumes position size is
   continuous. On a $50k account the ladder becomes 1 contract or 0, and
   `core/riskladder.py` has to be re-simulated in integers before any board
   number means anything on futures.
3. **Gold futures data is not on disk.** Everything cached is the Dukascopy CFD.
   Moving to MGC means a new data source and re-running the walk-forward, not a
   change of constant.
4. **The demo bot is on the most expensive venue in the table.** Whatever the
   3-week test concludes about fills, it concludes it at 5.50 bps.
5. **Crypto's 14 bps is confirmed and is not improvable.** Best realistic tier
   is 8.5 bps and requires volume we will not do. The five dead feed hypotheses
   stay dead on crypto and would need re-testing on gold to be revived.

---

## 6. Caveats, stated plainly

* **Spread is assumed at one tick for every futures line.** True most of the
  session on MGC and ES; false at the open, at rollover and in thin hours. Our
  own gold measurement shows the all-hours mean is far worse than the headline.
* **IBKR's MGC exchange/clearing fee is an estimate (~$0.70/side)** from a
  third-party comparison, because interactivebrokers.com blocks automated
  fetching. Topstep's $1.92 is from Topstep's own published fee table and is
  solid. **Confirm IBKR's on a real statement before trusting the tie.**
* **Dukascopy FX at 0.27 bps and gold at 1.64 bps are SPREAD ONLY.** Dukascopy
  charges a separate volume commission that this repo has never measured. Our
  FX cost assumptions are therefore optimistic by an unknown amount.
* **Crypto tiers move.** The 8.5 bps figure needs VIP volume plus BNB holdings.
* **No slippage is in any line.** Measured impact at $50k clips is ~0.02 bps on
  BTC (`strategies/depth/stage2_cost.py`), so it is genuinely small at our size
  — but it is not zero on thin instruments in bad minutes.

---

## Sources

- [Topstep — TopstepX commissions and exchange fees](https://help.topstep.com/en/articles/8284213-topstepx-commissions-and-fees)
- [Interactive Brokers — futures commissions](https://www.interactivebrokers.com/en/pricing/commissions-futures.php)
- [Interactive Brokers — spot currency commissions](https://www.interactivebrokers.com/en/pricing/commissions-spot-currencies.php)
- [Interactive Brokers — stock commissions](https://www.interactivebrokers.com/en/pricing/commissions-stocks.php)
- [BrokerChooser — IBKR micro gold futures fees](https://brokerchooser.com/broker-reviews/interactive-brokers-review/micro-gold-futures-fees)
- [BrokerChooser — best brokers for micro gold futures](https://brokerchooser.com/best-brokers/best-brokers-for-trading-micro-gold-futures)
- [ForexBrokers.com — IC Markets vs Pepperstone](https://www.forexbrokers.com/compare/ic-markets-vs-pepperstone)
- [BrokerChooser — lowest spread forex brokers, Europe](https://brokerchooser.com/best-brokers/best-forex-brokers/lowest-spread-forex-brokers/europe)
- [crypto.news — maker and taker fees across 8 exchanges](https://crypto.news/maker-and-taker-fees-compared-across-8-crypto-exchanges/)
- [Coin Bureau — Bybit vs OKX 2026](https://coinbureau.com/review/bybit-vs-okx)
- [TheTrustedProp — best prop firms for gold (XAUUSD) 2026](https://thetrustedprop.com/blogs/best-prop-firms-to-trade-gold-xauusd-2026)
- [CME Group — gold futures contract specs](https://www.cmegroup.com/markets/metals/precious/gold-futures.html)

---

# 7. Futures vs CFD, and Alpha Futures — asked 2026-09-22

## 7.1 Alpha Futures is out, on their own rule

> *"Automated trading bots and AI-based trading mechanisms are strictly
> prohibited on Alpha Futures accounts. Semi-automated execution with active
> oversight is allowed."*

Their universal rules list **EAs, bots, HFT and tick-scalping** as prohibited
strategies. Everything this project builds is a bot. It does not matter that
their end-of-day drawdown is friendlier than Topstep's trailing one.

*Worth keeping in view anyway:* Alpha uses **EOD drawdown**, not intraday
trailing, and their Zero plan has no consistency rule in the evaluation. If the
automation rule ever changes, the risk shape is better than Topstep's.

## 7.2 The firms that do allow a bot on a FUNDED account

Sourced from aggregators, September 2026, and **every line needs confirming on
the firm's own page before a cent moves** — `CLAUDE.md` already records two
firms (Blue Guardian, City Traders Imperium) recommended here on comparison-site
data that turned out wrong, and the sources below already contradict each other
about Apex.

| firm | eval | funded | max funded accounts |
|---|---|---|---|
| **Topstep** | yes | **yes** | 5 x $150k |
| **Bulenox** | yes | yes | 11 x $250k |
| **Phidias** | yes | yes | 15 x $150k |
| **IQ Capital** | yes | yes | 10 x $100k |
| Lucid, FundedNext, Tradeify, TradeDay, Blusky | yes | yes | 3–5 x $150k |
| **Apex** | yes | **disputed** — our 2026-09-21 source says banned on funded, an aggregator says allowed | 20 |
| **Alpha Futures** | **no** | **no** | — |

## 7.3 THE BLOCKER, and it is bigger than fees

Topstep's funded-account rules, as reported:

> *"Trade copiers cannot be used on Live Funded Accounts... mirrored trading,
> hedging behavior, or risk-stacking across accounts is strictly prohibited and
> subject to behavioral review."*

**Kris's stated goal is 10–20 funded accounts running the same bot.** That is,
read literally, mirrored trading. A bot allowed on *one* funded account and
banned across *ten* is a completely different business.

**This is now the first question to ask any futures firm, ahead of price, ahead
of drawdown type.** It sits with B1/B2 as a one-email item.

## 7.4 The thing that breaks if we move to futures: whole contracts

One MGC is 10 oz = **$43,326** of gold. Measured on gold 1h over the last twelve
months, the session VWAP sigma the shipped rule sizes its stop from has a median
of **$12.37/oz**, so one contract risks **$371 at a 3-sigma stop and $495 at 4**.

Contracts affordable on a **$50,000** account:

| risk per trade | $ at risk | contracts, 3σ stop | contracts, 4σ stop |
|---|---|---|---|
| 0.25% | 125 | 0.34 | 0.25 |
| 1.00% | 500 | 1.35 | 1.01 |
| **2.00%** | 1,000 | **2.70** | **2.02** |
| **4.00%** | 2,000 | **5.39** | **4.04** |

**Read the bottom two rows and then remember the rule trades FIVE settings in
parallel at a fifth of the risk each.** At 4% total that is 0.8–1.1 contracts per
leg; at 2% it is 0.4–0.5. **The shipped rule cannot be expressed in whole MGC
contracts on a $50k account.** It needs roughly $150k — Topstep's largest — to
give each leg 2–3 contracts, or it has to drop to one setting, which
`core/chosen.py` rejected explicitly because a single setting resolves an
evaluation on two or three trades.

Nothing in `core/riskladder.py` models integers. Every pass-rate and expected-days
number in this repo assumes continuous size.

## 7.5 So: are futures better for us?

**On the evidence, yes — but it is a rebuild, and it is not the next thing.**

**For:**
* **0.67 bps against 1.83.** The cost bar falls 2.7x. Nothing else available
  moves the hit rate that much without finding a new edge.
* **A real tape.** Spot gold has no central order book, which is why H-052's
  order-flow work rests on one broker's indicative quote size. COMEX has one
  book, one public print. **Every leg that has ever worked in this project came
  from a data feed** — futures is the only route to an honest one on gold.
* **Automation is explicitly permitted** at several firms, in writing, on funded
  accounts. On the CFD side it is "varies by firm" and mostly undocumented.
* Regulated exchange; nobody marks our P&L against us.

**Against, and these are not small:**
* **Whole contracts break the shipped rule at $50k** (§7.4). Real modelling work
  before any board number transfers.
* **No futures data on disk.** Everything cached is the Dukascopy CFD. New
  source, new cache, re-run the walk-forward — days, not hours.
* **Topstep's drawdown trails the highest end-of-day balance and never moves
  back down.** `CLAUDE.md` puts trailing-vs-static at up to **17 points of pass
  rate**. The 0.67 bps saving could be handed straight back.
* **Session hours differ** — futures are ~23/5 with a daily break, the CFD is
  24/5. H-027 is session-anchored, so the anchor itself may move.
* **The mirroring rule may kill the multi-account plan** (§7.3).

**What I would do about it, in order:**

1. **One email, to Topstep, before anything else.** Three questions: can a fully
   automated bot run on a funded account; can the *same* bot run on several of
   our accounts; is the drawdown trailing on intraday or on end-of-day balance.
   Free, and it decides whether §7.5 is a plan or a daydream. Fold it in with
   the B1/B2 email that has been open since 2026-09-08.
2. **Do not port anything yet.** We do not have a rule that clears the 5–14 day
   pace bar. A cheaper venue does not create one — it widens what the *factory*
   can find, which is exactly why this matters later and not now.
3. **When the factory produces its first survivor, price it on MGC, not on the
   CFD.** That is a one-line change to the cost assumption and it costs nothing
   to carry from the start.
4. **Keep gold futures as the target venue for the order-flow work** (H-052).
   That is the one research direction where the venue change is the point rather
   than a discount.

## Sources added 2026-09-22

- [Damn Prop Firms — 8 algo-trading futures prop firms, verified Sept 2026](https://damnpropfirms.com/best-prop-firms-for-algo-trading/)
- [PropFirmPlus — algo trading on futures prop firms, what's allowed in 2026](https://propfirmplus.com/algo-trading-on-futures-prop-firms-whats-actually-allowed-in-2026/)
- [Alpha Futures — futures prop firm rules explained 2026](https://alpha-futures.com/posts/futures-prop-firm-rules-explained-2026)
- [PropTradingVibes — Alpha Futures rules, complete guide](https://proptradingvibes.com/blog/alpha-futures-rules-overview)
- [Topstep — Live Funded Account rules](https://www.topstep.com/live-funded-account-rules)
- [For Traders — Topstep funded account rules, 2026 operating map](https://fortraders.com/blog/topstep-funded-account-rules)
