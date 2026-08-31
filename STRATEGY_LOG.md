# Strategy Log

One row per variation tested. Pass or fail — the failures are the denominator.

| Date | Idea | Variation | Asset/TF | Period | PF | Win% | Trades/day | Avg hold | Avg R | MaxDD | Sharpe | Days-to-resolve | Verdict | Notes |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 2026-08-31 | ORB (H-001) | full grid: 8 anchors x 15m-4h range x 2-24h hold x touch/close entry x 4 stop modes x 5 targets x follow/fade | BTCUSDT 15m | IS 2018-01→2024-01 | best 1.045 | 0.279 | 1.00 | 11.4h | +0.038 | -134% | 0.28 | 18.0 | **FAIL** | 0/8160 configs reach PF 1.20 at 1x cost; only 6 exceed 1.00 |
| 2026-08-31 | ORB (H-001) | same grid, zero fees (diagnostic) | BTCUSDT 15m | IS 2018-01→2024-01 | best 1.541 | 0.606 | 0.92 | 0.19h | +0.213 | -10% | 3.98 | 39.8 | **FAIL** | median PF 0.960 with NO costs → no edge to protect, not a fee problem |
| 2026-08-31 | ORB (H-001) | same grid, out of sample | BTCUSDT 15m | OOS 2024-01→2026-08 | best 1.011 | — | 1.00 | — | — | — | — | — | **FAIL** | 0/8160 reach 1.20; every top-IS config falls below 1.00 |
| 2026-08-31 | ORB (H-001) | wider stop to outrun cost (1-8x ATR) | BTCUSDT 15m | IS | 0.61-0.78 | — | 0.94 | — | — | — | — | — | **FAIL** | gross edge decays as fast as cost burden falls; maker tops out 0.93 |
| 2026-08-31 | ORB (H-001) | literature variants: rel-volume filter, first-candle entry, 5-20% daily-ATR stop, 3R/5R/10R | BTCUSDT 15m | IS+OOS | IS 1.907 → OOS 0.671 | 0.18 | 0.11 | — | — | — | — | ~140 | **FAIL** | 75 configs clear 1.20 IS, 4 repeat OOS (5.3%); median OOS of that group 0.945; survivors trade 1x/fortnight |
| 2026-08-31 | ORB (H-001) | walk-forward, 12m train / 3m test, 31 quarters | BTCUSDT 15m | 2019-01→2026-08 | 0.781 | 0.222 | ~1.0 | — | -0.216 | — | — | — | **FAIL** | stitched 2,746 trades, -594R; 5/31 quarters above breakeven; train 1.215 → test 0.816 |
| 2026-08-31 | ORB (H-001) | prop challenge sim, best config, 4%/8%/8% | BTCUSDT 15m | 2018→2026 | 1.019 | — | ~1.0 | — | — | — | — | — | **FAIL** | 35.5% pass, 64.1% breach max loss |
