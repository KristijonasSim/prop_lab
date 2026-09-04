# H-016 — trend-following MA ribbon (LonesomeTheBlue)

Opened 2026-09-04. Kris supplied the Pine v4 source of
**"Trend Following Moving Averages"** by LonesomeTheBlue and asked for a Python
port and tests.

## What the tool actually is

Twenty moving averages, lengths 5..100 step 5, each coloured by a **trend score
of its own**. The score is not slope. For each length:

```
chan  = 1% of the last 280 bars' (highest high - lowest low)   # shared by all 20
ma    = linreg( MA(close, len), 10, 0 )                        # if ulinreg
hh,ll = highest/lowest of ma over the last 20 bars
diff  = hh - ll
trend = +1 if ma > ll + chan ; -1 if ma < hh - chan ; else 0   # only when diff > chan
score = trend * diff / chan
```

So a length is "up" when its MA has climbed at least one channel **and** is
sitting near the top of that climb. `diff/chan` scales the reading by recent
volatility, which is what makes it comparable across regimes.

It is a `study` with **no entry, no exit and no strategy**, so nothing about it
could be scored as published. The port is in `ribbon.py`; what the Pine only
ever said in colour is made explicit in `features()`.

### Defects and asymmetries found in the original, preserved deliberately

- **The plotted line and the coloured line are different objects.** `plot()`
  draws `getma(len)` — the raw MA — while `getcol(gettrend(len))` computes the
  colour from the **linreg-smoothed** MA. With `ulinreg` on (the default) the
  colour does not describe the line it is painted on. Preserved, and documented
  at the point it happens.
- `highest(280)` / `lowest(280)` with one argument read `high` / `low`, not
  `close`. Easy to get wrong; `chan` is a true-range-style measure.
- `chan` is **global**, not per-length. A 5-bar MA and a 100-bar MA are held to
  the same absolute threshold, which is why short lengths read "flat" far more
  often than long ones.
- Pine's `ta.ema` / `ta.rma` seed from an SMA of the first `length` bars.
  pandas' `ewm(adjust=False)` seeds from the first value, which at length 100
  leaves a visible offset for hundreds of bars — enough to move a threshold
  crossing. Seeded the Pine way here.
- The colour ladder saturates at `|score| >= 10`, so the chart cannot show the
  difference between a 10 and a 40. `features()` keeps the number.

`test_parity.py` re-derives every primitive bar-by-bar straight from the Pine
text and asserts agreement: five MA types, `linreg`, `gettrend` at three
lengths, plus a truncation test that proves no future bar leaks backwards.
All pass to 1e-7 or better.

## Mechanism, before any result

Agreement across timescales. One MA turning up is noise; the 5-bar and the
100-bar agreeing means the same direction is being paid for both by the people
who arrived this hour and by the people who arrived last week. That is what
persistent one-way flow looks like, and whoever is on the other side is either
being stopped out or adding to a loser.

**Standing evidence against it, unprompted:**

- Price-derived hypotheses here are **0 for 6**. Every leg that ever worked came
  from a data feed.
- `CLAUDE.md` logs trend following as a **longer-hold family** — a future
  candidate, not a current-phase build. A 100-bar MA on 4h is a two-week
  timescale, which is the phase gate itself.
- Twenty lines, five free parameters. The null benchmark matters more here than
  usual.

## Stage 1 — the response test (the H-008 killer test), 2026-09-04

`stage1_response.py`. Bucket forward return by `agree` (mean sign of the twenty
scores) at **zero cost**, 5 coins x 15m/1h/4h x 1/4/16-bar horizons, signal read
at bar close and entry at the next open.

Crypto drifts up over this window, so raw band means measure drift plus signal.
Everything below is **excess over buy-and-hold on the same bars** — what a
long-only trend read has to beat, since holding is free.

Mean excess forward return, bps, averaged over 5 coins:

