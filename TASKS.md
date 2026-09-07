# TASKS — written 2026-09-07 after pulling `baaa763`

Source: `NEXT.md` (plan, 2026-09-06) + `SESSION_2026-09-06.md` (why).
This file is the checklist. `NEXT.md` is the reasoning behind it.

**State in one line:** gold (XAUUSD) is the only edge that ever beat a paired null
on a walk-forward. Crypto died to the look-ahead fix on 2026-09-06. The remaining
problem is **pace**: after the 2026-09-07 dead-bar fix (T7) the best gold book needs
**143.6 expected days two-step, 55.9 one-step**, against the pace target Kris
set on 2026-09-07: **5-14 days**, across several firms. Past **50 days** the
board flags `TOO SLOW` and the flag overrides the score. Both survivors are
flagged. See `NEXT.md` for the plan — items 1-3, and no new hypotheses first.

---

## Blocked on Kris — answer these first

| # | Question | Blocks |
|---|---|---|
| B1 | **Which prop firm?** Need a real cTrader one-step spec. | T4 (worth 17pp of pass rate) |
| B2 | **Is 144 days to funded acceptable** (56 if one-step) if the edge is real and the account survives? | whether T3 is priority or nice-to-have |
| B3 | **Power of Three — your exact entry, stop and target rules.** Tested version had a fixed session-close hold, no stop, no target. Only that formalisation is dead. | rerun of H-026 |

---

## T1 — `crowd_z` at a 4h hold, with a stop — **DONE 2026-09-07. FAILED its kill criterion.**

**Result:** drawdown does not come from hold length — it goes the other way, monotonically (median maxDD 2,810R at 2h against 184R at 72h; median PF@2x 0.41 against 0.92). The walk-forward at a fixed 4h hold scores PF@2x **0.646** against the 8-72h record's 1.050, with **negative** R/day and zero accounts funded. The signal still beats every null seed; it cannot pay 28bps in four hours. **H-006's short-hold lever is spent.** See `strategies/orderflow/notes.md` stage 9.

<details><summary>original task</summary>

- Kernel: `strategies/orderflow/orderflow.py`. Fixed 4h hold, trailing stop 1.5-3.0 sigma.
- Walk-forward quarterly, config picked blind on 2x-cost train PF.
- Score on **days-to-funded**, not PF.
- Why: `strategies/stack/stage2_size.py` — 19/220 cells clear 14bps and beat 1d/1w/1mo block nulls. BTC `dcrowd_4h` −17.3bps monotone 7/7 years; BTC `crowd_z` −16.2bps 7/7.
- H-006 tested this only at 8-72h holds, no stop, and died of **drawdown** (63.5R, 548 days).
- **Kill criterion:** if a 4h hold does not cut drawdown ~in proportion to the hold ratio, the drawdown is not from hold length. Family finished. Say so and stop.
</details>

## T2 — Nautilus cross-check of the GOLD legs — **DONE 2026-09-07. GOLD SURVIVED.**

**Result:** 5m matched 13/13 entry bars, 1h matched 11/12; matched trades agree on R to
1e-14. Three bugs turned up and all three were the PORT's. The single disagreement was
the **KERNEL's** — see T7.

<details><summary>original task</summary>


- `strategies/vwap/stage15_nautilus.py` is already faithful (commit `0342772`).
- Point it at XAUUSD 5m floor100 top10, and the 1h cell.
- Entry bars must match exactly. Exit-price gaps are a finding, not a failure.
- Why: the only independent-engine check ever run was BTCUSDT 4h MODE_BREAK — one config, one market. Gold is now the whole book and is as unverified as crypto was before it collapsed.
- **If gold does not survive this, the project has nothing.**
</details>

## T7 — the two dead-bar fixes — **DONE 2026-09-07. Edge holds, pace headline does not.**

Stage 19 wrote both fixes down and deliberately did NOT apply them. `stage20_deadfix.py`
applies them and measures the cost. `strategies/vwap/notes.md` stage 20 has the workings.

**The fixes.** (1) The `sd <= 0.0` volatility guard let float cancellation noise (~3e-5 on
gold, the floor is `price·sqrt(eps)`) act as a real band on sessions whose true sigma is
zero — now `sd <= vwap · 1e-6`. (2) The kernel refused neither to DECIDE nor to FILL on
Dukascopy's padded weekend bars, and **21.5% of the XAUUSD series is those**. Both engines
carry both rules; the Nautilus port in stage 17 was patched to match.

| | before | after |
|---|---|---|
| gold cells clearing PF 1.20 @2x measured | 15/20 | **15/20** |
| paired null, same procedure | 1/20 | 2/20 |
| median cell PF@2x | 1.395 | **1.485** |
| best book, expected days two-step | 100.2 | **143.6** |
| same, one-step | 46.9 | **55.9** |

