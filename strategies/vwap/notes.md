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

## Stage 18 — the gold book, at measured cost, and what combining the cells buys

TASK T3 item 1 and TASK T5 from `NEXT.md`. Code: `stage18_goldbook.py`.
Output: `backtests/vwap/stage18_gold_{cells,books}[_null].csv`.

### The re-pricing is exact

The walk-forward stored every trade at 1x and 2x cost and R is linear in cost,
so `C/risk = r_1x − r_2x` and any cost level follows. XAUUSD was walked forward
at an **assumed** 1.50bps/side (3.00 round trip). `core/fx_spread.py` sampled
478 hours of Dukascopy ticks: median spread 1.621bps of mid, mean 1.671, plus
~0.15bps round-trip cTrader commission — **1.83bps round trip**. Scale 0.61.

### Single cells, post-fix walk-forward, measured cost

| cell | trades | PF | maxDD | R/day | tpd | pass | median d | **expected d** |
|---|---|---|---|---|---|---|---|---|
| 4h floor30 top1 | 102 | 2.098 | 4.81R | 0.059 | 0.17 | 0.742 | 143 | **192.9** |
| 1h floor100 top10 | 1,908 | 1.601 | 9.49R | 0.083 | 3.10 | 0.787 | 165 | 209.6 |
| 4h floor100 top1 | 196 | 1.561 | 7.97R | 0.077 | 0.32 | 0.871 | 190 | 218.1 |
| 5m floor100 top10 | 2,308 | 2.021 | 10.79R | 0.235 | 3.73 | 0.779 | 170.5 | 218.8 |

The 5m cell reproduces SESSION_2026-09-06's headline (PF 1.879 → 2.021 here,
median 173 → 170.5; the small gap is the common-window cut this applies so every
cell is scored over identical dates). **17 of 20 real cells clear PF 1.20
against 5 of 20 for the paired null**, real best 2.109 against the null's 1.679.

### Combining the cells nearly halves the time

Two cells on the SAME timeframe are one walk re-selected, not two legs, so the
rule is **one cell per timeframe** — five genuine legs, 26 combinations, three
weightings each.

| book | trades | PF | maxDD | R/day | tpd | pass | median d | **expected d** | one-step |
|---|---|---|---|---|---|---|---|---|---|
| **5m + 4h, equal** | 2,504 | 1.849 | 8.00R | 0.156 | 4.05 | 0.899 | **90** | **100.2** | **46.9** |
| 5m+15m+4h, sig/cost | 5,062 | 1.796 | 7.68R | 0.172 | 8.16 | 0.897 | 92.5 | 103.1 | 50.3 |
| 5m+15m+4h, by R | 5,062 | 1.781 | 7.93R | 0.175 | 8.16 | 0.897 | 96 | 107.0 | 49.3 |
| *best single cell* | *102* | *2.098* | *4.81R* | *0.059* | *0.17* | *0.742* | *143* | *192.9* | *89.5* |

**193 expected days becomes 100.** The mechanism is visible in the columns: the
pair's R/day is 2.6x the best single cell's while its drawdown only rises from
4.81R to 8.00R, so `days = maxDD / R_per_day` falls. The 5m and 4h cells are
different holds on one instrument and they do not draw down at the same time.

**H-012's dilution warning did not bite, and it is worth saying why.** There,
adding legs made a book slower because the median leg had R/day −0.0013 and
equal weighting divides the book's R by the leg count. Here every leg has
positive R/day on the same instrument, so the division is against a positive
number. Equal weighting actually **beat** signal-to-cost weighting (100.2 days
against 143.7 for the same pair), which says the two legs are close enough in
quality that any tilt is noise.

### The null was searched exactly the same way

The whole procedure — pick a representative cell per timeframe on total R, build
all 26 combinations under all 3 weightings, take the fastest — was repeated on
`stage6_trades_shuffled_paired.parquet`.

| | real | paired null |
|---|---|---|
| books under 150 expected days | **9 / 78** | **0 / 78** |
| fastest book | **100.2 d** | 300.7 d |
| fastest book's PF | 1.849 | 1.272 |
| cells clearing PF 1.20 | 17 / 20 | 5 / 20 |

So the search that produced 100 days is controlled: the same search on
phase-randomised markets never gets under 150.

### Caveats, unprompted

- **The pairing is a maximum over 78 books chosen on the window it is scored
  on.** The null controls the search, but a held-out window would settle it and
  there is not one. This is the weakest joint in the result.
- **100 days is still 2.2x the 45-day target.** The honest headline has not
  changed shape, only size.
- **The one-step number is 46.9 days.** If the firm turns out to be one-step,
  this book is at the target already. That makes the firm question (T4/B1) worth
  more than any further tuning here.
- Seven walk-forward quarters, 2024-09 to 2026-05. Gold's cached history starts
  2023-09, so there is no more to hold out.

## Stage 17 — the gold legs through an independent engine. They survive.

