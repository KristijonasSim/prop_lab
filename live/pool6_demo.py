"""THE GOLD POOL ON BYBIT DEMO - six step-8 rules, one account, two risk sizes.

Kris, 2026-10-09: *"launch a test demo ... those 2 versions of 0.75 and 2%
risk on bybit"*. He chose ONE demo account trading 0.75% for real, with the 2%
version CALCULATED from the very same fills (same signals, same exits - only
the size differs, so the R of every trade is identical and the 2% account is
that R times 2%).

THE FOUR LEGS (24h cap, all long XAUUSDT), RE-PICKED 2026-10-09 AFTER THE
CLOCK FIX (`scripts/build_5y.py` had every FX/metals bar 23h late; the first
six-leg pool was chosen on that data and four of its legs did not survive):
    B3M trend pullback (4h) and Descending trendline breakout (4h) - the two
    step-8 survivors on the corrected data - plus Kris's pair from the 0.5-tpd
    hunt, EMA8 pullback (1h) and DEMA ATR turn-up (1h), both still REAL.
Measured on 3 years of corrected Dukascopy gold, PF 1.70, 1.68 trades/day:
    0.75% -> 59.5% pass (51-67), 16.8 expected days (15-22), median 10, 1.68 accounts
    2%    -> 42.6% pass (38-47),  7.0 expected days (6-8),   median 3,  2.35 accounts
    older years: 25% / 22% pass - the gold-trend caveat stands.

HOW A PASS WORKS (cron every 5 minutes, `live/pool6_cron.sh`):
  * ENTRIES only when a leg's own timeframe has closed a NEW bar. Each leg's
    rule is evaluated through `factory/build.series` - the exact code the
    backtest used - on Bybit's own bars. Fire on the closed bar -> market buy
    now (the backtest fills at the next bar's open). Stop and target from the
    ATR at the decision bar, as in `build.run`.
  * EXITS every pass, from Bybit 1-minute bars since the last pass: low <= stop
    -> out, high >= target -> out, time window over -> out. Bot-enforced,
    reduce-only market orders, because Bybit NETS all legs into one position.
  * A native BACKSTOP stop on the net position at the LOWEST open leg stop, so
    a dead machine cannot leave the account unprotected.
  * One position per leg, no pyramiding (`build.run` rule).

THE TWO EVALUATIONS (`virtual` in the state file), HOUSE 8% / 3% / 6%:
  Every leg's R is booked into a running ledger, open trades marked to market
  each pass. For each risk size an attempt measures equity = R since its start
  x risk: >= +8% PASS; daily drop >= 3% or >= 6% below start or below peak
  FAIL. A finished attempt is logged and a new one starts at once. MARKED TO
  MARKET, which is how a firm counts and is STRICTER than the backtest's
  closed-trade days (H-039) - expect the live pass rate to read lower.

SAFETY: dry run by default; `--arm` places orders and refuses any host but
Bybit's demo. Keys in ~/.config/prop_lab/bybit_demo.env, never in the repo.

    .venv/bin/python live/pool6_demo.py             # dry run
    .venv/bin/python live/pool6_demo.py --arm       # trade the demo
    .venv/bin/python live/pool6_demo.py --status    # the two evaluations
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from factory import build                                             # noqa: E402

_spec = importlib.util.spec_from_file_location("bybit_demo", ROOT / "live" / "bybit_demo.py")
B = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(B)
#: A FRESH demo account for this test (Kris, 2026-10-09), its own key file, so
#: the old H-027 account and its leftover short are never touched.
B.ENV = Path.home() / ".config" / "prop_lab" / "bybit_pool_demo.env"

STATE = ROOT / "live" / "paper" / "pool6_state.json"
TRADES = ROOT / "live" / "paper" / "pool6_trades.jsonl"
ATTEMPTS = ROOT / "live" / "paper" / "pool6_attempts.jsonl"
LEGS_JSON = ROOT / "live" / "pool6_legs.json"
SYMBOL = "XAUUSDT"
REAL_RISK = 0.0075
VERSIONS = (0.0075, 0.02)
TARGET, DAILY, MAXLOSS = 0.08, 0.03, 0.06
FEE_RT_BPS = 5.5          # measured on this account, 2026-09 (NEXT.md)
HOURS = {"1h": 1, "4h": 4}
QTY_STEP = 0.001


def now() -> datetime:
    return datetime.now(timezone.utc)


# --------------------------------------------------------------------------- #
# the legs, frozen to a file so a restart trades exactly what was launched
# --------------------------------------------------------------------------- #
def freeze_legs() -> list[dict]:
    from factory import bestpool      # research-only import; the VM never needs it
    keep = ("B3M trend pullback", "Descending trendline", "5m EMA8 pullback", "DEMA ATR")
    out = []
    for l in bestpool.legs():
        if l["market"] == "XAUUSD" and l["name"].startswith(keep):
            out.append({"name": l["name"], "tf": l["tf"], "rule": l["rule"].label(),
                        "stop_atr": l["rule"].stop_atr, "target_atr": l["rule"].target_atr,
                        "max_hold": l["rule"].max_hold})
    assert len(out) == len(keep), [x["name"] for x in out]
    LEGS_JSON.write_text(json.dumps(out, indent=1))
    return out


def legs() -> list[dict]:
    from factory.rescore import from_record
    xs = json.loads(LEGS_JSON.read_text()) if LEGS_JSON.exists() else freeze_legs()
    for x in xs:
        x["strategy"] = from_record({"name": x["name"], "idea": x["rule"],
                                     "stop_atr": x["stop_atr"], "target_atr": x["target_atr"],
                                     "max_hold": x["max_hold"]})
    return xs


# --------------------------------------------------------------------------- #
# data
# --------------------------------------------------------------------------- #
def klines(interval: str, pages: int = 1, start_ms: int | None = None) -> pd.DataFrame:
    rows, end = [], None
    for _ in range(pages):
        p = {"category": "linear", "symbol": SYMBOL, "interval": interval, "limit": 1000}
        if end:
            p["end"] = end
        if start_ms:
            p["start"] = start_ms
        r = B.public("/v5/market/kline", p)
        if r.get("retCode") != 0:
            raise RuntimeError(f"kline: {r.get('retMsg')}")
        got = r["result"]["list"]
        if not got:
            break
        rows += got
        end = int(got[-1][0]) - 1
        if len(got) < 1000 or start_ms:
            break
    df = pd.DataFrame(rows, columns=["ts", "open", "high", "low", "close", "volume", "to"]).astype(float)
    df["ts"] = pd.to_datetime(df.ts.astype("int64"), unit="ms", utc=True)
    return df.drop_duplicates("ts").set_index("ts").sort_index()[["open", "high", "low", "close", "volume"]]


def frames() -> dict[str, pd.DataFrame]:
    """CLOSED 1h and 4h bars. The forming bar is dropped; a 4h bar counts only
    once all four of its hours have closed (Dukascopy's 4h grid, 00:00 UTC)."""
    h = klines("60", pages=5)
    h = h[h.index <= pd.Timestamp(now()) - pd.Timedelta(hours=1)]
    f4 = h.resample("4h", label="left", closed="left").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}).dropna()
    f4 = f4[f4.index <= h.index[-1] - pd.Timedelta(hours=3)]
    out = {}
    for tf, f in (("1h", h), ("4h", f4)):
        f = f.copy()
        f["hour"] = f.index.hour.astype(float)
        out[tf] = f
    return out


