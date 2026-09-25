# Step 3 — the quick check. Design notes, 2026-09-22

Written after probing the real numbers, not from the diagram alone.
`docs/WORKFLOW.drawio` is the picture; this is the box marked "3rd QUICK CHECK".

**Nothing here is chosen. Kris picks the two numbers at the bottom.**

---

## What step 3 is for

Kill the obviously hopeless in seconds, before step 4 spends hours. It judges
**trades**, not bars (Kris, 2026-09-21: "the unit is a trade"). `factory/build.py`
already emits `Trade` objects with `r` net of a full round trip, so step 3 is a
thin layer over what exists — roughly 120 lines and a test file.

It is a **floor**, not a score. The scoreboard is step 7 (pass %, days).

---

## FINDING 1 — the skew check as written would kill everything, by construction

`core/screen.py` gate 3 is *"the median moves, not just the mean"*. It exists
because H-046c died with mean +16.73 and median −2.10, and that check was right
for a **bar-forward-return** signal.

**It cannot be carried over to trades.** A trade with a stop at 1R and a target
above it has a median of about −1R whenever the win rate is under 50%, which is
the normal shape of a breakout rule. Measured on 40 generated ideas, gold 1h,
2x cost:

```
median R > 0                1 of 40
median R between -1.0 and -1.05   38 of 40
```

The single exception (`price above highest100`) is the one rule with a win rate
over 50%. **A median gate would reject H-027's own family.**

### What replaces it

The real question the gate was asking is *"is this one lucky episode?"*. On
trades that is a **concentration** check, and it is just as cheap:

```
mean R after deleting the best 5 trades  >  0
```

It discriminates, which is the test of a gate that is worth having:

| | ideas |
|---|---|
| positive mean R at 2x cost | **14 of 40** |
| …and still positive after dropping the best 5 trades | **11 of 40** |

The three it removes are exactly the ones where one trade carried it —
`short when price below lowest200` has **22.3% of its total R in a single trade**
across 83 trades, and turns negative the moment that trade is deleted.

---

## FINDING 2 — gold went up, so every long passes. Step 3 needs a drift control.

The same 40 ideas, sorted:

* Every rule with a **positive** mean is long. Nearly every short is negative.
* 14 of 40 clear "mean R > 0 at 2x cost". A gate that passes **35% of randomly
  generated ideas** is not killing the obviously hopeless.

That is not 14 edges. It is one edge — gold rose over the window — being read
back 14 times. Longs collect drift; shorts pay it.

**The control, and it is seconds:** take the same side, the same stop and
target, the same number of trades, but enter at random bars. If the idea does
not beat that, the entry rule contributed nothing and only the direction did.
This is the step-5 luck check moved earlier and made cheaper — it is a
single-market, single-seed version, and it costs one extra `build.run`.

Without it, step 3 is a rubber stamp on any long rule on a trending market.

---

## The four questions, as proposed

| # | question | gate | why |
|---|---|---|---|
| 1 | enough trades? | **>= 0.4 trades/day** AND **>= 100 trades** in the cell | Kris's day-trading floor; 100 keeps the mean from being three episodes |
| 2 | does it beat costs? | **mean R > 0 at 2x** the market's round trip | reported at 1x/2x/3x, gated at 2x |
| 3 | one lucky run? | **mean R still > 0 after deleting the best 5 trades** | replaces the median check — see finding 1 |
| 4 | is it the entry, or the drift? | **beats a same-side random-entry control** | see finding 2 |

Anything that fails any of the four dies here, in seconds, and goes to
`tried.jsonl` with the reason so it is never re-proposed.

---

## The two numbers Kris picks

### A. The cost multiple

Recommendation: **gate at 2x, report 1x / 2x / 3x.**

`CLAUDE.md` already requires all three to be reported, and `core/screen.py`
already uses `COST_MULT = 2.0`. Using the same multiple here keeps one number in
the project instead of two. 1x alone would let a rule through on the assumption
that the quoted spread is the whole cost, which the Bybit demo disproved —
5.50 bps round trip charged against 1.83 assumed.

