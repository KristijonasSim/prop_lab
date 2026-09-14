# Going deeper into the VWAP — the plan, ranked

Written 2026-09-10 after Kris chose to **keep the baseline exit** (no target, no
fixed reward:risk) and asked what would take H-027 further.

**The frame.** Three axes exist on this hypothesis and two of them are spent:

| axis | state |
|---|---|
| **entry filters** | **exhausted.** 25 candidates screened; 24 of 25 raised profit factor and LOWERED R per day. The one survivor lost to its own shuffled control. |
| **exit shape** | **measured 2026-09-10.** Partial, trail, recross, and targets 1R–12R. Kris keeps the baseline. |
| **the VWAP itself** | **untouched.** Every H-027 number ever produced uses one definition: `vwap_series(df, 0, 0)` — reset at 00:00 UTC, tick-volume-weighted, typical price (H+L+C)/3. |

The third axis is the whole hypothesis and it has never been varied. That is where
the next work goes, and it is different in kind from a filter: a filter selects
among existing signals, an anchor change makes **different signals exist**.

---

## TIER 1 — what the VWAP *is*

### 1.1 The anchor — RUN 2026-09-10. **CLOSED, NEGATIVE.** (`research/anchors.py`)

Eight arms, gold 1h and 4h, blind walk-forward, paired null, same grid and costs.

| anchor | 1h PF@2x | 1h days | 4h PF@2x | 4h days |
|---|---|---|---|---|
| **utc 00:00 (shipped)** | **2.872** | **11.7 [9–14]** | 1.223 | 15.8 [13–23] |
| london | 1.421 | 13.3 [11–17] | 1.719 | 15.6 [13–20] |
| ny | 1.944 | 13.1 [10–16] | **2.633** | 18.7 [15–28] |
| weekly | 1.691 | 15.7 [12–20] | 2.345 | 15.3 [13–21] |
| rolling 4-day | 1.389 | 20.3 [16–27] | 1.444 | 25.4 [19–34] |
| rolling fortnight | 1.363 | 59.1 [42–102] | 1.388 | 51.2 [40–98] |
| daily + weekly agree | 1.484 | 15.7 [12–20] | 1.183 | 18.0 [14–24] |
| unweighted (TWAP) | 2.024 | 13.1 [12–18] | 1.343 | 14.6 [12–21] |

**The shipped anchor is the BEST on 1h and the WORST on 4h.** Every alternative
that beats it on 4h loses to it on 1h. That is H-026's signature for no effect — a
sign that flips between timeframes — and it is the same shape that killed the
fibonacci filter (−25.7 days on 1h, +344.6 on 4h).

And on the metric that decides pace, nothing separates at all: **every 4h days band
overlaps every other**, and on 1h only the two rolling anchors sit outside the
baseline's, both worse. One arm — rolling fortnight on 1h — **loses to its own
null** (1.363 against 1.498).

**Verdict: the anchor does not carry an effect at this depth. Keep 00:00 UTC.**
The one thing worth taking from the run is that a mid-session anchor is not
obviously wrong either; it is simply not distinguishable, which closes the axis
rather than recommending a change.

<details><summary>what was run</summary>

Seven arms on gold 1h and 4h, blind walk-forward, paired null, same grid and costs:
UTC 00:00 (shipped), London 07:00, NY 13:30, weekly, rolling 4-day, rolling
fortnight, and daily+weekly agreement.

**Why it should matter:** midnight UTC is not a moment any gold desk cares about,
and H-001 established on this repo's own data that **13:30 UTC is the only session
clock carrying anything on FX and metals**. Both the signal and the stop are
measured in this band, so the anchor moves both.

**How it was judged:** an arm had to beat the baseline *and* its own paired null,
on both timeframes, with a days band that does not overlap the baseline's. None
did.
</details>

### 1.2 The "V" in VWAP is doing almost nothing — MEASURED 2026-09-10

Recomputing the band **unweighted** (a session TWAP ± the same std) against the
shipped volume-weighted version:

| market | z correlation, VWAP vs TWAP | follow-through, volume | follow-through, time |
|---|---|---|---|
| XAUUSD 1h | **0.9977** | +24.6 bps | **+27.8** |
| XAGUSD 1h | 0.9792 | +35.8 | +33.4 |
| ETHUSDT 1h | **0.9983** | −5.7 | **+4.7** |
| BTCUSDT 1h | 0.9917 | +4.5 | **+13.6** |

The two signals are the same signal. On three of four markets the *unweighted* band
has better follow-through.

**Two consequences, and the second is the important one.**
* A TWAP arm was run in the walk-forward alongside the anchors: **1h 2.024 against
  the shipped 2.872, 4h 1.343 against 1.223.** It flips too, so the walk-forward
  does not say unweighted is better - it says the difference is not resolvable,
  which is the same conclusion by a different route.
* **The story we tell about this indicator has to change.** On Dukascopy FX and
  metals, "volume" is a **tick count, not traded size** — so this was never a
  volume-weighted price, and the mechanism is not "distance from the institutional
  benchmark". It is "distance from the session's own mean". A published TradingView
  indicator has to say that, or the first competent person who checks will say it
  for us.

### 1.3 Volume profile — RUN 2026-09-10. **DEAD.**