| tf | horizon | <=-0.8 | -0.4..-0.1 | flat | 0.1..0.4 | 0.4..0.8 | >=0.8 |
|---|---|---|---|---|---|---|---|
| 15m | 16 bars | +0.09 | -3.49 | +0.21 | +1.38 | +1.55 | **+2.09** |
| 1h | 16 bars | -4.64 | -14.38 | -3.23 | +0.97 | +4.67 | **+8.66** |
| 4h | 16 bars | -49.81 | -28.39 | -9.93 | -29.39 | -9.91 | **+54.26** |

Aggregated over every cut: strong up **+9.80** bps vs mild up **-3.35**;
strong down **-8.88** vs mild down **-6.48**; long-short spread on the strong
bands **+18.69** bps.

**The response is not flat, which is more than H-008 or H-010 managed.** But
read it precisely, because two things in it are uncomfortable:

1. **Only the extremes carry.** `>=0.8` is the sole band positive in excess at
   nearly every cut; the middle bands are noise and several are negative. This
   is a tail signal, not a monotone one, and a tail signal is exactly what a
   20-line, 5-parameter search produces by accident.
2. **The short side is much weaker than it looks.** `<=-0.8` is strongly
   negative in excess, but in raw terms it is near zero — the excess is mostly
   the drift being subtracted. Whether that shorts profitably is a separate
   question this stage does not answer.

Also note the horizon: the effect is clearest at 4h x 16 bars, a **~2.7 day
hold**. That is inside the phase constraint but at the slow end of it.

## Not yet done — nothing here is a result

- **No null.** Every number above is an in-sample description of one price
  path. Overlapping windows mean the sample size is not what `n` says, so a
  block-bootstrap or phase-randomised null is required before any of it counts.
- No cost. 14bps a round trip against an 18.69bps spread leaves very little.
- No trades, no stops, no drawdown, none of the mandatory reporting fields.
- No walk-forward. No parameter sensitivity across `prd`, `rateinp`, `linprd`
  or MA type — all five are at Pine defaults.

**Status: an indicator port with one encouraging diagnostic. Not a strategy,
and not evidence of one.**

---

# Stages 2-6 — all four variations, every market, every timeframe (2026-09-04)

Kris asked for all four variations tried, across timeframes, and named the
setup he had traded: **XAUUSD 15m, enter when every EMA turns green, exit on a
trailing TP.** That rule is the `entry_thr=1.0, require_flip=1, rr=0` corner of
the stage-2 grid and is reported first, on its own, before anything else.

`engine.py` is the trade kernel: signals on closed bars, fills at the next
open, stop-before-target inside a bar, fees and slippage both sides in bps from
H-002's per-asset table, R against the initial stop distance, and a minimum
stop floor so a stop on a level price cannot manufacture a 25R winner.

Two forms of trailing stop, because traders mean both by "trailing TP":
`TRAIL_FIXED` follows the running extreme at a distance frozen at entry;
`TRAIL_CHAND` recomputes `k * ATR(now)` every bar. `trail_start_r` separates
"trail from entry" from "leave the initial stop alone and only protect a
winner". These are different rules and they do not score the same.

660 configurations x 12 markets x 5 timeframes = **37,620 backtests**, plus
188,100 on five phase-randomised copies.

## Kris's rule, on Kris's market

XAUUSD 15m, all-green entry, pure trailing exit, every trail setting:

| trail | k | trades | PF | PF@2x | PF long | PF short | trades/day | hold h |
|---|---|---|---|---|---|---|---|---|
| fixed | 1.0 | 2110 | 0.750 | 0.468 | 0.817 | 0.684 | 1.93 | 1.8 |
| fixed | 4.0 | 1144 | 1.067 | 0.927 | 1.227 | 0.891 | 1.05 | 16.1 |
| chand | 4.0 | 1584 | 1.102 | 0.928 | 1.296 | 0.883 | 1.45 | 8.4 |
| chand | 8.0 | 875 | 1.382 | 1.249 | 1.751 | 0.991 | 0.80 | 20.6 |
| chand | 16.0 | 449 | 1.488 | **1.387** | **2.255** | **0.891** | 0.41 | 44.3 |

