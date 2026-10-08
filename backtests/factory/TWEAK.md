# Factory tweak — 2026-10-08

`factory/tweak.py`. Design is in its docstring, fixed before the run.

| idea | cell | original 3y | tweak picked | tweak 3y | newer-half lift | luck p90 | kept |
|---|---|---|---|---|---|---|---|
| EMA50/200 trend | XAU 4h | PF 1.48, 41.8%, 26.3d (24–43) | stop1 tgt6 hold240 | PF 1.62, 53.3%, 11.3d (10–15) | +0.130 | +0.302 | no — random entries gain more |
| Hemant sweep | XAU 1h | PF 1.37, 38.6%, 28.5d | stop1.5 tgt6 hold96 | PF 1.48, 31.1%, 28.9d | +0.040 | +0.108 | no |
| **Adaptive ATR dual-trend** | **XAU 4h** | **PF 1.45, 49.2%, 28.4d (22–37)** | **stop1 tgt6 hold24** | **PF 1.77, 50.7%, 17.8d (15–23)** | **+0.238** | **+0.156** | **yes** |
| 50-bar breakout | XAU 15m | PF 1.39, 49.6%, 26.2d | lengths x1.25 | PF 1.37, 44.4%, 33.8d | −0.048 | +0.069 | no |
| Neural Edge Scalper | XAU 4h | PF 1.84, 53.2%, 48.9d | lengths x0.75 (same trades) | same | 0 | +0.481 | no |
| 3H sweep + swing break | XAU 1h | PF 1.63, 65.3%, 68.9d | stop3 tgt6 hold96 | PF 2.07, 66.2%, 61.9d | +0.043 | +0.242 | no |
| Triaxial consensus | XAU 1h | PF 1.32, 36.9%, 19.0d | stop3 tgt4 hold48 | PF 1.53, 58.6%, 32.4d | +0.010 | +0.104 | no |
| EURUSD short wpr5 | EUR 1h | PF 1.30, 53.6%, 70.9d | stop2.5 tgt6 hold8 | PF 1.54, 67.2%, 83.3d | −0.011 | +0.074 | no |

Pace at the 2% rung, HOUSE 8/3/6, band 10–90%.

## Confirmation of the one kept (`backtests/factory/tweak_confirm.json`)

Same tweak, 4h, all six markets (mean R per trade, original → tweak):
BTC −0.038 → +0.115, **XAU +0.286 → +0.568**, XAG −0.120 → +0.118,
EUR −0.109 → −0.026, GBP −0.027 → −0.015, JPY −0.075 → +0.041. **6 of 6 better.**
Gold older years: −0.218 → −0.038 (PF 0.73 → 0.96) — better, still losing.

Weak points: one kept of eight is what luck gives; 17.8 days is still outside 5–14;
the 3y bands touch (15–23 vs 22–37); it only makes money on gold.
