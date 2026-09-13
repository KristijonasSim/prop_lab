# H-027 on the VOLUME CLOCK — pre-registered 2026-09-13, before the first run

Tier 1 item 2 of `VWAP_BACKLOG.md`. Kris asked for all of tier 1 on 2026-09-10;
item 1 (sub-hour) was run that day and died, item 4 was adopted, item 5 needed no
work. **This is the last one left.**

## Mechanism, stated before any result

Time bars oversample dead hours and undersample active ones. The Asian session
and the NY open are one hour each and carry very different amounts of
information. A standard-deviation band assumes something close to IID,
homoscedastic observations — and a time-sampled series of a market that trades
in bursts is neither.

Sampling every N units of volume instead of every N minutes is the standard
correction (López de Prado, *The Volume Clock*): volume bars are closer to IID
and far less heteroscedastic. **That is precisely the assumption the sigma band
needs and does not currently get.**

Who is on the other side: nobody new. This is not a new edge and it must not be
sold as one. It is the same H-027 rule, measured on a clock that matches its own
statistical assumption. If it works, the gain comes from the band being better
calibrated, not from a new mechanism.

## What is run

The traded rule UNCHANGED — wide stop 2.5–8σ, floor 30 / top 5, no target — on
XAUUSD, with **1h time bars as the control**, over the same window, grid, costs
and blind quarterly walk-forward as the board, with the same paired null.

| arm | clock |
|---|---|
| `1h` | time — the control |
| `vol1h` | volume: a bar every V units, V set so the AVERAGE is one bar per hour |
| `dol1h` | dollar: a bar every D of notional (volume × price), same calibration |

**The calibration is the whole point of the comparison.** V and D are chosen so
each arm produces the same number of bars as 1h over the span. Same bar count,
same horizon arithmetic, different clock — so any difference is the clock and not
the sample size. Sub-hour died precisely because more bars did not mean more
trades; this design removes that confound by construction.

Dollar bars are included because gold ran $1,800 → $3,500 over the long window: a
fixed volume threshold is not a fixed economic threshold, and the backlog notes
dollar bars as the fix for comparing old years with new.

## The caveats, named in advance

1. **`max_hold` stops being a time horizon.** The grid converts HOLD_HOURS to a
   bar count via `TF_BPH`. On a volume clock a bar can span minutes in the NY
   open and hours in a dead Asian session, so a 96-bar hold is 96 bars of
   *volume*, not 96 hours. `TF_BPH["vol1h"] = 1.0` makes it average out to the
   same thing and is exactly right on average and wrong on any single trade.
   **This is a change in what the horizon means, and no result may be reported
   without saying so.**
2. **The session filter reads the bar's OPEN hour.** `features()` uses
   `df.index.hour`, and a volume bar is labelled at its first minute. A bar that
   opens at 06:55 and closes at 09:10 is judged as hour 6.
3. **rvol is relative to a 20×24-bar window.** At one bar per hour on average
   this is ~20 days, matching 1h. It is not exact.
4. **Weekend padding must be dropped BEFORE accumulating**, not after. 21.5% of
   the XAUUSD series is synthetic zero-volume bars, and they contribute nothing
   to a volume accumulator but would otherwise fill buckets with dead minutes.

## The clock does what it claims — checked BEFORE the run, 2026-09-13

If bar duration were flat by hour, the volume clock would be a rename and the
study would be pointless. It is not flat. XAUUSD `vol1h`, 17,699 bars, median
duration **47 min**, p10 20, p90 122:

| UTC hour | median bar | what it is |
|---|---|---|
| 13:00 | **26 min** | NY open — the busiest hour of the day |
| 14:00 | 27 min | NY morning |
| 12:00 | 34 min | pre-NY |
| 03:00 | 88 min | Asian mid-session |
| 20:00 | 186 min | after the US close |
| **21:00** | **220 min** | the deadest hour |

