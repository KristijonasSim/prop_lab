# Everything left to test on H-027, ranked

Written 2026-09-10 at Kris's request: *"write me as much points as you can of what
else is left for us to do and test and adapt with vwap to make it better, fast and
stronger… rank them and why you think this could help."*

**Read the ranking as expected value, not as certainty.** Three days of work here
produced one arm that held (the Asian range) out of roughly forty measured. The
prior on any single item below is that it fails. What separates the top of this
list from the bottom is *how much it would move the number if it worked* and *how
directly it attacks the metric that decides everything* —
`expected days = median days to pass ÷ pass rate`.

**Two structural facts that shape the whole list.**

1. **Speed comes from trade frequency, not from a better signal.** The rule takes
   0.93 trades a day. An evaluation resolved on a handful of trades is resolved on
   luck. Anything that multiplies trades without destroying the edge beats anything
   that improves the edge at the same frequency.
2. **Blown accounts are the other half of the metric.** 37.8% of simulated accounts
   die. Every point off that is worth as much as a point of profit factor, and
   nothing on the entry side has ever touched it — the two things that did were the
   concurrency cap and the Asian-range book, both of which trade speed for safety.

---

## TIER 1 — could move the headline number

### 1. Run H-027 below 1h — 5m, 15m, 30m **[DONE 2026-09-10 — DEAD]**

> **RESULT, `research/subhour.py` → `backtests/vwapbreak/subhour.json`.** Nothing
> below 1h is faster, and the reason is NOT the one predicted below.
>
> | tf | trades | tpd | PF@2x | null | days | band | pass % |
> |---|---|---|---|---|---|---|---|
> | **1h** | 591 | 0.93 | **2.872** | 1.107 | **11.7** | 9.3–14.0 | 59.8 |
> | 30m | 643 | 1.02 | 1.348 | 0.805 | 13.2 | 11.3–17.3 | 60.8 |
> | 15m | 606 | 0.95 | 2.003 | 0.875 | 12.5 | 11.0–16.9 | 56.1 |
> | 5m | 701 | 1.10 | 1.862 | 0.666 | 16.9 | 13.9–20.7 | 65.1 |
>
> **The premise failed, not the cost arithmetic.** The whole case was "4x the
> sessions is 4x the signals". It is not: trades/day goes 0.93 → 1.10 at 5m, a
> 18% gain for a 12x finer bar, because `floor 30 / top 5` selection plus a
> horizon measured in HOURS keeps the trade count roughly fixed no matter how
> the bar is sliced. Sample size barely moves — 591 → 701.
>
> **And sigma/cost did NOT degrade** — 17.1 / 17.8 / 18.2 / 18.6 going down the
> timeframes, slightly UP rather than falling towards 6. The predicted failure
> mode never arrived; a different one did. Every sub-hour band overlaps 1h's, so
> none of the differences is resolvable anyway.

**The original entry, kept because the reasoning was sound and the prediction was wrong:** The
board holds twenty cells: ten markets × **1h and 4h only**. The kernel, the grid,
the walk-forward and the caches all support 5m, 15m and 30m — `data/` has
`XAUUSD_dukascopy_5min`, `15min` and `30min` sitting there — and H-027 has never
been run on any of them. H-002 used 5m through 4h routinely.

**Why it should help:** expected days is inversely proportional to how often the
strategy trades. Going 1h → 15m is roughly 4× the sessions and 4× the signals. If
even a third of the edge survives the higher cost-to-move ratio, the evaluation
resolves in a fraction of the time. It also fixes the *quality* problem underneath
the pace problem: 591 trades over two years means the whole result rests on ~20
big winners, and 4× the trades is 4× the sample.

**Why it might not:** cost is charged per trade, and gold's sigma at 15m is roughly
a third of its sigma at 1h while the spread is unchanged — the sigma/cost ratio
that explains why gold beats BTC gets worse as the bar shrinks. This is the same
arithmetic that kills BTC, applied to gold's own timeframe axis. **That is exactly
why it must be measured rather than assumed.**

**Cost:** one run of the existing pipeline per timeframe. Half a day, no new code.

### 2. Volume bars instead of time bars **[NEVER DONE]**

Sample a bar every N contracts of volume rather than every hour. The VWAP, the
band, the horizon and the stop are then all measured on the volume clock.

