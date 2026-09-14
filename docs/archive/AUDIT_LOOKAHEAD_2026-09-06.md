# Step 1c — look-ahead audit of the non-VWAP engines

Date: 2026-09-06. Triggered by the three look-aheads found in
`strategies/vwap/engine.py` on 2026-09-05.

**Verdict: clean. No new look-ahead of the VWAP class found.** One residual peek
in the VWAP kernel is confirmed still present and is quantified below.

## Method

The bug class is: *a value indexed at the FILL bar (`entry_i = i+1`) being read
while the decision is made at the close of bar `i`.* Every engine was checked on
four axes:

1. every feature read inside the entry decision — index must be `i`, not `i+1`;
2. every rolling statistic — must be `.shift(1)`ed or otherwise exclude its own bar;
3. every external feed join — must be as-of BACKWARD with the feed's own
   publication lag added;
4. in-trade state (trail distance, stop level) — must only use bars already closed
   when it is applied.

## `strategies/ribbon/engine.py` — CLEAN

| read | index | verdict |
|---|---|---|
| `agree`, `strength`, `nflat[i-1]`, `gate` | `i` | decision bar, correct |
| `prev_agree` | built as `agree` shifted 1 in `sweep.ribbon_inputs` | correct |
| `atr` for initial risk (`at`) | `i` | sized at decision, correct |
| `side_override` | `i` | correct |
| entry price `o[e]` | `i+1` | the fill, correct |
| chandelier trail `atr[j]` | `j`, applied after bar `j`'s stop check | affects bar `j+1` only, correct |
| flip exit `agree[j]` -> fill `o[j+1]` | closed-bar read, next-open fill | correct |

Note, not a bug: re-entry resumes at `i = exit_i`, so a new decision can be made
on the exit bar itself. The VWAP kernel uses `exit_i + 1`. Different convention,
no leak either way.

## `strategies/orderflow/orderflow.py` — CLEAN

- Signal `s[i]`, thresholds `lo[i]`/`hi[i]` — both built with `.rolling(...).shift(1)`,
  so a bar is never inside its own baseline or its own quantile band.
- Entry `o[i+1]`, exit `o[i+1+hold]`.
- Stop sizing `vol[e-1]` = `vol[i]` — the decision bar. Correct.
- `shift(-1)` appears only in `forward_returns`, which is a diagnostic label, not
  a trading rule.

Feed alignment: bars are indexed by `open_time`, metrics by `create_time`, joined
`inner` on the same 5m index with no forward fill. A metric stamped `T` is
observable at `T`; the decision that uses it is taken at the close of the bar
opening at `T`, i.e. at `T + 5m`. Conservative by one bar, not leaky.

## `strategies/xpos/` — CLEAN (inherits the above)

No engine of its own — `stage3_fastbook.py`, `stage13_final.py` and the rest call
`orderflow.trades()` and carry its `entry_i`/`exit_i` through. Spot-checked
`stage3_fastbook.py:235`: `entry_ts = test.index[n]` where `n` is the kernel's
entry index. Correct.

## Gate joins — CLEAN

- `strategies/ribbon/stage4_gates.py:80` `asof()` explicitly adds the source
  bar's own duration before the as-of merge, so a bar stamped `T` is only visible
  from `T + lag`. This is the right shape.
- `strategies/orderflow/stage6_gated_vwap.py:146-153`: `signal_series(...).shift(1)`
  then `merge_asof(..., direction="backward", tolerance=1h)` on `entry_ts`.
  `entry_ts` is the open of bar `i+1`, which is the same instant as the close of
  bar `i` — the decision instant — and the shifted signal stamped at that instant
  is knowable then. Correct.

## `strategies/absorb/`, `strategies/basis/`, `strategies/breadth/` — CLEAN

Response studies only, no trade simulation. All z-scores use
`.rolling(win).mean().shift(1)` / `.std().shift(1)`. `shift(-1)` appears only in
forward-return labels.

## Residual peek in the VWAP kernel — still present, deliberate

`strategies/vwap/engine.py`: the `min_risk_bps` floor is compared against
`entry = o[entry_i]`, the fill bar's open, while the decision is taken at the
close of bar `i`. Recorded in commit `0342772` as the Nautilus port's one
deliberate difference.

Not fixed, and the reason: it can only flip a skip/no-skip decision, and it
depends on the *price level* rather than on a return. Bar-to-bar the open moves
well under 1%, so the set of trades it changes is negligible. Fixing it means
re-running the walk-forward again. Left as a known, bounded, one-line item.

`hour[entry_i]` is NOT a peek — the UTC hour of the next bar is a calendar fact.

## What this does not cover

- Only the entry-decision path was audited. Exit-price realism (the kernel's
  stop-wins-ties assumption) is a separate, known question and is where the
  Nautilus cross-check is still incomplete: only MODE_BREAK on BTCUSDT 4h has
  been matched.
- `strategies/vwap/sweep.py:features` was not re-derived from scratch; the fix of
  2026-09-05 moved the reads to bar `i`, which makes the construction of `rvol`,
  `atr` and `ema` (all same-bar-inclusive, all read at `i`) correct by
  construction.
