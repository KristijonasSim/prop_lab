# H-048 — pump.fun. What is testable, what is not, and the test that will be.

2026-09-17. Kris: *"yes try something with pump.fun maybe follow whales maybe
follow telegram accounts and try to trade with them etc etc"*.

I argued against this in `docs/NEW_EDGES.md` on data grounds. Kris asked anyway,
so it was **probed rather than re-argued**, and the probe changed the answer from
"don't" to "you can't yet, and here is how that stops being true".

## What was probed, 2026-09-17

| endpoint | result |
|---|---|
| `frontend-api-v3.pump.fun/coins?offset=500` | works — **39 minutes back** |
| `...?offset=2000` | **empty. That is the wall.** |
| `frontend-api-v3.pump.fun/coins/{mint}` | **works for any mint, at any age** |
| `.../trades/{mint}`, `/trades/all/{mint}` | **404 — the trade endpoint is gone** |
| `frontend-api.pump.fun` (v1) | 530, dead |
| GeckoTerminal OHLCV, Solana pool | 1000 hourly bars a call, **pages back fine** |
| Dexscreener search | works |

## The conclusion, which is about the population and not the idea

**Prices are available. The list of historical launches is not.** The API serves
about forty minutes of launch history and nothing beyond it. Per-wallet trade
history — *real* whale following, the thing Kris actually asked for — needs a
Solana archive node, which is a paid service.

**So there is no honest backtest of pump.fun today, at any price we are paying.**
That is now demonstrated rather than asserted, which is the difference between
this entry and the one in `docs/NEW_EDGES.md`.

**What is free is enough to build the dataset going forward**, and the collector
is running: `strategies/pumpfun/collect.py`, one pass every 15 minutes into
`data/pumpfun/launches.jsonl`. Precedent is the `data/feeds/` collectors, which
is how every crypto feed in this repo came to exist.

## "Follow whales" becomes testable as FOLLOW THE DEPLOYER

`creator` is on every record. That turns the untestable question into one that
needs no archive node:

> **Does a creator's track record predict their next launch?**

Rank creators by the ATH market cap of their previous launches; test whether the
next launch beats one from a creator with no record.

**Why ATH and not a return.** Nobody can sell at the ATH, so this is not a
tradeable number and is not offered as one. It is a **screen**: if prior success
does not predict even the most generous possible outcome measure, it cannot
predict a tradeable one, and the idea dies without a price feed. A pass here
earns a second study with real fills; it is not itself a result.

## Pace — measured, and better than expected

From the first pass, 210 launches spanning 72 minutes:

| | |
|---|---|
| launch rate | **~4,200 a day** |
| distinct creators in 210 launches | 131 |
| **creators with more than one launch inside 72 minutes** | **29** |
| graduated to a real pool | 7 of 210 (**3.3%**) |
| ATH market cap | median **$3,726**, p90 $8,654, max $2.38M |

**Serial deployers are common**, which is what gives the creator test its power,
and it arrives in days rather than weeks. **The base rate is brutal and is the
thing to keep in view**: 97% never graduate and the median launch tops out under
four thousand dollars. Any edge here lives entirely in a thin tail, which is the
shape that most easily fakes a result in a mean.

## Kill criteria, fixed now, before any data has accumulated

1. **No creator effect on the screen.** If launches from creators with a prior
   top-decile ATH do not beat first-time creators, dead.
2. **The effect is in the mean and not the median.** With a max/median ratio of
   638 here, a mean-based pass is the H-047 skew trap and will be treated as a
   failure, not a finding.
3. **It does not survive a creator-shuffled null** — same launch outcomes,
   creator labels permuted.
4. **It needs more than 3.3% of launches to work.** A signal that only fires on
   graduating tokens is selecting on the outcome.

## Not attempted, and why

* **Telegram call-following.** Needs historical channel messages with timestamps,
  which needs a Telegram API credential tied to **Kris's own phone number**.
  Cannot be done without him. If he wants it, the credential is the blocker, not
  the code.
* **Sniping the first blocks.** The edge there is latency against co-located
  bots. Not a strategy question and not one this stack can win.
* **Anything involving holding a position in these tokens**, until the screen
  above passes. The rug risk is not modellable from the data collected here.