**Why it should help:** time bars oversample dead hours and undersample active
ones — the Asian session and the NY open are one hour each and carry very different
amounts of information. This is the standard finding in the microstructure
literature (López de Prado, *The Volume Clock*): volume bars have better
statistical properties, closer to IID and far less heteroscedastic, which is
precisely what a standard-deviation band assumes and does not get. It attacks the
same problem the session filters attacked — and every one of those was slower —
but **without throwing any trades away**.

**Bonus:** it doubles as the fix for the 11-year study. Gold went from $1,800 to
$3,500 over that window; dollar bars (volume × price) normalise the notional and
make the old years comparable to the new.

**Cost:** rebuild bars from the 1-minute Dukascopy cache. A day of work, and the
bar builder is reusable for every future hypothesis.

### 3. ~~Measure the prop firm's real gold spread~~ **[DONE AS SENSITIVITY — LARGELY DEFUSED]**

**Superseded the same day.** Re-pricing gold's own trades across cost multiples
(exact, no re-run) says the strategy is nearly cost-insensitive: at **10x**
Dukascopy's spread — 10.65bps round trip, wider than BTC pays — gold still scores
PF 2.361 at 53.9% pass. A round trip is **0.22% of a full stop**, because the stop
is 8-20 sigma wide. Still worth checking the firm's number once; no longer a
blocker for anything.

<details><summary>the original entry</summary>

Every cost in this repo is Dukascopy's: **1.06bps round trip**, measured from
ticks. A prop CFD feed is plausibly 2–4× that.

**Why it matters more than any signal work:** the whole explanation for why gold
works and BTC does not is **sigma ÷ cost** — 17.2 on gold against 3.8 on BTC. At
3bps instead of 1.06, gold's ratio falls to 6 and it sits where silver is now.
Every number on the board is conditional on this one unmeasured input.

**Cost:** one evening capturing quotes on a demo account.
</details>

### 4. Evaluation-aware position sizing **[DONE 2026-09-10 — ADOPTED]**

> **The best safety lever the project has found.** Budget-linear sizing — size in
> proportion to the drawdown budget still remaining — took pass **65.8% → 77.0%**
> and blown accounts **29.5% → 16.9%** for 1.7 expected days. `still_open` moves
> only 4.7% → 6.2%, so it is not the fake-zero-fail trap CLAUDE.md warns about.
> It is live in `core/chosen.py["sizing"]` and in the demo bot. `tier1.py`.

Size each trade against the *remaining* daily and max-drawdown budget rather than a
flat 2%: cut size when the day is already down 2%, and when the account is near its
trailing peak drawdown.

**Why it should help:** the binding constraint is not the profit target, it is the
**3% daily cap** — our worst day is −3.93% at 2% risk and three days in 221 broke
3%. Every one of those is a dead account. This does not need any new edge; it
converts a known failure mode into a smaller position.

**Why it is delicate:** CLAUDE.md forbids a "budget-shrinking risk manager that
sizes down to avoid ever breaching", because it produces a fake 0% fail rate. The
honest version scales *within* a fixed schedule declared in advance and is scored
on the same PASS/FAIL simulation with real breaches. If it only survives by never
trading, that shows up as `still_open` and it fails.

### 5. Risk scaled by band width **[SETTLED 2026-09-10 — NO WORK NEEDED]**

> **The strategy is already volatility targeted by construction.** The stop is
> `k × sigma` and size is set so a stop-out costs `risk_pct`, so position size is
> already ∝ 1/σ. There is nothing here to add. The `min_risk_bps` floor binds on
> ~5% of bars. `tier1.py`.

Position size ∝ 1/σ, so a wide-band session takes a smaller position.

**Why it should help:** the stop is already `k × σ`, so R is normalised — but the
*account* impact of a trade is not, because a wide-σ trade moves the equity curve
further per unit of R. This is textbook volatility targeting and it is the cheapest
untried way to cut the 37.8% blow-up rate without touching the signal.

---

## TIER 2 — real VWAP variants **[ALL CLOSED 2026-09-10 — `research/squeeze.py`]**

