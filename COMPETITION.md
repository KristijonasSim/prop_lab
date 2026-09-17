# Competition entry — 2026-09-15

**WITHDRAWN 2026-09-17. ENTRY 1 DOES NOT SURVIVE ITS OWN NULL.** The 8.9-day
claim below was never tested against a paired null and does not pass one:
shuffling the sequence out of gold makes the top-5 → top-20 ladder speed up by
**2.45x** against the real data's 1.72x, on three seeds that all beat the real
number. The same holds on silver (real 1.53, null 2.69) and on BTCUSDT, where
every cell loses money (PF@2x 0.44–0.80) and the wide configuration still
"resolves" in 14.5 days against 28.2. **The speed came from trade frequency, not
from the edge** — `expected_days = median_days / pass_rate` prices time and not
the evaluation fee. Pre-registration and result:
`strategies/vwapbreak/research/TOPN_NULL.md`, `topn.py`,
`backtests/vwapbreak/topn_rebuilt.json`.

**The study also had no committed code**, which is how it went a day and a half
without anyone being able to re-run it. That is fixed.

**Entry 2 (GVZ/VIX) stands** — it never claimed speed, and it says so below.

---

Kris set a one-hour contest against an agent running on another machine. This is
my submission and the scoring sheet for comparing it against theirs.

---

## THE SCORING SHEET — fill this in for the rival before comparing anything

A profit factor or an equity curve alone is not comparable. These four are:

| | mine | rival |
|---|---|---|
| expected days to a funded account | **8.9** (gold) | |
| its noise band | **8–13** | |
| blow-up rate | 66.1% | |
| tested on data the choice never saw? | **yes**, half held out | |
| cost charged | **2x the measured spread** | |
| markets it holds on | **5 of 5** | |

**If any row is missing from theirs, the comparison is not yet possible.** Send
me their rule and I will run it through `core/run_hypothesis.run_market` so both
sides are scored by the same code on the same folds.

---

## Entry 1 — the shipped configuration is not the fastest one

**Claim: 8.9 expected days on gold against the 15.3 currently traded, with
non-overlapping bands.** `research/TOPN_WIDE.md`.

`core/chosen.py` chose floor 30 / top 5 and recorded the comparison it was made
against: top 5 versus top 1. **It was never compared against top 10, 15 or 20**,
and never at a wider floor.

| market | shipped | this entry | bands disjoint |
|---|---|---|---|
| **XAUUSD** | 15.3 [13–22] | **8.9 [8–13]** | **yes** |
| **EURUSD** | 25.4 [20–37] | **11.8 [10–15]** | **yes** |
| **GBPUSD** | 43.9 [29–71] | **11.4 [11–16]** | **yes** |
| XAGUSD | 22.1 [17–30] | 14.4 [11–18] | no |
| USDJPY | 26.8 [20–40] | 15.8 [13–22] | no |

**Validated out of sample**: the choice of N was made on the first half of the
window and scored on the second, which it never saw. The trend replicates —
28.3 / 18.7 / 12.4 / 10.3 / 10.4 days for top 1/5/10/15/20 — and the shipped
config scores 15.8 blind against this entry's 10.4.

**It also rescues two dead markets.** GBPUSD scored PF@2x 0.684 and USDJPY 0.874
at top 5 — both losing money. The rule was never broken there; it was starved of
trades.

**What it is not:** a new edge. Same rule, same market, more parallel settings.

**What it costs:** blow-ups rise on every market (gold 60.7% → 66.1%). The trade
is attempts that resolve faster, not attempts that succeed more often.

## Entry 2 — gold has a data feed this project believed it did not have

**Claim: GVZ is real information about gold, worth 22 points of blow-up rate.**
`strategies/goldvol/gvzvix.py`.

CLAUDE.md records that gold "trades naked". That is true of order flow and false
in general: CBOE publishes GVZ, the gold volatility index, free and daily back to
2009. **GVZ / VIX** prices gold's fear against equity fear.

Tested for realness three ways, and it passes all three:

* beats a **random gate keeping the same 70 days** on profit factor (4.78 vs a
  p90 of 2.74), R per day (0.330 vs 0.101) and expected days (19.8 vs a p10 of 51);
* splitting one book by whether each trade's **direction agreed** with it gives
  **11.2 days against 53.4**, on halves of the same series with nothing optimised;
* as a filter it takes blow-ups from **44.6% to 22.2%** at the 2% rung the live
  book uses.

**It does not make anything faster.** Seven ways of spending it — standalone, day
filter, risk ladder, sizing overlay, wide configuration, side filter, stacked —
and none beats the unfiltered book on expected days. What it buys is per-trade
quality, and expected days does not reward that.

## What I did NOT find

**A new edge that beats H-027 on speed.** Seven attempts, all measured
identically, all slower or inside noise. Also killed today: the VIX term
structure (H-043, a shuffled series traded gold better than the real one), the
cross-sectional crowd ratio (H-042, real but 5 bps against a 14 bps round trip),
and seven alternative anchor lines (H-044, the VWAP does all the work).

## Owed before either entry trades

1. BTCUSDT, the sixth standard market.
2. A paired null on the top-N result.
3. The operational rebuild — twenty settings is twenty positions at a twentieth
   risk each, and `live/bybit_demo.py` was built for five against one netted
   Bybit position.