**As stated, with a normal trailing stop, the rule loses.** Every setting from
1 to 4 ATR is below breakeven at 2x cost. It only turns positive with a
chandelier trail of 8-16 ATR, and at 16 ATR the "stop" is so wide that the
position is held **75.7% of all bars**.

**The long and short sides are not the same strategy.** At every setting the
longs carry it and the shorts lose: 2.255 against 0.891 at the best setting.
Gold rose 130% over this window. A rule that is long more than half the time in
a market that rose 130% does not need an edge to print a profit factor.

## Gold was the right instinct

Best PF@2x per panel, Kris's rule, best trail setting:

| market | 5m | 15m | 30m | 1h | 4h |
|---|---|---|---|---|---|
| **XAUUSD** | 1.304 | 1.386 | 1.699 | **1.900** | 1.600 |
| XAGUSD | 1.088 | 1.248 | 1.150 | 1.410 | 1.306 |
| BTCUSDT | — | 1.078 | 1.342 | 1.339 | 1.655 |
| ETHUSDT | — | 1.331 | 1.360 | 1.202 | 1.339 |
| SOLUSDT | — | 1.197 | 1.357 | 1.457 | 1.283 |
| EURUSD | 0.899 | 0.950 | 1.048 | 0.952 | 1.006 |
| AUDUSD | 0.772 | 0.794 | 0.782 | 0.988 | 0.963 |

**XAUUSD is the best market at every single timeframe**, which is the finding
Kris brought and it survives. But **15m is not its best timeframe** — 1h and
30m both beat it, and the ordering by median across the whole grid is
4h > 1h > 30m > 15m > 5m at every market. The FX majors fail everywhere.

## What the levers say

Median PF@2x across all 30,000+ agree-mode configurations:

| lever | setting -> median PF@2x |
|---|---|
| `trail_k` | 1.0 → **0.487**, 2.0 → 0.687, 4.0 → 0.830, 8.0 → 0.921, 16.0 → **0.961** |
| `trail_start_r` | 0.0 → 0.758, 1.0 → 0.806, 2.0 → **0.844** |
| `entry_thr` | 0.6 → 0.801, 0.8 → 0.805, **1.0 → 0.817** |
| `trail_mode` | fixed 0.815, chandelier 0.798 |
| `rr` (fixed target) | none **0.816**, 2R 0.798 |

Two readings. **All-green really is the best entry threshold** — Kris's rule,
confirmed, though the margin over 0.6 is small (0.817 vs 0.801). And
**trailing only once in profit beats trailing from entry**, which is the more
common retail construction and the better one.

But the dominant lever is `trail_k`, and it is **monotone to the edge of the
grid**. Wider is better, all the way to 16 ATR, with no interior optimum. That
is the signature of an edge that is EXPOSURE rather than timing: the best
version of this rule is the one that most nearly never exits.

## The four variations

### B — extremes-only long/short. This is the all-green corner above.
Covered by stage 2. It is the best of the four and everything above applies.

### C — the squeeze (ribbon compressed, then fanning out). **Dead.**
Real median PF@2x **0.281 against its null's 0.434** — worse than noise, and
**0 of its configurations clear the gate against 0 for the null**. Requiring
compression first destroys the signal rather than sharpening it.

### A — the ribbon gates H-009. **Fails, in H-013's exact way.**

| on H-009's own trades | trades | PF@2x | maxDD | R/day | ret/DD |
|---|---|---|---|---|---|
| H-002, no gate | 6936 | 1.557 | −68.96R | 0.951 | 37.63 |
| **H-009, crowd gate (baseline)** | 3808 | 1.806 | −51.39R | 0.901 | **37.31** |
| H-009 + ribbon agrees | 2742 | **1.872** | −52.40R | 0.716 | 29.07 (**−22.1%**) |
| H-009 + ribbon, \|agree\|>=0.6 | 2358 | 1.846 | −41.38R | 0.601 | 30.93 (−17.1%) |
| H-009 + ribbon fully stacked | 1815 | 1.828 | −36.48R | 0.447 | 26.06 (−30.1%) |