A real session volume histogram - point of control, expanded to 70% of the
session's volume - in place of the standard deviation band. The value area is 40bps
wide on gold against the VWAP band's ~18bps sigma and price sits outside it 41% of
bars, so it is a genuinely different signal, not a relabelled one.

**It loses to its own null on 1h** (PF@2x 0.942 against 1.000) and the point of
control alone is worse than the VWAP on both timeframes (1.700 and 1.107 against
2.872 and 1.223). Measuring the session's shape does not beat assuming it. A
volume-pressure proxy - bar volume split buy/sell by where the close sits, 24h
accumulation, break must agree - beats its null on both timeframes (1.829 and
1.618) and is slower than the baseline on both.

### 1.4 What the band is made of — NOT STARTED

The band is the volume-weighted standard deviation of `(H+L+C)/3` about the VWAP.
Two substitutions, each one line in `features()`:

* **VWAP ± k × ATR(14).** ATR was tested as a *stop* (`exits.py`) and never as the
  *signal band*. Sigma collapses early in a session and ATR does not — which is
  exactly when the current rule fires most.
* **Close instead of typical price.** Free to test in the same run.

---

## TIER 2 — the VWAP as a structure, not a line

### 2.1 Multi-scale agreement — RUN 2026-09-10. **NEGATIVE.**

Take the daily break only when price is on the same side of the **weekly** VWAP.
Measured in the 1.1 run: **1h PF@2x 1.484 against the baseline's 2.872, 4h 1.183
against 1.223**, and it beats its null on both. It removes 13-15% of the trades and
takes the profit factor with them. The only "filter" made of the same material as
the signal fails the same way the twenty-five foreign ones did.

### 2.1b THE ASIAN RANGE — RUN 2026-09-10. **THE ONE THING THAT HELD.**

Not a VWAP idea at all, and it came out of Kris's volume request. The 00:00-07:00
UTC range as a LEVEL rather than as a session filter: trade its break during the
European and US day.

| | gold 1h | gold 4h |
|---|---|---|
| PF@2x | 1.747 | **2.215** |
| its paired null | 0.504 | 0.459 |
| win rate | 38.0% | 38.4% |
| pass rate | **75.1%** | **76.6%** |
| expected days | 18.6 [16-25] | 19.6 [16-26] |

**No sign flip, 3-5x its null on both timeframes** - the shape a real effect has,
and the first arm in three days of work to show it. It is slower than the VWAP
break (18.6 against 11.7 on 1h), so it is a safety trade, not a speed one.

**And it composes.** Daily-return correlation with the VWAP break is **0.114 (1h)
and 0.192 (4h)** - two different trades on the same instrument:

| book | expected days | pass % | blown % |
|---|---|---|---|
| vwap 1h alone | **11.8 [9-14]** | 59.5 | 37.8 |
| vwap 1h + asia 1h | 13.5 [10-17] | 66.9 | 28.9 |
| **vwap 1h + asia 1h + asia 4h** | 14.9 [11-19] | **73.6** | **22.6** |

Against yesterday's gold+ETH book (72.7% pass, 12.4 days) this reaches the same
pass rate two days slower **with no ETH leg** - no 94%-one-quarter dependency, no
assumed crypto spread, one market to trade. Kris's call, and it needs the second
engine first.

**Caveat that belongs on the same page:** this arm is ORB-family, which is on the
known-dead list for crypto and index futures, and it was picked as the winner after
seeing ten comparisons. It has one study behind it, not a programme.

### 2.2 VWAP slope — NOT STARTED

Gate on the direction of the anchor VWAP itself over the last N bars. Note the
prior: an MA200 slope gate lost to its own block-shuffled control on this exact
strategy, so **this one ships with a shuffled-slope control from the start** or it
does not get run.

### 2.3 Yesterday's VWAP as a level — NOT STARTED

The closing VWAP of the previous session is a level traders watch. Break of *that*,
rather than of a band around today's, is a different trade with the same materials.
Cheapest of the three; run it last.

---

## TIER 3 — the things that decide whether any of it can be traded

These are not VWAP research and they outrank most of Tier 2 by expected value.

1. **Second engine on whatever wins.** Nothing enters `core/chosen.py` without it.
   The current pick has 14 of 14 configurations matched; a new anchor has zero.
2. **Eleven years of gold on the winner.** The only thing ever measured that
   halves the band. It also cost the headline last time — 14.5 days became 20.0 —
   so run it before believing a new number, not after.
3. **The prop firm's real gold spread.** Every cost here is Dukascopy's 1.06bps
   round trip. A prop CFD feed is plausibly 2–4x that, and gold's whole advantage
   over BTC is its cost-to-sigma ratio. One evening on a demo account.
4. **The concentration problem.** Gold 1h keeps +81.6R of 188.4R after deleting its
   best quarter — it survives, but 57% in one quarter is the honest headline risk
   and no anchor change will fix it.

---

## What NOT to do next

* **More entry filters.** Measured to exhaustion. 24 of 25 made the evaluation
  slower.
* **More markets.** Sixteen screened; nothing beats gold, and the class split
  (metals/crypto continue, FX/oil fade) is already explained.
* **A wider basket for speed.** Three legs is the fastest measured; four is slower.
* **Any crypto decision** before the spread is measured.
* **Chasing the VWAP recross's 6.8 days.** Fastest number this project has produced
  and its profit factor is 1.090 — under our own gate, never priced at 3x.
