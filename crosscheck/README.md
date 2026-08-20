# Cross-check: proplab vs TradingView

An engine that only ever agrees with itself proves nothing. This compares
`orb_v2_ny_rvol` against an independent Pine implementation of the same rules.

## What to do

1. Open TradingView on **BINANCE:BTCUSDT.P**, timeframe **15m**.
2. Paste `orb_v2_ny_rvol.pine` into the Pine editor and add it to the chart.
3. Leave every input at its default. The strategy settings (capital, size,
   commission, slippage, fill timing) are set inside the script — **do not
   change them in the Properties tab**, or the comparison is meaningless.
4. Open **Strategy Tester → List of Trades**, set the date range to
   **2026-06-01 → 2026-08-01**, and compare against
   `orb_v2_proplab_trades_JUN_JUL.csv`.

Chart timezone should be **New York** so the timestamps line up with the
`entry_local` / `exit_local` columns.

## What proplab produced for that window

| | |
|---|---|
| trades | **22** |
| wins / losses | 5 / 17 (**22.7%**) |
| gross profit / loss | 679.35 / 1459.71 |
| profit factor | **0.465** |
| net P&L | **-780.36** |
| fees | 196.76 |

Warm-up matters: data is loaded from **2026-03-01** so the RVOL filter has three
completed weeks behind it before the comparison window opens. TradingView loads
history automatically, so it is warm too — but if you set the chart's *visible*
range to June you are still fine, whereas restricting proplab's data to June
would silently suppress the first three weeks of signals.

## What must match exactly

**Trade count, direction, and entry/exit bar.** These come purely from the rules
and the bar data. If they differ, one implementation is wrong, and that is the
whole point of doing this.

## What will differ slightly, and why

- **Position size.** Pine computes percent-of-equity at signal time; proplab
  computes it at fill time (the next bar's open). Quantities differ by the
  price move across one bar, and the difference compounds.
- **P&L per trade** follows from the above.
- **Data feed.** TradingView's BTCUSDT.P feed is normally identical to the
  Binance klines proplab downloads, but it is not guaranteed to be.

So: judge the comparison on **timing and direction first**. Treat P&L agreement
within a few percent as success, and exact P&L equality as unlikely.

## Three places the platforms disagree silently — all handled in the script

1. **Session windows.** Pine's `time(period, "1550-1555", tz)` matches on the
   bar's *open* only, so on 15m it never matches the 15:45 bar. proplab treats a
   bar as inside a window if it *overlaps*, so the 15:45 bar does flatten. The
   Pine script reimplements the overlap test by hand — without it, the flatten
   would fire an hour late and every exit would differ.
2. **Relative volume.** `ta.relativeVolume()` is a different calculation from
   proplab's. The script reimplements proplab's definition: cumulative volume
   since the start of the UTC week, against the same bar-offset in the last
   three completed weeks.
3. **Funding.** proplab charges perp funding at 00/08/16 UTC; Pine cannot model
   it. The parity run disables funding, which is why these numbers differ from
   the ones in the dashboard.

## Reproducing the proplab side

```bash
python -c "
from proplab import runner
from proplab.crosscheck import parity_config, export_trades, summary
from proplab.strategy import registry
res = runner.backtest(registry.get('orb_v2_ny_rvol'), symbol='BTCUSDT',
                      timeframe='15m', start='2026-03-01', end='2026-08-01',
                      run_checks=False, params={'notional_pct': 0.1},
                      config=parity_config())
print(summary(res)); export_trades(res, 'crosscheck/orb_v2_proplab_trades.csv')"
```

## If they disagree

Send me the TradingView trade list. The first divergent trade tells us where to
look, and a difference of one bar in an entry is a different bug from a missing
trade entirely.