def last_price() -> float:
    r = B.public("/v5/market/tickers", {"category": "linear", "symbol": SYMBOL})
    return float(r["result"]["list"][0]["lastPrice"])


# --------------------------------------------------------------------------- #
# state
# --------------------------------------------------------------------------- #
def load() -> dict:
    if STATE.exists():
        return json.loads(STATE.read_text())
    return {"started": None, "base_equity": None, "legs": {}, "closed_r": 0.0,
            "last_exit_check": None, "virtual": {}}


def save(s: dict) -> None:
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(s, indent=1, default=str))


def append(path: Path, row: dict) -> None:
    with path.open("a") as fh:
        fh.write(json.dumps(row, default=str) + "\n")


def r_of(leg: dict, px: float) -> float:
    cost = leg["entry_px"] * FEE_RT_BPS / 1e4
    return (px - leg["entry_px"] - cost) / leg["risk_px"]


# --------------------------------------------------------------------------- #
# the two evaluations
# --------------------------------------------------------------------------- #
def evaluate(s: dict, total_r: float, t: datetime) -> list[str]:
    msgs = []
    day = t.strftime("%Y-%m-%d")
    for v in VERSIONS:
        k = f"{v*100:g}%"
        a = s["virtual"].get(k)
        if a is None or a.get("done"):
            n = (a or {}).get("attempt", 0) + 1
            a = {"attempt": n, "start": str(t), "r0": total_r, "peak": 0.0,
                 "day": day, "day_r0": total_r, "done": False}
        if a["day"] != day:
            a["day"], a["day_r0"] = day, total_r
        eq = (total_r - a["r0"]) * v
        a["peak"] = max(a["peak"], eq)
        today = (total_r - a["day_r0"]) * v
        out = None
        if eq >= TARGET:
            out = "PASS"
        elif today <= -DAILY:
            out = "FAIL_DAILY"
        elif eq <= -MAXLOSS or eq - a["peak"] <= -MAXLOSS:
            out = "FAIL_MAX"
        a["equity_pct"], a["today_pct"] = round(eq * 100, 2), round(today * 100, 2)
        if out:
            a["done"], a["outcome"], a["end"] = True, out, str(t)
            a["days"] = round((t - datetime.fromisoformat(a["start"])).total_seconds() / 86400, 2)
            append(ATTEMPTS, {"version": k, **a})
            msgs.append(f"{k} attempt {a['attempt']}: {out} after {a['days']} days")
        s["virtual"][k] = a
    return msgs