### B. One cell or all 24?

Recommendation: **all 24** — six markets x four timeframes.

* **It is affordable.** 0.35 s per idea on gold 1h (22,800 bars). A full market
  is 15m+1h+4h+1d ~ 120,000 bars, so **~11 seconds per idea for all 24 cells**,
  ~37 minutes for a queue of 200. That is still "seconds", and the factory runs
  unattended.
* **One cell is the wrong cell.** Gold's round trip is 1.64 bps and EURUSD's is
  0.27. An idea killed on gold alone is killed at six times the cost bar it
  would face on EURUSD.
* **The 24-chances-at-luck objection is already answered** — the 2026-09-21
  simulation: junk reaching the desk is 31 per 1,000 on three years alone and
  **0.5 per 1,000 with the five-year re-check**. Step 6 pays for step 4's width,
  and it pays for step 3's the same way.
* **The bar does not move because 24 cells were tried.** That was settled with
  Kris on 2026-09-21 and it is not re-opened here. The ledger records the 24
  so the same idea is not tried twice — that is all it is for.

**The one cost of 24 cells that is real:** the survivor list becomes "idea X on
cell Y", so step 4 must carry the cell forward rather than re-searching it.

---

## What this does NOT do

It does not prove anything. Passing step 3 means an idea has earned the hours
that step 4 costs — nothing more. No number produced here is quotable.

---

## REVISED 2026-09-22 after Kris pushed back — and he is right about the fees

Kris: *"why do we charge it double fees? if we charge normal fees and it
survives just a bit, we could make improvements... with double fees we already
exclude some that would pass single fees."* And: *"number 2 I don't really
like, and I'm a little sceptical about number 4."*

Both objections were tested on the 45 ideas the generator produced, gold 1h.

### The cost multiple: KRIS IS RIGHT. Changed to 1x.

| gate | ideas surviving, of 45 |
|---|---|
| mean R > 0 at **1x** cost | **19** |
| mean R > 0 at **2x** cost | **17** |

**Doubling the fee removes two ideas out of forty-five.** It is not doing the
filtering — checks 3 and 4 are. And once the random-entry control is applied the
two columns are *identical*:

```
1x + drop-best-5 + control    5 survivors
2x + drop-best-5 + control    5 survivors
```

So the 2x gate buys nothing and costs exactly what Kris said it costs: an idea
that is marginal today and improvable tomorrow gets thrown away for no gain.

**Step 3 now gates at 1x and REPORTS 1x / 2x / 3x.** The 2x question moves to
step 7, where it belongs — by then the rule is fixed, the fills are honest, and
a cost sensitivity is a property of a finished candidate rather than a filter on
an unfinished one.

*The one thing 1x must not become:* an excuse to trust the quoted spread. Bybit
charged **5.50 bps round trip on gold against the 1.83 assumed**. 1x here means
1x the *measured* round trip in `core/markets.py`, and where it has not been
measured on the venue we will actually trade, that is a known unknown, not a
free pass.

### The random-entry control: it is the ONLY check with teeth

Same 45 ideas. Control = same side, same stop, same target, same hold, same
number of entries, entered at **random bars**, 20 seeds.

| filter, applied in order | survivors |
|---|---|
| all ideas | 45 |
| ...makes money at 1x cost | **19** |
| ...and still makes money after deleting its best 5 trades | **19** |
| ...**and beats its own random-entry control** | **5** |

**Fourteen of the nineteen "profitable" ideas are gold going up.** The control's
own median mean-R is **+0.05 to +0.09 R per trade** on the long side — random
long entries on gold, with a 2-ATR stop and a 3-ATR target, made money over this
window. Every one of those fourteen scored *below* that.

Read the table: the concentration check removed **zero** ideas here, and the
control removed **fourteen**. Without check 4, step 3 passes 42% of a randomly
generated idea list, all of them long, and hands step 4 hours of work on the
gold uptrend.

