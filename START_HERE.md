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

| ID | hypothesis | score | verdict |
|---|---|---|---|
| H-002 | VWAP | **9.2** | only survivor. BTC 4h + ETH 1h + ETH 30m + SOL 4h + gold 5m |
| H-003 | EMA × VWAP cross | 4.0 | rejected — loses to its own null |
| H-007 | Cross-sectional crypto ranking | 2.9 | rejected — real edge before costs, too small to pay the spread |
| H-008 | Beta-residual reversion | 2.1 | rejected — residual does not revert; null beats real on every cut |
| H-005 | Liquidity sweep fade | 4.0 | rejected — null beats it 19,062 to 1,702 |
| H-001 | ORB | 2.4 | rejected |
| H-004 | Funding fade | — | rejected, code deleted. Finding kept in `RESEARCH_LOG.md` |

H-002 as it stands: PF 1.772, **1.418 at 2x cost**, 5 positions at 0.33 trades/day
each. ETH is the strongest single market, ahead of BTC.

**Corrected 2026-09-01 — the "24 days" was a one-step number.** Firms are two-step
(8% then 5%), now modelled in `core/riskladder.run_accounts_two_step`. On the real
structure the same book is **88.3% pass, 0% killed, ~50 expected days** at 2.125%
risk. The second step is not half the work of the first: it is another chance to
breach, and the drawdown gets paid twice.

## Continue here

1. ~~**Cross-sectional crypto ranking**~~ — **done 2026-09-01, rejected.** See
   `strategies/xsec/notes.md`. It failed differently from every other rejected
   hypothesis here: the ranking **beats its paired null before costs** (95% of real
   configs profitable vs 59% of null), but the edge is ~10% on profit factor and a
   round trip costs more than that. Cost-limited, not signal-limited. The only open
   route is a 50–100 coin universe — dispersion grows with the number of names
   ranked while cost per trade does not — and that needs a data download, which the
   line below forbids. **Kris's call.**
2. ~~**Keep `core/feed_collector.py` running.**~~ **Cron installed 2026-09-01** —
   it had never been on a schedule, so `data/feeds/` held ~2 days, not a year.
   The clock starts now, which pushes H-006 out from 2026-10. Verify with
   `crontab -l` and check `data/feeds/collector.log` is growing.
   Original note: It records open interest and taker
   buy/sell delta, which Binance only serves for ~2 days — missed hours are gone
   forever. Around 2026-10 there is enough history for an order-flow hypothesis
   (H-006), which has the best mechanism of anything untested.
   ```
   */15 * * * * .venv/bin/python core/feed_collector.py --once >> data/feeds/collector.log 2>&1
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
