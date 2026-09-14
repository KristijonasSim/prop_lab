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
* **Three axes are now closed by measurement, not by opinion.** Entry (25
  filters, 2026-09-08), timeframe (5m/15m/30m and volume bars, 2026-09-10 and
  09-13), and the selector's objective (four of them, `strategies/beat/`,
  2026-09-13). All three are in `CLAUDE.md`'s known-dead list.
* **Nothing has beaten the shipped rule.** Three attempts on 2026-09-13, one of
  which cleared both pre-registered conditions on speed and died on blow-up rate.
* **The pace target is 5–14 days.** 21.7 with a band to 31.4 is outside it.
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

### B. The band-shape axis, which is the only untouched one left

`docs/VWAP_BACKLOG.md` items **6, 7, 9, 10, 11, 12, 13, 18, 19, 20, 21** have
never been run. They share a shape: they change what the band IS, rather than
what is done when price crosses it. Every closed axis changed the latter.

The honest prior is poor. Entry filters were 25 arms and 0 survivors, and a
shuffled gate scored better than the real one. **Anything here needs a
pre-registered arm list and a paired null before the first number is read**, or
it will produce another 60%-pass artifact — item 16 in the backlog says so and
was written before the last two studies proved it again.

### C. Publish the TradingView indicator

Deliverable 2 of the three, and the code half is done: 424 lines, signals only,
no orders and no equity curve, with `core/pine.py` filling in the five chosen
settings so the published script and `core/chosen.py` cannot drift apart.

**What is left is not a build, it is a decision.** Publishing means putting
Kris's name on the claim, and the claim has to carry the band — 21.7 expected
days is 16.8–31.4, which overlaps the luck zone measured on 2026-09-08. Kris's
own framing was that the honesty of the description matters as much as the
numbers, so the description is the work. This does not depend on A or B.

### D. The two method fixes that are owed

Both were found on 2026-09-13 and both are unfixed in code:

1. **`core/probe.py`'s null does not match hour of day.** An event that always
   fires at 00:00 UTC is compared against a population drawn from every hour,
   which gifts a short-side daily arm about 5bps. Every screen that used it is
   affected.
2. **The search is not priced.** 96 tests at a 95th percentile expect 4.8 false
   passes. This correction was written down for H-028 and rebuilt without it
   three days later.

Neither changes a shipped number. Both change what the NEXT screen is allowed
to claim, so they are cheap now and expensive later.

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
