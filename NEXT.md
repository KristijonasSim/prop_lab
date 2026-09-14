# What to do next — rewritten 2026-09-14

The plan of record. The previous version was written 2026-09-07, described a
board whose two survivors are no longer what the project trades, and had been
overtaken for a week; it is kept at `docs/archive/NEXT_2026-09-07.md`.

**Nothing below is chosen. Kris picks.**

---

## The state in seven lines

* **One hypothesis: H-027, the VWAP band breakout on gold.** Set by Kris
  2026-09-09 and unchanged. A new hypothesis is out of scope unless he asks.
* **The rule is frozen and pinned in `core/chosen.py`** — XAUUSD 1h, five
  settings in parallel, 2% total risk. **59.8% pass, 21.7 expected days, band
  16.8–31.4.** The band overlaps the measured luck zone; the number is a
  measurement, not a promise.
* **It is trading a demo account.** Bybit XAUUSDT, one cron pass per closed 1h
  bar on the Oracle VM, armed 2026-09-10 11:56 UTC. See `docs/LIVE_TEST.md` for
  the test, `live/DEPLOY_VM.md` for the box.
* **SEVEN axes are now closed by measurement, not by opinion.** Entry (25
  filters, 2026-09-08), timeframe (5m/15m/30m and volume bars, 2026-09-10 and
  09-13), the selector's objective (four of them, `strategies/beat/`,
  2026-09-13), exit shape (2026-09-10, re-run over eleven years), band shape
  (H-040, 2026-09-14), the daily-loss guard (H-041/042/043) and the account
  overlay as a class (H-044). All seven are in `CLAUDE.md`'s known-dead list.
* **Nothing has beaten the shipped rule.** Three attempts on 2026-09-13, one of
  which cleared both pre-registered conditions on speed and died on blow-up
  rate; four more on 2026-09-14, one of which is real and costs speed.
* **THE EIGHTH LEVER IS ARITHMETIC AND IT HAS NOW BEEN RUN.** H-044 took both
  arms over the full risk ladder, 0.25% to 5.00%, on both timeframes — 48 cells.
  **The fastest is 16.8 expected days.** Gold 1h runs 19.5 → 18.0 → 17.8 → 16.8
  → 16.8 as risk goes 2% → 5%, while blow-ups climb 43.5% → 58.3%.
* **The pace target is 5–14 days, and H-027 has never met it at any position
  size.** 21.7 with a band to 31.4 is outside it, and so is every one of the 48
  cells. This is not a tuning problem and there is no dial left to turn.
* **The indicator is written but not published.** `strategies/vwapbreak/
  indicator.pine` is 424 lines, signals only, and `core/pine.py` fills the five
  chosen settings into it from `core/chosen.py`. Deliverable 2 is now a decision
  about publishing, not a build.

---

## Open, in the order the evidence favours

### A. Let the demo test finish. Cost: nothing.

18 days from 2026-09-10 is **2026-09-28**. It is the first out-of-sample
evidence this project has ever had that was not a simulation, and every backtest
number above is worth less than it. Day 4 of 18 as of 2026-09-14: equity
$10,075, peak $10,180, four short legs open.

**What it can and cannot settle.** One account over 18 days at 0.93 trades a day
is roughly 17 trades. That resolves nothing about the 59.8% pass rate — it is one
draw from it. What it CAN settle is everything a backtest cannot see: whether the
fills look like the assumed costs, whether the bot's bookkeeping survives three
weeks unattended, and whether the spread on a real venue is what `docs/FIRMS.md`
assumed.

### B. ~~The band-shape axis~~ **CLOSED 2026-09-14, and so is everything after it**

**H-040 ran it** (`research/bandshape.py`, `BANDSHAPE.md`): atr, pct, sterr,
asym against the shipped sigma band, both timeframes, pre-registered. **Every
arm dead.** Backlog items 9–13 are answered.

**H-041 → H-044 then ran the account-overlay axis**, which was the last one
nobody had touched, and closed it too. The short version, full tables in
`strategies/vwapbreak/research/GUARDSWEEP.md`, `GUARDSWEEP2.md` and `LADDER.md`:

* H-041's −1.0% daily-loss guard was **the risk rung**, not the guard — at a
  fixed rung its 4h result is 70.5% → **70.8%** blown, not 70.5% → 48.3%.
* The guard **converts daily-cap deaths into max-cap deaths roughly 1:1** and
  saves nobody at that threshold.
* A real effect does exist at a tighter threshold — *stop for the day once it
  has booked any real loss* — and it is **the first thing on H-027 to survive a
  pre-registered confirmation**: it beat a matched-drop null on both timeframes
  and held in both halves of the sample. **It is also slower**, and over the
  full ladder it is slower at every rung ≥2%.
* It is the better curve **below ~42% blown**, and the 2% risk floor lands the
  shipped rule at 43.5% — the crossover. **A business input, not a research one.**

**The honest prior in the original entry was right.** It said anything here
needed a pre-registered arm list and a paired null before the first number or it
would produce another 60%-pass artifact. Four studies were run that way and the
one survivor is a trade-off, not an improvement.

### C. Publish the TradingView indicator

Deliverable 2 of the three, and the code half is done: 424 lines, signals only,
no orders and no equity curve, with `core/pine.py` filling in the five chosen
settings so the published script and `core/chosen.py` cannot drift apart.

**What is left is not a build, it is a decision.** Publishing means putting
Kris's name on the claim, and the claim has to carry the band — 21.7 expected
days is 16.8–31.4, which overlaps the luck zone measured on 2026-09-08. Kris's
own framing was that the honesty of the description matters as much as the
numbers, so the description is the work. This does not depend on A or B.

### D. ~~The two method fixes that are owed~~ **BOTH DONE 2026-09-14**

1. **`core/probe.py`'s null now matches hour of day.** `hour_matched_shifts`
   restricts the circular shift to whole days and **checks each candidate
   against the real minute-of-day** instead of assuming a regular grid; where
   the grid cannot support it the old behaviour stands and `null_hour_matched`
   in the output row says so. `tests/test_probe.py` pins it, including the
   counterfactual — on a market whose only structure is an hour-of-day effect,
   the free shift promotes it at the 95th percentile of its own null and the
   matched shift does not. **Screens run before this date are still affected;
   nothing shipped depends on one.**
2. **The search is now priced.** `core/search_cost.py` — `expected_false`,
   `sidak_pctile`, `resolvable`, `verdict`. The usable form is a kill criterion
   rather than a corrected bar: **a 200-resample null cannot express the 99.8th
   percentile a 16-cell family needs**, and `resolvable()` says so, so the
   honest statement is *one cell clearing a null is what a screen this size
   produces anyway — only a monotone family counts*. H-042 closed an axis on
   that arithmetic and H-043 reopened it on the same arithmetic.

---

## Blocked on Kris

| # | Question | Blocks |
|---|---|---|
| B1 | **Static or trailing max drawdown at Thunderbolt?** Worth 17 points of pass rate on a zero-edge strategy. Modelled as both, the stricter reading. | every pass-rate number on the board |
| B2 | **Is XAUUSD tradeable there at all?** The offer shows crypto pairs. The only surviving hypothesis is gold-only. | whether the board describes a plan or a simulation |
| B3 | Any consistency rule — max share of profit from one day? | the top-5 book, which concentrates entries on one bar |
| B4 | Minimum trading days? Modelled as 0. | the 21.7-day headline |

B1 and B2 are answerable with one email to the firm and have been open since
2026-09-08.
