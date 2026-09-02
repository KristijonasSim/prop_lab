"""Forward collector for the feeds Binance will not give history for.

Funding reaches back to 2019, so H-004 could be backtested immediately. Open
interest and the taker buy/sell ratio are capped at roughly two days on the
public endpoint, which is why they could not be tested at all. The only way they
ever become testable is to start recording now.

Appends to parquet on every pass, deduplicates on timestamp, and is safe to stop
and restart - it re-reads what it already has and only keeps new rows. Every hour
it is not running is an hour of data that cannot be recovered later.

Run in the background:
    nohup .venv/bin/python core/feed_collector.py > data/feeds/collector.log 2>&1 &

Or better, from cron every 15 minutes (it exits after one pass with --once):
    */15 * * * * /home/kris/prop_lab/.venv/bin/python /home/kris/prop_lab/core/feed_collector.py --once >> /home/kris/prop_lab/data/feeds/collector.log 2>&1
"""
from __future__ import annotations

import sys, time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
FEEDS = ROOT / "data" / "feeds"
FEEDS.mkdir(parents=True, exist_ok=True)

SYMBOLS = ("BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT")
PERIOD = "5m"
SLEEP = 600          # 10 minutes between passes; the endpoint gives 5m buckets


def _ex():
    import ccxt
    return ccxt.binanceusdm({"enableRateLimit": True})


def _append(path: Path, new: pd.DataFrame) -> int:
    if new.empty:
        return 0
    if path.exists():
        old = pd.read_parquet(path)
        both = pd.concat([old, new])
    else:
        both = new
    both = both[~both.index.duplicated(keep="last")].sort_index()
    before = 0 if not path.exists() else len(pd.read_parquet(path))
    both.to_parquet(path)
    return len(both) - before


def collect_once(ex) -> dict:
    got = {}
    for sym in SYMBOLS:
        tag = sym.split("/")[0]
        try:
            oi = ex.fetch_open_interest_history(sym, PERIOD, limit=500)
            d = pd.DataFrame([{
                "ts": x["timestamp"],
                "oi_base": x.get("openInterestAmount"),
                "oi_quote": x.get("openInterestValue"),
            } for x in oi]).dropna(subset=["ts"])
            d.index = pd.to_datetime(d.ts, unit="ms", utc=True)
            got[f"{tag}_oi"] = _append(FEEDS / f"{tag}_oi_{PERIOD}.parquet",
                                       d.drop(columns=["ts"]))
        except Exception as e:
            got[f"{tag}_oi"] = f"ERR {type(e).__name__}"

        # taker buy/sell volume ratio - the aggressor imbalance
        try:
            raw = ex.fapiDataGetTakerlongshortRatio({
                "symbol": tag + "USDT", "period": PERIOD, "limit": 500})
            d = pd.DataFrame([{
                "ts": int(x["timestamp"]),
                "taker_ratio": float(x["buySellRatio"]),
                "buy_vol": float(x["buyVol"]),
                "sell_vol": float(x["sellVol"]),
            } for x in raw])
            d.index = pd.to_datetime(d.ts, unit="ms", utc=True)
            got[f"{tag}_taker"] = _append(FEEDS / f"{tag}_taker_{PERIOD}.parquet",
                                          d.drop(columns=["ts"]))
        except Exception as e:
            got[f"{tag}_taker"] = f"ERR {type(e).__name__}"
    return got


def main():
    once = "--once" in sys.argv
    ex = _ex()
    while True:
        stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        got = collect_once(ex)
        print(f"{stamp}  " + "  ".join(f"{k}+{v}" for k, v in got.items()), flush=True)
        if once:
            return
        time.sleep(SLEEP)


if __name__ == "__main__":
    main()
