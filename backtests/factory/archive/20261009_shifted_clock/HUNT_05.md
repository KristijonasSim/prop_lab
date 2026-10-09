# Step 8 - improvements (factory/improve.py)

Left: as it is. Right: best version found (picked on older half). Luck check: same search on random entries; REAL = newer-half gain beats 95% of random.

| # | strategy | cell | pass | days | accts | PF | tpd || change | pass | days | accts | PF | tpd | luck check |
|---|---|---|---|---|---|---|---||---|---|---|---|---|---|---|
| 1 | 50-bar breakout in uptrend | XAUUSD 15m | 48.3% | 31.1 | 2.07 | 1.33 | 0.63 || 4h candle green | 56.0% | 28.6 | 1.79 | 1.45 | 0.56 | luck (p=0.47) |
| 2 | NY window drift long (proxy) (rule 1) | XAUUSD 4h | 42.5% | 51.7 | 2.35 | 1.27 | 0.72 || London+NY 07-17; stop1.5 tgt6 hold6 | 50.1% | 35.9 | 1.99 | 1.41 | 0.52 | luck (p=0.28) |
| 3 | TrendSurfers+TrendOsc long (rule 1) | XAUUSD 15m | 37.4% | 16.0 | 2.67 | 1.34 | 0.61 || EMA50 over EMA200; stop3 tgt6 hold96 | 52.1% | 28.8 | 1.92 | 1.51 | 0.54 | luck (p=0.93) |
| 4 | Underworld Hunter long (rule 1) | XAUUSD 1h | 46.8% | 47.0 | 2.13 | 1.28 | 0.54 || RSI14 over 50; stop5 tgt4 hold12 | 59.7% | 126.5 | 1.68 | 1.42 | 0.52 | luck (p=1.00) |
| 5 | LANZ BOS up + uptrend (no clock gate) (r | XAUUSD 1h | 42.3% | 26.0 | 2.36 | 1.33 | 0.76 || EMA50 over EMA200; stop1.5 tgt4 hold10 | 48.0% | 37.5 | 2.08 | 1.37 | 0.54 | luck (p=0.90) |
| 6 | BB breakout long with EMA200 trend and v | XAUUSD 1h | 33.7% | 29.7 | 2.97 | 1.23 | 0.76 || 4h candle green; stop2 tgt6 hold24 | 46.3% | 25.9 | 2.16 | 1.56 | 0.52 | REAL |
| 7 | EMA100/500 trend-aligned long | XAUUSD 15m | 32.8% | 15.2 | 3.05 | 1.27 | 1.16 || tf 4h; EMA50 rising; stop1.5 tgt3 hold6 | 41.3% | 26.6 | 2.42 | 1.45 | 0.60 | luck (p=0.85) |
| 8 | sustained strength above VWAP | XAUUSD 1h | 35.8% | 39.1 | 2.79 | 1.25 | 0.57 || VWAP24 rising; stop2 tgt10 hold12 | 42.8% | 37.4 | 2.34 | 1.48 | 0.57 | luck (p=0.07) |
| 9 | Triaxial consensus long (trend stack + R | XAUUSD 1h | 31.3% | 22.4 | 3.2 | 1.23 | 0.85 || EMA50 over EMA200; stop5 tgt6 hold24 | 62.7% | 60.6 | 1.59 | 1.51 | 0.53 | luck (p=0.95) |
| 10 | ORION box breakout long (rule 1) | XAUUSD 1h | 41.8% | 35.9 | 2.39 | 1.25 | 0.61 || above EMA200; stop2 tgt10 hold24 | 49.1% | 20.4 | 2.04 | 1.45 | 0.53 | REAL |
| 11 | Daily low above daily EMA21 for 3 days | XAUUSD 15m | 35.7% | 14.0 | 2.8 | 1.20 | 1.39 || tf 4h; stop1.5 tgt3 hold6 | 36.4% | 33.0 | 2.75 | 1.29 | 0.62 | luck (p=0.45) |
| 12 | CMS bull stack + RSI | XAUUSD 1h | 41.1% | 26.8 | 2.43 | 1.25 | 0.85 || 4h candle green; stop2 tgt6 hold24 | 53.4% | 26.2 | 1.87 | 1.56 | 0.57 | luck (p=0.25) |
| 13 | SMMA high-band two-bar breakout | XAUUSD 4h | 48.6% | 45.2 | 2.06 | 1.21 | 0.75 || London+NY 07-17; stop5 tgt2 hold4 | 73.2% | 151.7 | 1.37 | 1.55 | 0.67 | luck (p=0.70) |
| 14 | 5m EMA8 pullback with 1H trend filter lo | XAUUSD 1h | 43.8% | 22.8 | 2.28 | 1.24 | 0.87 || EMA50 over EMA200; stop2 tgt10 hold24 | 55.7% | 19.7 | 1.79 | 1.72 | 0.53 | REAL |
| 15 | Keltner breakout long (approx) | XAUUSD 1h | 28.6% | 24.4 | 3.49 | 1.19 | 1.04 || tf 4h; above VWAP24; stop1.5 tgt4 hold6 | 41.1% | 29.2 | 2.43 | 1.51 | 0.56 | luck (p=0.07) |
| 16 | SR pivot breakout (long) | XAUUSD 1h | 45.8% | 34.9 | 2.18 | 1.30 | 0.56 || above VWAP24; stop5 tgt4 hold24 | 58.5% | 83.7 | 1.71 | 1.44 | 0.51 | luck (p=0.28) |
| 17 | Donchian 20 breakout + rising 200 trend | XAUUSD 1h | 34.3% | 37.9 | 2.92 | 1.19 | 0.61 || EMA50 rising; stop5 tgt10 hold12 | 63.9% | 72.0 | 1.57 | 1.37 | 0.56 | luck (p=0.53) |
| 18 | Super Scalper long (rule 1) | XAUUSD 1h | 38.2% | 31.4 | 2.62 | 1.24 | 0.69 || above VWAP96; stop1.5 tgt10 hold24 | 40.9% | 17.1 | 2.45 | 1.40 | 0.53 | REAL |
| 19 | Narrow-state trend reversal bar (long) | XAUUSD 1h | 35.0% | 42.9 | 2.86 | 1.20 | 0.61 || above VWAP24; stop5 tgt2 hold24 | 47.1% | 161.5 | 2.12 | 1.26 | 0.54 | luck (p=0.95) |
| 20 | Aurum AVE long break (rule 1) | XAUUSD 1h | 33.1% | 33.2 | 3.02 | 1.14 | 0.74 || EMA50 over EMA200; stop1.5 tgt6 hold24 | 42.3% | 26.0 | 2.36 | 1.44 | 0.52 | REAL |
| 21 | Buy-pressure uptrend proxy | XAUUSD 1h | 42.8% | 46.7 | 2.34 | 1.17 | 0.62 || above VWAP24; stop3 tgt10 hold24 | 40.1% | 49.9 | 2.49 | 1.31 | 0.51 | luck (p=0.65) |
| 22 | CEM trend-stack long | XAUUSD 1h | 38.7% | 23.3 | 2.59 | 1.23 | 1.03 || New York 12-17; stop1 tgt6 hold24 | 39.5% | 20.3 | 2.53 | 1.39 | 0.51 | luck (p=0.72) |
| 23 | BB basis EMA cross + AO positive | XAUUSD 1h | 43.1% | 34.8 | 2.32 | 1.23 | 0.70 || above EMA200; stop2 tgt10 hold12 | 45.6% | 30.7 | 2.19 | 1.60 | 0.63 | REAL |
| 24 | AutoFib 1.618 breakout above EMA200 | XAUUSD 1h | 42.9% | 16.3 | 2.33 | 1.23 | 0.89 || EMA50 over EMA200; stop1.5 tgt4 hold24 | 41.8% | 23.9 | 2.39 | 1.53 | 0.57 | luck (p=0.42) |
| 25 | PCT confluence long (trend core) (rule 1 | XAUUSD 1h | 33.3% | 30.0 | 3.0 | 1.19 | 0.91 || 4h candle green; stop5 tgt10 hold24 | 56.0% | 59.0 | 1.79 | 1.54 | 0.56 | luck (p=0.45) |
| 26 | EMA9 reclaim in uptrend | XAUUSD 1h | 38.6% | 31.1 | 2.59 | 1.21 | 0.67 || above SMA200; stop3 tgt10 hold12 | 49.4% | 46.5 | 2.02 | 1.52 | 0.56 | luck (p=0.12) |
| 27 | Seasonal month-start long (always-in pro | XAUUSD 15m | 30.0% | 20.0 | 3.33 | 1.02 | 1.77 || tf 4h; EMA50 rising | 79.4% | 91.9 | 1.26 | 1.63 | 0.54 | luck (p=0.40) |
| 28 | EMA50 MACD RSI long (rule 1) | XAUUSD 4h | 33.4% | 35.9 | 2.99 | 1.15 | 0.62 || VWAP24 rising; stop3 tgt1.5 hold4 | 48.7% | 197.1 | 2.05 | 1.19 | 0.53 | luck (p=0.80) |
| 29 | Tomukas trend+VWAP+RSI long | XAUUSD 1h | 42.6% | 28.2 | 2.35 | 1.27 | 0.90 || 4h candle green; stop5 tgt10 hold24 | 63.5% | 52.0 | 1.58 | 1.72 | 0.49 | luck (p=0.50) |
| 30 | DEMA ATR line turns up (rule 1) | XAUUSD 1h | 36.4% | 33.0 | 2.75 | 1.17 | 0.97 || volume over avg; stop1 tgt10 hold24 | 43.6% | 11.5 | 2.29 | 1.55 | 0.67 | REAL |
| 31 | Grid dip-buy proxy | XAUUSD 4h | 48.8% | 147.5 | 2.05 | 1.13 | 0.80 || New York 12-17; stop1 tgt10 hold6 | 51.4% | 23.4 | 1.95 | 1.50 | 0.57 | luck (p=0.42) |
| 32 | Keltner breakout long | XAUUSD 1h | 34.1% | 35.2 | 2.93 | 1.13 | 0.65 || EMA50 rising; stop5 tgt4 hold24 | 51.5% | 79.6 | 1.94 | 1.35 | 0.53 | luck (p=0.80) |
| 33 | MR Pro long (rule 1) | XAUUSD 1h | 25.7% | 38.9 | 3.89 | 1.08 | 0.94 || not Asia 07-21; stop5 tgt6 hold24 | 82.3% | 62.0 | 1.21 | 1.66 | 0.55 | luck (p=0.85) |
| 34 | Bullish engulfing above EMA200 | XAUUSD 1h | 36.2% | 44.2 | 2.77 | 1.19 | 0.64 || SMA200 rising; stop1.5 tgt6 hold24 | 38.8% | 25.8 | 2.58 | 1.36 | 0.52 | luck (p=0.47) |
| 35 | Hermes ALMA return trend + breakout + ma | XAUUSD 1h | 33.4% | 35.9 | 2.99 | 1.17 | 0.77 || EMA50 over EMA200; stop1.5 tgt10 hold24 | 42.0% | 19.0 | 2.38 | 1.56 | 0.52 | REAL |
| 36 | ATR GOD long ST3 flip (rule 2) | XAUUSD 15m | 42.5% | 47.1 | 2.35 | 1.21 | 0.83 || above SMA200; stop1.5 tgt10 hold96 | 47.7% | 12.6 | 2.1 | 1.67 | 0.48 | REAL |
| 37 | Concordance long: bias up + stochastic m | XAUUSD 1h | 30.2% | 26.5 | 3.31 | 1.13 | 1.12 || tf 4h; RSI14 over 50; stop2 tgt3 hold6 | 53.6% | 42.9 | 1.87 | 1.54 | 0.57 | luck (p=0.28) |
| 38 | Squeeze breakout above 20-bar high, abov | XAUUSD 1h | 34.6% | 49.2 | 2.89 | 1.09 | 0.64 || EMA50 over EMA200; stop1.5 tgt4 hold12 | 37.2% | 43.0 | 2.69 | 1.19 | 0.55 | luck (p=0.70) |
| 39 | IB breakout retrace long | XAUUSD 1h | 38.9% | 28.2 | 2.57 | 1.17 | 0.87 || 4h candle green; stop1 tgt10 hold24 | 35.2% | 17.0 | 2.84 | 1.30 | 0.55 | luck (p=0.68) |
| 40 | VWAP + BB dip in uptrend | XAUUSD 1h | 26.3% | 34.2 | 3.81 | 1.15 | 0.85 || RSI14 over 50; stop3 tgt10 hold24 | 54.2% | 35.0 | 1.84 | 1.62 | 0.53 | luck (p=0.12) |