**An 8.5x spread between the busiest and deadest hour.** That is the
heteroscedasticity the sigma band is assuming away, made visible. The clock
compresses the NY open and stretches the post-close dead zone, which is exactly
what it is supposed to do.

**Calibration held.** `vol1h` produced **17,699** bars against the 1h control's
**17,693 live** bars — six apart. The bar-count confound that killed sub-hour is
absent here by construction.

This says the mechanism is present. It says nothing about whether it pays.

## KILL CRITERION — fixed now, before the first backtest

A volume-clock arm survives only if **all three** hold against the 1h control:

1. expected days **below** the 1h control's;
2. its 10–90% noise band **does not overlap** the control's
   (`core/noiseband.overlap`) — the rule that killed the percentage band;
3. it **beats its own paired null**, as every arm on this board must.

**Anything else is a fail and the volume clock is closed by measurement.** The
prior is that it fails: the entry axis of H-027 is already closed, nine band and
anchor variants died in `squeeze.py`, and sub-hour died the week before. A clock
change is a smaller intervention than most of those.

## Honest expectation

Low. The one thing that argues for it is that every previous variant changed
*what the band is*, while this changes *what a bar is* — the one input none of
them touched. That is a genuinely different axis, which is why it is worth the
day. It is not a reason to expect a result.

---

# RUN 1 IS VOID — a bug in this study, found 2026-09-13

**The first run of `volclock.py` produced a number and the number was nonsense.**
Recorded here rather than quietly re-run, because the failure is the third
instance of one specific bug in this repo and the pattern is worth more than the
result.

## What it printed

| tf | sigma bps | trades | win% | PF@2x | days |
|---|---|---|---|---|---|
| 1h (control) | 18.2 | 591 | 20.3 | 2.872 | 11.7 |
| vol1h | **321.3** | 385 | **60.8** | 1.182 | **83.1** |
| dol1h | **194.8** | 406 | 53.7 | 1.027 | 82.2 |

Both arms "failed" the kill criterion. Neither result meant anything.

## The cause

`sweep.vwap_series` finds its session boundary by an **exact timestamp match**:

```python
at_anchor = (df.index.hour == anchor_hour) & (df.index.minute == anchor_minute)
sess = at_anchor.cumsum()
```

Every 1h time bar carries one stamped exactly `00:00`, so on the control this
fires **938 times** across the window. A volume bar is labelled at the first
minute of its bucket — 21:37, 03:14 — and essentially never lands on `00:00`. It
fired **8 times in three years** on `vol1h` and 19 on `dol1h`.

So `cumsum` produced 8 sessions, the VWAP accumulated across months instead of
resetting daily, and the band sigma measured multi-month dispersion of a series
that ran $1,813 → $5,586. Median 326.6 bps against the control's 18.4.

Everything downstream followed mechanically: stops are `2.5–8 × sigma`, so they
became **8–25% wide**, nothing ever stopped out, every trade exited on the
horizon, the win rate jumped to 60.8%, and R/day collapsed to 83 expected days.

## Why it was caught

The sigma column was in the printed table. 321 bps is 3.2%, and gold's intraday
dispersion about its own VWAP is not 3.2%. **The diagnostic that caught it was
printed beside the result rather than computed only when something looked
wrong** — `subhour.py` put `sigma` and `s/cost` in its table for a different
reason and that is what made this visible.

## THE THIRD TIME

`anchors.py::_snap` documents the same masking failure: a 13:30 anchor never
occurs on a 1h series, the mask was empty, and the "NY anchor" arm printed 64.5%
win rate and 402 expected days. Same mechanism, same shape of wrong answer — a
high win rate and an absurd day count, which is what a stop that can never be
hit looks like.

**The lesson is not "check the anchor".** It is that `vwap_series` silently
returns a whole-series VWAP when its mask misses, instead of failing. A mask that
matches nothing is never intentional.

## The fix

