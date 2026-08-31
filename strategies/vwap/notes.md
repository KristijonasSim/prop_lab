# H-002 — VWAP

## Why an edge could exist, and who pays for it

VWAP is the benchmark institutional execution is *graded against*. A desk working a
large order is measured on whether it beat the day's VWAP, which creates mechanical,
continuous flow around the line: a buy program that has fallen behind VWAP must buy
more aggressively, and passive liquidity accumulates near it.

This is a materially better fit for our markets than ORB was. ORB needed a once-a-day
auction, which crypto does not have and FX only half has. VWAP's mechanism runs all
session, every session.

## What the literature claims

**Zarattini & Aziz, "VWAP: The Holy Grail for Day Trading Systems".** Long above VWAP,
short below, flip on the cross. On QQQ: **+671% net of commissions, max drawdown 9.4%,
Sharpe 2.1.** Note the shape — a 9.4% drawdown with that return is the profile a prop
challenge wants, unlike the ORB papers' 24%-win-rate lottery tickets.

**Band fade (practitioner, not academic).** Bands at VWAP ± k x the volume-weighted
standard deviation. Fade the 2-3 sigma touch, target VWAP. The universally stated
caveat: it works in balanced sessions and is a fast way to lose money on a trend day,
so it needs a regime or volume filter to be tested honestly.

## Prior evidence from Kris's earlier repo (`~/trading-bots`)

- **VWAP trend / stop-and-reverse on BTC: DEAD.** PF 0.99-1.02 at *zero* fee across
  3m-4h, three years. Not a cost problem, no signal.
- **The same mechanic had real edge on Gold, USDJPY and NAS100.** Explicitly recorded as
  asset-specific, not a dead family. We now have gold and USDJPY, so this is the first
  hypothesis we can test where the prior repo says it should work.
- **VWAP standard-deviation band fade: backtested PF 3.0, traded live at ~0.7.** Root
  cause: a resting-limit backtest assumes a fill whenever a wick touches the level,
  which cannot be verified against real order-book queue priority.

That last one dictates the method. **Every band strategy is run twice** — once with a
resting limit at the band (maker, optimistic, unverifiable) and once requiring a close
beyond the band with entry at the next open (taker, honest). The gap between those two
numbers IS the finding; the limit version is a diagnostic, never a result.

## Model families tested

| # | Family | Entry | Mechanism |
|---|---|---|---|
| 0 | Trend / stop-and-reverse | long above VWAP, short below, flip on cross | ride institutional flow chasing the benchmark |
| 1 | Band fade | enter against a k-sigma extension | provide liquidity to a stretched program |
| 2 | Band breakout | enter with a break of the k-sigma band | extension signals a real imbalance, not noise |
| 3 | VWAP reclaim | price returns through VWAP after being beyond a band | failed extension, flow flips |
| 4 | First pullback | first touch back to VWAP in the session's direction | the classic desk entry |

## Carried over from H-001 (ORB), already proven on this data

- Do **not** add breakeven stops (-0.078 median PF) or retest entries (-0.029). Tested,
  they destroy edge.
- Relative-volume filters are the only filter family that lifted a median.
- The NY cash open (13:30 UTC) is the only session anchor that carried anything.
- Report PF at 1x, 2x and 3x cost. The ORB winner died between 1.0x and 1.6x.
- Judge a filter by the paired lift on the **median**, never by a new best.

## Sources

- <https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4631351>
- <https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4824172>
- <https://www.quantifiedstrategies.com/intraday-momentum-trading-strategy/>