Profit factor goes up and **return over drawdown goes down at every
threshold**, because R per day falls faster than drawdown does. This is
precisely why H-013 was rejected: `days = maxDD_R / R_per_day` gets worse. The
control (keep what the ribbon *disagrees* with) is also worse than baseline,
which says the gate is mostly just removing trades.

### D — the crowd gates the ribbon. **Weak, and only at 4h.**

| leg | trades | PF@2x | ret/DD |
|---|---|---|---|
| BTCUSDT 4h ribbon, no gate | 348 | 1.498 | 7.00 |
| **+ crowd offside** | 292 | 1.619 | **10.07** |
| CONTROL: crowd agrees | 56 | 0.906 | −0.13 |
| SOLUSDT 4h ribbon, no gate | 232 | 1.248 | 3.07 |
| **+ crowd offside** | 176 | 1.465 | **4.06** |
| CONTROL: crowd agrees | 56 | 0.574 | −0.98 |

The signature is right on the two 4h legs — the gate helps and its control goes
negative. It does nothing at 1h (BTC 8.82 → 5.69, ETH 5.24 → 5.25, SOL 5.92 →
3.71). Consistent with H-006's finding that the positioning signal lives at
8-24 hours, but the control samples are 46-84 trades and that is not a result.

## Stage 5 — it beats its null, which no price pattern here has done

Identical grid, five phase-randomised copies, gate PF>=1.20 at 2x with floors
of 100 trades and 0.1 trades/day:

| | real | null, per seed |
|---|---|---|
| configs clearing the gate | **2,362** | 781 |
| median PF@2x | 0.805 | 0.777 |

Per market, real vs null clears: XAUUSD **771 vs 132**, SOLUSDT 450 vs 29,
XAGUSD 384 vs 241, ETHUSDT 312 vs 22, BTCUSDT 282 vs 12 — against AUDUSD
**4 vs 66**, EURUSD 9 vs 60, GBPUSD 47 vs 85. It beats its null on the trending
assets and loses to it on the mean-reverting FX majors, which is a coherent
split rather than a scatter.

**And it beats a direction control.** Same entry bars, same exits, side drawn
at random at the same long share, exits re-simulated rather than negated:

| | real PF@2x | random side | time in market | long share |
|---|---|---|---|---|
| XAUUSD 15m | 1.387 | 0.997 ± 0.112 | 75.7% | 48.8% |
| XAUUSD 1h | 1.501 | 1.083 ± 0.203 | 80.2% | 53.9% |
| XAUUSD 30m | 1.699 | 1.188 ± 0.172 | 77.3% | 49.4% |
| BTCUSDT 4h | 1.252 | 0.954 ± 0.145 | 61.2% | 43.3% |
| USDJPY 1h | 0.987 | 0.938 ± 0.188 | 71.7% | 54.6% |

Real beats the coin flip on 7 of 8 panels, by 2-3 standard deviations on gold.
The long share is ~49%, so this is **not** simply a long-only book. The ribbon
is reading direction.

## Stage 6 — walk-forward, and this is where it fails

12 months train / 3 months test, quarterly, configuration chosen blind inside
each fold on 2x-cost profit factor, test quarter never consulted. 32 stitched
out-of-sample series. The same procedure re-run on three phase-randomised
copies of every market.

| | real | null, per seed |
|---|---|---|
| median stitched PF@2x | **1.070** | 0.979 |
| series clearing 1.20 | **7 of 32** | **5.7 of 32** |
| best stitched PF@2x | 2.113 | **2.549** |

**Seven survivors against the null's five and a half is not a result.** The
median is better than the null's and the null's *maximum* is higher than the
real maximum — the same pattern that ended H-002's walk-forward as a family and
the exact shape that killed H-003.

The survivors are all gold:

