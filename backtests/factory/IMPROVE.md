# Step 8 - improvements (factory/improve.py)

Left: as it is. Right: best version found (picked on older half). Luck check: same search on random entries; REAL = newer-half gain beats 95% of random.

| # | strategy | cell | pass | days | accts | PF | tpd || change | pass | days | accts | PF | tpd | luck check |
|---|---|---|---|---|---|---|---||---|---|---|---|---|---|---|
| 1 | 123 reversal long (rule 1) | XAUUSD 4h | 56.1% | 49.9 | 1.78 | 1.51 | 0.32 || volume 1.5x; stop2 tgt6 hold96 | 74.2% | 36.4 | 1.35 | 2.49 | 0.15 | luck (p=0.35) |
| 2 | Asia ORB long (rule 1) | XAUUSD 4h | 49.7% | 46.3 | 2.01 | 1.46 | 0.37 || vol expanding; stop3 tgt4 hold32 | 82.2% | 77.8 | 1.22 | 2.40 | 0.17 | luck (p=0.40) |
| 3 | HMA vs daily open long (rule 1) | XAUUSD 1h | 45.9% | 28.3 | 2.18 | 1.24 | 0.82 || tf 4h; volume 1.5x; stop2 tgt4 hold12 | 65.9% | 56.1 | 1.52 | 2.03 | 0.23 | luck (p=0.62) |
| 4 | MA alignment + new high long | XAUUSD 15m | 45.8% | 26.2 | 2.19 | 1.26 | 0.86 || tf 1h; New York 12-17; stop2 tgt10 hold50 | 66.3% | 28.7 | 1.51 | 2.09 | 0.26 | luck (p=0.17) |
| 5 | HTF trend cloud flip (long, approximated | XAUUSD 1h | 42.5% | 47.0 | 2.35 | 1.21 | 0.39 || tf 4h; above VWAP24; stop5 tgt10 hold12 | 49.4% | 334.7 | 2.02 | 1.78 | 0.11 | luck (p=0.82) |
| 6 | Trend Pulse breakout (no OBV) | XAUUSD 1h | 42.3% | 33.1 | 2.36 | 1.17 | 0.58 || tf 4h; London+NY 07-17; stop3 tgt6 hold12 | 40.4% | 286.9 | 2.47 | 1.47 | 0.11 | luck (p=1.00) |
| 7 | MACD cross up long (rule 1) | XAUUSD 1h | 41.3% | 43.6 | 2.42 | 1.17 | 0.59 || tf 4h; above EMA50; stop5 tgt6 hold24 | 82.1% | 121.8 | 1.22 | 2.69 | 0.12 | luck (p=0.17) |
| 8 | BOS demand-zone retest confirmation (lon | XAUUSD 1h | 40.8% | 24.5 | 2.45 | 1.19 | 0.92 || tf 4h; London 07-12; stop1.5 tgt4 hold6 | 71.2% | 60.4 | 1.4 | 2.18 | 0.16 | luck (p=0.45) |
| 9 | Daily change up long (rule 1) | XAUUSD 1h | 39.3% | 20.4 | 2.55 | 1.17 | 1.18 || tf 4h; New York 12-17; stop1.5 tgt10 hold48 | 55.5% | 25.2 | 1.8 | 2.29 | 0.22 | luck (p=0.10) |
| 10 | EMA21/SMA200 trend long (rule 1) | XAUUSD 1h | 39.0% | 23.1 | 2.57 | 1.21 | 0.96 || tf 4h; vol expanding; stop3 tgt2 hold24 | 68.6% | 113.7 | 1.46 | 1.60 | 0.26 | luck (p=1.00) |
| 11 | SSL+Hama long (rule 1) | XAUUSD 1h | 37.5% | 26.7 | 2.67 | 1.25 | 0.87 || tf 4h; New York 12-17; stop2 tgt10 hold24 | 58.4% | 37.7 | 1.71 | 2.32 | 0.18 | luck (p=0.25) |
| 12 | UPF pivot-low demand bounce long | XAUUSD 1h | 37.3% | 34.9 | 2.68 | 1.23 | 0.78 || tf 4h; vol expanding; stop3 tgt10 hold12 | 83.5% | 119.7 | 1.2 | 2.66 | 0.12 | luck (p=0.70) |
| 13 | B3M trend pullback breakout (reduced) | XAUUSD 1h | 36.4% | 24.7 | 2.74 | 1.19 | 0.97 || tf 4h; VWAP24 rising; stop3 tgt6 hold24 | 76.3% | 51.1 | 1.31 | 2.14 | 0.22 | luck (p=0.17) |
| 14 | HTF 12h candle green + above EMA50 (rule | XAUUSD 1h | 36.4% | 24.7 | 2.75 | 1.23 | 0.93 || tf 4h; volume 1.5x; stop3 tgt6 hold24 | 77.0% | 54.6 | 1.3 | 2.15 | 0.22 | luck (p=0.50) |
| 15 | ORB retest long + VWAP | XAUUSD 1h | 35.9% | 44.5 | 2.78 | 1.18 | 0.42 || volume 1.5x; stop1 tgt6 hold24 | 51.8% | 42.4 | 1.93 | 1.77 | 0.19 | luck (p=0.25) |
| 16 | BTC 3/48 SMA with 168 trend filter (long | XAUUSD 1h | 35.9% | 30.6 | 2.78 | 1.15 | 0.94 || tf 4h; volume 1.5x; stop5 tgt6 hold24 | 81.3% | 99.6 | 1.23 | 2.02 | 0.19 | luck (p=0.78) |
| 17 | NDX close crosses above SMA10, above EMA | XAUUSD 1h | 35.8% | 39.1 | 2.79 | 1.21 | 0.63 || tf 4h; AI 4: Rising average price with above-normal volume shows real par; stop1.5 tgt3 hold36 | 61.2% | 65.4 | 1.64 | 2.82 | 0.12 | luck (p=0.07) |
| 18 | TSI/HullMA/VWMA long (rule 1) | XAUUSD 1h | 35.4% | 22.6 | 2.82 | 1.19 | 1.22 || tf 4h; London 07-12; stop5 tgt3 hold24 | 70.2% | 163.1 | 1.42 | 1.84 | 0.19 | luck (p=0.97) |
| 19 | TURKS 200-SMA trend gate | XAUUSD 1h | 35.2% | 25.6 | 2.84 | 1.22 | 1.00 || late 17-24; stop1.5 tgt10 hold96 | 56.2% | 14.2 | 1.78 | 1.93 | 0.33 | luck (p=0.20) |
| 20 | Pivot high breakout against Supertrend d | EURUSD 15m | 34.8% | 40.2 | 2.87 | 1.18 | 0.64 || tf 1h; volume over avg; stop1 tgt10 hold24 | 44.5% | 35.9 | 2.25 | 2.16 | 0.14 | REAL |
| 21 | Hemant gold liquidity sweep long (K) | XAUUSD 1h | 38.6% | 28.5 | 2.59 | 1.37 | 0.44 || tf 4h; VWAP24 rising; stop1 tgt10 hold24 | 60.6% | 34.6 | 1.65 | 2.73 | 0.10 | REAL |
| 22 | EMA50/200 trend + breadth proxy (K) | XAUUSD 4h | 41.8% | 26.3 | 2.39 | 1.48 | 0.38 || VWAP24 rising; stop1.5 tgt10 hold480 | 62.2% | 20.9 | 1.61 | 2.34 | 0.14 | luck (p=0.68) |
| 23 | Harmonic D proxy: pivot low confirmed (r (K) | XAUUSD 1h | 34.1% | 29.4 | 2.94 | 1.22 | 0.87 || tf 4h; EMA50 rising; stop5 tgt10 hold12 | 86.2% | 90.5 | 1.16 | 2.64 | 0.18 | luck (p=0.53) |
| 24 | VWAP + zero-lag trend pullback long (K) | XAUUSD 4h | 32.9% | 31.9 | 3.04 | 1.24 | 0.68 || vol expanding; stop5 tgt6 hold48 | 73.5% | 114.3 | 1.36 | 2.54 | 0.13 | luck (p=0.82) |
| 25 | Descending trendline breakout long (rule (K) | XAUUSD 15m | 40.7% | 32.0 | 2.46 | 1.23 | 1.11 || tf 4h; EMA50 rising; stop5 tgt1.5 hold8 | 77.2% | 283.6 | 1.29 | 2.84 | 0.14 | luck (p=0.68) |
| 26 | nonstop DCA long proxy (K) | XAUUSD 1h | 38.2% | 88.9 | 2.62 | 1.11 | 1.24 || tf 4h; vol expanding; stop1.5 tgt10 hold240 | 68.6% | 24.8 | 1.46 | 3.02 | 0.11 | REAL |
| 27 | 8PM MGC range breakout long (rule 1) (K) | XAUUSD 1h | 38.0% | 21.0 | 2.63 | 1.23 | 0.79 || AI 4: A late-session break out of a quiet, low-trend market tends ; stop1.8 tgt4 hold36 | 64.5% | 74.4 | 1.55 | 1.67 | 0.16 | luck (p=0.93) |
