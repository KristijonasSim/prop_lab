# Step 4 — repair the near-misses. Design, 2026-09-22

Kris: *"if it fails 3rd step but not that far off try to tweak and play with
it, if no then move on."* And: *"fixed list, make it bigger — maybe add session
filters, EMAs, VWAPs, some other filter."*

`factory/repair.py`, `tests/test_factory_repair.py`. Step 3 is `docs/STEP3.md`.

---

## 1. What step 4 is, and what it deliberately is not

**It is:** a fixed list of changes, decided before any near-miss was looked at,
applied to the matching subset once, on one cell, with every attempt logged.

**It is not a walk-forward**, and the reason is worth stating because the
diagram said it would be. "Learn on 1 year → trade the next 3 months blind"
protects against a parameter fitted on the training window. **Every idea the
factory produces has a fixed stop, target and hold** (`sources/invent.py`
hard-codes 2 / 3 / 48), so nothing is fitted and a train/test split would
protect against nothing. What protects this stage is step 5's paired null and
step 6's five-year re-check.

**It is not a hunt.** Nineteen of forty-five generated ideas already clear the
cost gate on gold. Poke at a near-miss long enough and one poke gets it through
the rest by luck. The three things that keep it honest:

* the list is **fixed** — adding to it later is a new search and is logged as one;
* each near-miss gets its matching subset **once**. No second round, no repair
  of a repair, no adaptive choice of what to try next;
* a repaired survivor is flagged, so we can later measure whether repaired
  ideas die at step 6 more often than first-try ones. **That is the number that
  says whether this stage was worth having.**

---

## 2. The list, and why it is split

**The finding it is built around.** `CLAUDE.md`, 2026-09-08: 25 entry filters
were screened on H-027 gold — moving averages, fibonacci, six session windows,
volatility regime, day of week. **24 of 25 raised profit factor and LOWERED R
per day**, which makes an evaluation slower, not faster. Every session window
was worse on both timeframes. The one survivor, MA200 slope, then lost to its
own block-shuffled control.

A filter buys quality by spending trades. **Step 3's commonest failure is not
having enough trades** — most generated ideas sit at 0.15–0.5 a day against a
0.4 floor. Handing a thin idea a filter makes its real problem worse. So the
list is split by what actually failed:

| failed on | repairs offered | why |
|---|---|---|
| **trades** | hold 48→24, hold 48→12, target 3→2 ATR, stop 2→1.5 ATR | one position at a time, so anything that frees the slot sooner raises the rate |
| **edge** | London+NY hours, NY hours, with EMA200, against EMA200, price past VWAP(20), ATR14 > ATR100 | spend trades to buy quality — the family above, applied only where there are trades to spare |
| **either** | stop 2→3 ATR, target 3→5 ATR | changes the payoff shape without changing what is traded |

Six repairs per idea, not twelve.

**`against trend` is in the list as a control, not as a candidate.** If both
directions of the same filter "help", the help is the filter cutting trades,
not the trend telling us anything. That is the H-026 sign-flip test, applied
inside the repair list.

**The volatility filter is `ATR14 above ATR100`, not "ATR above its median".**
The grammar cannot say "above its own median" and adding that would be a new
term for one repair. Fast-vol-above-slow-vol is the same idea, expressible.

---

## 3. "Not that far off" — the two scales

A near-miss is a cell that failed **one** gate (the gates short-circuit, so a
`Check` only ever carries its first failure) and failed it narrowly.

**On the count gate, narrowly means a quarter.** 0.30 trades/day against the
0.4 floor, or 75 trades against 100. `repair.NEAR_RATIO = 0.75`.

**On the edge gates, a percentage is meaningless** — the threshold is zero, and
a quarter of zero is zero. The scale used instead is the result's **own
standard error**: within one standard error of breakeven is a result that noise
alone could have flipped, which is the honest reading of "not far off". Further
than that and a tweak is not repairing anything, it is drawing again.
`repair.NEAR_SIGMA = 1.0`, and `check.Check` now carries `mean_r_se` and
`mean_r_drop_best_se` for it.

**On the drift gate**, near-miss means it beat the middle of its own
random-entry control but not the 90th percentile.

`repair.closeness` puts all four on one 0–1 scale so an idea's near-miss cells
can be ranked against each other. That was not cosmetic: a cell that dies on
trade count has no mean R at all, so ranking by mean R sorted every
count-failure to the bottom and picked between them arbitrarily. Found running
the queue on 2026-09-22.

---

## 4. One cell, not twenty-four

Step 3 already searched 24 cells. Re-running every repair across all 24 would
multiply the search by 24 again — and `NEXT.md` records a result withdrawn for
exactly that shape (the top-N study, where widening the configuration bought
"speed" that the paired null beat).

So the repair is applied to **the cell the idea came closest on**, and a
survivor's identity is (idea + repair, that cell). A survivor is written to
`backtests/factory/survivors.jsonl` by `queue.keep`, **not back onto the
queue** — re-queueing it would send it through step 3's 24-cell search a second
time.

**The first passing repair is taken, not the best.** Choosing the best of
several passing repairs would be a selection made on the test data, which is
the move this whole stage exists to avoid.

---

## 5. Two additions to the grammar, and why they are safe

Step 4 needed things `factory/spec.py` could not say.

**`hour`** — UTC hour of day, so a session window is two ordinary conditions
(`hour above 6.5 and hour below 16.5` is 07:00–16:00, since `above`/`below` are
strict). It is a property of bar *t* and of no other bar, so it cannot leak:
knowing the current bar is 14:00 says nothing about the next one's price. It is
carried as a **column** by `factory/cells.py`, because `build.run` drops the
DatetimeIndex before a strategy ever sees the frame. `guard.Window` guards it
like any other column, and a frame without the column returns 0.0 — which makes
every hour condition **false**, the safe direction. A session filter that
silently matched every bar would look like a working filter and be nothing.

**`vwap`** — volume-weighted average of typical price over the last *n* bars.
**It is a rolling VWAP, not a session VWAP**, and the difference matters:
H-027 anchors to a session and that anchor *is* the strategy; this is a filter,
which wants a stable reference rather than one that resets to the price every
morning. A rolling window is also bounded, so it stays inside `guard.Window`
where the guard can check it, instead of needing a precomputed cumulative
column the guard cannot see. It falls back to the unweighted mean when volume
is zero, so a padded weekend does not divide by zero.

**Neither is offered to the idea generator.** `sources/invent.py` does not
enumerate them. They exist to be bolted onto something that already nearly
works, not to widen the search.

---

## 6. What must be watched

1. **The trades repairs may not work at all.** Early runs show `hold 48→24` and
   `hold 48→12` producing the *same* trade count, because trades exit on their
   stop or target long before 48 bars — the hold is not what limits the rate,
   the entry rule's firing frequency is. If the measured lift stays near zero,
   the honest conclusion is that "not enough trades" is a property of the idea
   and not a repairable parameter, and those four repairs should be deleted.
2. **Repair is a draw.** Six repairs on a near-miss is six more tests. The base
   rate to compare against is step 3's own: 5 of 45 ideas pass first try. If
   repairs pass at a similar rate per test, repairing is not better than
   drawing a fresh idea, and it is cheaper to draw.
3. **The multiple-testing cost is real and is paid downstream.** Each attempt
   is one more trial in the ledger's sense. Gate 4 runs inside every attempt —
   so a repair that passes has already beaten a random-entry version of
   *itself* — but six attempts still deserve steps 5 and 6.