> **Every item 6–13 below was run in one study on 2026-09-10** and the entry axis
> of H-027 is now closed by measurement. 1h PF@2x: base **2.872**, pct 1.647, atr
> 1.583, asym 1.346, sunday 1.304, stderr 1.230, compression 1.144, **swing
> 1.009**, confluence 0.544. The swing anchor — rated the most promising VWAP idea
> remaining when this file was written — scores 1.009; event anchors die the way
> clock anchors did. Only the flat percentage band is faster on both timeframes
> (9.3 vs 11.7 on 1h) and its band overlaps the baseline's, so the gain is not
> resolvable. `backtests/vwapbreak/squeeze.json`.
>
> **Do not re-propose anything in this tier.** The text is kept for the reasoning,
> not as work.

### 6. Anchored VWAP from the last swing high or low **[NEVER DONE]**

The classic *anchored* VWAP as traders actually use it: reset the accumulation at
the last significant extreme rather than at a clock time.

**Why it should help:** the clock-anchor sweep of today was negative — midnight,
London, NY, weekly, rolling, all flat — but every one of those is a *time* anchor.
An event anchor is a different object: it measures the average price paid *since
the market last turned*, which is the quantity a trapped position actually cares
about. This is the single largest untested family inside VWAP itself.

### 7. Anchor confluence as a regime **[NEVER DONE]**

Compute daily, weekly and monthly VWAPs and measure how tightly they cluster. Trade
only when they sit within X% of one another.

**Why it should help:** it is not a direction filter — those are exhausted, 25 of
them — it is a *compression* detector built from the strategy's own material. When
three horizons of average price agree, the market has no disagreement left to
resolve, and a break out of that is a different event from a break out of an
ordinary day.

### 8. Week anchored at the real week open, 22:00 Sunday **[PARTIALLY DONE]**

Today's weekly arm anchored at Monday 00:00 UTC. The FX and metals week actually
opens Sunday 22:00, so the arm discarded the first two hours of every week —
including the weekend gap, which is the most information-dense moment of the week
for gold.

**Why it should help:** small and cheap, and the weekly anchor was one of the
better performers on 4h (PF@2x 2.345). It deserves to be tested at the right time
before being written off.

### 9. VWAP ± ATR instead of ± σ **[NEVER DONE]**

**Why it should help:** σ is the dispersion of price *about the VWAP since the
anchor*, so it collapses to near zero early in a session and then grows all day.
The rule therefore fires on a different-sized move at 02:00 than at 20:00 — an
inconsistency nobody chose. ATR does not have that property. ATR was tested as a
*stop* and never as the *band*.

### 10. Percentage bands **[NEVER DONE]**

A band at a fixed number of basis points. Crude, and the point: it removes the
session-shape problem entirely and tells us how much of the edge is the *band* and
how much is simply *distance from the mean*.

### 11. Standard-error bands, σ/√n **[NEVER DONE]**

**Why it should help:** it is the opposite shape to σ. A standard error narrows as
the session accumulates observations, so the band is wide when little is known and
tight when a lot is. If the current rule's real problem is that it fires too easily
early in the session, this fixes it and the percentage band does not.

### 12. Asymmetric bands **[NEVER DONE]**

Separate volume-weighted semi-deviations above and below the VWAP.

**Why it should help:** gold's upside and downside dispersion are not the same, and
the shipped rule uses one σ for both directions — so the long threshold and the
short threshold are not equally hard to reach. Any asymmetry in the result today
could be an artifact of that rather than a real directional edge.

### 13. Compression → expansion **[NEVER DONE]**

Take the break only when the band width sits in the bottom quartile of its own
recent history.

**Why it should help:** it is the squeeze idea expressed in VWAP terms rather than
in Bollinger terms, and it is a *state* rather than a filter — the signal count
does not simply shrink, the population changes. The generic volatility-regime
filter was tested and was slower; band-width percentile is not the same quantity.

---

## TIER 3 — validation. Not edge, but nothing gets traded without it

### 14. Second engine on the Asian range and on partial 2R **[DONE 2026-09-10 — BOTH PASS]**

> 20 of 20 arm-configurations match every bar through NautilusTrader, written from
> the RULE rather than translated from the kernel. Entry-bar match **1.0000**,
> exit-bar match 1.0000, `max |dR|` **7.0e-08** on the partial and **2.2e-16** on
> the Asian range. Both are eligible to trade on the same standard as the shipped
> rule. `nautilus_check2.py`.

