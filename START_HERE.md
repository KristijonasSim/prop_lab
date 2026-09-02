# START HERE

Short version for whoever picks this up next. Full detail is in `HANDOFF.md`.

## Clone and set up

```bash
git clone git@github.com:KristijonasSim/prop_lab.git && cd prop_lab
python3 -m venv .venv
.venv/bin/pip install -r requirements-lock.txt
.venv/bin/python smoke_test.py          # must end with READY
```

`.venv` is the only thing not in git. All market data is committed — do not
re-download anything. (The one thing that would justify an exception is the wide
crypto universe for H-007; see item 1 below.)

## Look at this first

**The board**: <https://claude.ai/code/artifact/f9ac29b6-5251-4510-81d9-ef3d5b7dd3d3>
Rebuild locally with `.venv/bin/python core/build_scoreboard.py`.

Scores below are on the **two-step** evaluation (8% then 5%), the structure the
board has been scored on since 2026-09-02.

| ID | hypothesis | score | verdict |
|---|---|---|---|
| H-009 | **VWAP gated by crowd positioning** | **8.9** | **the best book in the project** — beats H-002 on every scored component |
| H-002 | VWAP | **8.6** | the base it improves on. BTC 4h + ETH 1h + ETH 30m + SOL 4h + gold 5m |
| H-003 | EMA × VWAP cross | 4.0 | rejected — loses to its own null |
| H-005 | Liquidity sweep fade | 3.5 | rejected — null beats it 19,062 to 1,702 |
| H-007 | Cross-sectional crypto ranking | 2.9 | rejected — real edge before costs, too small to pay the spread |
| H-011 | Prev day/week high-low reversal | 2.6 | **beats its null at every cost level** — the first fade here to manage it — but too small to clear the gate |
| H-010 | VWAP band rejection | 2.5 | rejected — loses to its own null; the VWAP target is its worst lever |
| H-001 | ORB | 2.4 | rejected |
| H-008 | Beta-residual reversion | 2.1 | rejected — residual does not revert; null beats real on every cut |
| H-006 | Order flow (fade the crowd) | 1.3 | **signal real, strategy dead** — see below |
| H-004 | Funding fade | — | rejected, code deleted. Finding kept in `RESEARCH_LOG.md` |

H-002 as it stands: PF 1.772, **1.418 at 2x cost**, 5 positions at 0.33 trades/day
each. ETH is the strongest single market, ahead of BTC.

