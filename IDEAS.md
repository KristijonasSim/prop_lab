# IDEAS — project-level levers, not hypotheses

Written 2026-09-07.

**What this file is.** Ideas that change how the *whole project* is run, not
ideas for a new strategy. A hypothesis is "does this market pattern pay". These
are "are we even measuring the right thing".

**Why it is separate.** `NEXT.md` is the agreed plan and should stay short.
`STRATEGY_LOG.md` is the per-variation ledger. Neither is the place for a lever
that applies across every hypothesis at once. **Nothing in here is agreed work
until Kris picks it** — see the status column.

| # | idea | est. value | cost | status |
|---|---|---|---|---|
| **A** | Measure the six unmeasured FX spreads and re-price everything | **high** | half a day | **not started** |
| **B** | Split evaluation risk from funded risk | **high** — 2.5x on speed | half a day | **not started** |
| **C** | Screen on speed, not profit factor | **high** | 1 day | **not started** |
| **D** | Model parallel accounts properly | medium | half a day | **not started** |

---

## The context that makes these urgent

Kris set the pace target on 2026-09-07: **evaluations that resolve in 5–14
days**, across several prop firms. The two surviving hypotheses need **143.6 and
175.9 expected days**. That is roughly **10x away**, not 3x.

Every pace lever *inside* H-002 has already been tried and is spent:

* combining gold cells — worked, 193 → 100 days (pre-fix)
* re-pricing gold at measured cost — worth 0.33 profit factor
* raising risk within the drawdown cap — **no headroom, the cap binds first**

**So speed will not come from tuning the two books that exist.** It has to come
from either a faster mechanism or from measuring something we have been getting
wrong. A and B below are the second kind, and they are cheap.

---

## IDEA A — measure the six unmeasured FX spreads, then re-price everything

### The evidence

`core/fx_spread.py` has measured exactly **two** instruments from real Dukascopy
ticks. Every other market in the walk-forward is charged a cost somebody guessed
in `strategies/vwap/stage1_grid.py::ASSETS`.

For EURUSD the guess was **5.5x too expensive**:

| | round trip | cells clearing PF 1.20 at 2x | best cell |
|---|---|---|---|
| assumed (`ASSETS`) | 1.50 bps | **3 / 20** | 1.273 |
| **measured** (`fx_spread`) | **0.274 bps** | **10 / 20** | **1.644** |

**One measurement took EURUSD from "basically dead" to the second-best market in
the project.** No new code, no new data, no new hypothesis — the strategy was
always this good and we were charging it a made-up fee.

### Why this is the highest-value item in the file

The cost spread across venues is enormous and we have been treating them as
comparable:

| market | round trip | source |
|---|---|---|
| **EURUSD** | **0.274 bps** | measured |
| XAUUSD | 1.83 bps | measured |
| XAGUSD | 9.11 bps | measured |
| **crypto** | **14 bps** | measured, and it is fee + spread, not impact |

**EURUSD is 51x cheaper than crypto.** The screening spec says a strategy needs
8–20 bps net per trade in crypto; on EURUSD that requirement is closer to
0.3 bps. **A signal far too weak to trade on BTC can be a business on EURUSD.**

This reframes the whole "every crypto hypothesis died" result. Twelve price
hypotheses died against a **14 bps** hurdle. Nobody has re-run one of them
against a **0.27 bps** hurdle.

### What to do

1. Extend `core/fx_spread.py` to GBPUSD, USDJPY, AUDUSD, USDCAD, USDCHF, NZDUSD.
   Same method: sample real tick spreads across many hours, add commission.
2. Replace the guessed `ASSETS` costs with measured ones, keeping the guess
   beside it so the correction is visible and auditable.
3. Re-price the existing walk-forward — **no re-run needed**, `reprice()` is
   exact because R is linear in cost.
4. Report which markets change verdict. Expect at least one more EURUSD.

### The honest caveat

**A cheap spread is not an edge.** EURUSD at 10/20 cells still has to clear the
null, the walk-forward and the pace gate, and its median cell was 0.91 at the old
cost. Re-pricing changes what is *worth testing*, not what is *proven*. Also:
EURUSD's 10/20 was computed on the **pre-dead-bar-fix** walk-forward, so it needs
the corrected kernel before anyone believes the exact number.

---

## IDEA B — evaluation risk and funded risk are different numbers

### The evidence

`core/riskladder.pick` refuses any risk level whose peak drawdown exceeds the 8%
cap. That constraint alone forces H-002 to 1.00% risk. But **`expected_days`
already divides by pass rate — it already pays for every blown account:**

| risk | maxDD | pass | killed | median days | **one-step expected days** |
|---|---|---|---|---|---|
| **1.00%** ← what the board picks | 7.5% | 89.8% | 0.0% | 129 | **55.9** |
| 1.50% | 11.3% | 63.5% | 30.0% | 69.5 | 39.3 |
| 2.50% | 18.8% | 49.7% | 49.5% | 40 | 26.2 |
| **3.00%** | 22.6% | 49.5% | 49.7% | 33 | **22.2** |
| **4.00%** | 30.1% | 40.3% | 58.9% | 26.5 | **22.1** |
| 5.00% | 37.6% | 20.6% | 78.6% | 18 | 20.5 |

