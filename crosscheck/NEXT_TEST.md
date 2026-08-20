# Next test — hand-trade v4 rules, then compare

Status: **waiting on Kris's manual trade log.** Nothing else is blocked.

## Settings (do not change these — the comparison breaks otherwise)

| setting | value |
|---|---|
| symbol | `BYBIT:BTCUSDT.P` (perp, not spot) |
| timeframe | 15m |
| window | **2026-06-01 → 2026-06-14** |
| initial capital | 10,000 USDT |
| commission | **Percent, 0.02** (maker/limit) |
| orders | **limit only** |
| indicator | `crosscheck/orb_v2_ny_rvol_indicator.pine` |

Perp, not spot: spot taker is 0.1% and would eat the edge. proplab's data is
Binance USDT-M perp, so perp also matches the engine more closely — the
remaining gap is just the Bybit-vs-Binance feed, about $25 on BTC.

## The rules to trade

Both London and New York sessions.

| | London | New York |
|---|---|---|
| range | 08:00–08:30 London | 09:30–10:00 NY |
| trade window | 08:30–10:30 London | 10:00–12:00 NY |

1. Mark the high/low of the range (the indicator draws it once complete).
2. **Skip the session if the first candle of the range is small** compared to
   recent candles. Big/high-volume opening candle = tradeable; small = no trade.
3. Enter on the first close outside the range, in that direction.
4. **Stop** on the far side of the range.
5. **Exit within ~3 hours** — do not hold to the session close.
6. **No weekends.**
7. One trade per session per day.

## What to send back

Export the replay trade list to CSV, same format as
`crosscheck/manual_kris_20260820.csv`. The important columns are entry time,
exit time, side, price, and P&L.

**Add a note per trade wherever possible** — especially *why a setup was
skipped*. The skips are the most valuable data: last time they were what
separated +1,693 from -1,210. A skipped-setup log is worth more than another
winning trade.

## Order of operations, and why it matters

Kris sends his log **first**, then proplab runs the same window. Not the other
way round. If the engine result is known first, the manual rules can drift
toward it without anyone intending it, and the comparison stops meaning
anything.

## What happens after

`proplab/manual_diff.py` splits the log three ways against the mechanical run:

- **SKIPPED** — signals declined by hand. If those lose on average, the filter
  is the edge.
- **EXTRA** — trades taken with no mechanical signal. The rules are blind to
  something.
- **MATCHED** — same setup, different execution. Entry and exit timing compared
  in minutes.

Whatever that finds becomes v5, then goes through in-sample tuning and a single
out-of-sample look.

## Where things stand

- **v4** (`proplab/strategy/library/orb_v4_kris_rules.py`) already encodes the
  three rules above. In-sample Jan–Jul 2026: 129 trades, 50.4% win, PF 1.134,
  avg 0.049R, +3.1%, 2.5h average hold. Positive but thin.
- Its estimated time to reach an 8% target is **374 trading days**, far too slow
  for an evaluation. So v4 is not a candidate yet — the point of this test is to
  find what the hand-trading does that v4 still does not.
- Previous comparison (2026-08-13..08-20, same sizing): **hand +1,693 vs
  mechanical −1,210**. 74% of that came from one lucky trade; excluding it,
  +433 vs −1,210, so the gap is not only luck. Nine trades is far too few to
  conclude anything, which is why this second window exists.

## For whoever runs this next

Read `README.md` first, particularly the one-look rule on out-of-sample data
and the acceptance bar. Do not spend `orb_v4_kris_rules`'s out-of-sample look
on this comparison — this window is for finding rules, not for judging them.
