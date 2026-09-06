# What to do next — written 2026-09-06

Read `SESSION_2026-09-06.md` first for why. This file is only the plan.

## Where the project actually stands

One real edge exists, and it is **gold**. It is the only thing here that has ever
beaten a paired null on a walk-forward: XAUUSD clears PF 1.20 at 2x on 11 of 20
cells against the null's **0 of 20**, and the null's best cell (1.178) does not
even reach the gate.

At the cost we now MEASURE rather than assume it is PF **1.879**, 3.8 trades a
day, 78% pass rate — and **173 median days to funded** against a 45-day target.

**The problem is no longer signal. It is pace.** That is a different problem from
the one the last three weeks have been working on, and the plan below reflects
that.

Two facts that should shape every decision from here:

- **Crypto cannot get there at 14bps.** The screening spec (`core/target_spec.py`)
  says a strategy needs 8-20bps NET per trade depending on frequency. The best
  verified crypto signal is `crowd_z`@4h at ~17bps GROSS, which nets ~3bps. The
  gap is 4-7x, not a tuning problem.
- **A coin flip funds an account.** With zero edge, one account passes 40.2% of
  the time (57.1% if the firm's max loss is static rather than trailing). Pass
  rate alone means almost nothing; what matters is the lift over that line and
  keeping the account afterwards.

---

## Tomorrow, in order

### 1. `crowd_z` at a 4-hour hold, with a stop — the cheapest shot at PACE

The single most promising untested thing in the repo, and it is cheap.

**Why.** `strategies/stack/stage2_size.py` found 19 of 220 cells clear 14bps AND
beat 1d / 1w / 1mo block nulls. At 4h: BTC `dcrowd_4h` −17.3bps monotone 1.00
**7/7 years**; BTC `crowd_z` −16.2bps **7/7 years**; ETH and LINK the same at
6/6. H-006 only ever tested this family at **8-72h holds with no stop**, and it
died of **drawdown** (63.5R, 548 days) — its own log says "the killer is
drawdown, not profit factor". A 4h hold is 2-18x shorter and nobody has run it.

**Do.** Take `strategies/orderflow/orderflow.py`'s kernel, fixed 4h hold, stop at
1.5-3.0 trailing sigma (stage 4 showed wide stops help, tight ones destroy it),
walk-forward quarterly, config chosen blind on 2x-cost train PF. Score on
**days-to-funded**, not PF — H-017 stage 5/6 already showed gates can raise PF
and make the book slower.

**Kill criterion.** If the 4h hold does not cut drawdown by roughly the ratio of
the hold lengths, the drawdown is not coming from hold length and this family is
finished. Say so and stop.

### 2. Nautilus cross-check of the GOLD legs

**Why.** The only independent-engine check ever run covers **one config, one
market: BTCUSDT 4h MODE_BREAK**. Gold is now the entire book and has never been
cross-checked. Three look-aheads were found in this kernel three weeks ago. Gold's
numbers are exactly as unverified today as crypto's were before they collapsed.

**Do.** `strategies/vwap/stage15_nautilus.py` is already faithful (commit
`0342772`). Point it at XAUUSD 5m floor100 top10 and the 1h cell. Entry bars must
match exactly; exit-price gaps are a finding, not a failure.

**This is the highest-risk item on the list.** If gold does not survive it, the
project has nothing.

### 3. Close the pace gap on gold, or decide it cannot close

173 median days must become ~45. Options, in the order I would try them:

- **Combine the gold cells.** 5m, 1h and 4h cells all clear and are different
  holds on the same instrument. They were scored separately; as one book their
  drawdowns may not coincide. Cheap to test, and H-012's dilution warning applies
  — weight by signal-to-cost, not equally.
- **Re-price EVERYTHING at measured cost.** Only XAUUSD and EURUSD have been
  re-priced so far. The correction was worth 0.33 of profit factor and 60 days on
  gold. Every other board number is still on an assumption.
- **Raise risk deliberately.** The ladder picked 0.25-0.5%. With a real edge and a
  78% pass rate there may be room, and the daily-loss limit — not the max-loss
  limit — is what binds first.

**If none of these reach ~45 days, say so plainly.** A real edge that is four
times too slow is a legitimate answer, and it points at a different firm structure
rather than more research.

### 4. Confirm the actual firm spec — it is worth 17 points

**Why.** `core/prop_rules.py` enforces the max loss BOTH static and trailing, as
the stricter reading. Under a **static-only** rule a zero-edge strategy passes
57.1% instead of 40.2%. That is a bigger effect than most edges in this repo.

Also fix the code defect: `PropRules.trailing` and `.static` are documented as
configurable but `core/riskladder.run_accounts` ORs both conditions and reads
neither flag. Since `peak >= 0` the trailing term always dominates, so `static` is
redundant and `trailing=False` is silently ignored.

**Do.** Pick a real cTrader one-step firm, read its spec, and confirm: static vs
trailing max loss, min trading days, consistency rule, and whether EAs are allowed
without restriction.

### 5. Board hygiene — it currently publishes dead numbers

`backtests/scoreboard.html` and `backtests/xpos/board.json` still show the
pre-fix world: H-017 at 28.5d/9.7d, the crypto legs, and silver. All three are
dead. Prune or rebuild, and put gold on it with the measured-cost numbers.

Also: `strategies/xpos/stage10_wide.py` writes files named `stage14_*`. Confusing,
pre-existing, worth renaming while touching it.

---

## Do NOT do these

- **More single-feed crypto hypotheses.** Six have now been measured and every one
  landed in the 1-9bps band: quarter-hour 2.67, absorption 6.55, depth 7.9, DVOL
  8.9, premium ~10.9 quintile spread, crowd ~17. The band looks structural, and
  the spec says 8-20bps NET is required. Adding a seventh is not a plan.
- **Signal stacking.** Tested. The feeds are nearly independent (median |corr|
  0.027) and combining them still scored **3.1bps WORSE** than the best single
  ingredient. Equal weighting dilutes.
- **Moving down the cap curve.** Tested across 11 coins: 0 of 935 depth cells
  clear 14bps. The literature's small-cap advantage is a 3-second effect and does
  not reach 15m-4h.
- **Three copies of one strategy on three accounts.** They are perfectly
  correlated and pass or fail together. The 1-(1-p)^3 arithmetic only applies to
  genuinely DIFFERENT strategies — which is what Kris proposed and what the plan
  should stay aimed at.
- **Silver.** 2 real cells against its null's 2, and its cost was assumed at HALF
  the measured spread (2.25 assumed vs 4.554 per side). Dead twice over.

---

## Open questions for Kris

1. **Power of Three** — the version tested has a fixed hold to the session close,
   **no stop and no target**. Yours presumably has both. Give me your exact entry,
   stop and target rules and I will rerun it; the current result only kills the
   formalisation I chose.
2. **Is 173 days acceptable** if the edge is real and the account survives
   afterwards? That changes whether item 3 is a priority or a nice-to-have.
3. **Which firm?** Item 4 cannot start without one.
