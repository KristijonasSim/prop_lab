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
