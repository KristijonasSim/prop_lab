# Contest entry, 2026-09-15 — the best next hypothesis that is not the VWAP

Kris: *"now you are in competition with another ai to create best next
hypothesis besides vwap"*. Two to three hours. This is the submission.

**Both hypotheses I ran are dead, both were pre-registered before any number, and
the second one is dead in a way that names what to do next.** No expected-days
row is offered, because neither reached gate 2 and a pace number for a rule that
failed its response test would be a fabrication.

---

## 1. How to compare this against the rival's entry

`COMPETITION.md`'s sheet assumes both sides have a tradeable rule. A hypothesis
that died at gate 1 cannot fill it, so the comparison has to happen one row
earlier. **Ask their entry these six questions before comparing any number:**

| | mine | rival |
|---|---|---|
| were the kill criteria written before the numbers? | **yes** — `strategies/fixflow/PREREG.md`, `strategies/partrev/PREREG.md`, both committed before their stage ran | |
| how many cells were searched, and is the best one scored against the **best-of-N** null? | **200** (H-046) and **72** (H-047), both scored against the max over cells | |
| does it run on all six of `core/universe.STANDARD`? | **yes**, both | |
| is there a control that should show **nothing**? | **yes** — BTCUSDT has no 16:00 fix and stayed silent at −0.29 of the bar | |
| what is the gross edge in **bps**, against the round trip at 2x? | stated per market, both studies | |
| what does it **close** if it is dead? | the clock axis; short-horizon reversal as a standalone rule | |

**If a rival entry reports a p-value without saying how many cells it searched,
that p-value is not comparable to anything here.** H-046 produced a cell at
p = 0.001 that is p = 0.130 once the search is priced. That is the single most
important number in this submission.

---

## 2. H-046 — the 16:00 London fix. Dead. `strategies/fixflow/FIXFLOW.md`

**Mechanism.** Index funds and corporates trade *at* the benchmark rate, so the
flow is price-insensitive, concentrated and pre-announced. Dealers hedge into it
and push price; when the window shuts the pressure stops and the move should come
back. Fade the drift into the fix, hold an hour.

**Result.** 1 of 5 fix markets clears the cost bar, at 1.08x. The pooled test
against an **hour-matched** null gives p = 0.418. And the fix ranks **11th of 24**
on its own placebo clock — the 23 hours with no fix in them are not distinguishable
from the one that has it. The BTCUSDT control was silent, which is the only
criterion of four that passed.

**Then the whole clock, priced.** 200 cells, 20 usable London anchors × 5 markets
× 2 signs. 16 cells at p < 0.05 against 10 expected; best cell **p = 0.130**
against the best-of-200 null; its anchor flips sign across markets, +18.9bps on
silver and −1.9 on EURUSD.

**What it closes.** The hour of the day, as a standalone object, on FX and metals.
**What would reopen it:** an event list. A fix is a *time*; a CPI print is a time
*with a known flow attached*, and this design cannot tell one from the 250
ordinary days sharing its slot.

**One method finding, and it is transferable.** Stage 1 pooled `edge / cost`
across markets, which hands the cheapest market the largest weight — EURUSD's
round trip is 0.19bps against gold's 1.06, so one 4.7bps EURUSD spread scored 6.35
and carried a pooled number nothing else supported. **Never pool a ratio whose
denominator varies 50x across the things pooled.** Stage 2 standardises by each
cell's own dispersion and applies cost separately.

---

## 3. H-047 — participation decides whether a move reverses. Dead, and it is the
better death. `strategies/partrev/PARTREV.md`

**Mechanism.** A move that carries volume is information and stays. A move that
carries none is the liquidity provider's inventory and comes back
(Campbell–Grossman–Wang 1993). The claim is an **interaction**: reversal in thin
participation, continuation in heavy. This repo has only ever used participation
as a filter on the VWAP rule — where the fold selector chose it in **498 of 536
folds** — never as the rule itself.

**The signal is real.** 28 of 72 cells at p < 0.05 against 3.6 expected, and the
best cell beats the **best-of-72** null at **p = 0.000**. The five most
significant cells are all the thin tercile. USDJPY reads +1.00 / +0.47 / −0.41 bps
across thin / mid / heavy, which is the mechanism written as a sentence.

**And it is 2–4x too small.** Best market is GBPUSD at **64% of the 2x round
trip**; 0 of 6 clear it; gold has the wrong sign. The tail does not rescue it —
the |z| response is flat, and the **top 1% of moves is negative on 4 of 6
markets**: past some size a move is information whatever the volume looked like.

---

## 4. THE ENTRY — what I nominate as the next hypothesis, and why

Three independent signals in this repo are now measured as **real and under the
cost bar by less than a factor of four**:

| | gross edge | bar it failed against |
|---|---|---|
| H-024 book depth imbalance | 7.9bps best honest cell | 14bps taker round trip |
| H-011 previous day/week level fade | "real edge, too small" | 28bps |
| **H-047, today** | 0.53bps edge, GBPUSD | 0.82bps at 2x |

**Nominated: H-048 — the round trip is the hypothesis. Re-price the real signals
under a measured limit fill instead of an assumed crossing one.**

*Mechanism, and who is on the other side.* Every rule above is a
liquidity-providing rule: it buys what somebody had to sell. A liquidity provider
who crosses the spread to get on is paying for the privilege of being paid for the
spread, which is the wrong side of its own trade. **H-023 already measured the
alternative on ticks**: through-given-touch fills are **99.8–100%** at every
distance from 5 to 80bps, **96–98%** even assuming 10 BTC resting ahead in the
queue, and adverse selection is ~0 — the forward return one hour after a
through-fill is within **0.08bps** of after a mere touch. On Binance futures that
takes the round trip from **9.0bps to 4.0**. H-024's 7.9bps cell crosses it.

*Why it is the strongest available move.* It is the only lever that acts on
several dead hypotheses at once, it needs no new data, and the instrument to test
it already exists and has already been validated on this repo's own ticks. Every
other candidate on the table buys one hypothesis a second chance.

*What would kill it, written now.* (a) The queue check fails outside BTC — ETH,
SOL and XAUUSD maker numbers are extrapolations and the FX/CFD venues do not let a
limit order earn the spread at all, which is the assumption `core/markets.Cost`
already flags. (b) A resting entry misses exactly the moves it most wants — if
fill rate correlates with the sign of the next hour, the saving is paid back as
adverse selection. (c) H-023 stage 14 priced a whole book from 14bps to **zero**
and moved it 57 days to 32: free execution buys 33–44% of the pace gap and the
target needs ~85%. **So H-048 can convert dead signals into live ones and still
not reach 5–14 days.** It should be run for what it makes tradeable, not for pace.

*Runner-up, if Kris prefers a market hypothesis to an execution one:* **the
calendar version of H-046.** The clock failed because a fixed hour cannot tell a
release day from an ordinary one. FOMC, CPI and NFP are times with a known,
one-sided, pre-announced flow, they hit all six standard markets at once, and they
are the only feed that reaches gold and FX, which every real feed in this repo
does not. It needs a release calendar — roughly 32 events a year — and that is a
download, not a research problem.

---

## 5. What this session cost and what it bought

Two hypotheses, four stages, 272 cells, every one of them measured against a null
that was chosen before the data was seen. Two deaths, two axes closed, one method
rule (do not pool a ratio across a 50x denominator), and one nomination that is
grounded in three of this repo's own measurements rather than in a paper.

**Neither entry should be traded and neither is offered as a rule.**
