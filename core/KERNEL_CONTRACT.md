# The kernel contract

**Status: written 2026-09-07 as preparation for item 4 in `NEXT.md`. This
describes what the kernels ALREADY have in common and what a shared interface
must preserve. Nothing has been refactored yet — do not assume the code matches
this document until item 4 is done and this line is removed.**

Read `NEXT.md` before acting on this file. Items 1–3 come first.

---

## Why this document exists

Each hypothesis currently reinvents its engine. Two kernels exist
(`strategies/vwap/engine.py`, `strategies/ribbon/engine.py`) and they already
agree on more than they disagree on — by convention, written in comments, held
together by whoever wrote them remembering.

**A convention held together by memory is how three look-aheads survived in one
kernel for weeks.** Writing the contract down is the step before enforcing it in
code, and enforcing it is what makes a shared `Strategy` interface safe rather
than a large blind refactor.

---

## 1. What every kernel already agrees on

These are invariants. **A new kernel that breaks one of these is wrong, not
different.**

### 1.1 Output shape

Both kernels return an `(n_bars, 8)` float64 array, one row per trade, with
identical meanings in the first seven columns:

| index | name | meaning |
|---|---|---|
| 0 | `T_ENTRY_I` | bar index the trade entered on |
| 1 | `T_EXIT_I` | bar index the trade exited on |
| 2 | `T_DIR` | +1 long, −1 short |
| 3 | `T_ENTRY_PX` | fill price |
| 4 | `T_EXIT_PX` | exit price |
| 5 | `T_R` | profit in R multiples, **costs already subtracted** |
| 6 | `T_REASON` | why it closed |
| 7 | — | **kernel-specific.** vwap uses `T_SESS`, ribbon uses `T_MFE` |

Column 7 is the only divergence and it is deliberate. A shared interface should
keep columns 0–6 fixed and let column 7 be named per kernel.

**The buffer is sized by BAR count, never by session count.** Sizing by sessions
segfaulted on stop-and-reverse, which can flip many times in one session.

### 1.2 Timing — the rule that matters most

* **Signals are computed on CLOSED bars only.**
* **Entries fill at the NEXT bar's open.**
* **A filter may only read bar `i`, never `entry_i`.** Reading rvol, ATR or the
  close at `entry_i` asks the entry bar's own completed volume and range — none
  of which exist when the order is placed. This exact mistake inflated PF at 2x
  cost from 0.627 to 2.765 on the board's most-selected config and manufactured a
  "participation lifts it" pattern that was not real.
  * The one exception is a series built with an explicit `.shift(1)` at
    construction, such as `atr_rank`. Those are already lagged.

### 1.3 Intrabar pessimism

* **If a bar contains both the stop and the target, the STOP fills first.** The
  bar hides the intrabar path and this is the pessimistic read.
* Exit checks run in a fixed order — stop, target, indicator exit, flip — and
  **the stop wins every tie.**

### 1.4 Costs and risk

* Fees and slippage are charged **both sides**, in bps of notional.
* Risk is **fixed-fractional**, so an R multiple means the same thing on every
  trade.
* A `min_risk_bps` floor is mandatory. Without it a stop placed at a level the
  price may have crossed divides by ~0 and manufactures 25R "winners".
* **2x and 3x cost are computed by charging the extra cost against the same
  trades in R units, never by re-running the kernel.** Re-running would also move
  every stop, which conflates "costs doubled" with "a different strategy".
  * This is what makes `reprice()` exact: R is linear in cost, so from the stored
    1x and 2x series any cost level is recoverable with
    `r_s = (r_1x + C) − (s/assumed)·C` where `C = r_1x − r_2x`.

### 1.5 Data honesty

* **`live` array, uint8, 1 = the bar really traded.** Both kernels refuse to
  decide on a dead bar and refuse to fill on one. Dukascopy pads the closed FX
  weekend with zero-volume bars carrying the last price repeated — **21.5% of
  XAUUSD**. Crypto has none. Added 2026-09-07.
* **A volatility guard needs a tolerance in PRICE terms, not `<= 0.0`.** Any
  quantity of the form `sqrt(A/B − C²)` is a difference of near-equal accumulated
  sums; its cancellation floor is `price·sqrt(eps)`, about 3e-5 on gold. Use
  `SD_EPS_FRAC = 1e-6` of price.
* **Both fill assumptions must be runnable.** A resting limit at a level
  (optimistic, unverifiable — a wick touch is not a fill unless you were at the
  front of the queue) and a close beyond the level with entry at the next open
  (honest). **The gap between them is the finding.** A strategy in the previous
  repo backtested at PF 3.0 and traded live at 0.7 for exactly this reason.

---

## 2. What is genuinely per-kernel

Do not try to unify these. They are what makes a hypothesis a hypothesis.

* **The feature arrays.** vwap needs `vwap`, `vwstd`, `sess_start`; ribbon needs
  `agree`, `prev_agree`, `nflat`, `strength`. There is no common set.
* **Entry modes.** vwap has five, ribbon has four. They are not the same objects.
* **Exit modes.** vwap has session/VWAP/opposite-band/RR targets; ribbon has
  trailing variants with a `trail_start_r` distinction.
* **The session concept.** vwap is session-anchored with a rolling-window
  fallback; ribbon has no session at all.

---

## 3. What a shared interface should look like

Sketch only. Not built. The point is that the *contract* above is the valuable
part; the class shape is negotiable.

```python
class Strategy(Protocol):
    name: str

    def features(self, df: DataFrame) -> Features:
        """Everything the kernel needs that does not depend on the config.
        MUST NOT look forward. Enforced by the truncation test."""

    def grid(self) -> list[Config]:
        """Every configuration this hypothesis wants tested."""

    def run(self, df, features, cfg, costs) -> Trades:
        """(n, 8) array. Columns 0-6 as in section 1.1."""
```

Everything downstream — `sweep`, walk-forward, null benchmark, `board.py`,
`riskladder`, `scorecard` — already works off the `(n, 8)` trade array and does
not care which kernel produced it. **That is why this refactor is worth doing and
also why it is not urgent: the integration point already exists.**

---

## 4. The tests that must exist before item 4 starts

Item 4 moves code. Moving code without these is how a fix becomes a regression.
Each is described in `NEXT.md` item 3.

1. **Truncation / no-look-ahead** — cut the last N bars, rerun, earlier trades
   must be byte-identical. *This single test would have caught the three
   look-aheads that killed every crypto result.*
2. **Degenerate inputs** — zero volume, flat OHLC, zero sigma, one bar, constant
   price. Property-based via `hypothesis`, because every bug this project has
   found was an input nobody thought to write by hand.
3. **Cost monotonicity** — PF must fall as cost rises, and the 0x/1x/2x linear
   identity must hold.
4. **Golden output** — pin a known config's trade list per kernel. Any edit that
   moves it must be explained in the commit message, not discovered weeks later.
5. **Second-engine agreement** — the NautilusTrader port, run automatically
   rather than once by hand. **This is the check that has actually found bugs.**

---

## 5. Kernel inventory

| kernel | file | tests today | second-engine checked |
|---|---|---|---|
| vwap | `strategies/vwap/engine.py` | **none** | **yes** — 26/26 configs exact, 2026-09-07 |
| ribbon | `strategies/ribbon/engine.py` | indicators only (`test_parity.py`) | **no** |

`strategies/orderflow/orderflow.py` is **not** a strategy kernel — it is the
shared feed loader (metrics join, point-in-time features, block-shuffle null)
imported by more than twenty files across a dozen hypotheses. Do not fold it into
this contract and do not delete it because H-006 died.
