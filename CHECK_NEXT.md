# What to check next — a do-list, written 2026-09-14 evening

`NEXT.md` is the plan of record and `NEXT_SESSION.md` is the state on the day.
**This file is neither. It is the list of things to physically go and check**,
in order, with the command for each.

**Research on H-027 is finished.** Seven axes are closed by measurement, the
eighth (the risk ladder) is arithmetic and has been run end to end, and the
fastest of 48 cells is 16.8 expected days against a 5–14 day target. Nothing on
this list is a study. If you find yourself designing one, read section 5 first.

---

## 1. Is the bot still alive? — every session, first thing

It runs on the Oracle VM, one cron pass per closed 1h bar at :02.

    KEY=~/trading-bots/bybit_bot/deploy/ssh/oracle_bots      # chmod 600
    ssh -i $KEY ubuntu@89.168.78.138 'tail -30 ~/prop_lab/live/paper/bybit_cron.log'
    ssh -i $KEY ubuntu@89.168.78.138 'cat ~/prop_lab/live/paper/bybit_state.json'

**What to look for, in this order:**

1. **A pass in the last two hours.** Cron fires hourly; a gap means the VM is
   down or the crontab is gone. It has happened: a hardcoded path survived an
   rsync to a different username, cron kept firing, and **the bot placed no
   decision for 18 hours while a six-leg book sat open.**
2. **Does the log print what the exchange RETURNED, not what was sent?** Fixed
   2026-09-13 — `set_backstop` used to print success whether the exchange had
   accepted the stop or refused it, so an unprotected account looked identical
   to a protected one. If you see a bare `backstop stop-loss set at …` with no
   confirmation, that regression is back.
3. **Equity, peak, and open legs** against the state file. Day 4 of 18 as of
   2026-09-14: equity $10,075, peak $10,180.

## 2. The date that matters — 2026-09-28

**18 days from 2026-09-10.** The demo test finishes and it is **the only
out-of-sample, non-simulated evidence this project has ever had.** Every
backtest number in the repo is worth less than it.

**What it can settle** (and it is not the pass rate — ~17 trades is one draw):

* do the **fills** look like the assumed costs, or is the real spread wider than
  `docs/FIRMS.md` assumed;
* does the bot's **bookkeeping** survive three weeks unattended;
* does anything in the live path behave differently from the kernel.

**What it cannot settle:** 59.8%, 21.7 days, or any board number. One account
over 18 days is one sample. Do not let a good or bad result there rewrite a
measured number — write it up as what it is.

The comparison to run on the day: `live/counterfactual.py`, which already exists
and reconstructs what each leg would have done.

## 3. The publish decision — not blocked, but wait

`strategies/vwapbreak/PUBLISH.md` has the paste-ready description, a register of
every factual claim in it with the file that backs it, and the numbers we could
have quoted and deliberately did not. **It carries no performance claim at all.**

**Its recommendation is to wait for 2026-09-28.** The code is done (424 lines,
signals only), the description does not improve by waiting, and publishing first
spends the one clean read. Nothing to do before then except read it and decide
whether a description with no numbers reads as honest or as evasive — **that is
the actual open question and it is Kris's.**

## 4. The email that has been owed since 2026-09-08

Two questions to Thunderbolt, one email, and they have been open for six days:

| | question | what it blocks |
|---|---|---|
| **B1** | **Static or trailing max drawdown?** | worth 17 points of pass rate on a zero-edge strategy; modelled as both, the stricter reading |
| **B2** | **Is XAUUSD tradeable there at all?** | the offer shows crypto pairs, and the only surviving hypothesis is **gold-only** |

**B2 is the bigger one.** If the answer is no, the board describes a simulation
rather than a plan, and every pass-rate number is about a firm that will not
take the trade. Also worth asking: minimum trading days (modelled as 0) and any
consistency rule (max share of profit from one day).

## 5. What NOT to do, and why this section exists

**Do not propose a new H-027 study.** On 2026-09-14 a stale sentence in
`CLAUDE.md` led straight to proposing a study that had already been run four
days earlier. **Check `STRATEGY_LOG.md` and `backtests/vwapbreak/` before
believing any "never been tested" claim anywhere, including in this file.**

Closed by measurement, all in `CLAUDE.md`'s known-dead list:

| axis | |
|---|---|
| entry | 25 filters; the one survivor lost to its own shuffled control |
| timeframe | 5m/15m/30m and volume-clock bars |
| selector objective | four of them, all on one curve |
| exit shape | partial, trailing, VWAP-recross, over eleven years |
| band shape | ATR, percentage, standard-error, asymmetric (H-040) |
| daily-loss guard | H-041's headline was the risk rung (H-042) |
| account overlay, as a class | slower at every rung ≥2% (H-044) |
| **risk ladder** | **arithmetic, run end to end, floor 16.8 days** |

**And if you are about to measure a change that REMOVES trades:** pair it with a
matched-drop null before reading the first number. Fewer trades is less exposure
and less exposure lowers a blow-up rate on its own, so "it lowers blow-ups" is
arithmetic, not a finding. `research/guardsweep.py` has the null.

## 6. The dates already in the diary

| date | what |
|---|---|
| **2026-09-28** | demo test ends — section 2 |
| **2026-12-01** | **re-rank the five settings.** They were ranked on the twelve months to 2026-08-30 and are traded unchanged for one quarter. Same procedure, new twelve months, swap the five, **do not touch them in between** (`core/chosen.py`) |

## 7. Housekeeping, when you have five minutes

    .venv/bin/python -m pytest          # NOT -q: pytest.ini already sets it,
                                        # and a second -q hides the summary line
    git status --short                  # the feed collector dirties data/feeds/

Last full run: **205 passed, 4 skipped, 0 failed.**

## 8. If accounts ever stop being cheap

`strategies/vwapbreak/research/LADDER.md` has the frontier. **Below ~42%
blow-ups the daily-loss guard is strictly the better curve** — 24.4 expected
days against the baseline's 39.2 at a 30% blow-up rate. Kris's 2% risk floor
lands the shipped rule at 43.5% blown, which is the crossover itself, and that
is why the guard has looked useless every time it was measured at the traded
rung. **A business input, not a research question** — it changes the moment the
price of an account changes.
