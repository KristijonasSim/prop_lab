"""Paper-trade H-027 — today's gold signals, the stop, and the size. No orders.

Kris, 2026-09-10: *"launch it on demo"*. This is the demo runner for the strategy
frozen in `core/chosen.py`: XAUUSD 1h, five settings in parallel, wide stop, no
target, 384-hour horizon, sized against the remaining drawdown budget.

WHAT IT DOES. Rebuilds the kernel's own features from the same bars the backtest
used, walks the five settings over the most recent closed bar, and writes any
signal to `live/paper/vwapbreak_signals.jsonl` with everything an order ticket
needs: side, the entry it would fill at (next bar's open), the stop level, the
risk in price and in account percent, and the horizon.

**IT PLACES NO ORDERS.** The point is to compare live signals against the
backtest before a cent is at risk, exactly as `live/paper_trade.py` does for the
older book.

THE BLOCKER, STATED UP FRONT AND UNCHANGED SINCE 2026-09-07. This box has no live
gold feed. The MetaTrader5 pip package is Windows-only, `~/.mt5` is a wine install
needing an `mt5linux`-style shim, and no cTrader connector is written yet. So this
runs off the DUKASCOPY CACHE, which ends whenever the cache was last refreshed -
it is a signal generator and a dry run of the sizing arithmetic, **not a live
feed**. The route out is a cTrader connector, because the chosen firms are on
cTrader and it carries gold; that is the one piece of plumbing between here and a
real demo account.

THE SIZING RULE, adopted 2026-09-10 (`core/chosen.py["sizing"]`):

    mult = clip((max_loss + drawdown) / max_loss, 0.25, 1.0)
    risk on this trade = risk_pct x mult

`drawdown` is the account's distance below its high-water mark, so at a new high
the multiplier is 1.0 and nothing changes. Pass `--equity` and `--peak` to see the
size the rule gives for a real account state.

Run:  .venv/bin/python live/vwapbreak_paper.py
      .venv/bin/python live/vwapbreak_paper.py --equity 100000 --peak 102000
      .venv/bin/python live/vwapbreak_paper.py --loop        every 5 minutes
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.chosen import CHOSEN, SETTINGS                       # noqa: E402
from core.markets import COSTS, EXEC_MODE, TF_BPH, load        # noqa: E402
from core.prop_rules import THUNDERBOLT                        # noqa: E402
from strategies.vwapbreak.strategy import STRATEGY             # noqa: E402

OUT = ROOT / "live" / "paper"
OUT.mkdir(parents=True, exist_ok=True)
LOG = OUT / "vwapbreak_signals.jsonl"

SYM, TF = CHOSEN["market"], CHOSEN["tf"]


def size_multiplier(equity: float, peak: float, max_loss: float) -> float:
    """The adopted budget-linear rule. 1.0 at a new high, floored at 0.25."""
    if peak <= 0:
        return 1.0
    dd = min((equity - peak) / peak, 0.0)
    return float(np.clip((max_loss + dd) / max_loss, CHOSEN["sizing"]["floor_mult"], 1.0))


def signals_on_last_bar(df: pd.DataFrame) -> list[dict]:
    """Every setting that fires on the most recently CLOSED bar.

    The kernel decides on bar i and fills at the open of bar i+1, so the last bar
    of the frame is the decision bar and the fill has not happened yet. That is
    why the entry price below is a level to work, not a price already got.
    """
    f = STRATEGY.features(df)
    z, sd, live = f["z"], f["sd"], f["live"]
    rvol, hour = f["rvol"], f["hour"]
    i = len(df) - 1
    out = []
    if not (np.isfinite(z[i]) and live[i]):
        return out
    for n, cfg in enumerate(SETTINGS, 1):
        thr = float(cfg["thr"])
        side = 1 if z[i] >= thr else (-1 if z[i] <= -thr else 0)
        if side == 0:
            continue
        h_lo, h_hi = int(cfg["hour_lo"]), int(cfg["hour_hi"])
        if h_lo != h_hi:
            hh = int(hour[i])
            inside = (h_lo <= hh < h_hi) if h_lo < h_hi else (hh >= h_lo or hh < h_hi)
            if not inside:
                continue
        if float(cfg["min_rvol"]) > 0.0 and rvol[i] < float(cfg["min_rvol"]):
            continue
        px = float(df.close.values[i])
        risk = float(cfg["stop_sig"]) * float(sd[i])
        risk = max(risk, px * COSTS[SYM].min_risk_bps / 1e4)
        out.append({
            "setting": n, "side": "long" if side > 0 else "short",
            "z": round(float(z[i]), 3), "thr": thr,
            "stop_sig": float(cfg["stop_sig"]),
            "signal_bar": str(df.index[i]),
            "signal_close": round(px, 3),
            "entry": "next bar open",
            "stop_px": round(px - side * risk, 3),
            "risk_px": round(risk, 3),
            "risk_bps": round(risk / px * 1e4, 1),
            "max_hold_bars": int(cfg["max_hold"]),
            "max_hold_hours": round(int(cfg["max_hold"]) / TF_BPH[TF], 1),
            # A THIN-SESSION WARNING, not a filter. The band sigma is the
            # dispersion of price about the session VWAP SINCE THE ANCHOR, so a
            # session that has barely traded - the Sunday re-open, a holiday -
            # has a tiny sigma, a huge z, and a stop of a few basis points. The
            # backtest takes those trades and they are in every number on the
            # board, so this does not refuse them; it flags them, because the
            # first live signals are worth looking at by eye before they are
            # worth trusting. Gold's median stop at 2.5 sigma is 46bps.
            "thin_session": bool(risk / px * 1e4 < 15.0),
        })
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--equity", type=float, default=100_000.0)
    ap.add_argument("--peak", type=float, default=None,
                    help="account high-water mark; defaults to equity")
    ap.add_argument("--loop", action="store_true")
    # THE BRIDGE TO A REAL DEMO ACCOUNT, and the reason it is a file rather than
    # an API call. No cTrader or MT5 connector can be written or tested from this
    # box: there is no network to install a client library and no credentials to
    # authenticate with. What CAN be done is to make the bar source pluggable, so
    # the moment a broker export exists - any parquet or CSV with
    # open/high/low/close/volume on a UTC index - this runner produces signals
    # against the broker's own prices rather than against Dukascopy's cache.
    ap.add_argument("--bars", type=str, default=None,
                    help="parquet or CSV of broker bars; defaults to the cache")
    a = ap.parse_args()
    peak = a.peak if a.peak is not None else a.equity

    def bars() -> pd.DataFrame:
        if not a.bars:
            return load(SYM, TF)
        p = Path(a.bars)
        df = (pd.read_parquet(p) if p.suffix == ".parquet"
              else pd.read_csv(p, index_col=0, parse_dates=True))
        df = df.sort_index()
        if df.index.tz is None:
            df.index = df.index.tz_localize("UTC")
        missing = {"open", "high", "low", "close", "volume"} - set(df.columns)
        if missing:
            sys.exit(f"{p} is missing columns: {sorted(missing)}")
        return df

    while True:
        df = bars()
        stale = (pd.Timestamp.now(tz="UTC") - df.index[-1]).total_seconds() / 3600
        mult = size_multiplier(a.equity, peak, THUNDERBOLT.max_loss)
        risk_pct = CHOSEN["risk_each_pct"] / 100.0 * mult

        src = a.bars or "dukascopy cache"
        print(f"{datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC  {SYM} {TF}  "
              f"[{src}]")
        print(f"  last bar {df.index[-1]}  ({stale:.1f}h old"
              f"{'  <-- CACHE, NOT A LIVE FEED' if stale > 2 else ''})")
        print(f"  equity {a.equity:,.0f}  peak {peak:,.0f}  "
              f"drawdown {(a.equity - peak) / peak * 100:+.2f}%  "
              f"size multiplier {mult:.2f}")
        print(f"  risk per setting {risk_pct * 100:.3f}% of account "
              f"({CHOSEN['risk_each_pct']:.2f}% x {mult:.2f}), five settings")

        sigs = signals_on_last_bar(df)
        if not sigs:
            print("  no signal on the last closed bar")
        for s in sigs:
            qty = a.equity * risk_pct / s["risk_px"]
            s.update({"account_risk_pct": round(risk_pct * 100, 4),
                      "size_multiplier": round(mult, 3),
                      "units": round(qty, 4), "equity": a.equity,
                      "written_at": datetime.now(timezone.utc).isoformat()})
            print(f"  SIGNAL setting {s['setting']}: {s['side'].upper():5} "
                  f"z={s['z']:+.2f}  stop {s['stop_px']}  "
                  f"risk {s['risk_bps']}bps  {qty:.3f} units  "
                  f"hold <= {s['max_hold_hours']:.0f}h"
                  + ("   [THIN SESSION - check by eye]" if s["thin_session"] else ""))
            with LOG.open("a") as fh:
                fh.write(json.dumps(s) + "\n")
        if sigs:
            print(f"  wrote {len(sigs)} signal(s) to {LOG.relative_to(ROOT)}")
        if not a.loop:
            return 0
        time.sleep(300)


if __name__ == "__main__":
    raise SystemExit(main())
