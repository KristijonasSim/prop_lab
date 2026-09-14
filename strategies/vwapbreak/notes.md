# H-027 — VWAP band breakout on gold

**This is the project's single focus** (Kris, 2026-09-09) and the only rule that
is trading anything. It is also the one strategy folder that had no `notes.md`,
though `README.md` tells you to read one before touching a hypothesis's code.

**This file is an index, not a record.** The work is written up where it was
done, and nothing here restates a number that lives somewhere else — that
duplication is how this repo ended up with two boards disagreeing.

## The rule, and where it is defined

`core/chosen.py` is the single definition: XAUUSD 1h, five configurations in
parallel at a fifth of the risk each, 2% total. The board does NOT pick it — the
file says why, at length. The Pine indicator and the board both read from it, so
they cannot drift apart.

**The settings expire.** They were ranked on the twelve months ending
2026-08-30 and are traded unchanged for one quarter. Re-rank 2026-12-01.

## Where everything is

| what | where |
|---|---|
| the rule as traded | `core/chosen.py` |
| the kernel, whole hypothesis in one file | `strategies/vwapbreak/hypothesis.py` |
| what the board record depends on | `strategies/vwapbreak/manifest.py` |
| the demo-account test and its spec | `docs/LIVE_TEST.md` |
| the bot that trades it | `live/bybit_demo.py`, `live/DEPLOY_VM.md` |
| everything left to test, ranked | `docs/VWAP_BACKLOG.md` |
| the published indicator | `strategies/vwapbreak/indicator.pine` |
| the publication description and its claims register | `strategies/vwapbreak/PUBLISH.md` |
| per-study workings | `strategies/vwapbreak/research/` |
| every variation tried, pass or fail | `STRATEGY_LOG.md` |
| what is closed and must not be re-proposed | `CLAUDE.md`, known-dead list |
| what to check next, as a do-list | `CHECK_NEXT.md` (repo root) |

## What is closed, so you do not re-open it

**Seven axes are closed by measurement as of 2026-09-14**, and each is written
up in `CLAUDE.md`:

* **Entry.** 25 filter candidates, 2026-09-08. 24 of 25 raise profit factor and
  LOWER R per day, which makes the evaluation slower — the metric is
  `days = maxDD_R / R_per_day`, not PF. The one survivor lost to its own
  block-shuffled control.
* **Timeframe.** 5m/15m/30m (2026-09-10) and volume-clock bars (2026-09-13).
  Every band overlaps 1h's.
* **The fold selector's objective.** Four of them (`strategies/beat/`,
  2026-09-13). All four sit on the same frequency-versus-survivability curve and
  profit factor is the best of them.

* **Exit shape.** 2026-09-10, re-run over eleven years. Partial, trailing and
  VWAP-recross all measured and rejected.
* **Band shape.** H-040, 2026-09-14 (`research/BANDSHAPE.md`). ATR, percentage,
  standard-error and asymmetric bands against the shipped sigma band. Every arm
  dead. Backlog items 9–13 are answered.
* **The daily-loss guard.** H-041 → H-043 (`research/GUARDSWEEP.md`,
  `GUARDSWEEP2.md`). H-041's headline was **the risk rung**, not the guard —
  held at one rung its 4h result is 70.5% → 70.8% blown, not 70.5% → 48.3%.
* **The account overlay as a class.** H-044 (`research/LADDER.md`). Over the
  full risk ladder the guard is slower at every rung ≥2% on both timeframes.

**There is no untouched axis left.** The eighth lever, the risk ladder, is
arithmetic rather than a search and has now been run end to end: 48 cells, and
**the fastest is 16.8 expected days against a 5–14 day pace target. H-027 has
never met the pace target at any position size.**

**The one real finding of 2026-09-14, and it is a trade-off, not an
improvement.** *Stop for the day once it has booked any real loss* — the rule
that −0.15/−0.25/−0.35/−0.50% all express — beat a matched-drop null on both
timeframes and held in both halves of the sample, which nothing else here has
done. It halves the trade count and is slower. It is the better curve **below
~42% blow-ups**, and Kris's 2% risk floor lands the shipped rule at 43.5% —
the crossover itself. **A business input, not a research question.**

## The one thing to hold on to

**Quote the band or do not quote the number.** 21.7 expected days is 16.8–31.4,
and the luck zone measured on 2026-09-08 runs 13.3–26.5. The rule beating its
null by 2.6x is the part worth trusting. The pace is not resolved.