**The signal survives; the median cell got BETTER.** Weekend padding was adding noise, not
edge. **The pace headline does not survive.** The old book's peak drawdown was 8.00R
against an 8.00R cap — exactly on the line — so a 3.8% trade cut takes it to 8.60R,
`riskladder.pick` drops a risk rung, and the day count nearly doubles. The 100-day number
was never robust.

New book: `5m+30m+1h+4h` weighted by **signal-to-cost** — H-012's prescription, now winning
on its own. Control: 3 of 78 real books under 150 days against **0 of 78** null; the null's
fastest needs 474.7 days.

**H-016 got BETTER, not worse.** Ribbon was far more exposed than VWAP — XAUUSD 1h took
25.19R of 54.25R from dead-bar entries and 4h took 11.87R of 2.15R. After the fix its
metals legs clear 11/14 against a null mean of 4.33/14, up from 7/14 against 4.67. Slower
though: 175.9 expected days. Rescored 5.5 → 5.0. H-002 rescored 6.7 → 6.0.

Crypto is untouched: it has **zero** zero-volume bars.

**Still open on this:** the four-leg book and its weighting were chosen on the window they
are scored on, same weak joint as stage 18. Pre-fix results backed up at
`backtests/ribbon/prefix_2026-09-07/` and `backtests/vwap/board.json.prefix-2026-09-07`.

## T3 — Close the pace gap on gold — **items 1 and 2 DONE, item 3 has no headroom**

| step | result |
|---|---|
| 1. combine the gold cells | **WORKS. 193 expected days → 100.2** (5m+4h, equal weight). Null control: 9/78 real books under 150 days, **0/78 null**. |
| 2. re-price at measured cost | Done for the ribbon too. On gold it is worth 0.33 PF; on the ribbon it is a **no-op** — gold's gain and silver's loss cancel. Silver also **loses to its own null** and came off the board. |
| 3. raise risk | **No headroom.** At 1.00% risk peak drawdown is exactly −8.00%, the cap. At 1.25% it is −10.01% and `fail_max` goes 0% → 20.8%. The **max-loss** cap binds first, not the daily-loss limit — the opposite of what `NEXT.md` guessed. |

**SUPERSEDED BY T7.** Every number in this section was measured on the pre-dead-bar-fix
kernel. The 100.2-day book re-scores to 185.8 on the corrected data, and the re-run search
finds 143.6 (55.9 one-step). The conclusion is unchanged in shape and worse in size: if the
firm is one-step the book is near the target, so B1 is still the highest-value open
question. Item 3's finding — the **max-loss** cap binds before the daily-loss limit — is
what makes the fix cost so much, since the old book sat exactly on that cap.

<details><summary>original task</summary>

In order of what to try:

1. **Combine the gold cells** (5m + 1h + 4h). Different holds, same instrument, scored separately so far. Weight by signal-to-cost, **not equally** — H-012's dilution finding.
2. **Re-price everything at measured cost.** Only XAUUSD and EURUSD are done. On gold the correction was worth 0.33 PF and 60 days. Every other board number is still an assumption.
3. **Raise risk deliberately.** Ladder picked 0.25-0.5%. With 78% pass rate there may be room; the **daily** loss limit binds before the max-loss limit.

If none reach ~45 days, say so plainly. A real edge that is 4x too slow is a legitimate answer and points at a different firm structure, not more research.

## T4 — Firm spec + fix the risk-rule defect — **code defect FIXED; the spec is still blocked on B1**

- Confirm: static vs trailing max loss, min trading days, consistency rule, EAs allowed unrestricted.
- Static-only max loss lifts a **zero-edge** pass rate from 40.2% → 57.1%. Bigger than most edges in this repo.
- **Code defect — FIXED 2026-09-07.** `core/riskladder` now routes both call sites through `_breached()`, which reads the flags. Defaults unchanged (both True), so no published number moves — verified. `PropRules(trailing=False)` now means something.

## T5 — Board hygiene — **DONE 2026-09-07**

- H-017 and H-009 are off the board. Records **renamed, not deleted**, with a `WHY_DEAD.md` beside each.
- H-002 rewritten gold-only at measured cost: **6.7** (was 8.6 with its crypto legs).
- H-016 rewritten gold-only at measured cost, silver dropped: **5.5** (was 6.5).
- `stage10_wide.py` writing `stage14_*` files is still unrenamed.

<details><summary>original task</summary>

- `backtests/scoreboard.html` and `backtests/xpos/board.json` still show the pre-fix world: H-017 at 28.5d/9.7d, the crypto legs, silver. All dead.
- Prune or rebuild. Put gold on it with **measured-cost** numbers.
- Rename while touching: `strategies/xpos/stage10_wide.py` writes files named `stage14_*`.
</details>