| leg | rule | folds | trades | PF@2x | total R | maxDD | quarters >1 | days to +8% |
|---|---|---|---|---|---|---|---|---|
| XAUUSD 1h | single | 7 | 103 | **2.113** | 31.3 | −5.24 | 5/7 | 183 |
| XAUUSD 15m | single | 7 | 105 | **1.881** | 33.2 | −4.45 | 5/7 | 147 |
| XAUUSD 30m | single | 7 | 95 | 1.623 | 15.1 | −4.80 | 5/7 | 349 |
| XAUUSD 1h | top10 | 7 | 1077 | 1.575 | 20.0 | −2.35 | 5/7 | 129 |
| XAUUSD 15m | top10 | 7 | 1365 | 1.369 | 19.2 | −2.00 | 6/7 | **114** |
| XAGUSD 30m | single | 7 | 96 | 1.344 | 12.3 | −6.75 | 4/7 | 596 |
| XAGUSD 4h | single | 7 | 67 | 1.231 | 5.7 | −4.56 | 5/7 | 866 |

Gold on 15m — Kris's market and timeframe — is in there twice, and the top-10
book is the most consistent series in the table at 6 of 7 quarters positive.
**But seven quarters is seven quarters**, gold's cache only starts 2023-09, and
a null that produces five to six survivors from noise can produce these.

The controls behaved: EURUSD 0.776 and AUDUSD 0.653, both far below breakeven,
so the procedure is not fitting everything it touches.

## The phase gate kills it regardless

`days = maxDD_R / R_per_day`. The **best** number in the entire walk-forward is
**67 days** (XAUUSD 15m, top-10 book), then 75 (XAUUSD 1h top-10) and 86
(XAUUSD 15m single). Against a phase constraint of **~14 days**.

*(Corrected 2026-09-04: these were first reported as 114/129/147 days. The
span was being taken over the whole series rather than over the stitched
out-of-sample window, which understated R per day by about 1.7x on the gold
legs. The verdict is unchanged - the best leg is still ~5x too slow - but the
numbers were wrong and stage 6 now divides by the OOS span.)*

Nothing here resolves inside one to two weeks of trading, and it is not close —
the best leg is eight times too slow. `CLAUDE.md` files trend following as a
longer-hold family precisely for this reason, and this is what that looks like
measured rather than assumed.

## Verdict

**H-016 is the strongest price pattern this project has tested, and it is still
not tradeable now.**

What is genuinely new: it is the **first price-derived hypothesis here to beat
its paired null** (2,362 vs 781) and the first to beat an honest direction
control. The mechanism reads as real — it works on trending assets and fails on
mean-reverting ones, which is what a trend reader should do.

What kills it:

1. **Walk-forward does not separate from the null** — 7 survivors against 5.7,
   and the null's best beats the real best.
2. **Days to target is 114 at best** against a ~14-day phase gate.
3. **The best configurations are barely strategies.** `trail_k` is monotone to
   the grid edge and the winners hold 76-83% of all bars. Most of what the
   profit factor measures is exposure to two assets that rose 130% and 1,671%.
4. **The short side loses everywhere** (PF 0.83-0.99 against 2.0-2.5 long).
5. **Kris's rule as stated — 15m gold, all green, trailing TP — loses** at any
   normal trail width. It needs an 8-16 ATR chandelier to turn positive, which
   is a different trade from the one he described.

Not proposed for the book. Kept for two reasons: the null margin is real and
unmatched by anything price-derived here, and variation D's 4h legs are the one
thread with a live mechanism behind them.

---

# Stage 7 — the gold legs against simply owning gold (2026-09-04)

Kris's question, and the one the exposure finding demands: the winning
configurations hold a position 76-83% of all bars in a market that rose 130%,
so does any of this beat just buying the metal?

Both sides are levered so their worst drawdown exactly fills the **8% prop
cap**, then compared on what they return. Same arithmetic the whole project
uses. Out-of-sample window only - the stitched walk-forward quarters,
**2024-10-01 to 2026-07-01, 638 days / 7 quarters**.

*(Corrected: this was first written as "~356 days", which was buy-and-hold's
days-to-target read as if it were the window length. The window is 638 days.)*

