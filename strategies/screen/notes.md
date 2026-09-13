# Four candidates, one gate-2 screen — PRE-REGISTERED 2026-09-13

Kris: *"please test all of them."* Everything named as untested after H-034 died,
run through `core/probe.py` on one pass, with every definition, direction and
kill criterion fixed **before the first number**.

**One thing is deliberately NOT here.** H-026 with a stop and a target is the
honest SMC door, and `CANDIDATES.md` records it as *blocked on Kris: his exact
entry, stop and target rules*. Guessing them would kill it for the wrong reason.
It stays blocked.

## The gate, identical for all four

`core/probe.py`. Forward return after the event against the same statistic on
400 randomly shifted event dates. No stops, no targets, no sizing, no grid —
those are gate 3 and cost days.

Horizons **4, 12, 24, 72** hourly bars. Markets **BTCUSDT** and **ETHUSDT**,
1h perp bars, 2021 → 2026-08. Hurdle **14.0 bps**, the measured crypto round
trip. Entry is the NEXT bar's open; `probe` enforces it.

**A candidate survives only if all four hold:**

1. `edge_bps` **>** 14.0;
2. `pctile` **≥ 95** against its shuffled-date null;
3. same sign in **≥ 4** of the years the reading actually spans — stated
   relative to available years, which is the correction H-034 earned;
4. its **opposite** does NOT also clear 1 and 2. Both sides clearing means the
   market is being measured, not the mechanism, and both die.

**Anything else is closed by measurement.** All four are expected to fail. The
base rate in this repo is 31 dead hypotheses.

---

## H-035 — on-chain exchange flows

**Mechanism.** Coins moving onto an exchange are being positioned to sell; coins
leaving are being withdrawn to hold. The counterparty is whoever absorbs that
supply. This is the only candidate here not derived from an order book.

**Events.** Netflow = `FlowInExNtv − FlowOutExNtv`, daily.

| id | event | direction | control |
|---|---|---|---|
| F+ | netflow in the **top decile** of trailing 90d — coins arriving to sell | **short** | F− |
| F− | **bottom decile** — coins leaving to be held | **long** | F+ |

**THE CAVEAT THAT OUTRANKS THE RESULT.** The feed is daily, published ~24h late,
and every value is `flash` — provisional and revised, with the original print
unrecoverable from the free API. Values are stamped **D+2** so the lag is
honestly handled, but **the revision cannot be**: the backtest reads revised
numbers as if they had been live. **This test is optimistic by construction and
a pass here is weaker than a pass anywhere else on this page.** A pass would
need paid point-in-time data before it meant anything.

---

## H-036 — the funding settlement as an EVENT

**Not H-004, and the difference is the whole hypothesis.** H-004 tested funding
as a **continuous level** scored on every bar and it died cleanly, 0 of 12
walk-forward series clearing 1.20. The settlement **moment** is a different
object: it is a scheduled, observable transfer at 00:00 / 08:00 / 16:00 UTC, and
positioning is adjusted *around* it. Nobody here has tested the moment.

**Mechanism.** At settlement the crowded side pays the other. A position held
only for carry has a reason to close just before paying, and a reason to reopen
after. That is forced, scheduled flow with a nameable payer.

| id | event | direction | control |
|---|---|---|---|
| P+ | settlement bar where funding is in the **top decile** of trailing 90d — longs pay | **short** | P− |
| P− | **bottom decile** — shorts pay | **long** | P+ |

Fires at most 3×/day and only on extremes, so roughly 0.3/day — inside the 1–2
trades/day design constraint.

---

## H-037 — the variance risk premium

**Not H-025.** H-025 tested the DVOL **level** (`dvolz`) and found a real but
small 8.9bps edge. `core/deribit_dvol.py` names a second reading in its own
docstring and it has never been run:

> LEVEL — is risk currently cheap or dear
> **IMPLIED − REALISED — the variance risk premium: is the option market
> over-charging for the movement that actually arrives**

**Mechanism.** Option sellers charge a premium over the movement that actually
turns up; they are paid for bearing risk. When that premium is unusually wide,
the option market is unusually frightened relative to what is happening — and
fear that is not being realised has historically resolved upward in the
underlying.

**VRP** = `DVOL` − realised vol, where realised is the annualised stdev of 1h
log returns over the trailing 30 days, both in vol points.

| id | event | direction | control |
|---|---|---|---|
| V+ | VRP in the **top decile** of trailing 90d — fear over-priced | **long** | V− |
| V− | **bottom decile** — realised is outrunning implied | **short** | V+ |

---

## H-038 — fair value gaps

**The one SMC primitive with a mechanical definition.** `VWAP_BACKLOG.md` ranked
FVG second of five and gave the reason: a three-candle gap is either there or it
is not, so it is the least corruptible by researcher choice. Order blocks and
CHoCH/BOS have far more free parameters and a worse prior; killzones are already
closed by the six-window session study.

**Every parameter is fixed here, before the run**, because CLAUDE.md warns this
family can be made to look good by definition-shopping:

* 1h bars, three consecutive candles `i-2, i-1, i`;
* **bullish FVG**: `low[i] > high[i-2]` — strict;
* **bearish FVG**: `high[i] < low[i-2]` — strict;
* the event bar is `i`, the bar the gap is complete and visible on;
* no minimum gap size in the primary arm. A second arm requires the gap to
  exceed **10 bps** of price, declared now so it is not a later rescue.

**Mechanism, and the honest problem with it.** SMC claims price returns to fill
the gap. But the load-bearing primitive underneath already failed here: H-005
(liquidity sweeps, 541k backtests) and H-026 (AMD) are both dead, and a zone
drawn around a sweep is unlikely to pay if the sweep does not.

| id | event | direction | control |
|---|---|---|---|
| G↑ | bullish FVG forms | **long** — continuation | G↑fade |
| G↓ | bearish FVG forms | **short** — continuation | G↓fade |
| G↑fade | bullish FVG forms | **short** — the gap fills | G↑ |
| G↓fade | bearish FVG forms | **long** — the gap fills | G↓ |

Continuation and fill are tested as explicit opposites. If both "work", both die.

---

## Honest expectation

**All four fail.** H-038 is a price pattern and seventeen of those have died.
H-035 cannot be tested honestly on free data. H-036 and H-037 are the two with
real mechanisms and neither is likely to clear 14bps at a 4–72h horizon.

The reason to run them together is that gate 2 costs an hour for all four, and
the alternative is re-proposing them from memory in three weeks.