**The "24 days" was a one-step number, and it is gone from the board.** Firms are
two-step (8% then 5%). Since 2026-09-02 `core/riskladder.ladder` scores every
hypothesis on `run_accounts_two_step` and keeps the one-step value beside it for
comparison only, so the board no longer reports a structure nobody trades. H-002
on the real structure: **88% pass, 0% killed, 53 expected days** at 2.00% risk
(the verifier's 49.8 at 2.125% is the same curve on a finer risk step). The
second step is not half the work of the first: it is another chance to breach,
and the drawdown gets paid twice.

Two scores moved when the structure changed — H-002 9.2 → **8.6**, H-005
4.0 → **3.5** — and H-005, H-007 and H-008 now have **no finite time to a funded
account at all**: at every allowed risk level, zero simulated accounts clear both
phases.

**Null seeds were not reproducible until 2026-09-02.** Eleven sites seeded their
shuffle with `hash()` over a string tuple, which Python randomises per process,
so every null was a fresh random draw and none could be checked. Fixed with
`stage3_timeframes.null_seed` (CRC32). It surfaced because H-007 flipped
`beats_null` between two runs of identical code. On the now-fixed seeds H-007
loses to its null by **0.001** (real PF@2x 1.063, null best 1.064) — that verdict
is a coin toss and should be read as "inside the noise", not as a result. Every
**stage-1 grid** null in `RESEARCH_LOG.md` is still on the old unreproducible
draws and is provisional until its grid is re-run.

**H-009 is the headline, 2026-09-02.** Take H-002's trades unchanged and keep
only the ones where the crowd is positioned on the other side — a long only when
the long/short account ratio has been falling, a short only when it has been
rising. Same legs, same stage-10 configurations chosen blind, nothing refitted,
gate threshold fixed at zero.

| same selection rule as stage 11 | gate off | gate on |
|---|---|---|
| profit factor | 1.768 | **2.047** |
| at 2x cost | 1.458 | **1.651** |
| max drawdown | −3.66R | **−2.82R** |
| return / drawdown | 24.6 | **34.4** |
| two-step pass rate | 88.0% | **92.4%** |
| expected days to funded | 53.4 | **48.7** |

It keeps 55% of the trades and total R goes up. It improves **six of six** crypto
legs on both profit factor and drawdown, none hurt. Inverting the gate — keeping
the trades the crowd *agrees* with — gives PF 1.137 and goes negative at a tighter
threshold, so almost all of H-002's edge is in the disagreement. It beats every
null seed, and a shuffled gate hurts.

**It now scores 8.9 against H-002's 8.6**, winning or tying every component.
That took a second null. Scored against a shuffled FEED it measures only the
increment — a far harder test than H-002 faces, worth 0.191 — and it ranked below
the strategy it improves on for that reason alone. Measured the way stage 11
measures H-002, by phase-randomising the MARKET and counting legs that still hold
PF 1.20 at double cost: **6 of 8 survive on the real market, 0 of 8 on the
shuffled one**, a margin of 1.000, the same statistic that gives H-002 its 1.000.
Both nulls are kept. `strategies/orderflow/gated_notes.md` has the argument and
the weaknesses.

**H-006, opened and closed 2026-09-02 — read this before dismissing the 1.3.**
The score is the strategy, not the signal. Binance publishes the long/short
**account** ratio — a headcount of who is positioned which way — and fading it
works: quintile response +25.0 / +21.8 / +13.5 / −0.9 / −13.2 bps over the next
24h, monotone, same sign in 6 of 7 years, and the walk-forward beats every null
seed after costs (**PF 1.050 at 2x against a null best of 0.984**). Following the
crowd instead of fading it loses 13.35bps a trade, so the direction is not
arbitrary. Open interest on its own predicts **nothing** directional — both
tails are +17bps, which is a volatility read. It is positioning that pays, not
leverage and not aggression.

It scores 1.3 because it has **no stop**: R is a return over trailing
volatility, one loser runs the whole hold, and the book draws down **49.8R**
against H-002's 3.8R — which kills 28.7% of simulated accounts at the lowest
risk on the ladder. It fails on risk shape, not on edge. The next test is a stop.
Detail in `strategies/orderflow/notes.md`.

**H-011, 2026-09-02 — the one rejected result worth reading.** Fading the sweep
of the previous day's or week's high/low is the first fade hypothesis here whose
real data **beats its paired null at every cost level** (2x: 0.739 vs 0.658) and
beats its own direction control at every level, clearing the gate on 952 configs
against the null's 436 per seed. H-005 faded a rolling 10-100 bar extreme and lost
to its null 19,062 to 1,702 — so a schelling point everyone watches is measurably
a different object from an arbitrary level, which is a result about H-005 too.

It still fails: walk-forward PF **0.897 at 2x**, and 0 of 12 panels hold the gate
alone. A real edge that a 28bps round trip eats.

Two readings from it that travel: **open interest earns its place once a level has
been taken** (0.708 → 0.741) where the raw series did nothing directional in H-006
— "were contracts closed?" separates a stop run from a breakout. And **the
reversion is real enough to enter on but not reliable enough to exit on** —
targeting the level's midpoint is the worst exit in the grid (0.576) against
exiting on time (0.862), the identical pattern H-010 showed with the VWAP.

**Five strategies were deleted on 2026-09-02** — H-001 ORB, H-003 EMA x VWAP,
H-005 liquidity sweep fade, H-008 beta-residual reversion and H-010 VWAP band
rejection. Each is refuted at the level of its mechanism, not merely unprofitable:
ORB loses at zero cost, H-003's null produced more survivors than the real data,
H-005's null cleared the gate eleven times more often, H-008's z-response is flat,
and H-010 loses to its null while its defining lever is the most harmful in its
grid. **Their board records are kept**, so they stay in the denominator — the
scores, verdicts, notes and grids all still render. What went is the code and
about 250MB of raw sweep output. Their notes are preserved verbatim at the end of
`RESEARCH_LOG.md` and every one is in the known-dead list in `CLAUDE.md`, and all
of it is recoverable from git at `9bbc5cd`. Note the working tree is smaller but
a clone is not: the history still carries the deleted files.

Kept deliberately, despite low scores: **H-007** (2.9) beats its null BEFORE costs
and its identified cure — a 50-100 coin universe — became feasible the moment the
Binance archive was found. **H-011** (2.6) is the only fade here that beats its
null at every cost level, and it produced two findings still being carried. **H-006**
(1.3) is dead as a strategy but its kernel is what H-009 runs on.

## Continue here

1. ~~**Cross-sectional crypto ranking**~~ — **done 2026-09-01, rejected.** See
   `strategies/xsec/notes.md`. It failed differently from every other rejected
   hypothesis here: the ranking **beats its paired null before costs** (95% of real
   configs profitable vs 59% of null), but the edge is ~10% on profit factor and a
   round trip costs more than that. Cost-limited, not signal-limited. The only open
   route is a 50–100 coin universe — dispersion grows with the number of names
   ranked while cost per trade does not — and that needs a data download, which the
   line below forbids. **Kris's call.**
2. ~~**Keep `core/feed_collector.py` running.**~~ **Cron installed 2026-09-02** —
   it had never been on a schedule, so `data/feeds/` held ~2 days, not a year.
   The clock starts now, which pushes H-006 out from 2026-10. Verify with
   `crontab -l` and check `data/feeds/collector.log` is growing.
   **2026-09-02:** the 2026-09-01 entry was not on this box — `crontab -l` showed
   only the unrelated `trading-bots` job and the feeds had a 10h hole, backfilled
   from Binance's ~2-day window before it closed. The line below is what is now
   installed. Every path in it is absolute: cron runs from `$HOME`, so the relative
   form printed here before would have failed silently into the log.
   **2026-09-02: the reason for waiting was wrong.** Binance publishes these
   same feeds as daily files at `data.binance.vision/data/futures/um/daily/metrics/`,
   5-minute granularity, back to **2020-09-01**, free. Six years were available
   the whole time; H-006 does not have to wait for 2026-10 and is open now.
   `core/binance_metrics.py` downloads them. Keep the collector running anyway —
   it records the live present and the archive stops at yesterday.
   Original note: It records open interest and taker
   buy/sell delta, which Binance only serves for ~2 days — missed hours are gone
   forever. Around 2026-10 there is enough history for an order-flow hypothesis
   (H-006), which has the best mechanism of anything untested.
   ```
   */15 * * * * /home/kris/prop_lab/.venv/bin/python /home/kris/prop_lab/core/feed_collector.py --once >> /home/kris/prop_lab/data/feeds/collector.log 2>&1
   ```
3. **NautilusTrader cross-check of the VWAP kernel** — never done. See
   `core/nautilus_setup.py` and `strategies/orb/stage6_nautilus.py`.
4. ~~**Pick a prop firm.**~~ **Decided 2026-09-01: two-step on cTrader.**
   `CLAUDE.md` prefers cTrader outright (real REST/socket Open API vs MT5's
   GUI-only, Windows-only package), this box is Linux with no MT5 bridge, and
   cTrader carries both crypto and XAUUSD — the one choice that unblocks the whole
   book instead of half of it. `core/prop_rules.py` now has `TWO_STEP` and
   `riskladder.run_accounts_two_step`. **Still to do:** confirm the exact
   percentages, minimum trading days and consistency rules against the specific
   firm's live spec before any money moves — only the structure is modelled.

**Live-trading blocker**: two of H-002's legs are XAUUSD and this box has no MT5
bridge, so `live/paper_trade.py` runs gold signal-only off cached data. Half the
book cannot be paper-traded until that is solved.

## Rules that were learned the hard way — do not regress

- **Use the paired null** (`shuffle_market_paired`). The original null permuted
  volume independently of returns, destroying a +0.47 correlation and handing
  every participation filter a free win.
- **Select configurations on 2x-cost profit factor inside the fold.** Selecting on
  1x and checking 2x afterwards let four fragile legs into the book.
- **One shuffle seed is a sample of size one.** Read the null as a distribution.
- **Trades per day is not a plan.** A "top 10 configs × 6 legs" book is 60 parallel
  strategies. What sets time to pass is
  `days = maxDD_in_R / R_per_day × (target / cap)`.
- **Everything goes on the board as soon as it exists, pass or fail.** A rejected
  hypothesis that is invisible is not part of the denominator.
- **Answer Kris in a few short bullets.** He has asked twice; long replies slow the
  work down. Detail goes in the logs, never in chat.

`core/verify_board.py` recomputes every headline number straight from the raw
trade file, importing nothing from the pipeline. Use it to check anything here.
**Fixed 2026-09-01**: it had been left pinned to the stage-9 four-leg book (BTC
30m/4h + XAU 30m/5m) and to 1x-cost selection, so it verified a book the board no
longer shows. It now reads `stage10_trades.parquet`, the five legs above, and
gates on 2x cost — and reproduces PF 1.772 / 1.418 exactly.


## What happened 2026-09-01

Two hypotheses tested, both rejected, both logged. H-007 cross-sectional ranking
and H-008 beta-residual reversion — continuation and reversion on the same
relative structure, in opposite directions. H-007 found a real edge before costs
(95% of configs profitable vs the null's 59%) that a 14bps round trip beats.
H-008 found nothing: the null reverts more than the real data, and the z-response
is flat, meaning the size of a residual says nothing about what comes next.

**Together they close a family.** The relative structure of the crypto majors is
not tradeable at retail cost. Do not reopen without a much wider universe or a
much cheaper venue.

**They are also the 4th and 5th price-derived hypotheses to fail here, against
zero successes.** The repo's standing pattern holds: every leg that ever worked
came from a data feed, not a price pattern. H-006 order flow is still the best
untested mechanism in the project, and its recorder is finally running.

**Cheap test to run first on any future reversion idea:** the z-response. Bucket
profit factor at ZERO cost by entry threshold. If a 3σ deviation does not revert
harder than a 1.5σ one, there is no mechanism and nothing else is worth building.
It would have killed H-008 in ten minutes.

**Still not done:** the NautilusTrader cross-check of the VWAP kernel. Everything
this project believes rests on one implementation that no second engine has ever
verified.