TASK T2 from `NEXT.md`, and it was called "the highest-risk item on the list":
gold is the whole book and had never been checked by anything but the kernel
that produced it. Code: `stage17_goldnautilus.py`.
Output: `backtests/queue/stage17_gold_nautilus.csv`.

### What was actually tested

The only cross-check this project had ever run covered **one configuration on
one market** — BTCUSDT 4h, MODE_BREAK, rolling anchor, no target. Gold's folds
select twenty-five different rule shapes: five entry modes, three anchors
(rolling, midnight, London), both stop modes, two target modes, holds from none
to 144 bars. Each one was run over the full XAUUSD series in both engines and
compared trade by trade.

The Nautilus strategy is handed one bar at a time and holds no array it could
index into. Indicators are rebuilt incrementally, including the awkward ones:
the session VWAP and its volume-weighted sigma, the rvol baseline over prior
bars only, the ATR percentile rank, and the `while i < stop_bar` loop's habit of
**never visiting the bars a trade occupies** — which MODE_TREND's `prev_side`
and MODE_RECLAIM's stretched flags depend on.

### Result

| timeframe | configs | entry bars match exactly | worst |
|---|---|---|---|
| 5m | 13 | **13 / 13** | 1.0000 |
| 1h | 12 | **11 / 12** | 0.8754 |

Matched trades agree on entry price to the cent and on R to 1e-14 - 1e-8.

### Three bugs were found on the way and all three were the PORT's

Worth recording because a port that agrees immediately usually means the port
is wrong in the same way as the thing it is testing.

1. **`atr_rank` was ranked one bar early.** The kernel builds it as
   `rolling(5760).rank(pct=True).shift(1)` and reads it at `entry_i`, so the
   value is the rank of `atr[i]` in a window ending at `i`. Ranking before the
   append gave `atr[i-1]`. Cost: 40% of the entries.
2. **Zero-volume bars.** `sweep.vwap_series` does
   `volume.replace(0, nan).ffill().fillna(1.0)`, so a zero-volume bar is
   weighted by the LAST NON-ZERO volume. The port weighted it 1.0, which is what
   the BTC port did and is harmless on a perpetual. XAUUSD 1h has **4,819
   zero-volume bars** out of 22,512, so it moved the VWAP everywhere.
3. **`prev_vwap` was overwritten** with the current bar's value before
   MODE_RECLAIM and MODE_PULLBACK compared against it.

And a precision trap before any of that: `core.nautilus_setup.add_bars` builds
bars against a BTCUSDT perpetual with **price_precision 1 and size_precision
3**. Gold closes carry three decimals and its tick-count volume runs at 0.0216;
both would have been rounded on the way in. `fx_instrument()` was added for it.

### The one disagreement is a flaw in the KERNEL, and it is worth knowing

XAUUSD 1h, MODE_TREND, midnight anchor, ATR stop, RR target — 87.5%. The first
divergent bar:

```
2023-09-01 21:00   O=H=L=C 1939.238   volume 0.00000   vwstd 3.692849
2023-09-03 00:00   O=H=L=C 1939.238   volume 0.00000   vwstd 0.000000   <- anchor
2023-09-03 01:00   O=H=L=C 1939.238   volume 0.00000   vwstd 0.000000
2023-09-03 02:00   O=H=L=C 1939.238   volume 0.00000   vwstd 0.000031   <- trades
```

That is the FX weekend. Dukascopy pads the closed market with synthetic bars
carrying zero volume and the last traded price repeated. A session made entirely
of them has a volume-weighted sigma of exactly zero — but `vwstd` is
`sqrt(p2v/v − vwap²)`, a difference of two nearly-equal accumulated sums, so it
comes out as **3.1e-5 of floating-point noise**. The kernel's only guard is
`if sd <= 0.0: skip`, and 3.1e-5 passes it.

**So the kernel resolves a trade decision on rounding noise in a market that was
closed.** The streaming port accumulates the same sums in a different order,
gets exactly 0.0, and skips. Neither is wrong; the guard is.

## Stage 19 — how much of gold is booked on dead bars

`stage19_deadbars.py`. Every gold walk-forward trade tagged by whether its entry
bar had zero volume.

| | count | share |
|---|---|---|
| gold walk-forward trades | 18,119 | |
| entered on a **zero-volume** bar | **696** | **3.84%** |
| R carried by those trades | **6.04R** of 724.30R | **0.83%** |

On the board's own book (5m floor100 top10 + 4h floor100 top1), removing all 58
of them **raises** profit factor 1.618 → 1.629 and costs 2.11R.

**So it is a footnote for the board and a real hazard for the cells that are not
on it.** `15m floor30 top1` takes **46.5%** of its total R from dead bars, and
`30m floor30 top1` gets −124% — its dead-bar trades lose more than the cell
makes. Both are low-trade-count `top1` cells, which is exactly where a handful
of noise trades can dominate.

**Two fixes, neither applied yet** because they change every gold number and
should be done deliberately rather than at the end of a session:
1. change the kernel's `sd <= 0.0` guard to a tolerance in price terms;
2. drop zero-volume bars from FX/metals data at load, or at least refuse to
   trade them.
