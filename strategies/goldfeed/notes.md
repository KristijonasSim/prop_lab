# H-030 — a feed layer for gold (CFTC positioning as a gate on H-027)

Kris, 2026-09-11: "do it", after H-031 died. Ranked #2 in
`NEXT_HYPOTHESIS_2026-09-10.md`.

## Mechanism, before any result

Gold is the one market left and it trades with no feed. The one free
positioning feed with history is the CFTC Commitments of Traders report for
COMEX gold (disaggregated, futures only, weekly since 2006). Managed money -
CTAs and hedge funds, mostly trend followers - is the crowd.

Two opposite stories, and both are tested because the data should pick:

* **Crowding.** When managed money is already very long, the marginal buyer is
  used up and a long breakout has less fuel, while a short breakout has a
  liquidation behind it. Gate: refuse the crowded side.
* **Flow.** When managed money is adding, a trend has a buyer behind it. Gate:
  trade only in the direction of their weekly change.

**Honest prior: this probably fails.** The report is 3-10 days stale when it
lands, and the 25-filter study already showed gates on H-027 raise profit factor
and LOWER R/day, which makes an evaluation slower. The one survivor of that
study lost to its own shuffled control.

## Data, and when it was knowable

`cot.py`. 1,056 weekly reports, 2006-06 to 2026-09-01. Positions as of Tuesday,
used only from Friday 20:30 UTC (the 15:30 ET release, an hour conservative in
summer); from Monday 20:30 UTC after a week with a federal holiday; from
2025-12-30 for every report caught in the 2025 shutdown backlog. Late, never
early.

**Not used, and why:** CME daily GC volume/OI has no free history. SPDR's GLD
holdings archive now serves a PDF bar list, not the CSV.

## The screen — fixed before the first run, 2026-09-11

Trades: the traded rule's own blind walk-forward (wide stop, floor 30 / top 5,
591 OOS trades, PF 2.951 - `baseline.py` reproduces `core/chosen.py` exactly).
Direction is the sign of z on the signal bar. A gate removes trades; it moves
nothing else. Seven gates, each with its opposite as a control:

| gate | rule | control |
|---|---|---|
| G1 crowd-fade | refuse longs when MM net is in its top 20% of 3y, shorts in its bottom 20% | G2 |
| G2 crowd-follow | the reverse | G1 |
| G3 flow-1w | only trades in the sign of MM's 1-week change | G4 |
| G4 against-1w | the reverse | G3 |
| G5 flow-4w | only trades in the sign of MM's 4-week change | G6 |
| G6 against-4w | the reverse | G5 |
| G7 OI rising | only when total OI rose over 4 weeks | G7' OI falling |

Scored at **2% flat risk, Thunderbolt** (6% target, 3% daily, 6% max) - the
board's own simulation - plus budget-linear sizing as a second read.

## Kill criterion

A gate survives to stage 2 (in-kernel re-run with a block-shuffled gate, as
`gate_null.py` did for MA200) only if **all three** hold:

1. expected days **below the ungated baseline's**;
2. expected days **below the 10th percentile of 50 block-shuffled copies of
   the same gate** (the weekly series cut into blocks at its own median run
   length and reordered: same duty cycle, same persistence, no alignment);
3. its 10-90% noise band **does not overlap** the baseline's
   (`core/noiseband.overlap`).

**H-030 (COT) dies if no gate clears all three.** Seven gates is a search, so a
survivor is a maybe for stage 2, not a result.

---

## RESULT, 2026-09-11 — DEAD. No gate clears criterion 1.

`gates.py` → `backtests/goldfeed/gates.json`. 591 OOS trades, 2024-09 → 2026-05.
Flat 2% risk, Thunderbolt. Baseline **21.7 expected days** (band 16.3–32.1),
PF@2x 2.872, 0.93 trades/day.

| gate | kept % | trades/day | PF@2x | R/day | maxDD R | **days** | band | null p10 | fails |
|---|---|---|---|---|---|---|---|---|---|
| baseline | 100 | 0.93 | 2.872 | — | −19.1 | **21.7** | 16.3–32.1 | — | — |
| G1 crowd-fade | 81.4 | 0.76 | 1.766 | 0.103 | −19.6 | 37.7 | 25.7–62.1 | 26.0 | 1 2 3 |
| G2 crowd-follow | 82.2 | 0.76 | 2.857 | 0.232 | −19.1 | 26.3 | 18.6–36.3 | 22.6 | 1 2 3 |
| G3 flow-1w | 49.2 | 0.46 | 2.210 | 0.097 | −20.6 | 61.6 | 40.3–121.6 | 35.3 | 1 2 |
| G4 against-1w | 50.8 | 0.47 | 3.538 | 0.199 | −9.5 | 38.0 | 25.0–56.3 | 34.3 | 1 2 3 |
| G5 flow-4w | 47.5 | 0.44 | 2.826 | 0.143 | −14.9 | 40.7 | 29.2–68.1 | 37.8 | 1 2 3 |
| G6 against-4w | 52.5 | 0.49 | 2.917 | 0.153 | −9.8 | 56.0 | 34.5–84.0 | 33.4 | 1 2 |
| G7 OI rising | 57.4 | 0.53 | 2.607 | 0.146 | −12.4 | 32.9 | 23.7–47.8 | 38.4 | 1 3 |
| G7' OI falling | 42.6 | 0.40 | 3.228 | 0.150 | −10.6 | 64.1 | 48.3–151.0 | 36.8 | 1 2 |

* **Every gate is slower than no gate.** The 25-filter lesson again: a gate
  cuts trades faster than it cuts drawdown, and `days = maxDD_R / R_per_day`.
* **The crowding story is backwards.** Refusing the crowded side (G1) drops
  PF@2x from 2.872 to 1.766 — the 18% of trades it removes, breakouts in the
  direction managed money is already crowded, are among the rule's best.
  Consistent with H-029: gold moves in momentum, not reversion.
* G4 halves the drawdown (−9.5R) at PF@2x 3.538 — and still needs 38 days,
  because it halves the trades too. It does not beat its shuffled null's p10.
* G7 (OI rising) is the only gate that beats its null, and it is slower than
  baseline with an overlapping band.

**Not claimed:** that COT carries nothing. G1 vs G2 is a 1.1 PF gap on the same
trade count. It says a crowd-aligned tilt in SIZE might matter; that is a new
question with a new search, and it is logged, not run.
