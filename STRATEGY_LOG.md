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
| 2026-08-31 | ORB (H-001) | full grid on XAUUSD, 3y | XAUUSD 15m | 2023-09→2026-08 | 1.262 | 0.201 | 0.71 | 7.7h | +0.251 | -64% | 1.08 | 11.3 | **FAIL** | 2/8160 clear 1.20 at 1x; 0 survive the IS/OOS split; 0 at 2x cost |
| 2026-08-31 | ORB (H-001) | full grid on EURUSD, 3y | EURUSD 15m | 2023-09→2026-08 | 1.081 | 0.178 | 0.71 | 5.7h | +0.087 | -65% | 0.40 | 14.0 | **FAIL** | 0/8160 clear 1.20 at any cost level |
| 2026-08-31 | ORB (H-001) | full grid on GBPUSD, 3y | GBPUSD 15m | 2023-09→2026-08 | 1.439 | 0.549 | 0.40 | 1.0h | +0.058 | -9% | 1.63 | 338.7 | **FAIL** | 11/8160 clear 1.20; all one cluster at the 20:00 anchor, the WORST anchor by median; 339 days to resolve |
| 2026-08-31 | ORB (H-001) | full grid on BTCUSDT, same 3y window | BTCUSDT 15m | 2023-09→2026-08 | 0.993 | 0.271 | 1.00 | 11.2h | -0.006 | -75% | -0.05 | 18.9 | **FAIL** | 0/8160 even reach breakeven at 1x |
| 2026-08-31 | ORB (H-001) | session-anchor test, median PF by anchor | all 4 assets | 2023-09→2026-08 | 0.789 best | — | — | — | — | — | — | — | **FAIL** | NY open is the best anchor on all 3 FX/metal, NY close the worst; best median still 0.789 |
| 2026-08-31 | ORB (H-001) | 20 session anchors incl. Tokyo/Sydney/half-hours | 4 assets 15m | 2023-09→2026-08 | 0.791 best median | — | — | — | — | — | — | — | **FAIL** | NY cash open 13:30 UTC best on all 3 FX/metal; Asia worst region; NY close worst anchor 0.577 |
| 2026-08-31 | ORB (H-001) | 29 filters, paired lift vs same configs unfiltered | 4 assets 15m | 2023-09→2026-08 | 0.768 best median | — | 0.57 | — | — | — | — | — | **FAIL** | base 0.679; best lift breakout-rvol>2.0 (+0.052); breakeven stops and retest entries all NEGATIVE |
| 2026-08-31 | ORB (H-001) | stacked filters, IS/OOS split | 4 assets 15m | fit 2y / test 1y | BTC 2.18 OOS | — | 0.52 | — | — | — | — | — | **MAYBE** | BTC 103/179 survive OOS (10.6x base rate); best config +ve in 8/9 years, longs 1.43 shorts 1.97 |
| 2026-08-31 | ORB (H-001) | **walk-forward, filtered family, chosen blind** | BTCUSDT 15m | 2019-01→2026-08 | **1.165** | 0.419 | **0.16** | — | +0.090 | — | — | ~1.5 yrs | **FAIL (phase)** | 470 trades, +42.4R, 13/31 quarters >1. Up from 0.781 unfiltered — real lift, still under the 1.20 gate and far too slow |