`volclock.DayAnchored` resets on the **day change** rather than on a timestamp
equal to `00:00`, reusing `anchors._vwap_on`. On time bars the two are provably
identical — 938 sessions and 18.4 bps either way — and on an irregular clock the
day change still means "reset at the start of the UTC day". Corrected sigma:
**vol1h 21.0, dol1h 22.7**, against the control's 18.4.

`strategies/vwap/sweep.py` is NOT touched. It is a declared kernel in
`vwapbreak/manifest.py`, imported by every hypothesis on the board, and
`anchors.py` already set the precedent that this arithmetic lives in research.

**The wrapper is applied to the 1h control too.** The anchors are identical on
time bars, so the control must reproduce 11.7 days and PF@2x 2.872. If it does
not, the wrapper is wrong and run 2 is void as well. The check is built into the
comparison rather than left to judgement.

---

# RESULT, run 2, 2026-09-13 — DEAD. Neither arm clears the criterion.

**The control reproduced the board exactly**: 591 trades, PF@2x 2.872, 11.7 days
[9–14], 59.8% pass. The day-change anchor is identical to the shipped one on time
bars, as predicted, so the volume arms differ by the clock and nothing else. The
run is readable.

| tf | bars | sigma | s/cost | trades | tpd | win% | PF@2x | null | days | band | pass% |
|---|---|---|---|---|---|---|---|---|---|---|---|
| **1h** control | 22,512 | 18.2 | 17.1 | 591 | 0.93 | 20.3 | **2.872** | 1.107 | **11.7** | 9–14 | 59.8 |
| vol1h | 17,699 | 20.9 | 19.6 | 598 | 0.94 | 20.1 | 1.945 | 0.819 | 13.1 | 11–18 | 60.9 |
| dol1h | 17,698 | 22.5 | 21.1 | 672 | 1.06 | 23.4 | 1.457 | 1.085 | 11.3 | 9–15 | **71.1** |

## Against the criterion fixed before the run

| arm | 1 faster | 2 band disjoint | 3 beats null | verdict |
|---|---|---|---|---|
| vol1h | no (13.1) | no | yes | **FAIL** |
| dol1h | **yes (11.3)** | **no** | yes | **FAIL** |

## `dol1h` is the interesting failure, and it is still a failure

It is faster than the control, takes 14% more trades, and lifts pass rate
**59.8% → 71.1%**. On the pass rate alone it looks like the best thing measured
on this hypothesis in a week.

Its band is **[9–15] against the control's [9–14]**. They overlap almost
completely, so the difference is not resolvable and criterion 2 refuses it. This
is the same rule that killed the flat percentage band in `squeeze.py`, and the
noise-floor study exists precisely because a shuffled gate carrying no
information once reached 60% pass in 14.5 days on this strategy.

Two further things say the same: PF@2x falls monotonically **2.872 → 1.945 →
1.457** across the three clocks, and `dol1h`'s margin over its own null collapses
to 1.457 vs 1.085 against the control's 2.872 vs 1.107. **The clock buys pass
rate by spending edge quality**, which is the trade the concurrency cap already
offers without rebuilding the bars.

## What this closes

**The mechanism was present and still did not pay.** Bar duration ran 26 min at
the NY open to 220 min at 21:00 UTC — an 8.5x spread — so the heteroscedasticity
the sigma band assumes away is real and measurable. Correcting for it changes
nothing that survives the noise floor.

That is worth more than another dead variant. Every previous H-027 arm changed
*what the band is*; this changed *what a bar is*, the one input none of them
touched, and the answer is the same. **Tier 1 of `VWAP_BACKLOG.md` is now fully
closed.**

Not claimed: that volume bars carry nothing anywhere. This is one instrument, one
rule, one three-year window, and `dol1h`'s pass-rate lift is a real number inside
a band — it is unresolved, not disproved. Re-opening it needs a longer window to
narrow the band, not another variant.