Both are candidates as of today and neither has been near NautilusTrader. The
current pick matched 14 of 14 configurations bar for bar; a new arm has zero. **The
look-ahead fix of 2026-09-06 took a whole crypto book off this board.** Nothing
enters `core/chosen.py` without this.

### 15. Eleven years of gold on whatever wins **[DONE 2026-09-10 — AND IT OVERTURNED THE DAY'S BEST FIND]**

> 40 quarters instead of 8. **Nothing is faster than the baseline** (20.0 days
> [18–23]); partial 2R and the Asian range sit OUTSIDE that band on the slow side
> (21–27), so their slowness is real rather than noise. **Partial 2R was rejected
> here**: over three years it doubled the win rate (20.3% → 41.9%) at the same
> pace, but over eleven its PF falls to 1.168 and its worst quarter carries 64.5%
> of the profit against the baseline's 48.3%. The Asian range is the most robust
> arm the project has measured — 71.4% pass, lowest quarter concentration.
> `longcandidates.py`.

The three-year window said 14.5 expected days; eleven years said **20.0**, and the
band halved. Every new arm measured today has two years behind it.

### 16. A pre-registered arm list

Today I ran roughly forty comparisons and reported the one that held. That is
exactly the multiple-comparison problem the paired null exists to catch, and the
null caught it — the Asian range beats its own null by 3–5× — but the discipline
should be structural: **write the arm list down before running it**, and report all
of it. `STRATEGY_LOG.md` does that after the fact; the list should exist before.

### 17. Re-run the whole board on the corrected selector objective

`Pipeline.SELECT_ON` accepts `days` and `rday` as well as profit factor, and on 4h
ranking by days was materially faster (20.6 → 10.3 expected days). It was left at
profit factor because the 1h difference sat inside the band. With any new arm the
question reopens, and the board currently ranks on a metric it does not care about.

---

## TIER 4 — worth knowing about, low expected value

### 18. Re-entry after a failed break
The current kernel resumes scanning at the exit bar. A second attempt after a
stop-out has never been separated from a fresh signal.

### 19. Multi-day VWAP ladders as levels
Yesterday's and last week's *closing* VWAP as horizontal levels, rather than a band
around today's. Cheap; the weakest mechanism story of the group.

### 20. VWAP slope
Only with a block-shuffled slope control shipped alongside it, because an MA200
slope gate on this exact strategy lost to precisely that control.

### 21. Volume-pressure proxy, tuned
Beat its null on both timeframes today (1.829 and 1.618) but was slower than the
baseline. Only the 24-hour accumulation was tested; the length was not swept.

### 22. Gold's own feed layer (H-030) **[DONE 2026-09-11 — DEAD]**

> Eight pre-registered COT gates on the traded rule's own OOS trades. **Every gate
> is slower than no gate** — 26.3–64.1 expected days against 21.7. The crowding
> story runs backwards: refusing the side managed money is crowded on cuts PF@2x
> 2.872 → 1.766, so gold breakouts WITH the crowd are the good ones. Free CME GC
> volume/OI history does not exist and SPDR's GLD archive is now a PDF, so gold
> still trades naked. `strategies/goldfeed/notes.md`.
COT positioning weekly, CME volume and open interest daily. Gold is the only
survivor and it trades naked. Slow data, so it can only gate, not trigger —
and it is the only genuinely *new information* available to this strategy.

---

## Explicitly closed — do not re-propose without new evidence

| | why |
|---|---|
| Entry filters, as a family | 25 screened; 24 raised PF and lowered R/day |
| Session windows including Asia | every window slower on both timeframes |
| Fibonacci zones | −25.7 days on 1h, **+344.6** on 4h — sign flip |
| Clock anchors | 8 arms; best on 1h is worst on 4h |
| Volume profile / value area | loses to its own null on 1h |
| Point of control as the centre | worse than VWAP on both timeframes |
| Daily+weekly VWAP agreement | 1.484 against the baseline's 2.872 |
| Fixed targets 1R–12R | no target still the best profit factor |
| A wider market basket for speed | 3 legs fastest, 4+ slower |
| More markets | 16 screened, none beat gold |