# --------------------------------------------------------------------------- #
def once(arm: bool) -> None:
    global STATE, TRADES, ATTEMPTS
    host = B.DEMO_HOST
    if arm and host != B.DEMO_HOST:
        sys.exit("refusing: --arm only runs against the demo host")
    if not arm:   # a dry run never touches the armed book's files
        STATE, TRADES, ATTEMPTS = (p.with_name("dry_" + p.name) for p in (STATE, TRADES, ATTEMPTS))
    s = load()
    fresh = s["started"] is None
    t = now()
    eq = B.equity(host)
    if s["started"] is None:
        s["started"], s["base_equity"] = str(t), eq
    risk_usd = REAL_RISK * s["base_equity"]
    L = legs()
    px = last_price()
    print(f"{t:%Y-%m-%d %H:%M} UTC  {'ARMED' if arm else 'dry run'}  equity ${eq:,.2f}  "
          f"XAUUSDT {px:.2f}  risk/trade ${risk_usd:,.2f}")

    # ---- exits, from 1m bars since the last check --------------------------
    since = s.get("last_exit_check")
    m1 = klines("1", start_ms=int(pd.Timestamp(since).timestamp() * 1000)) if since else None
    for x in L:
        leg = s["legs"].get(x["name"], {}).get("open")
        if not leg:
            continue
        seen = m1[m1.index >= pd.Timestamp(leg["entry_time"])] if m1 is not None else None
        why = None
        if seen is not None and len(seen):
            if seen.low.min() <= leg["stop"]:
                why = "stop"
            elif seen.high.max() >= leg["target"]:
                why = "target"
        if why is None and t >= pd.Timestamp(leg["exit_due"]):
            why = "time"
        if not why:
            continue
        if arm:
            r = B.signed(host, "/v5/order/create", {
                "category": "linear", "symbol": SYMBOL, "side": "Sell", "orderType": "Market",
                "qty": f"{leg['qty']:.3f}", "timeInForce": "IOC", "reduceOnly": True,
                "orderLinkId": f"p6x-{int(time.time()*1000) % 10**9}"}, post=True)
            if r.get("retCode") != 0:
                print(f"  EXIT REFUSED {x['name'][:30]}: {r.get('retMsg')}")
                continue
        fill = last_price()
        R = r_of(leg, fill)
        s["closed_r"] += R
        append(TRADES, {"leg": x["name"], **leg, "exit_time": str(now()), "exit_px": fill,
                        "why": why, "r": round(R, 3), "armed": arm})
        print(f"  EXIT  {x['name'][:34]:34} {why:6} {leg['entry_px']:.2f} -> {fill:.2f}  {R:+.2f}R")
        s["legs"][x["name"]]["open"] = None

    # ---- entries, on a NEW closed bar of each leg's timeframe ---------------
    fr = frames()
    for x in L:
        tf = x["tf"]
        f = fr[tf]
        bar = str(f.index[-1])
        st = s["legs"].setdefault(x["name"], {"open": None, "last_bar": None})
        if st["last_bar"] == bar:
            continue
        st["last_bar"] = bar
        if fresh:   # the first pass only learns where the bars are - no stale entries
            continue
        if st["open"]:
            continue
        fire, atr = build.series(x["strategy"], f.reset_index(drop=True))
        if not fire[-1] or not np.isfinite(atr[-1]) or atr[-1] <= 0:
            continue
        entry = last_price()
        risk_px = x["stop_atr"] * atr[-1]
        if risk_px < 2.0 * entry * FEE_RT_BPS / 1e4:
            print(f"  skip  {x['name'][:34]} stop narrower than cost")
            continue
        qty = max(QTY_STEP, round(risk_usd / risk_px / QTY_STEP) * QTY_STEP)
        if arm:
            r = B.signed(host, "/v5/order/create", {
                "category": "linear", "symbol": SYMBOL, "side": "Buy", "orderType": "Market",
                "qty": f"{qty:.3f}", "timeInForce": "IOC",
                "orderLinkId": f"p6e-{int(time.time()*1000) % 10**9}"}, post=True)
            if r.get("retCode") != 0:
                print(f"  ENTRY REFUSED {x['name'][:30]}: {r.get('retMsg')}")
                continue
            entry = last_price()
        due = pd.Timestamp(bar) + pd.Timedelta(hours=HOURS[tf] * (1 + x["max_hold"]))
        st["open"] = {"entry_time": str(now()), "decision_bar": bar, "entry_px": entry,
                      "qty": qty, "risk_px": float(risk_px),
                      "stop": float(entry - risk_px),
                      "target": float(entry + x["target_atr"] * atr[-1]),
                      "exit_due": str(due)}
        print(f"  ENTRY {x['name'][:34]:34} {tf} qty {qty:.3f} @ {entry:.2f}  "
              f"stop {entry - risk_px:.2f}  target {entry + x['target_atr']*atr[-1]:.2f}  until {due:%m-%d %H:%M}")

    # ---- backstop, reconcile, evaluations ----------------------------------
    open_legs = [v["open"] for v in s["legs"].values() if v.get("open")]
    want = round(sum(o["qty"] for o in open_legs), 3)
    if arm:
        held = sum(float(p["size"]) * (1 if p["side"] == "Buy" else -1) for p in B.positions(host))
        if abs(held - want) > 1e-6:
            print(f"  MISMATCH: exchange holds {held:+.3f} XAU, legs say {want:+.3f}")
        if open_legs:
            r = B.set_backstop(host, min(o["stop"] for o in open_legs))
            if r and r.get("retCode") not in (0, 34040):
                print(f"  BACKSTOP REFUSED: {r.get('retMsg')}")
    open_r = sum(r_of(o, px) for o in open_legs)
    total = s["closed_r"] + open_r
    for m in evaluate(s, total, t):
        print("  " + m)
    s["last_exit_check"] = str(t)
    save(s)
    v = s["virtual"]
    print(f"  book: {len(open_legs)} open, {want:.3f} XAU, closed {s['closed_r']:+.2f}R, open {open_r:+.2f}R | "
          + " | ".join(f"{k} #{a['attempt']} {a['equity_pct']:+.2f}% (today {a['today_pct']:+.2f}%)"
                       for k, a in v.items()))


def status() -> None:
    s = load()
    print(json.dumps({k: s.get(k) for k in ("started", "base_equity", "closed_r", "virtual")},
                     indent=1, default=str))
    if ATTEMPTS.exists():
        rows = [json.loads(l) for l in ATTEMPTS.read_text().splitlines() if l.strip()]
        for v in VERSIONS:
            k = f"{v*100:g}%"
            mine = [r for r in rows if r["version"] == k]
            p = [r for r in mine if r["outcome"] == "PASS"]
            print(f"{k}: {len(mine)} finished, {len(p)} passed"
                  + (f", median {np.median([r['days'] for r in p]):.1f} days" if p else ""))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--arm", action="store_true")
    ap.add_argument("--status", action="store_true")
    a = ap.parse_args()
    if a.status:
        status()
    else:
        once(a.arm)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