| leg | PF@2x | maxDD | risk/lev at the 8% cap | return | days to +8% |
|---|---|---|---|---|---|
| XAUUSD 15m top10 | 1.369 | −2.00R | 3.99% per trade | **+76.6%** | **67** |
| XAUUSD 1h top10 | 1.575 | −2.35R | 3.40% per trade | **+67.9%** | 75 |
| XAUUSD 15m single | 1.881 | −4.45R | 1.80% per trade | +59.6% | 86 |
| XAUUSD 1h single | 2.113 | −5.24R | 1.53% per trade | +47.9% | 107 |
| XAUUSD 30m single | 1.623 | −4.80R | 1.67% per trade | +25.1% | 203 |
| **buy and hold gold** | — | **−28.8%** | **0.28x** | **+14.4%** | **356** |
| XAGUSD 30m single | 1.344 | −6.75R | 1.18% per trade | +14.6% | 349 |
| **buy and hold silver** | — | −53.7% | 0.15x | +12.9% | 395 |

**Under a prop cap the strategy wins, and not narrowly** — 4 to 5 times the
return of holding, and 67 days to target against 356. The reason is entirely
drawdown: gold's own peak-to-trough over this window is **−28.8%**, so an 8%
cap only permits 0.28x of it. Owning gold is not a strategy an 8% account can
run at size; it breaches the cap three and a half times over at 1x.

## But with no cap, holding wins

At a conventional 1% risk per trade, over the same out-of-sample window:

| leg | strategy return | strategy DD | hold return | hold DD |
|---|---|---|---|---|
| XAUUSD 15m single | +33.1% | −4.5% | **+52.0%** | −29.1% |
| XAUUSD 1h single | +31.3% | −5.2% | **+51.6%** | −28.8% |
| XAUUSD 15m top10 | +19.2% | −2.0% | **+52.0%** | −29.1% |
| XAGUSD 30m single | +12.3% | −6.8% | **+86.6%** | −53.7% |

**Holding beats every leg on raw return, on all six.** The strategy wins on
return per unit of drawdown and loses on return per unit of capital.

## What that actually says

The honest reading is that H-016 on gold is **a drawdown-reduction machine, not
a return machine.** It takes gold's move and delivers a third to two thirds of
it with a seventh of the pain. That is exactly the property a prop evaluation
pays for and exactly the property a cash account does not.

Three things this does not settle:

- **The window is one gold bull market**, 638 out-of-sample days over 7
  quarters (2024-10 to 2026-07), inside a gold cache that only starts 2023-09. Both sides of this comparison are one draw. A strategy that keeps
  60% of the upside with a seventh of the drawdown would look very different in
  a gold bear market, and there is not one in the cache to test on.
- **The comparison flatters the strategy on gap risk.** Its drawdown assumes
  every stop fills at its price; gold gaps over weekends and its −2.00R becomes
  larger the moment one does not. Buy-and-hold's −28.8% has no such assumption.
- **It still fails the phase gate.** 67 days at best against ~14, so "beats
  buy-and-hold" and "tradeable in this phase" are different questions and only
  the first one is answered yes.

---

# Stage 9 — silver, S&P 500, US30 and Nasdaq (2026-09-04)

Kris asked for silver and the three US indices. Silver was already in the
sweep. The indices were not in the repo at all and were pulled from the same
Dukascopy feed everything else uses, **2023-09-01 to 2026-08-31** — the
identical window gold and silver run on. `core/fx_data.DUKAS_SYM` maps our
names onto Dukascopy's (`USA500IDXUSD`, `USA30IDXUSD`, `USATECHIDXUSD`); the
1e3 price scale was verified against a live day rather than assumed.

Indices are charged **gold's** cost model, which overstates their real spread
(US30's ~2 points on 53,000 is 0.38bps against gold's 1.00bps). Nothing was
re-tuned for them: same 660-config grid, same paired null, same blind
walk-forward.

## Grid against the paired null

| market | 15m | 30m | 1h | 4h |
|---|---|---|---|---|
| **XAGUSD** real / null per seed | **60** / 24 | **95** / 56 | **127** / 71 | **93** / 30 |
| SPX500 | 4 / 18 | 6 / 19 | 6 / 28 | 0 / 49 |
| US30 | 0 / 2 | 10 / 9 | 15 / 28 | 27 / 40 |
| NAS100 | 5 / 16 | 31 / 17 | 42 / 77 | 21 / 16 |

