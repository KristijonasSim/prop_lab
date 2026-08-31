# ORB — Opening Range Breakout

## What it is

Mark the high and low of the first N minutes after a session opens. Go long on a
break above the high, short on a break below the low. Exit on a stop, an R
multiple, or at the session close.

On a 24/7 market like BTC there is no opening auction, so the "session" has to be
picked by hand — 00:00 UTC, the London open, or the New York open. That choice is
a free parameter, which is itself a warning sign.

## Claimed mechanism (from the literature)

**Zarattini, Barbon & Aziz 2024 — US equities, 7,000+ stocks, 2016-2023.**
5-minute opening range, stop order beyond the range, stop at 10% of the 14-day
ATR, target = end of day, 1% risk, 4x leverage cap.

- Unfiltered ORB: **+29% total, 41.4% win rate, Sharpe 0.48.** Barely anything.
- Filtered to the top 20 "stocks in play" by opening relative volume:
  **+1,637%, 48.4% win rate, Sharpe 2.81, 12% max DD.**

The stated mechanism is *not* the price pattern. It is that overnight news forces
institutions to reprice a stock, and that repricing shows up as abnormal order
flow concentrated into the first minutes of the single daily auction. The
opening range is a proxy for "an informed participant is working a large order
right now". The 56x gap between the unfiltered and filtered versions is the whole
story: **the relative-volume filter is the edge, the breakout is just the trigger.**

**Zarattini & Aziz 2025 — QQQ / TQQQ.** 5-min range, enter in the direction of the
first candle, stop at the candle's opposite extreme, target 10R or EOD.
QQQ +676%, **24% win rate**, Sharpe 1.13, 22% max DD. Explicitly assumes **no
slippage**. The 24% win rate is the wrong shape for a prop challenge: the payoff
depends on rare 10R winners, so a losing streak breaches the daily cap long
before the big winner lands.

## Why it may not transfer to BTC

Who is on the other side? In equities, a market maker who has to reprice against
informed flow at a once-a-day auction. On BTC there is:

- no auction and no single open — order flow is spread across 24 hours;
- no overnight accumulation of unexecuted orders to release at 09:30;
- no news gap concentrated at one clock time;
- a continuous, arbitraged, fully electronic book across dozens of venues.

So the specific imbalance the papers exploit does not have a place to build up.
What is left is "price broke a recent high, buy it" — a generic momentum trigger
that has to pay costs on every attempt.

## Prior evidence against (Kris's own earlier repo, `~/trading-bots`)

- Session-anchored ORB **failed on BTC and on real Gold / Silver / Nasdaq futures**,
  every timeframe, both NY and London sessions.
- `session_orb` with a real London/NY clock scored **PF 0.986** and did not beat a
  plain UTC anchor.
- Breakout + retest failed at every timeframe 3m-4h; its *inverse* (fade the
  breakout) is what worked.
- Larry Williams daily range breakout: PF 0.88-1.00 at taker cost.

This test is therefore a **re-examination, not a fresh idea.** It is worth
re-running only because (a) it is being tested here with a different exit and
sizing model, (b) the relative-volume filter — the part the literature says is the
actual edge — is being tested explicitly, and (c) the fade variant is in the grid.

## Cost reality on a 30-minute BTC range

A 30-minute opening range on BTC is typically 0.3-0.5% wide. If the stop sits at
the far side of the range, that whole width is 1R. Binance spot taker at
0.10%/side is 0.20% round trip = **~0.5R of cost per trade**. Futures taker at
0.05%/side is ~0.25R. This is why the base venue assumption here is the USDT-M
perpetual, and why every result is also reported at **zero cost** — that run is
the diagnostic that separates "no edge" from "edge eaten by fees".

## Sources

- <https://www.sfi.ch/en/publications/n-24-98-a-profitable-day-trading-strategy-for-the-u.s.-equity-market>
- <https://concretumgroup.com/a-profitable-day-trading-strategy-for-the-u-s-equity-market/>
- <https://danfin.net/opening-range-breakout-research>
- <https://www.luxalgo.com/library/concept/opening-range-and-orb/>
