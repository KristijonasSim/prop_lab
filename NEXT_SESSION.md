# Next session — start here

Written 2026-09-08 at session close. Read `ENGINES.md` for the machine,
`CLAUDE.md` for the rules. This file is only what to do next.

---

## The state in five lines

* **Engines 2 and 3 are built and green.** 130 tests, CI on every push, blind
  walk-forward pipeline, fingerprinting, verification gate. Engine 1 (hypothesis
  generator) is not started.
* **The firm is real:** Thunderbolt, 1 step, **6% target, 3% daily drawdown, 6%
  max drawdown**, unlimited time, €21.89 an account.
* **Kris's goal: ≥60% pass rate within 14 days.** NOT MET.
* **Best blind result: XAUUSD 1h, 62.6% pass in 19.2 days** (H-027, filtered).
  Session started at 257 days.
* The board is `backtests/board.html` — open it, it reloads itself every 30s.

---

## TASK 1 — run the two levers that are already coded

They are committed and unrun. This is a single command, ~15 minutes, and it is
the most likely thing to close the last gap.

```
.venv/bin/python strategies/vwapbreak/hypothesis.py
.venv/bin/python core/build_board.py
```

**Why these two, specifically:**

| lever | why |
|---|---|
| `core/pipeline.TOPN` now `(1, 3, 5, 10)` | `topn=1` has PF **2.150** and avg R **+1.16** but only 0.69 trades/day, so accounts **stall** and never reach 60%. `topn=10` reaches 62.6% but **blows 35%** — ten correlated positions at 0.50% risk put 5% at risk against a **3% daily cap**. Nothing between was ever tested. The answer is probably 3 or 5. |
| `HOLD_HOURS` now `(96, 192, 384)` | The blind selector chose 192 — the longest in the old grid — in **all seven folds**. That is a binding grid edge, not a preference. |

**The frontier you are trying to cross** (gold 1h, filtered, blind):

```
risk    pass%   blown%   days
0.50%    62.6     35.3   19.2
0.75%    55.1     43.5   14.5
1.00%    53.7     45.5   13.0
```

60% at 14 days sits exactly between two rungs. **The blocker is the blown rate,
and it is driven by the daily cap, not the max drawdown.** Anything that cuts
simultaneous correlated exposure should move it.

**If that is not enough, in order of expected value:**
1. A **two-leg book of XAUUSD 1h + 4h only** — both strong and partly
   uncorrelated. NOT the class-wide basket, which failed twice (see below).
2. **Anchor variations** — the whole study used a UTC-day anchored VWAP. A
   session anchor or a rolling window is untested on this shape.
3. **A trailing stop** instead of a fixed one — the payoff is trend-shaped and a
   fixed stop may be giving back too much.

---

## What H-027 is, and why it is not H-002 retuned

Three findings from the deep dive, each measured rather than assumed:

* **The direction is FOLLOW, not fade.** On identical bars, thresholds and
  holds, follow beat fade in **79 of 100 paired cells** (25 of 25 on ETH 4h and
  XAUUSD 1h). H-002's own walk-forward already agreed — it picks `MODE_BREAK` in
  100 of 140 folds. **H-002 is named after a trade it does not make.**
* **A fixed target was destroying the payoff.** Average R rose monotonically with
  reward:risk to the edge of every grid. Removing the target moved XAUUSD 1h from
  **+0.155R to +0.684R**. The shape is one winner in nine carried a long way.
* **It survives its null.** The identical 375-cell search on phase-randomised
  markets found **0 hits in 1,125 cells** across three seeds; its fastest route
  to 60% pass was 30.8 days against the real 12.9.

**And one that contradicts the repo's own prior:** the blind selector picked the
**Asia session (00–07 UTC) in all seven folds** on gold 1h. Asia was put in the
grid *because* H-001 found it the worst session for ORB. Seven independent folds
choosing it is a regime, not a fit. Worth understanding — nobody has explained it.

---

## Do NOT redo these

* **Class-wide baskets.** Failed twice, same mechanism both times. Equal
  weighting divides the book's R/day by the leg count while drawdown falls by far
  less, and the classes contain markets that lose alone. H-027's baskets never
  resolve an account at all. A *two-leg book of two strong legs* is a different
  proposition and is untested.
* **Execution cost as a route to pace.** Measured and closed: 14bps → **0bps**
  moves a book only 57 → 32 days. Free execution buys 33–44% of the days; the
  target needs ~85%. Take the maker fill because it is free and measured safe —
  do not expect it to fix pace.
* **Fading a VWAP extreme.** 0 of 100 cells cleared PF 1.20 and beat their null;
  gold is negative at every threshold and hold.

---

## Open bugs and gaps

| | |
|---|---|
| 2 second-engine disagreements | vwap 30m (4 trades of 330) and 15m (1 of 416). Both at boundaries, neither reaches the board. Fail in `pytest -m slow` on purpose. |
| Nightly slow suite | has never completed clean end to end |
| `core/verify_board.py` | still hardcodes the old 8%/4%/8% firm spec — will disagree with the board for the wrong reason |
| Engine 1 | not started; `core/target_profile.py` and `CANDIDATES.md` exist, no gate |
| The ~90 old stage scripts | still on disk, superseded by `core/pipeline.py` |

---

## House rules that are easy to break

* **Always rebuild and open the UI before reporting.** Kris reads the board, not
  the chat. `.venv/bin/python core/build_board.py`.
* **Always push to `main`.** Every change, straight away.
* **Answer in short key points.** See `HOW_TO_ANSWER.md`. A long reply is a bug.
* **Three years of data, one common window**, snapped to a month start so adding
  a market never moves another market's numbers.
* **Never quote a number that has not beaten its own paired null**, and never one
  chosen on the window it was scored on.