**Silver beats its null at all four timeframes.** The indices do not: SPX500
loses to its null on every cut, US30 on three of four, NAS100 on two of four —
and NAS100's two nominal wins (30m, 4h) are inside the noise the walk-forward
then removes.

## Walk-forward, last two years, against owning the thing

Window **2024-08-30 to 2026-08-30**, configuration chosen blind on the 12
months before each test quarter, both sides levered so worst drawdown fills the
8% cap.

| | trades | PF@2x | maxDD | size at cap | return | days to +8% | vs hold |
|---|---|---|---|---|---|---|---|
| XAUUSD 15m top10 | 1568 | 1.356 | −2.00R | 3.99% | **+84.5%** | 69 | **WIN** |
| XAUUSD 15m single | 120 | 1.870 | −4.45R | 1.80% | +65.2% | 90 | **WIN** |
| XAUUSD 1h top10 | 1239 | 1.461 | −2.35R | 3.40% | +64.0% | 91 | **WIN** |
| *buy and hold gold* | — | — | −28.8% | 0.28x | +21.4% | 272 | — |
| XAGUSD 15m single | 126 | 1.471 | −5.32R | 1.51% | **+29.8%** | 196 | **WIN** |
| XAGUSD 15m top10 | 1400 | 1.211 | −3.93R | 2.04% | +24.9% | 235 | **WIN** |
| XAGUSD 1h top10 | 826 | 1.110 | −4.43R | 1.81% | +5.2% | 1129 | lose |
| *buy and hold silver* | — | — | −54.0% | 0.15x | +19.8% | 295 | — |
| SPX500 15m single | 129 | **0.815** | −14.54R | 0.55% | **−6.0%** | — | lose |
| SPX500 1h top10 | 1211 | 0.798 | −12.98R | 0.62% | −6.8% | — | lose |
| SPX500 15m top10 | 1670 | 0.761 | −19.53R | 0.41% | −7.7% | — | lose |
| *buy and hold SPX500* | — | — | −21.4% | 0.37x | +13.8% | 423 | — |
| US30 15m single | 126 | 0.909 | −18.88R | 0.42% | −2.0% | — | lose |
| US30 1h top10 | 1016 | 0.924 | −5.72R | 1.40% | −4.1% | — | lose |
| US30 15m top10 | 1701 | 0.838 | −20.10R | 0.40% | −5.5% | — | lose |
| *buy and hold US30* | — | — | −18.5% | 0.43x | +12.6% | 462 | — |
| NAS100 15m top10 | 1883 | 0.871 | −11.95R | 0.67% | −7.5% | — | lose |
| NAS100 1h top10 | 1060 | 0.843 | −9.44R | 0.85% | −5.2% | — | lose |
| NAS100 15m single | 158 | 0.853 | −18.35R | 0.44% | −5.2% | — | lose |
| *buy and hold NAS100* | — | — | −26.2% | 0.30x | +15.5% | 377 | — |

## The finding

**The ribbon works on metals and fails on equity indices.** All nine index legs
lose money out of sample — profit factor 0.76 to 0.92, not one above breakeven
— while five of six metal legs are profitable and four beat buy-and-hold under
the cap. The split is total and it is not marginal.

It is also mechanically sensible, which is the part worth carrying. A cash
index grinds upward through shallow, frequent pullbacks: price crosses a
20-length moving average constantly without the trend ending, so a
ribbon-agreement rule is whipsawed in and out. The index drawdowns say the same
thing from the other side — the strategy's maxDD on SPX500 is **−19.53R against
gold's −2.00R**, roughly ten times worse for the same rule. Metals move in
longer one-way impulses that a multi-timescale agreement reading can actually
hold.

Note the direction of the error too: the indices are the markets where
buy-and-hold is *closest* to viable under a cap (0.30-0.43x against gold's
0.28x) and where the strategy is worst. There is no version of this where the
indices are the answer.