**Taking 3x the risk funds an account 2.5x faster, after paying for every account
it destroys.** The project has been forbidding that by construction.

### The idea

**Two risk numbers, not one.**

* **Evaluation risk — high.** An evaluation account is a lottery ticket with a
  fixed fee. You do not need to survive it, you need to *pass* it. Blowing half
  of them is fine if the survivors arrive twice as fast, because accounts are
  cheap and Kris intends to run many.
* **Funded risk — low.** A funded account is the asset. Once it exists, the
  objective flips completely: keep it alive, take the drawdown cap seriously.

Nothing in this repo has ever modelled that split. `riskladder` picks **one**
risk and applies it to both phases.

### What to do

1. Add an **evaluation-risk** selector to `core/riskladder.py` that optimises
   time-to-funded and is *allowed* to breach, alongside the existing
   cap-respecting selector which becomes the **funded-risk** number.
2. Report both on the board. The headline should say "passes in X days at Y%
   risk, then trades at Z% once funded".
3. **Cost it in money, not just days.** `expected_days` treats a blown account
   as costing only time. It also costs the evaluation fee. The correct objective
   is *expected cost per funded account*, and that needs a fee input — so **ask
   Kris what an account actually costs before trusting the optimum.**

### The honest caveats

* **This does not create edge.** It changes how the same edge is harvested.
* **The consistency rule may forbid it.** Many firms cap the share of profit that
  may come from one day. A high-risk sprint concentrates profit and can fail the
  consistency check even when it hits the target. **Unverifiable until a firm is
  picked** — this is a real reason B might not survive contact.
* **The optimum flattens then reverses** — 3.00% and 4.00% are the same, 5.00% is
  worse. There is a genuine peak, not a "more is better" gradient.

---

## IDEA C — screen on speed, not profit factor

### The evidence

The identity that decides everything:

```
days = maxDD_in_R / R_per_day × (target / cap)
```

**Profit factor does not appear in it.** Neither does trades per day, except
through R per day.

Yet every screen in this repo ranks by profit factor: stage 1 grids, the
walk-forward fold selector, the gate at 1.20, the null comparison. **We have
been searching for high-PF objects and then being disappointed that they are
slow.** A high profit factor with a tiny R per day is exactly what a slow book
looks like, and our search actively prefers it.

H-002 is the proof: PF 2.016, one of the best numbers the project has produced,
and 143.6 days.

### What to do

1. Add `r_per_day / max_dd_r` as a first-class screening metric everywhere PF is
   currently used to rank.
2. **Change the fold selector** to rank on it inside the training window. This is
   the substantive change — it selects different configurations, not just a
   different report.
3. Keep the PF ≥ 1.20 gate as a *filter*, not a *ranking*. It usefully removes
   things that lose money; it is a bad way to choose between things that do not.

### The honest caveat

**This is a new search, so it needs a new null.** Re-ranking a search by a
different metric is exactly the kind of change that finds a better number
without finding a better strategy. The paired-shuffle null has to be re-run under
the new ranking before any result from it is believed. Budget for that.

---

## IDEA D — model parallel accounts properly

### The evidence

Kris wants 10–20 funded accounts. The board models **one account, restarted after
each failure**. Those are different problems.

At 3.00% risk H-002 passes 49.5% of the time in a median of 33 days one-step.
Run ten evaluations **in parallel**:

```
P(at least one funds) = 1 − 0.505^10 ≈ 99.9%
```

Time to the *first* funded account is far shorter than the single-account median,
because it is the minimum of ten draws rather than the median of one.

### The idea

Report **time to first funded account across N parallel evaluations** beside the
current single-account number, and let N be a slider on the board the way risk
already is.

### The honest caveats

* **This only works with genuinely different strategies or genuinely different
  entry timing.** Already established in `CLAUDE.md`: three copies of one
  strategy on three accounts are perfectly correlated and pass or fail together.
  The `1 − (1−p)^N` arithmetic **does not apply** to identical bots.
  * The one legitimate version with a single strategy is **staggered start
    dates**, which decorrelates the draws through the equity path rather than
    through the signal. That is worth measuring; it is not free.
* **It changes no underlying number.** It is a better description of the same
  edge — useful for planning how many accounts to buy, not for making a slow
  strategy fast.

---

## What these four do NOT do

**None of them creates an edge.** A, C and D change what we *measure* and *look
for*; B changes how an existing edge is harvested. If the underlying signals are
not there, all four produce better-described failure.

The reason to do them first anyway is that they are cheap, they apply to every
future hypothesis, and **A has already demonstrated it can resurrect a market
that was written off.**

Standing constraint from `NEXT.md`: **items 1–3 (fingerprinting, verification
gate, tests) come before new hypotheses.** A–D are measurement and framework
work, not hypotheses, so they can run alongside — but they should not be used as
a reason to defer the verification work again.
