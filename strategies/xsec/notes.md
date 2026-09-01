# H-007 — Cross-sectional crypto ranking

**Status: rejected (board 3.0/10).** Requested by Kris; HANDOFF predicted it would
fail, and it did, though not for the reason that was predicted.

## Mechanism (stated before the results)

At any moment some coins are the ones flows are going into and others are being
left behind. The claim is that the *relative ordering* carries information the
individual price series does not, and that trading top-minus-bottom strips out
the market factor — if the whole complex rips, both sides move together and only
dispersion is left. On the other side: index-style and headline-driven buyers,
against liquidity providers who end up holding the laggard.

Two ranking signals, because they are two different hypotheses:

- `mom` — L-bar log return. The literal "rank coins, trade the spread" ask.
- `rvol` — volume over its own rolling median. This is the signal the equity ORB
  paper actually used (top 20 of 7,000 by opening relative volume), and
  `RESEARCH_LOG.md` lists the crypto analogue as next-candidate #2. It is the one
  with a mechanism rather than a pattern.

## What was run

`stage1_grid.py` — 360 configurations: 2 signals × {1h, 4h, 1d} × lookbacks
{3,6,12,24,48} × top/bottom k ∈ {1,2} × {spread, long-only} × 3 hold lengths,
each priced at 0x / 1x / 2x / 3x cost (Binance spot taker 5bps + 2bps slippage
per side). Every configuration is run again on 5 paired-shuffle null panels.

`stage2_walkforward.py` — quarterly walk-forward for board parity. The config for
quarter Q is chosen only on trades closed before Q, and chosen on **2x-cost**
profit factor, never 1x.

No lookahead: signal and volatility at bar t use bars up to and including t,
entry is the open of t+1, exit the open of t+1+H, and rebalances are
non-overlapping so trades never share a window.

## Result

| | real | paired null |
|---|---|---|
| configs clearing PF 1.20 at 2x | **23** of 360 | 0 / 1 / 2 / 9 / 14 (mean 5.2) |
| best config PF at 2x | 1.465 | **1.502** |
| median PF before costs (0x) | **1.096** | 1.009 |
| configs beating PF 1.0 at 0x | **95.0%** | 59.4% |
| walk-forward stitched PF | 1.168 | — |
| walk-forward PF at 2x | 1.063 | 0.833 / 1.059 / **1.065** / 0.962 / 0.985 |

## Reading

**The ranking is not noise.** Before costs it beats its paired null cleanly —
95% of real configurations are profitable against 59% of null ones, and the
median is 1.096 against 1.009. Something about the cross-sectional ordering is
real. That is the one genuinely interesting line here.

**It is far too small to trade.** The edge is worth roughly 10% on profit factor.
A round trip costs 14bps. Median PF falls 1.096 → 0.825 → 0.618 as cost goes
0x → 1x → 2x. Costs, not the signal, are the entire story.

**Everything that survives cost is a 7-day hold.** All 23 gate-clearing cells are
1d bars with H=7, ~0.14 trades/day, 301 trades over six years. `CLAUDE.md` says
longer-hold ideas are logged as future candidates, not built this phase — and
time-to-target is 400–875 days against H-002's 25.

**It does not beat its own null where it counts.** The best single null cell
(1.502) beats the best real cell (1.465), and in the walk-forward the best null
seed (1.065) beats the real stitched result (1.063). Cell counts favour the real
data; the extremes do not. One shuffle seed is a sample of size one, which is why
five were run — and the spread across them, 0 to 14 gate-clearing cells, is wide
enough that 23 is not the clean separation it looks like at first.

## The known weakness, unprompted

Five coins is not a cross-section. The published edge ranks 500–7,000 names; here
the "top vs bottom" of five high-beta majors with pairwise correlation above 0.7
is close to a coin-flip on dispersion, and the spread is close to a leveraged bet
on whichever alt is hottest. This is a fair test of *what is committed to the
repo*, not a fair test of the published hypothesis.

**The one thing that would change the answer:** a 50–100 coin universe. That
needs a data download, which `START_HERE.md` says not to do. It is the only open
route, and the 0x-cost result is the only reason it might be worth taking —
a real-but-tiny edge across five names could be a tradeable edge across a hundred,
because dispersion rises with universe size while the cost per trade does not.
