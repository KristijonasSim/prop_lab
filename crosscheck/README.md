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

---

# Trading it by hand — the indicator

`orb_v2_ny_rvol_indicator.pine` is the **indicator** version: it plots what the
rules see and marks where they *would* fire, without taking anything. Window and
RVOL logic are identical to the strategy version, so any difference you see on
the chart is your discretion, not a different calculation.

It covers **London and New York**, both on by default. proplab's `orb_v2` is
New-York-only because it mirrors the supplied Pine reference; `orb_v1` already
trades both. Whether London is worth adding to v2 is an open question, and this
is the cheapest way to look at it — London signals are marked `LDN`, New York
`NY`.

Levels are drawn with `plot()`, not line objects: line objects were rendering
thousands of dollars away from the candles, while `plot()` is anchored to the
price scale and cannot drift.

It draws:
- the 09:30-10:00 opening range, extended across the trade window
- shading for the opening-range / trade / flatten windows
- triangles where the mechanical rules would enter, an X where they would flatten
- a state table: range, range width, live RVOL, whether the filter passes,
  today's signal, and how many weeks of RVOL history exist

Signals are marked on the bar whose **close** triggers them; the mechanical fill
is the **next bar's open**.

## The actual experiment

You are profitable on this setup and the mechanical version is not. That gap is
the useful thing here — it is somewhere in **which setups you skip**, **when you
enter**, or **when you get out**.

1. Add the indicator, use bar replay, and trade the setups as you normally would.
2. Log every trade in `manual_trades_template.csv` — `entry_time, exit_time,
   side` are the minimum; prices and a note on *why* are more valuable.
3. Send it back. `proplab/manual_diff.py` splits the result three ways:

   - **SKIPPED** — signals you declined. If those lose on average, your filter
     *is* the edge, and identifying what you are filtering is the prize.
   - **EXTRA** — trades you took with no mechanical signal. The rules are
     blind to a setup you can see.
   - **MATCHED** — same setup, different execution. Entry and exit timing are
     compared trade by trade, in minutes.

Whatever it finds becomes a new variation with a mechanical rule attached, which
then goes through the normal in-sample / one-look-out-of-sample pipeline.

## One caveat worth stating plainly

Trades marked after the fact are chosen with hindsight, and hindsight makes
anyone profitable. This is only worth trusting on trades recorded **forward**,
with bar replay and no peeking ahead. That is not a reason to skip the exercise
— it is the reason to do it properly, because a discretionary filter that
survives an honest forward log is exactly the kind of edge worth mechanising.

---

# Editing the Pine files

Pine cannot be compiled locally, so `crosscheck/pine_lint.py` checks the
mistakes that kept reaching the editor:

```bash
python crosscheck/pine_lint.py
```

It rejects three things, each of which produced a real compile error here:

1. **A function defined inside an `if` block** → `Syntax error at input "=>"`.
   Pine requires function declarations at global scope.
2. **A statement wrapped onto the next line**, especially a ternary broken
   before its `:` → `end of line without line continuation`. Every statement in
   these files is on one line, however long.
3. **Unbalanced brackets on a line** — the same failure from the other side.

Rule 2 is stricter than Pine strictly requires, but one statement per line costs
nothing and removes the whole class of error. Run the linter before pasting
anything into TradingView.
