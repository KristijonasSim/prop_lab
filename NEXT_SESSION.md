# Start here — written 2026-09-14, for whoever picks this up next

Kris is away. This file is what to do when he is back. `NEXT.md` is the plan of
record; this is the state on the day.

**Read `HOW_TO_ANSWER.md` first. Kris asked three times today for shorter
answers. Key points, numbers, no essays. He means it.**

---

## 1. THE RUN THAT IS PROBABLY STILL GOING — check this first

**H-040, the band-shape study.** Started 2026-09-14 ~14:30 UTC, in the
background on the desk.

    log     see section 7 - copied to backtests/vwapbreak/bandshape.log on completion
    code    strategies/vwapbreak/research/bandshape.py
    result  backtests/vwapbreak/bandshape.json   <- exists only if it finished
    PRE-REGISTRATION: strategies/vwapbreak/research/BANDSHAPE.md

**If `bandshape.json` exists, read BANDSHAPE.md FIRST, then score the table
against the criterion written there — not against your own judgement.** The
criterion, fixed before the run:

> An arm wins only if it has **fewer expected days with a band that does not
> overlap the baseline's**, AND does not raise the blow-up rate, AND does it on
> **both 1h and 4h**. A win on one timeframe and a loss on the other is noise —
> that is what killed the fibonacci result and H-035.

**If it did not finish, just re-run it:** `.venv/bin/python
strategies/vwapbreak/research/bandshape.py` (~1–2 hours, 10 cells with nulls).

**Expected outcome is that every arm dies.** Four axes have closed this way
already. If that happens, say so plainly: H-027 has no axis left, and the honest
next question is publish-or-drop, not more tuning.

---

## 2. Why this study is the last one

Kris asked "how can we improve this strategy". Four axes are closed **by
measurement** and are in `CLAUDE.md`'s known-dead list. Do not re-propose any of
them:

| axis | verdict |
|---|---|
| entry filters | dead — 25 candidates, 24 raise PF and LOWER R/day |
| timeframe | dead — 5m/15m/30m and volume bars, all bands overlap 1h |
| exit shape | dead — partial/trailing/recross, reversed over eleven years |
| selector objective | dead — four objectives, all on one trade-off curve |
| **band shape** | **H-040, running now. The last one.** |

**I nearly wasted a session today by not checking this.** `CLAUDE.md` still said
the exit axis was untested; it had been closed four days earlier. Corrected in
commit `6280c98`. **Before believing any "never tested" claim in any file here,
grep `STRATEGY_LOG.md` and `ls backtests/vwapbreak/`.**

---

## 3. The live demo account — state as of 2026-09-14 11:20 UTC

    Bybit demo, XAUUSDT 1h, cron :02 every hour on the Oracle VM
    equity $10,347.11  (+3.47%)   target +6%   started 2026-09-10
    FLAT - Kris closed the book by hand at 11:16

**The bot is fine and needs nothing.** The 12:02 pass will have seen the
exchange flat against a 6-leg book, printed `RECONCILE`, dropped the book and
cold-started. That is the 2026-09-13 fix working.

**Three real trades so far. Not one has exited by the rule's own stop or
horizon** — two Kris closed by hand, one the exchange backstop took. Read any
"live validation" claim against that.

| # | closed | net | closed by |
|---|---|---|---|
| 6 | 09-12 12:41 | +$136.51 | Kris |
| 7 | 09-14 02:52 | −$53.88 | exchange backstop |
| 8 | 09-14 11:16 | +$284.52 | Kris |

**The counterfactual on the two hand-closes** (`live/counterfactual.py`):
holding would have made **~$192 more**. Trade 6 clearly (+332 vs +137); trade 8
was a coin flip won by **84 cents** — the highest high since entry was 4344.53
against stops at 4345.37.

**Measured cost, from the real fills:** Bybit charges **2.750 bps/side** on
XAUUSDT, 5.50 round trip, against the 0.915/side `core/markets.py` assumes for a
gold CFD. **Exactly 3.0x** — the pessimistic column this project already reports.

---

## 4. THE ONE THING WORTH MORE THAN ANY BACKTEST — still not done

**Blocker B1: does the firm measure drawdown on EQUITY (open positions
included) or on CLOSED BALANCE?** Open since 2026-09-08. It is one email.

H-039 measured what it is worth (`strategies/vwapbreak/research/MARKTOMARKET.md`):

| | exit-booked (what the board assumes) | marked to market |
|---|---|---|
| fail on the MAX cap | 27.6% | 4.2% |
| fail on the DAILY cap | 22.4% | **45.8%** |
| worst single day | −3.10 R | **−83.16 R** |

Pass rate and total blow-ups are **identical** (50.0 vs 49.9, 50.0 vs 50.0), so
the board's headline numbers stand. What changes is **which cap kills the
account**, and that decides whether a daily-loss guard is worth building.

**Every board number silently assumes closed-balance accounting and that has
never been written down anywhere except in that file.**

---

## 5. What is NOT to be done

* **Do not change the trading rule.** Not a trailing stop, not a partial exit,
  not a take-profit. All measured, all lost. `core/chosen.py` carries the
  rejections with numbers.
* **Do not edit a file a manifest declares — not even a comment.**
  `core/fingerprint.py` hashes bytes, so a docstring change marks every board
  record stale. Nearly done today with five of them; see
  `core/KERNEL_CONTRACT.md` section 6 for the grep that catches it.
* **Do not quote `exitshape.py`'s day counts next to `core/chosen.py`'s.**
  exitshape ran on Upcomers Ash (2% target), chosen.py on Thunderbolt (6%).
  Different firms, not comparable.

---

## 6. Numbers Kris asked for today, so they are not re-derived

**Blind walk-forward, gold 1h, $15,000 from 2026-05-01 at 2% risk, Bybit's real
3x cost:** → **$18,121 (+20.8%)** by 2026-08-31. 205 trades, maxDD −29.9%.
Monthly R: May +9.9, Jun +4.5, **Jul −12.5**, Aug +10.9.

**Annual expectation**, 2 years out-of-sample, 957 trades, at 2% risk and 3x
cost: CAGR **+261%** with maxDD **−65%**; block-bootstrap p10 **+38%**, median
+250%, p90 +907%. **The spread is the answer, not the median.** He was told to
plan on the low end. At 1% risk: ~+106% with −41% drawdown.

**Caveat that must travel with those numbers:** two years, one instrument, and
2026 alone is +204% of it — the January gold run (4695 → 5562 → 4504) dominates
everything.

---

## 7. Housekeeping

* Everything through `ad39d1f` is pushed to `origin/main`. H-040's code and
  pre-registration are **not yet committed** — commit them with the result.
* Gold cache now runs to **2026-09-13**; that is what unlocked the Jun–Aug fold
  (+144 blind trades). Sept 1–13 still has no fold — it needs a complete Sep–Nov
  test quarter.
* **`build_tf(sym, "15m")` is a trap.** Current pandas reads `15m` as fifteen
  MONTHS. The working file is `_15min.parquet`. I damaged `_15m.parquet` twice
  today and restored it from git both times.
* `download(..., force=True)` over a short window **rewrites the whole parquet
  with only that window**. It cost 90,048 rows. The raw `.bi5` files are the
  backstop.
