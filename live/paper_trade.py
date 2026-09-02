"""Paper-trade the current H-002 book: emit today's signals, execute nothing.

Reads the configuration each walk-forward fold actually chose, rebuilds the same
features from live data, and writes any signal to a log. It deliberately places
no orders - the point is to compare live signals against the backtest before a
cent is at risk.

BLOCKER, stated up front: one of the five legs is XAUUSD, and this box has no
working MT5 bridge (the pip package is Windows-only; ~/.mt5 is a wine install
needing an mt5linux-style shim). The gold leg therefore runs in SIGNAL-ONLY mode
off the cached Dukascopy data, which is not live. The four crypto legs (BTC, ETH
x2, SOL) are on a live Binance feed. Since the firm choice is cTrader, the route
out is a cTrader connector rather than an MT5 bridge - it carries gold too.

Run:  .venv/bin/python live/paper_trade.py            one pass
      .venv/bin/python live/paper_trade.py --loop     every 5 minutes
"""
from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from strategies.vwap.sweep import features, run_one          # noqa: E402
from strategies.vwap.stage3_timeframes import TFS            # noqa: E402
# The twelve-market universe, not stage 1's ten: the board's book contains
# ETHUSDT and SOLUSDT, which stage 1 never priced. COSTS is stage 1's ASSETS
# plus those, so importing it is what keeps the paper trader on the same costs
# the walk-forward used.
from strategies.vwap.stage10_universe import COSTS, CRYPTO   # noqa: E402

OUT = ROOT / "live" / "paper"
OUT.mkdir(parents=True, exist_ok=True)
BOARD = ROOT / "backtests" / "vwap" / "board.json"
CFGKEY = ["anchor_hour", "anchor_minute", "mode", "fill_mode", "band_k", "stop_mode",
          "stop_k", "target_mode", "rr", "max_hold_bars", "min_rvol",
          "min_atr_rank", "max_atr_rank", "warmup_bars", "min_risk_bps"]


def current_legs() -> list[dict]:
    """The book on the board, with the config its most recent fold chose."""
    b = json.loads(BOARD.read_text())
    legs = [tuple(x.split()) for x in b["candidate"].split(", equal")[0].split(" + ")]
    folds = None
    # stage 10 first: it is the walk-forward the board's five-leg book comes
    # from. Stage 9 was the four-leg BTC+XAU book and has no ETH or SOL folds,
    # so reading it silently dropped three of five legs.
    for name in ("stage10_folds.parquet", "stage9_folds_2xselect.parquet",
                 "stage6_folds.parquet"):
        p = ROOT / "backtests" / "vwap" / name
        if p.exists():
            folds = pd.read_parquet(p)
            break
    if folds is None:
        sys.exit("no fold file - run the walk-forward first")
    out = []
    for sym, tf in legs:
        g = folds[(folds.symbol == sym) & (folds.tf == tf)]
        if "floor" in g:
            g = g[(g.floor == 100) & (g.topn == 1)]
        if g.empty:
            print(f"  !! no fold config for {sym} {tf}")
            continue
        last = g.sort_values("quarter").iloc[-1]
        cfg = {k: last[k] for k in CFGKEY if k in last}
        out.append({"symbol": sym, "tf": tf, "cfg": cfg,
                    "chosen_in": str(last.quarter),
                    "live": sym in CRYPTO})
    return out


def load_live(sym: str, tf: str) -> pd.DataFrame:
    """Crypto comes from the exchange. Gold has no live feed on this box."""
    if sym in CRYPTO:
        import ccxt
        ex = ccxt.binance({"enableRateLimit": True})
        rule = {"5m": "5m", "15m": "15m", "30m": "30m", "1h": "1h", "4h": "4h"}[tf]
        o = ex.fetch_ohlcv(CRYPTO[sym], rule, limit=1000)
        d = pd.DataFrame(o, columns=["ts", "open", "high", "low", "close", "volume"])
        d.index = pd.to_datetime(d.ts, unit="ms", utc=True)
        return d[["open", "high", "low", "close", "volume"]]
    from core import fx_data
    return fx_data.load(sym, TFS[tf][0]).tail(4000)      # cached, NOT live


def scan(leg: dict) -> dict | None:
    sym, tf, cfg = leg["symbol"], leg["tf"], dict(leg["cfg"])
    df = load_live(sym, tf)
    if len(df) < 300:
        return None
    fee, slip, minrisk = COSTS[sym]
    cfg.setdefault("min_risk_bps", minrisk)
    cfg.setdefault("one_trade", 0)
    cfg.setdefault("dir_mode", 0)
    feats = features(df)
    tr = run_one(df, feats, {}, cfg, fee, slip)
    if not len(tr):
        return None
    last = tr[-1]
    entry_i, exit_i = int(last[0]), int(last[1])
    # a signal counts as live only if it opened on one of the final few bars
    fresh = entry_i >= len(df) - 3
    return {
        "symbol": sym, "tf": tf, "live_feed": leg["live"],
        "config_chosen_in": leg["chosen_in"],
        "last_signal_entry": str(df.index[entry_i]),
        "last_signal_exit": str(df.index[exit_i]),
        "direction": "long" if last[2] > 0 else "short",
        "entry_px": round(float(last[3]), 2),
        "r_multiple": round(float(last[5]), 3),
        "fresh": bool(fresh),
        "bar_time": str(df.index[-1]),
    }


def main():
    loop = "--loop" in sys.argv
    legs = current_legs()
    print(f"book: {len(legs)} legs, "
          f"{sum(1 for l in legs if l['live'])} on a live feed")
    while True:
        stamp = datetime.now(timezone.utc).isoformat()
        rows = []
        for leg in legs:
            try:
                s = scan(leg)
            except Exception as e:
                s = {"symbol": leg["symbol"], "tf": leg["tf"],
                     "error": f"{type(e).__name__}: {e}"}
            if s:
                s["scanned_at"] = stamp
                rows.append(s)
                mark = "NEW" if s.get("fresh") else "   "
                feed = "live" if s.get("live_feed") else "CACHED"
                print(f"  {mark} {s['symbol']:8s} {s['tf']:4s} [{feed:6s}] "
                      f"{s.get('direction','-'):5s} last entry {s.get('last_signal_entry','-')}"
                      f"  R {s.get('r_multiple','-')}")
        if rows:
            p = OUT / "signals.jsonl"
            with p.open("a") as f:
                for r in rows:
                    f.write(json.dumps(r) + "\n")
        if not loop:
            return
        time.sleep(300)


if __name__ == "__main__":
    main()
