# Step 8 - improvements (factory/improve.py)

Left: as it is. Right: best version found (picked on older half). Luck check: same search on random entries; REAL = newer-half gain beats 95% of random.

| # | strategy | cell | pass | days | accts | PF | tpd || change | pass | days | accts | PF | tpd | luck check |
|---|---|---|---|---|---|---|---||---|---|---|---|---|---|---|
| 1 | Descending trendline breakout long (rule | XAUUSD 15m | 40.7% | 32.0 | 2.46 | 1.23 | 1.11 || daily candle green | 40.3% | 29.8 | 2.48 | 1.26 | 1.04 | luck (p=0.62) |
| 2 | 200 SMA regime gate | XAUUSD 1h | 30.8% | 22.7 | 3.25 | 1.06 | 1.44 || not Asia 07-21; stop1.5 tgt4 hold24 | 28.3% | 17.7 | 3.54 | 1.21 | 1.05 | luck (p=0.88) |
| 3 | CRTS long score approx (rule 1) | XAUUSD 15m | 28.4% | 21.1 | 3.52 | 1.19 | 1.35 || SMA200 rising; stop1.5 tgt10 hold96 | 43.4% | 9.2 | 2.3 | 1.41 | 1.09 | REAL |
| 4 | BB basis fast-EMA cross up | XAUUSD 1h | 32.1% | 28.0 | 3.11 | 1.12 | 1.32 || none | 32.1% | 28.0 | 3.11 | 1.12 | 1.32 | luck (p=0.68) |
| 5 | TSI/HullMA/VWMA long (rule 1) | XAUUSD 1h | 30.5% | 23.0 | 3.28 | 1.15 | 1.44 || above EMA200 | 35.9% | 22.3 | 2.78 | 1.23 | 1.02 | luck (p=0.78) |
| 6 | EMA44 reclaim in EMA200 uptrend | XAUUSD 15m | 31.3% | 12.8 | 3.19 | 1.18 | 1.20 || EMA50 over EMA200 | 33.5% | 11.9 | 2.98 | 1.27 | 1.01 | luck (p=0.12) |
| 7 | Z-Score oversold long (rule 1) | EURUSD 15m | 38.3% | 33.9 | 2.61 | 1.18 | 1.00 || stop1.5 tgt10 hold96 | 38.6% | 7.8 | 2.59 | 1.29 | 1.01 | REAL |
| 8 | L_PULL (rule 1) | XAUUSD 1h | 37.1% | 24.3 | 2.69 | 1.14 | 1.17 || stop5 tgt3 hold24 | 46.2% | 69.2 | 2.16 | 1.17 | 1.01 | luck (p=0.97) |
| 9 | EMA 9/21 cross long | XAUUSD 15m | 26.9% | 22.3 | 3.72 | 1.09 | 1.31 || RSI14 over 50; stop3 tgt10 hold48 | 29.6% | 16.9 | 3.38 | 1.21 | 1.39 | luck (p=0.12) |
| 10 | Second reversal bar long (rule 1) | XAUUSD 1h | 33.2% | 30.1 | 3.01 | 1.18 | 1.24 || stop3 tgt3 hold24 | 36.5% | 41.1 | 2.74 | 1.18 | 1.12 | luck (p=0.95) |
| 11 | Daily change up long (rule 1) | XAUUSD 1h | 32.7% | 21.4 | 3.06 | 1.10 | 1.54 || EMA50 over EMA200; stop1 tgt6 hold24 | 35.5% | 11.3 | 2.82 | 1.25 | 1.05 | luck (p=0.28) |
| 12 | NSE Elite v6 trend-momentum confluence ( | XAUUSD 15m | 34.3% | 11.6 | 2.91 | 1.16 | 1.66 || above VWAP24; stop2 tgt10 hold96 | 40.1% | 10.0 | 2.49 | 1.31 | 1.19 | luck (p=0.07) |
| 13 | Index low above 21 EMA trend long | XAUUSD 1h | 34.8% | 25.9 | 2.87 | 1.10 | 1.13 || RSI14 over 50 | 38.8% | 25.8 | 2.58 | 1.14 | 1.11 | luck (p=0.62) |
| 14 | Prism MA stack long (rule 1) | XAUUSD 1h | 29.2% | 22.3 | 3.43 | 1.12 | 1.17 || VWAP24 rising; stop2 tgt10 hold12 | 46.4% | 19.4 | 2.16 | 1.40 | 1.04 | REAL |
| 15 | UNI STRAT volume-mode long proxy (rule 1 | XAUUSD 1h | 30.7% | 22.8 | 3.26 | 1.07 | 1.69 || SMA200 rising; stop1.5 tgt6 hold24 | 37.6% | 13.3 | 2.66 | 1.25 | 1.04 | REAL |
| 16 | Sweep-and-reclaim long | XAUUSD 1h | 32.5% | 21.5 | 3.08 | 1.09 | 1.29 || stop1 tgt4 hold24 | 31.1% | 12.9 | 3.22 | 1.07 | 1.38 | luck (p=0.80) |
| 17 | MA slope turn-up (approx: price cross ab | XAUUSD 1h | 31.1% | 22.5 | 3.21 | 1.12 | 1.26 || stop1 tgt3 hold24 | 27.2% | 14.7 | 3.68 | 1.12 | 1.44 | luck (p=0.72) |
| 18 | M0PB long (rule 1) | EURUSD 15m | 46.0% | 34.8 | 2.17 | 1.14 | 1.07 || EMA50 rising; stop5 tgt3 hold24 | 53.9% | 61.2 | 1.85 | 1.22 | 1.08 | luck (p=0.80) |
| 19 | RSI40 cross above 60 long (rule 1) | XAUUSD 15m | 33.6% | 35.7 | 2.97 | 1.14 | 1.06 || above VWAP24; stop1.5 tgt10 hold96 | 37.6% | 8.0 | 2.66 | 1.22 | 1.09 | luck (p=0.15) |
| 20 | Inertia RVI proxy long (RSI20 > 50) (rul | XAUUSD 1h | 34.0% | 20.6 | 2.94 | 1.12 | 1.31 || above EMA200; stop2 tgt10 hold12 | 41.5% | 16.9 | 2.41 | 1.50 | 1.10 | REAL |
| 21 | Momentum candle long | XAUUSD 1h | 28.3% | 31.8 | 3.53 | 1.07 | 1.15 || stop2 tgt6 hold24 | 37.8% | 18.5 | 2.64 | 1.18 | 1.05 | luck (p=0.23) |
| 22 | Multi-timeframe range score > 10 | XAUUSD 1h | 21.3% | 37.5 | 4.69 | 0.99 | 1.31 || above SMA200; stop1.5 tgt4 hold24 | 22.3% | 18.0 | 4.49 | 1.13 | 1.13 | luck (p=0.82) |
| 23 | EMA trend + 20-bar breakout (long) | XAUUSD 15m | 30.2% | 26.5 | 3.31 | 1.13 | 1.14 || VWAP24 rising; stop5 tgt10 hold24 | 44.7% | 35.8 | 2.24 | 1.27 | 1.07 | luck (p=0.88) |
| 24 | ALMA close/open cross long (rule 1) | XAUUSD 1h | 27.6% | 21.8 | 3.63 | 1.00 | 1.80 || 4h candle green; stop5 tgt3 hold24 | 52.8% | 68.2 | 1.89 | 1.23 | 1.00 | luck (p=0.47) |
| 25 | Bill Williams bottom fractal long | XAUUSD 1h | 29.0% | 27.6 | 3.45 | 1.13 | 1.25 || stop3 tgt4 hold24 | 32.9% | 42.6 | 3.04 | 1.14 | 1.09 | luck (p=0.88) |
| 26 | Multi-factor score long (3-vote proxy) | XAUUSD 1h | 38.5% | 26.0 | 2.6 | 1.05 | 1.17 || above VWAP24; stop2 tgt10 hold12 | 40.1% | 19.9 | 2.49 | 1.27 | 1.16 | luck (p=0.17) |
| 27 | RSI 55 cross in uptrend | XAUUSD 15m | 30.6% | 32.6 | 3.26 | 1.12 | 1.22 || EMA50 over EMA200; stop2 tgt10 hold96 | 35.2% | 14.2 | 2.84 | 1.21 | 0.99 | luck (p=0.45) |
| 28 | XGB Mini proxy: momentum above SMA15/EMA | XAUUSD 1h | 31.2% | 22.4 | 3.2 | 1.08 | 1.24 || above EMA200; stop1.5 tgt4 hold24 | 32.9% | 18.2 | 3.04 | 1.22 | 1.04 | luck (p=0.35) |
| 29 | Alpha S/R engulf long | XAUUSD 15m | 34.0% | 11.8 | 2.94 | 1.12 | 1.51 || ADX14 over 20 | 39.9% | 17.5 | 2.51 | 1.14 | 1.00 | luck (p=0.85) |
| 30 | Fib EMA 21/55 long (rule 1) | XAUUSD 1h | 33.3% | 24.0 | 3.01 | 1.00 | 1.41 || not Asia 07-21; stop3 tgt2 hold24 | 40.3% | 57.1 | 2.48 | 1.16 | 1.05 | luck (p=0.97) |
| 31 | SMA60/280 trend + prior bar up | XAUUSD 1h | 31.9% | 31.3 | 3.13 | 1.11 | 1.21 || above SMA200; stop3 tgt10 hold12 | 45.3% | 26.5 | 2.21 | 1.35 | 1.04 | luck (p=0.20) |
| 32 | Uptrend re-entry above slow EMA | XAUUSD 1h | 27.4% | 25.5 | 3.64 | 1.01 | 1.48 || not Asia 07-21; stop1.5 tgt6 hold24 | 26.9% | 18.6 | 3.72 | 1.22 | 1.01 | luck (p=0.23) |
| 33 | CCI(11) oversold cross up (rule 1) | XAUUSD 1h | 24.5% | 20.4 | 4.09 | 1.05 | 1.26 || stop1 tgt4 hold24 | 28.4% | 17.6 | 3.52 | 1.09 | 1.23 | luck (p=0.25) |
| 34 | NY VWAP momentum long | XAUUSD 1h | 29.7% | 26.9 | 3.36 | 1.09 | 1.21 || above EMA50; stop1.5 tgt6 hold24 | 36.4% | 13.7 | 2.74 | 1.27 | 1.03 | luck (p=0.23) |
| 35 | 2MA high breakout long (rule 2) | XAUUSD 15m | 32.3% | 21.7 | 3.1 | 1.12 | 1.41 || above EMA50; stop1 tgt6 hold48 | 35.3% | 8.5 | 2.84 | 1.20 | 1.05 | luck (p=0.12) |
| 36 | Eliora Gold long (rule 1) | XAUUSD 1h | 31.3% | 22.4 | 3.19 | 1.07 | 1.56 || above EMA200; stop1.5 tgt4 hold24 | 33.0% | 18.2 | 3.03 | 1.22 | 1.15 | luck (p=0.72) |
| 37 | EMA trend with efficiency filter (effici | XAUUSD 1h | 27.3% | 18.3 | 3.67 | 1.01 | 1.56 || RSI14 over 50; stop5 tgt10 hold12 | 58.4% | 46.3 | 1.71 | 1.37 | 1.05 | luck (p=0.75) |
| 38 | nonstop DCA long proxy | XAUUSD 1h | 19.4% | 118.8 | 5.17 | 0.88 | 2.07 || tf 15m; ADX14 under 20; stop3 tgt10 hold96 | 38.9% | 15.4 | 2.57 | 1.24 | 1.13 | luck (p=0.23) |
| 39 | green candle long (rule 1) | XAUUSD 1h | 26.0% | 23.1 | 3.85 | 0.99 | 1.98 || New York 12-17; stop1.5 tgt3 hold24 | 37.0% | 24.3 | 2.7 | 1.19 | 1.08 | luck (p=0.30) |
| 40 | SMA20/120 trend + ADX long (rule 1) | XAUUSD 1h | 35.7% | 25.2 | 2.8 | 1.05 | 1.21 || above SMA200; stop2 tgt10 hold12 | 35.2% | 17.1 | 2.84 | 1.28 | 1.15 | luck (p=0.07) |
