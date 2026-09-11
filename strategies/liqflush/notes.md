# H-031 — liquidation-pressure fade

Kris picked it 2026-09-11 ("ok start") from `NEXT_HYPOTHESIS_2026-09-10.md`.

## Mechanism, before any result

A liquidated position is closed by the exchange engine at market, whatever the
price. That seller is forced, not informed. Forced flow overshoots, and whoever
supplies liquidity into it is paid when price comes back. Binance's per-event
liquidation dump is gone, so a flush is rebuilt from what the feed does keep:
**open interest collapsing while price falls** over the same 30 minutes. The
same fall with open interest stable is informed selling, and it is the control.

## Stage 1 is the DRAWDOWN study. Written BEFORE it was run.

H-006 had a real signal and died on risk shape: no stop, 24h hold, 63.5R
drawdown, 548 days. H-031 has the same shape. So the first question is not
"does it make money" but "can its drawdown be carried inside a 6% cap".

**Fixed from the screen, not searched:** bottom 2% of 30m OI change (trailing
30-day quantile, shifted one bar, so the threshold is causal), price down over
the same 30m, long at the next 5m open, 24h hold, one position per coin at a
time. 10 coins. Last 3 years, common end 2026-08-31.

**The only thing varied is the stop** — none, 1, 1.5, 2, 3, 4, 6 x the trailing
1h sigma, and one structural stop under the flush's own low. Eight arms, all
reported. A stop the bar gaps through fills at that bar's open.

**Sizing:** flat risk per trade and the adopted budget-linear overlay
(`core/chosen.py["sizing"]`), Thunderbolt rules (6% target, 3% daily, 6% max).

## Kill criterion — fixed 2026-09-11, before the first run

H-031 **dies and stays dead** unless at least one stop arm clears **all three**,
at **2x cost** (28bps round trip), on the 3-year window:

1. `|maxDD_R| / R_per_day` **<= 50 days** — the repo's pace metric, the one
   H-006 scored 548 on;
2. budget-linear Thunderbolt **expected days <= 50** at some risk rung, with
   PF@2x >= 1.2;
3. its budget-linear expected days, at the same risk rung, **beat the median of
   the block-shuffled null** for the same stop arm (the flush flag cut into
   day blocks and reordered, 20 seeds; a seed that funds nothing counts as
   infinite).

Passing is NOT a result. The stop arm is chosen in-sample from eight, so a
survivor goes to a blind walk-forward with a paired null, the 1x/2x/3x cost
ladder and a noise band — stage 2 — and to nothing else.

---

## RESULT, 2026-09-11 — DEAD. Fails criterion 1 on all eight arms.

`stage1_drawdown.py`, `backtests/liqflush/stage1.json` (3 years) and
`stage1_full.json` (2021-12 on, cross-check). 24 seconds per run.

| stop | trades | trades/day | PF@0x | PF@1x | **PF@2x** | win% 2x | hold h | maxDD R 2x | R/day 2x |
|---|---|---|---|---|---|---|---|---|---|
| none | 5,097 | 4.65 | 1.155 | **1.033** | 0.924 | 46.7 | 24.0 | −607 | −0.25 |
| 1 sig | 10,745 | 9.80 | 1.159 | 0.914 | 0.743 | 17.6 | 7.0 | −3,325 | −2.96 |
| 1.5 sig | 9,080 | 8.28 | 1.134 | 0.947 | 0.802 | 24.2 | 9.6 | −1,841 | −1.58 |
| 2 sig | 8,133 | 7.42 | 1.111 | 0.954 | 0.826 | 29.7 | 11.9 | −1,339 | −1.07 |
| 3 sig | 7,071 | 6.45 | 1.108 | 0.976 | 0.862 | 37.5 | 15.3 | −785 | −0.57 |
| 4 sig | 6,426 | 5.86 | 1.106 | 0.985 | 0.878 | 41.9 | 17.8 | −560 | −0.37 |
| 6 sig | 5,774 | 5.27 | 1.105 | 0.990 | 0.889 | 45.6 | 20.8 | −345 | −0.21 |
| wick | 12,102 | 11.04 | 1.244 | 0.879 | 0.667 | 14.6 | 5.9 | −6,149 | −5.38 |

R/day is negative at 2x on every arm, so `maxDD_R / R_per_day` has no finite
value anywhere. Criterion 1 fails eight times out of eight; 2 and 3 are moot.

**Why it dies — the edge is real and small, and most of the screen was drift.**
Gross per trade, no stop, one position per coin, causal threshold:

| | 3 years | since 2021-12 |
|---|---|---|
| flush | +26.7 bps | +14.6 |
| control (same fall, OI stable) | +20.5 | +13.5 |
| null (flush flag block-shuffled, 20 seeds, median) | +11.8 | +3.4 |

* The feed is worth **~+15bps over a random long** and **~+6bps over its own
  control** on three years — and **+1bp** over the control on the longer run.
  The screen's "control drifts −6bps" does not survive a same-size-fall control
  on this window: at the bar level flush and control are +38.6 and +40.1 at 24h.
* Against a 28bps round trip that is nothing. Same verdict shape as H-011 and
  H-024: real, and too small to pay the spread.
* **Every stop makes it worse, monotonically** — PF@2x climbs 0.743 → 0.889 as
  the stop widens from 1 to 6 sigma and the no-stop arm is best. Post-flush
  volatility stops the trade out and the re-entry doubles the trade count and
  the costs. The same thing H-006's fold selector said (no stop in 37 of 52).
* Only 5 of 10 coins net positive at 2x even with no stop (BNB +30.7, XRP
  +24.9, ADA +18.1, DOGE +13.4, SOL +4.2bps) and only BNB clears PF 1.2 (1.203);
  BTC −18.9, DOT −28.8, LINK −23.8. Since 2021-12 BTC is −32.7.
* **Cascades fire the whole book at once**: 10 of 10 coins open together,
  worst day −46R with no stop. Any sizing has to treat the ten as one trade.

**READ THIS BEFORE QUOTING THE PROP SIM.** Every arm shows 2–5 "expected days"
at 2% risk. That is the lottery effect `riskladder.pick` warns about: a
**losing** book at 10 concurrent positions passes 26–43% of accounts on
variance and blows the other 57–74%. It is not a pace.

**What this closes.** `NEXT_HYPOTHESIS_2026-09-10.md` ranked H-006-R third on
the argument that H-031 would answer the stop question for both. It did: a stop
does not repair a slow-drift feed signal, it harms it. H-006-R is closed on the
same evidence.
