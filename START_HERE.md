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
re-download anything.

## Look at this first

**The board**: <https://claude.ai/code/artifact/f9ac29b6-5251-4510-81d9-ef3d5b7dd3d3>
Rebuild locally with `.venv/bin/python core/build_scoreboard.py`.

| ID | hypothesis | score | verdict |
|---|---|---|---|
| H-002 | VWAP | **9.2** | only survivor. BTC 4h + ETH 1h + ETH 30m + SOL 4h + gold 5m |
| H-003 | EMA × VWAP cross | 4.0 | rejected — loses to its own null |
| H-005 | Liquidity sweep fade | 4.0 | rejected — null beats it 19,062 to 1,702 |
| H-001 | ORB | 2.4 | rejected |
| H-004 | Funding fade | — | rejected, code deleted. Finding kept in `RESEARCH_LOG.md` |

H-002 as it stands: PF 1.772, **1.418 at 2x cost**, 93% pass rate, 0% of accounts
killed, **24 expected days** to a funded account, 5 positions at 0.33 trades/day
each. ETH is the strongest single market, ahead of BTC.

## Continue here

1. **Cross-sectional crypto ranking** — Kris asked for it, never started. Rank many
   coins and trade the spread between top and bottom. Note the research argues
   against it (time-series momentum beats cross-sectional in crypto; coins are too
   correlated, ~55% drawdowns). Test it anyway, expect it to fail.
2. **Keep `core/feed_collector.py` running.** It records open interest and taker
   buy/sell delta, which Binance only serves for ~2 days — missed hours are gone
   forever. Around 2026-10 there is enough history for an order-flow hypothesis
   (H-006), which has the best mechanism of anything untested.
   ```
   */15 * * * * .venv/bin/python core/feed_collector.py --once >> data/feeds/collector.log 2>&1
   ```
3. **NautilusTrader cross-check of the VWAP kernel** — never done. See
   `core/nautilus_setup.py` and `strategies/orb/stage6_nautilus.py`.
4. **Pick a prop firm.** No-time-limit evaluations are now standard, so the ~14-day
   constraint in `CLAUDE.md` is self-imposed, not a firm rule. Most firms are
   two-step (8% then 5%) while `core/prop_rules.py` models one step at 8%.

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
