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
| per-study workings | `strategies/vwapbreak/research/` |
| every variation tried, pass or fail | `STRATEGY_LOG.md` |
| what is closed and must not be re-proposed | `CLAUDE.md`, known-dead list |

## What is closed, so you do not re-open it

Three axes are closed **by measurement**, and each is written up in `CLAUDE.md`:

* **Entry.** 25 filter candidates, 2026-09-08. 24 of 25 raise profit factor and
  LOWER R per day, which makes the evaluation slower — the metric is
  `days = maxDD_R / R_per_day`, not PF. The one survivor lost to its own
  block-shuffled control.
* **Timeframe.** 5m/15m/30m (2026-09-10) and volume-clock bars (2026-09-13).
  Every band overlaps 1h's.
* **The fold selector's objective.** Four of them (`strategies/beat/`,
  2026-09-13). All four sit on the same frequency-versus-survivability curve and
  profit factor is the best of them.

**The band-shape axis is the only untouched one** — backlog items 6, 7, 9–13 and
18–21. It needs a pre-registered arm list and a paired null before the first
number is read, for the reason the entry axis demonstrates: a gate carrying no
information by construction reached 60% pass in 14.5 days on this exact data.

## The one thing to hold on to

**Quote the band or do not quote the number.** 21.7 expected days is 16.8–31.4,
and the luck zone measured on 2026-09-08 runs 13.3–26.5. The rule beating its
null by 2.6x is the part worth trusting. The pace is not resolved.
