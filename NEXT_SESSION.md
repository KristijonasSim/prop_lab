# Start here — written 2026-09-14 evening, for whoever picks this up next

`NEXT.md` is the plan of record; this is the state on the day. The morning's
version, written while H-040 was still running, is at
`docs/archive/NEXT_SESSION_2026-09-14_morning.md`.

**Read `HOW_TO_ANSWER.md` first. Kris asks for shorter answers and means it.**

---

## 1. Nothing is running. Nothing is outstanding.

Four studies were pre-registered and run this session and all four are finished,
scored against criteria fixed before their numbers, and written up:

| | study | file | verdict |
|---|---|---|---|
| H-042 | daily-loss guard, finer sweep + **fixed rung** + a matched-drop null | `research/GUARDSWEEP.md` | **FAIL, all four conditions** |
| H-043 | is −0.50% a curve or one lucky cell | `research/GUARDSWEEP2.md` | **real effect, not an improvement** |
| H-044 | does survival buy speed — **the full risk ladder** | `research/LADDER.md` | **FAIL, axis closed for good** |
| — | the two method debts in `NEXT.md` item D | `core/probe.py`, `core/search_cost.py` | **both paid** |

## 2. The three things to say if Kris asks "what happened"

**1. H-041's guard was the risk rung.** Its headline — 4h blow-ups 70.5% →
48.3% — came from its own scorer handing the guarded arm 2.0% risk against the
baseline's 3.0%. At a fixed rung it is **70.5% → 70.8%**. Its own result section
had flagged this as confound 3 and called the fix not optional, which is the only
reason it was caught.

**2. Something real was found anyway, and it is one rule with four names.**
−0.15/−0.25/−0.35/−0.50% are identical on every number — at 3% risk they are all
0.05–0.17R and the same loser trips all of them. The rule is *stop for the day
once it has booked any real loss*. It beat a matched-drop null on both
timeframes and **held in both halves of the sample**, which nothing else on
H-027 has done. **It halves the trade count and is slower at every rung ≥2%.**

**3. The ladder is exhausted and the pace target was never reachable.** 48 cells
— 2 arms × 12 rungs × 2 timeframes. **The fastest is 16.8 expected days against
a 5–14 day target.** Gold 1h runs 19.5 → 18.0 → 17.8 → 16.8 → 16.8 as risk goes
2% → 5%, while blow-ups climb 43.5% → 58.3% and the continuous curve draws to
−165%. The ladder is the one lever CLAUDE.md exempts from the noise floor and it
has now been run end to end.

## 3. What NOT to propose

**Seven axes are closed by measurement** and are in `CLAUDE.md`'s known-dead
list: entry, timeframe, selector objective, exit shape, band shape, the
daily-loss guard, the account overlay as a class. The eighth, the risk ladder,
is arithmetic and bottoms out above the pace target.

**There is no ninth axis and proposing one is the failure mode this file exists
to prevent.** On 2026-09-14 a stale sentence in CLAUDE.md led straight to
re-proposing a study that already existed. Check `STRATEGY_LOG.md` and
`backtests/vwapbreak/` before believing any "never been tested" claim anywhere,
including here.

## 4. What is actually open

**A. The demo test finishes 2026-09-28.** Day 4 of 18 as of 2026-09-14. It is
the only out-of-sample evidence this project has ever had that is not a
simulation, and every backtest number is worth less than it. `docs/LIVE_TEST.md`.

**B. Publish-or-drop on the TradingView indicator.** The code half is done —
424 lines, signals only, `core/pine.py` fills the five chosen settings from
`core/chosen.py`. **The description is now drafted too:
`strategies/vwapbreak/PUBLISH.md`** — paste-ready text, a register of every
factual claim in it with its source, and the list of numbers we could have
quoted and deliberately did not.

**It carries no performance claim at all.** Not the 59.8% pass, not the 21.7
expected days, not PF@2x 2.872, not the 2.6× null margin. Every favourable
number this project has is inseparable from a method a reader cannot check on
their own chart, so the honest description has none in it. **Its recommendation
is to wait for 2026-09-28** — the code is done, the description does not improve
by waiting, and publishing first spends the one clean out-of-sample read.

**C. B1 and B2 are still unanswered by the firm** and have been since
2026-09-08. One email. Static or trailing max drawdown, and whether XAUUSD is
tradeable at Thunderbolt at all. The second one decides whether the board
describes a plan or a simulation.

## 5. If accounts ever stop being cheap

`research/LADDER.md` has the frontier. **Below ~42% blow-ups the guard is
strictly the better curve** — at ≈30% blown it needs 24.4 expected days against
the baseline's 39.2. Kris's 2% risk floor lands the shipped rule at 43.5% blown,
which is the crossover itself, and that is why the guard has looked useless
every time it was measured at the traded rung. **That is a business input, not a
research question.**