The five that survive:

| idea | trades | mean R @1x | random-entry median |
|---|---|---|---|
| long when price above highest100 | 276 | **+0.222** | +0.074 |
| long when price above highest200 | 227 | **+0.189** | +0.074 |
| long when rsi10 crosses above 80 | 367 | **+0.137** | +0.072 |
| long when price above highest50 | 375 | **+0.118** | +0.059 |
| short when price below lowest200 | 83 | **+0.113** | −0.120 |

Momentum, not mean reversion — and the last one fails check 1 anyway at 0.09
trades/day. **None of this is a result.** It is evidence that the gate
discriminates, which is all step 3 is asked to do.

### The four questions, final

| # | question | gate |
|---|---|---|
| 1 | enough trades? | >= 0.4 trades/day AND >= 100 trades |
| 2 | beats costs? | mean R > 0 at **1x**; 1x/2x/3x all reported |
| 3 | one lucky run? | mean R still > 0 after deleting the best 5 trades |
| 4 | the idea, or the drift? | beats the 90th percentile of its own random-entry control |

---

## BUILT 2026-09-22 — `factory/check.py`, and one claim of mine that was wrong

```
python -m factory.check                  # 5 ideas off the queue, all 24 cells
python -m factory.check -n 20 -v         # every cell, not just the verdict
python -m factory.check --market XAUUSD --tf 1h
```

`factory/cells.py` holds the 24 cells; `tests/test_factory_check.py` pins
thirteen behaviours. Three things were settled while writing it that are not in
the design above.

### The cost charged is the CROSSING cost, not `core.markets.EXEC_MODE`

`markets.EXEC_MODE` is `mixed`, which assumes the entry is a resting limit
order and prices gold at 1.07 bps instead of 1.83. The factory's grammar
generates breakout-shaped rules, whose entry is on the far side of the market
by construction — **you cannot rest a buy limit above the price.** H-023 already
measured what a limit entry is worth on a fade (+0.011 profit factor; the whole
benefit was the fee) and measured that breakouts gain nothing from it (+0.008).
So step 3 charges `round_trip("taker")`.

### "Trades per day" needed a denominator, and the obvious two were both wrong

* Calendar days overstates by 7/5 — the weekend is not a trading day.
* Days containing at least one live bar was the first version and it is wrong
  at the edges: gold's week opens 22:00 UTC on a Sunday, so **155 two-hour
  Sundays each counted as a full day**, inflating the denominator 20%.
* What it uses: **live bars ÷ bars in a full session**, measured once per
  market on its 1h series and reused for all four of its cells. It handles the
  Sunday open and the daily break by itself, and it gives the same day count
  whatever timeframe you look through — so a trades/day figure is comparable
  across the 24 cells, which is the property that matters.

The daily resample also had to move its bin edges to 22:00 UTC, or the Sunday
stub becomes its own daily bar.

### I CLAIMED TWELVE CELLS WERE IMPOSSIBLE. THEY ARE NOT.

A first version of `check.py` computed a ceiling of `bars_per_day / max_hold`
and labelled any cell below the 0.4 floor **CELL IMPOSSIBLE**, on the reasoning
that one position at a time held for `max_hold` bars caps the trade rate. At the
grammar's 48 bars that "proved" 4h and 1d could never pass — half the grid.

**It is wrong, and a test caught it before it reached the diagram.** `max_hold`
is a maximum, not the hold: nearly every trade exits earlier on its stop or
target. A rule with `max_hold=5000` still traded 254 times in 250 days. The real
bound is one trade per bar — 6/day on 4h, 1/day on 1d — and both are above the
floor.

What step 3 reports instead is the **measured mean hold in days**, printed
beside the rate, because a low rate on 4h usually is the hold rather than a
fussy entry rule, and the two call for different fixes. The reasoning that
produced the wrong claim is kept in `check.mean_hold_days`'s docstring.
