# Step 8 - improvements (factory/improve.py)

Left: as it is. Right: best version found (picked on older half). Luck check: same search on random entries; REAL = newer-half gain beats 95% of random.

| # | strategy | cell | pass | days | accts | PF | tpd || change | pass | days | accts | PF | tpd | luck check |
|---|---|---|---|---|---|---|---||---|---|---|---|---|---|---|
| 1 | 50-bar breakout in uptrend | XAUUSD 15m | 46.7% | 32.2 | 2.14 | 1.33 | 0.63 || 4h candle green | 58.5% | 29.1 | 1.71 | 1.44 | 0.56 | luck (p=0.50) |
| 2 | NY window drift long (proxy) (rule 1) | XAUUSD 4h | 43.5% | 43.6 | 2.3 | 1.31 | 0.72 || London+NY 07-17; stop2 tgt3 hold6 | 56.9% | 54.5 | 1.76 | 1.48 | 0.54 | luck (p=0.38) |
| 3 | TrendSurfers+TrendOsc long (rule 1) | XAUUSD 15m | 36.9% | 16.3 | 2.71 | 1.34 | 0.61 || EMA50 over EMA200; stop3 tgt6 hold96 | 52.9% | 30.2 | 1.89 | 1.51 | 0.54 | luck (p=0.82) |
| 4 | Underworld Hunter long (rule 1) | XAUUSD 1h | 50.6% | 45.5 | 1.98 | 1.28 | 0.54 || RSI14 over 50; stop5 tgt4 hold12 | 59.7% | 125.6 | 1.67 | 1.42 | 0.52 | luck (p=1.00) |
| 5 | LANZ BOS up + uptrend (no clock gate) (r | XAUUSD 1h | 42.5% | 25.9 | 2.35 | 1.33 | 0.76 || EMA50 over EMA200; stop1.5 tgt4 hold10 | 48.2% | 37.3 | 2.07 | 1.37 | 0.54 | luck (p=0.90) |
| 6 | BB breakout long with EMA200 trend and v | XAUUSD 1h | 32.7% | 30.5 | 3.05 | 1.22 | 0.76 || EMA50 over EMA200; stop2 tgt10 hold24 | 41.9% | 23.8 | 2.38 | 1.46 | 0.53 | luck (p=0.12) |
| 7 | EMA100/500 trend-aligned long | XAUUSD 15m | 32.5% | 15.4 | 3.08 | 1.27 | 1.16 || tf 4h; EMA50 rising; stop2 tgt10 hold6 | 59.9% | 30.1 | 1.67 | 1.71 | 0.53 | luck (p=0.25) |
| 8 | sustained strength above VWAP | XAUUSD 1h | 36.1% | 41.5 | 2.77 | 1.24 | 0.57 || VWAP24 rising; stop2 tgt10 hold12 | 45.1% | 37.7 | 2.22 | 1.47 | 0.57 | REAL |
| 9 | Triaxial consensus long (trend stack + R | XAUUSD 1h | 31.4% | 22.3 | 3.19 | 1.23 | 0.85 || EMA50 over EMA200; stop5 tgt6 hold24 | 62.7% | 60.6 | 1.59 | 1.51 | 0.53 | luck (p=0.93) |
| 10 | ORION box breakout long (rule 1) | XAUUSD 1h | 42.0% | 35.7 | 2.38 | 1.25 | 0.61 || above EMA200; stop2 tgt10 hold24 | 49.3% | 20.3 | 2.03 | 1.45 | 0.53 | REAL |
| 11 | Daily low above daily EMA21 for 3 days | XAUUSD 15m | 33.3% | 15.0 | 3.0 | 1.19 | 1.39 || tf 4h; stop2 tgt10 hold6 | 44.3% | 40.7 | 2.26 | 1.41 | 0.55 | luck (p=0.53) |
| 12 | CMS bull stack + RSI | XAUUSD 1h | 40.0% | 25.0 | 2.5 | 1.25 | 0.85 || not Asia 07-21; stop5 tgt4 hold24 | 69.5% | 67.6 | 1.44 | 1.65 | 0.49 | luck (p=0.95) |
| 13 | SMMA high-band two-bar breakout | XAUUSD 4h | 44.3% | 42.9 | 2.26 | 1.28 | 0.74 || above EMA50; stop2 tgt3 hold6 | 48.7% | 36.9 | 2.05 | 1.50 | 0.67 | luck (p=0.20) |
| 14 | 5m EMA8 pullback with 1H trend filter lo | XAUUSD 1h | 44.4% | 24.8 | 2.25 | 1.24 | 0.87 || EMA50 over EMA200; stop2 tgt10 hold24 | 55.0% | 20.9 | 1.82 | 1.72 | 0.53 | REAL |
| 15 | Keltner breakout long (approx) | XAUUSD 1h | 29.2% | 24.0 | 3.42 | 1.19 | 1.04 || tf 4h; above EMA50; stop1 tgt10 hold6 | 39.3% | 17.8 | 2.54 | 1.57 | 0.61 | REAL |
| 16 | SR pivot breakout (long) | XAUUSD 1h | 45.2% | 35.4 | 2.21 | 1.30 | 0.56 || above VWAP24; stop5 tgt4 hold24 | 58.6% | 83.6 | 1.71 | 1.44 | 0.51 | luck (p=0.38) |
| 17 | Donchian 20 breakout + rising 200 trend | XAUUSD 1h | 33.1% | 39.3 | 3.02 | 1.19 | 0.61 || EMA50 rising; stop5 tgt10 hold12 | 60.9% | 75.6 | 1.64 | 1.37 | 0.56 | luck (p=0.57) |
| 18 | Super Scalper long (rule 1) | XAUUSD 1h | 38.1% | 31.5 | 2.62 | 1.23 | 0.69 || not Asia 07-21; stop1.5 tgt6 hold24 | 42.4% | 33.0 | 2.36 | 1.32 | 0.51 | luck (p=0.28) |
| 19 | Narrow-state trend reversal bar (long) | XAUUSD 1h | 34.0% | 41.2 | 2.95 | 1.20 | 0.61 || EMA50 over EMA200; stop1 tgt6 hold24 | 33.3% | 15.0 | 3.0 | 1.35 | 0.60 | luck (p=0.62) |
| 20 | Aurum AVE long break (rule 1) | XAUUSD 1h | 30.6% | 32.6 | 3.26 | 1.14 | 0.74 || EMA50 over EMA200; stop1.5 tgt6 hold24 | 40.3% | 27.3 | 2.48 | 1.44 | 0.52 | REAL |
| 21 | Buy-pressure uptrend proxy | XAUUSD 1h | 42.8% | 46.7 | 2.34 | 1.17 | 0.63 || above VWAP24; stop3 tgt10 hold24 | 40.2% | 49.8 | 2.49 | 1.31 | 0.51 | luck (p=0.57) |
| 22 | CEM trend-stack long | XAUUSD 1h | 38.9% | 23.2 | 2.57 | 1.23 | 1.03 || New York 12-17; stop1 tgt6 hold24 | 42.1% | 19.0 | 2.38 | 1.51 | 0.52 | luck (p=0.25) |
| 23 | BB basis EMA cross + AO positive | XAUUSD 1h | 41.2% | 36.4 | 2.43 | 1.23 | 0.70 || above EMA200; stop2 tgt4 hold24 | 49.5% | 30.3 | 2.02 | 1.52 | 0.54 | luck (p=0.12) |
| 24 | AutoFib 1.618 breakout above EMA200 | XAUUSD 1h | 43.5% | 18.4 | 2.3 | 1.23 | 0.89 || EMA50 over EMA200; stop1.5 tgt4 hold24 | 41.8% | 23.9 | 2.39 | 1.53 | 0.57 | luck (p=0.53) |
| 25 | PCT confluence long (trend core) (rule 1 | XAUUSD 1h | 31.4% | 30.2 | 3.18 | 1.19 | 0.91 || vol quiet; stop2 tgt10 hold24 | 41.1% | 20.7 | 2.43 | 1.60 | 0.47 | REAL |
| 26 | EMA9 reclaim in uptrend | XAUUSD 1h | 39.2% | 30.6 | 2.55 | 1.21 | 0.67 || not Asia 07-21; stop1 tgt10 hold24 | 34.8% | 17.2 | 2.87 | 1.38 | 0.51 | luck (p=0.35) |
| 27 | Seasonal month-start long (always-in pro | XAUUSD 15m | 29.6% | 20.2 | 3.37 | 1.01 | 1.78 || tf 4h; New York 12-17; stop2 tgt10 hold4 | 57.6% | 57.3 | 1.73 | 1.45 | 0.89 | luck (p=0.65) |
| 28 | EMA50 MACD RSI long (rule 1) | XAUUSD 4h | 31.5% | 34.9 | 3.17 | 1.21 | 0.60 || not Asia 07-21; stop1.5 tgt1.5 hold6 | 41.2% | 60.7 | 2.43 | 1.26 | 0.56 | luck (p=0.93) |
| 29 | Tomukas trend+VWAP+RSI long | XAUUSD 1h | 40.7% | 29.5 | 2.46 | 1.27 | 0.90 || above EMA50; stop2 tgt10 hold24 | 47.0% | 21.3 | 2.13 | 1.55 | 0.67 | REAL |
| 30 | DEMA ATR line turns up (rule 1) | XAUUSD 1h | 36.4% | 32.9 | 2.74 | 1.17 | 0.97 || volume over avg; stop1 tgt10 hold24 | 43.7% | 11.4 | 2.29 | 1.55 | 0.67 | REAL |
| 31 | Grid dip-buy proxy | XAUUSD 4h | 50.2% | 153.3 | 1.99 | 1.14 | 0.80 || New York 12-17; stop1 tgt10 hold6 | 46.6% | 30.1 | 2.15 | 1.38 | 0.60 | luck (p=0.78) |
| 32 | Keltner breakout long | XAUUSD 1h | 32.1% | 34.3 | 3.11 | 1.13 | 0.65 || EMA50 rising; stop5 tgt4 hold24 | 51.5% | 79.6 | 1.94 | 1.35 | 0.53 | luck (p=0.75) |
| 33 | MR Pro long (rule 1) | XAUUSD 1h | 26.6% | 41.3 | 3.76 | 1.08 | 0.94 || not Asia 07-21; stop5 tgt6 hold24 | 76.6% | 60.0 | 1.3 | 1.55 | 0.56 | luck (p=0.93) |
| 34 | Bullish engulfing above EMA200 | XAUUSD 1h | 34.6% | 46.3 | 2.89 | 1.19 | 0.64 || SMA200 rising; stop1.5 tgt6 hold24 | 38.8% | 25.8 | 2.58 | 1.36 | 0.52 | luck (p=0.57) |
| 35 | Hermes ALMA return trend + breakout + ma | XAUUSD 1h | 33.4% | 35.9 | 2.99 | 1.16 | 0.77 || EMA50 over EMA200; stop1.5 tgt10 hold24 | 42.1% | 19.0 | 2.38 | 1.56 | 0.52 | REAL |
| 36 | ATR GOD long ST3 flip (rule 2) | XAUUSD 15m | 42.8% | 46.8 | 2.34 | 1.21 | 0.83 || above SMA200; stop1.5 tgt10 hold96 | 49.2% | 12.2 | 2.03 | 1.67 | 0.48 | REAL |
| 37 | Concordance long: bias up + stochastic m | XAUUSD 1h | 30.6% | 26.2 | 3.27 | 1.13 | 1.12 || tf 4h; not Asia 07-21; stop1.5 tgt10 hold6 | 50.6% | 29.6 | 1.98 | 1.66 | 0.52 | REAL |
| 38 | Squeeze breakout above 20-bar high, abov | XAUUSD 1h | 34.5% | 49.3 | 2.9 | 1.09 | 0.64 || EMA50 over EMA200; stop1.5 tgt4 hold12 | 37.5% | 40.0 | 2.67 | 1.19 | 0.55 | luck (p=0.47) |
| 39 | IB breakout retrace long | XAUUSD 1h | 36.7% | 35.4 | 2.72 | 1.18 | 0.80 || not Asia 07-21; stop1.5 tgt4 hold24 | 39.1% | 28.1 | 2.56 | 1.30 | 0.72 | luck (p=0.35) |
| 40 | VWAP + BB dip in uptrend | XAUUSD 1h | 26.4% | 34.1 | 3.79 | 1.15 | 0.85 || RSI14 over 50; stop3 tgt10 hold24 | 54.2% | 36.9 | 1.84 | 1.61 | 0.53 | luck (p=0.25) |