## T6 — Feed hygiene — **DONE 2026-09-07, no work needed**

- The six 5m rolling feeds (`BTC/ETH/SOL` × `oi`/`taker`) were dirty at pull time and were reverted to the committed version. Local copies reached 2026-09-07 10:25 but held only ~1944 rows over a 7.7-day span — ~270 bars missing; the committed copies were dense but stopped 17h earlier.
- **The cron collector repaired it on its own.** `*/15 * * * * core/feed_collector.py --once` re-fetches a 500-bar (~41h) REST window every pass and merges on the index, so the gap refilled within two passes. All six files are now **dense — zero missing bars — through 2026-09-07 10:40 UTC**.
- Nothing to re-download. The dirty local copies were a half-written snapshot, not better data. Backup kept at `/tmp/claude-1000/-home-kris-prop-lab/a0857ce8-44df-439c-9ec4-3bf1321c45af/scratchpad/feeds_backup/` and can be deleted.
- Worth knowing: the collector self-heals any gap shorter than ~41h. Longer than that is unrecoverable — Binance serves no history on this endpoint.

---

## Do NOT do

- **More single-feed crypto hypotheses.** Six measured, all in the 1-9bps band: quarter-hour 2.67, absorption 6.55, depth 7.9, DVOL 8.9, premium ~10.9, crowd ~17. Spec needs 8-20bps **net**. The band looks structural.
- **Signal stacking.** Tested. Feeds nearly independent (median |corr| 0.027) and combining scored **3.1bps worse** than the best single ingredient.
- **Moving down the cap curve.** 0 of 935 depth cells clear 14bps across 11 coins. The small-cap effect is 3-second and does not reach 15m-4h.
- **Three copies of one strategy on three accounts.** Perfectly correlated, pass or fail together. The 1-(1-p)^3 arithmetic needs genuinely different strategies.
- **Silver.** 2 real cells vs its null's 2, and costed at half the measured spread (2.25 assumed vs 4.554/side). Dead twice.
- **A wider universe as a drawdown cure** without solving weighting first (H-012).

---

## BACKLOG — logged, ranked, not started

Source: `RESEARCH_2026-09-06_FEEDS_AND_HYPOTHESES.md` §3, and `SESSION_2026-09-06.md` §"What is left".
Of the ten ranked hypotheses, H-024/025/026/027/028 were built and closed the same day. These five remain.

| ID | hypothesis | why it is here | why it is not higher |
|---|---|---|---|
| **H-030** | **A feed layer for gold** | Gold is the only survivor and it trades **naked**. COT (weekly, 3d stale) + CME daily volume/OI, both free. Too slow to trigger, maybe fast enough to **gate**. | Honest expectation from weekly data on an intraday strategy is small. But it is the only market left, so the asymmetry is good. **Top of the backlog.** |
| H-029 | Premium conditioned on depth | H-013 killed the perp premium standalone and as a flat gate, never conditioned on **how thin the book was**. Rich premium into a deep book = arbitrage working; into a hollow book = leverage with nothing under it. H-013 averaged over both. | Depends on H-024 landing. **H-024 failed on cost**, so this likely dies with it. Needs a decision before any work. |
| H-031 | Liquidation-pressure proxy | Binance per-event liquidation dumps are gone (verified: zero files). Reconstruct from OI collapse + adverse price + one-sided taker, all in the 5m metrics feed. Fade the flush. | Two strikes: "fading an extreme" is on the known-dead list, and the cascade literature says early warning is event-heterogeneous. The OI ingredient is the only new part. |
| H-032 | Spot ETF flows | Strong published effect — 21% of daily return variation, 53bps per $100M. | **Fails the phase constraint, not the edge test.** Daily, published after the US close, history only from 2024, at most one trade a day. Explicitly logged as a future candidate, not built now. |
| H-033 | Hyperliquid account-level flow | "Follow the accounts that actually win" — a mechanism nothing else here can express. History grows daily. | 13 months of perp history cannot be walk-forwarded, egress is requester-pays, and Binance leads the venue by 700ms so the obvious edge is an HFT edge. |

**Blocked, not backlog:**

- **One-step, three-account timing math.** Kris asked for it. Blocked on there being a book at all — after the engine fix there is nothing left to price it on. Unblocks if T2 (gold Nautilus check) passes.

**Note on the backlog as a whole:** four of the five are crypto single-feed or
feed-derived ideas, and `NEXT.md`'s "Do NOT do" list says six of those have now
been measured into a **1-9bps band** against a spec that needs 8-20bps net. Treat
H-029/031 as needing a new argument, not just a free slot. H-030 is the exception
— it serves the one book that survived.
