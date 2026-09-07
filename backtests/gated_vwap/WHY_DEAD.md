# H-009 was taken off the board on 2026-09-07

`board.json` is renamed, not deleted, for the reason given in
`backtests/xpos/WHY_DEAD.md`.

**Why.** H-009 is H-002's VWAP entries gated by the crowd-positioning feed. Both
halves are gone:

- the entries came from the pre-fix kernel, and on the corrected kernel every
  crypto VWAP leg fails (BTCUSDT 11 walk-forward cells clearing PF 1.20 at 2x
  → **0**);
- the gate is Binance's long/short account ratio, a **crypto perpetual** feed.
  There is no equivalent for XAUUSD, so the gate cannot follow the one market
  that survived.

The score of 8.9 was the top of the board and it was measured on a book that no
longer exists. H-006's own notes reach the same place from the other side: the
signal's value was "as H-009", and H-009 was crypto.

Restore only with a post-fix walk-forward and a gate that applies to the market
being traded.