**Silver is real but second-best.** It beats its null at every timeframe and
beats hold under the cap on two of three legs, but its best days-to-target is
196 against gold's 69, and its 1h book is barely above water. Silver's own
−54.0% drawdown means holding it under a cap permits only 0.15x, which is why
even a mediocre strategy beats it there.

Gold remains the only market in H-016 worth another hour, and the phase gate
(69 days against ~14) still fails.

---

# Stage 10 — the metals book on the board (2026-09-04)

Gold and silver are the only markets left, so the board record is metals only.
Eight legs (2 markets x 4 timeframes) x 2 selection rules, all walk-forward.

| leg | trades | PF@2x | quarters >1 |
|---|---|---|---|
| XAUUSD 1h single | 103 | **2.113** | 5/7 |
| XAUUSD 15m single | 105 | 1.881 | 5/7 |
| XAUUSD 30m single | 95 | 1.623 | 5/7 |
| XAGUSD 15m single | 112 | 1.586 | 5/7 |
| XAUUSD 1h top10 | 1077 | 1.575 | 5/7 |
| XAUUSD 15m top10 | 1365 | 1.369 | **6/7** |
| XAGUSD 30m single | 96 | 1.344 | 4/7 |
| XAGUSD 4h single | 67 | 1.231 | 5/7 |
| XAGUSD 15m top10 | 1235 | 1.219 | 4/7 |
| XAUUSD 30m top10 | 1165 | 1.162 | 5/7 |
| XAGUSD 30m top10 | 1030 | 1.179 | 3/7 |
| XAGUSD 4h top10 | 679 | 1.067 | 4/7 |
| XAUUSD 4h top10 | 685 | 1.055 | 3/7 |
| XAGUSD 1h top10 | 724 | 1.007 | 3/7 |
| XAUUSD 4h single | 76 | 0.902 | 3/7 |
| XAGUSD 1h single | 69 | 0.736 | 3/7 |

**Metals-only null**: the identical walk-forward on phase-randomised gold and
silver clears PF 1.20 at 2x on **real 9 of 16 against the null's 5.3 of 16**
(seeds 2, 7, 7). Better than the all-markets cut in stage 6 (7 against 5.7) but
still thin, and the seed spread (2 to 7) is wider than the margin it wins by.
**Read this as "probably not noise", not as "not noise".**

## The book

Chosen on the phase gate among subsets clearing PF 1.20 at 2x, capped at four
legs. H-012 established that widening a book here DILUTES it - equal weighting
divides R by the leg count and a weak leg costs more R per day than it saves in
drawdown - so the search is not allowed to pile legs on.

**XAUUSD 15m + 30m + 1h (single) + XAGUSD 30m (single)** — PF 1.84, **PF@2x
1.765**, 394 trades, 0.631/day across 4 sub-strategies (0.158/day each),
R/day +0.0404.

Prop simulation, two-step, at the ladder's pick of **4.00% risk**: **75.7%
pass, 0% of accounts killed, median 96 days, expected 126.8**.

**Board score 6.5/10**, third behind H-009 (8.9) and H-002 (8.6).

## What the 6.5 is and is not

It is the best score any price-derived hypothesis has reached in this project,
and it is *below* both feed-driven books. The gap is exactly where it should
be: H-009 expects a funded account in 48.7 days, this expects 126.8.

Three things keep it off the candidate list:

1. **The phase gate.** 126.8 expected days against a ~14-day constraint.
2. **The null margin is thin** — 9 against 5.3, on 16 series, with the null's
   own seeds ranging 2 to 7.
3. **Leg selection is in-sample.** Every trade is out-of-sample, but which four
   legs to run was chosen on the same window it is reported on. H-002 carries
   the identical caveat; it is not a reason to prefer this over H-002, only a
   reason not to read 1.765 as a forward expectation.

And the standing caveats do not go away: the gold cache is one bull market with
no bear market in it, and the −2.00R drawdown assumes every stop fills at its
price.
