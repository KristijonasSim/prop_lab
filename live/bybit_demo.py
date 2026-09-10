"""H-027 on Bybit's XAUUSDT perpetual — demo account, both signals, real orders.

Kris, 2026-09-10, having found gold on Bybit and opened a demo account. This is
the first thing in this project that can place an order without a human.

WHY BYBIT AND NOT THE PROP FIRMS' PLATFORM. The two eligible firms are on MT5 and
cTrader; the MetaTrader package is Windows-only and this box is Linux, and no
cTrader connector exists. Bybit's XAUUSDT is a **TradFi perpetual on the gold
index** (not a token: XAUT and PAXG are the tokens, this is not one), it has a v5
REST API with a demo endpoint, and NautilusTrader ships an adapter for it. It is
the only route from a signal to a filled order that this machine can actually
take today.

WHAT WAS MEASURED BEFORE WRITING THIS, on 2026-09-10:

    top-of-book spread          0.02 bps
    impact at 0.4% risk sizing  1.1 bps one-way (20 XAU, ~$88k)
    book depth                  314 / 331 XAU, about $1.4M a side
    tracking vs our gold cache  return correlation 0.9735, vol 24.2 vs 24.5 bps
    funding, long, median hold  +0.7 bps (positive on only 22% of stamps)
    all-in round trip           ~8-14 bps typical, ~22-28 bps on a long held out
                                to the fortnight horizon

Against the cost tolerance measured the same day - gold keeps profit factor 2.361
and 53.9% pass at 10.65bps round trip - the typical trade fits and the long tail
does not. That is a real caveat, not a footnote: a long held to the horizon pays
about a third of a stop in funding.

TWO THINGS THIS CANNOT PAPER OVER

  * **185 days of history.** XAUUSDT listed 2026-03-09, so there is no
    walk-forward on Bybit's own bars. The rule was validated on eleven years of
    Dukascopy gold and is being run on a correlated instrument. Defensible;
    not the same thing.
  * **Bybit trades weekends and Dukascopy does not.** 28.1% of bars are weekend,
    carrying 9.2% of the turnover, with a median range of 6.8bps against 35.1 on
    weekdays. The band sigma is a session quantity, so a Saturday builds a tiny
    sigma and a huge z out of nothing. **Weekend bars are skipped by default**
    (`--weekends` to allow them) because the backtest never saw one.

SAFETY, and it is the reason this file is long

  * The key lives in ~/.config/prop_lab/bybit_demo.env, outside the repo, and is
    read from there. Nothing here is committed with a secret in it.
  * **DRY RUN IS THE DEFAULT.** It prints the orders it would send and sends
    nothing. `--arm` is required to place an order, and `--arm` refuses to run
    against anything but the demo host.
  * The demo host is pinned. The key was tested against the live endpoint and is
    rejected there, which is the correct kind of key to hand a bot.
  * A native stop sits on the net position at the widest live leg's level, so a
    disconnect cannot leave the account unprotected. The per-leg stops are
    enforced by this bot - see the netting note below.
  * One position per setting, held in `live/paper/bybit_state.json`, so a restart
    does not double up.

TWO THINGS THE FIRST DRY RUN EXPOSED, both fixed here rather than explained away

  1. **Bybit nets.** The account is in one-way mode (`positionIdx 0`), so six
     orders on XAUUSDT do not become six positions with six stops - they become
     ONE position, and the last order's stopLoss overwrites the rest. The five
     settings and the Asian leg are therefore kept as a LOCAL leg book: each run
     nets the legs into a single market order, exits legs individually with
     reduce-only orders when their own stop or horizon says so, and leaves a
     native stop on the exchange at the WIDEST live leg's level as a
     disconnect backstop - not as the strategy's stop.
  2. **The risk budget was 2.4%, not 2%.** Sizing every leg at the shipped
     `risk_each_pct` gave five VWAP settings plus the Asian leg all at 0.4%. The
     book was measured at EQUAL WEIGHT, half the risk to each signal, so that is
     what is used: 1% across the five VWAP settings (0.2% each) and 1% on the
     Asian leg.

Run:  .venv/bin/python live/bybit_demo.py                 dry run, both signals
      .venv/bin/python live/bybit_demo.py --arm           actually place orders
      .venv/bin/python live/bybit_demo.py --loop 300      every 5 minutes
      .venv/bin/python live/bybit_demo.py --symbol XAUTUSDT --arm
"""
from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.chosen import CHOSEN, SETTINGS                       # noqa: E402
from core.prop_rules import THUNDERBOLT                        # noqa: E402
from strategies.vwapbreak.strategy import STRATEGY             # noqa: E402

DEMO_HOST = "https://api-demo.bybit.com"
LIVE_HOST = "https://api.bybit.com"
ENV = Path(os.path.expanduser("~/.config/prop_lab/bybit_demo.env"))
STATE = ROOT / "live" / "paper" / "bybit_state.json"
#: XAUUSDT is the better contract - 0.02bps spread, $130M a day, 0.01bps impact
#: at our size - and it CANNOT BE TRADED ON DEMO. Its Trading Terms agreement has
#: to be accepted first, and Bybit's own agreement endpoint answers demo requests
#: with `10032: Demo trading are not supported`, so the acceptance has to happen
#: on the live account before the demo will take an order.
#:
#: RESOLVED 2026-09-10: Kris accepted the terms on the live account and they
#: CARRIED to demo - XAUUSDT filled and closed on the demo account minutes later.
#: The diagnosis that they could not be accepted from demo was right; the fix was
#: to accept them elsewhere. Note the failure mode when re-testing this: an
#: undersized probe returns 110094 (minimum order value $5), NOT 110123, and the
#: first check here read any non-zero code as "still blocked" and reported the
#: opposite of the truth. Read the code, not the fact that one exists.
#:
#: XAUTUSDT (Tether Gold) needs no agreement and remains the fallback. It costs a
#: little more - 0.23bps spread against 0.02, $31M a day against $130M, 0.11bps
#: impact against 0.01 - and tracks spot gold just as closely (0.9733 against
#: 0.9735). Its weakness is a WANDERING BASIS: over the sample it ran -0.61% to
#: +0.34% against Dukascopy gold, about two stops of slow drift the backtest
#: never saw. That is why XAUUSDT is the default now that it works.
SYMBOL = os.environ.get("BYBIT_SYMBOL", "XAUUSDT")
CATEGORY = "linear"
RECV = "5000"
QTY_STEP = 0.001           # XAU, from the instrument filter
MIN_QTY = 0.001
#: the book of 2026-09-10 is equal weight across the two SIGNALS, half the total
#: risk to each - not equal weight across the six legs.
SIGNAL_SPLIT = 0.5


# --------------------------------------------------------------------------- #
# transport
# --------------------------------------------------------------------------- #
def creds() -> tuple[str, str]:
    if not ENV.exists():
        sys.exit(f"missing {ENV} - put BYBIT_DEMO_KEY and BYBIT_DEMO_SECRET in it")
    env = {}
    for line in ENV.read_text().splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip()
    try:
        return env["BYBIT_DEMO_KEY"], env["BYBIT_DEMO_SECRET"]
    except KeyError as e:
        sys.exit(f"{ENV} has no {e}")


def public(path: str, params: dict) -> dict:
    q = urllib.parse.urlencode(params)
    with urllib.request.urlopen(f"{LIVE_HOST}{path}?{q}", timeout=20) as r:
        return json.load(r)


def signed(host: str, path: str, params: dict | None = None,
           post: bool = False) -> dict:
    key, sec = creds()
    ts = str(int(time.time() * 1000))
    body = json.dumps(params or {}, separators=(",", ":")) if post else ""
    q = "" if post else urllib.parse.urlencode(params or {})
    sig = hmac.new(sec.encode(), (ts + key + RECV + (body or q)).encode(),
                   hashlib.sha256).hexdigest()
    url = f"{host}{path}" + (f"?{q}" if q and not post else "")
    req = urllib.request.Request(
        url, data=body.encode() if post else None,
        headers={"X-BAPI-API-KEY": key, "X-BAPI-TIMESTAMP": ts,
                 "X-BAPI-RECV-WINDOW": RECV, "X-BAPI-SIGN": sig,
                 "Content-Type": "application/json"},
        method="POST" if post else "GET")
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.load(r)


# --------------------------------------------------------------------------- #
# data
# --------------------------------------------------------------------------- #
def bars(interval: str = "60", limit: int = 1000) -> pd.DataFrame:
    """Closed 1h bars. Bybit returns the forming bar first; it is dropped."""
    r = public("/v5/market/kline", {"category": CATEGORY, "symbol": SYMBOL,
                                    "interval": interval, "limit": limit})
    if r.get("retCode") != 0:
        sys.exit(f"kline: {r.get('retMsg')}")
    df = pd.DataFrame(r["result"]["list"],
                      columns=["ts", "open", "high", "low", "close", "volume", "to"])
    df = df.astype(float)
    df["ts"] = pd.to_datetime(df.ts.astype("int64"), unit="ms", utc=True)
    df = df.set_index("ts").sort_index()[["open", "high", "low", "close", "volume"]]
    now = pd.Timestamp.now(tz="UTC").floor("1h")
    return df[df.index < now]              # only bars that have actually closed


def asia_levels(df: pd.DataFrame) -> tuple[float, float]:
    """Today's 00:00-07:00 UTC high and low, or (nan, nan) before it closes."""
    lo_h, hi_h = CHOSEN["second_signal"]["window_utc"]
    last = df.index[-1]
    day = df[df.index.date == last.date()]
    win = day[(day.index.hour >= lo_h) & (day.index.hour < hi_h)]
    if len(win) == 0 or last.hour < hi_h:
        return float("nan"), float("nan")
    return float(win.high.max()), float(win.low.min())


# --------------------------------------------------------------------------- #
# signals
# --------------------------------------------------------------------------- #
def vwap_signals(df: pd.DataFrame, cold: bool = False) -> list[dict]:
    f = STRATEGY.features(df)
    z, sd, rvol, hour = f["z"], f["sd"], f["rvol"], f["hour"]
    i = len(df) - 1
    out = []
    if not np.isfinite(z[i]):
        return out
    for n, cfg in enumerate(SETTINGS, 1):
        thr = float(cfg["thr"])
        side = 1 if z[i] >= thr else (-1 if z[i] <= -thr else 0)
        if side == 0:
            continue
        h_lo, h_hi = int(cfg["hour_lo"]), int(cfg["hour_hi"])
        if h_lo != h_hi:
            hh = int(hour[i])
            if not ((h_lo <= hh < h_hi) if h_lo < h_hi else (hh >= h_lo or hh < h_hi)):
                continue
        if float(cfg["min_rvol"]) > 0.0 and rvol[i] < float(cfg["min_rvol"]):
            continue
        # COLD START. A backtest runs continuously, so it takes a break on the
        # FIRST bar that clears the threshold. A bot started in the middle of a
        # move takes it on whatever bar it happens to wake up on - later, more
        # extended, and with the stop measured from a worse price. On the first
        # pass with no book, a signal that was ALREADY firing on the previous bar
        # is therefore skipped and only a fresh cross is taken. This is not a
        # rule change: from the second pass onward the bot behaves exactly as the
        # kernel does, re-entering on an extended bar after an exit if that is
        # what the rule says.
        if cold and np.isfinite(z[i - 1]) and abs(z[i - 1]) >= thr \
                and np.sign(z[i - 1]) == side:
            out.append({"tag": f"vwap{n}", "skipped": "already firing at start-up",
                        "side": side, "z": round(float(z[i]), 3)})
            continue
        px = float(df.close.values[i])
        risk = max(float(cfg["stop_sig"]) * float(sd[i]), px * 3.0 / 1e4)
        out.append({"tag": f"vwap{n}", "signal": "VWAP band break", "side": side,
                    "z": round(float(z[i]), 3), "risk_px": risk,
                    "stop": px - side * risk, "ref": px,
                    "risk_pct": (CHOSEN["risk_pct"] / 100.0 * SIGNAL_SPLIT
                                 / len(SETTINGS)),
                    "max_hold_h": int(cfg["max_hold"])})
    return out


def asia_signal(df: pd.DataFrame, cold: bool = False) -> list[dict]:
    s = CHOSEN["second_signal"]
    hi, lo = asia_levels(df)
    if not np.isfinite(hi) or hi <= lo:
        return []
    mid, half = (hi + lo) / 2.0, (hi - lo) / 2.0
    px = float(df.close.values[-1])
    if half <= abs(mid) * 1e-6:
        return []
    z = (px - mid) / half
    thr = float(s["settings"]["thr"])
    side = 1 if z >= thr else (-1 if z <= -thr else 0)
    if side == 0:
        return []
    if cold:
        prev = float(df.close.values[-2])
        zprev = (prev - mid) / half
        if abs(zprev) >= thr and np.sign(zprev) == side:
            return [{"tag": "asia", "skipped": "already firing at start-up",
                     "side": side, "z": round(z, 3)}]
    risk = max(float(s["settings"]["stop_sig"]) * half, px * 3.0 / 1e4)
    return [{"tag": "asia", "signal": "Asian range break", "side": side,
             "z": round(z, 3), "risk_px": risk, "stop": px - side * risk,
             "ref": px, "risk_pct": CHOSEN["risk_pct"] / 100.0 * SIGNAL_SPLIT,
             "max_hold_h": int(s["settings"]["max_hold"]),
             "range": (round(lo, 2), round(hi, 2))}]


# --------------------------------------------------------------------------- #
# account
# --------------------------------------------------------------------------- #
def equity(host: str) -> float:
    r = signed(host, "/v5/account/wallet-balance", {"accountType": "UNIFIED"})
    if r.get("retCode") != 0:
        sys.exit(f"wallet: {r.get('retMsg')}")
    return float(r["result"]["list"][0]["totalEquity"])


def positions(host: str) -> list[dict]:
    r = signed(host, "/v5/position/list", {"category": CATEGORY, "symbol": SYMBOL})
    if r.get("retCode") != 0:
        return []
    return [p for p in r["result"]["list"] if float(p.get("size") or 0) > 0]


def load_state() -> dict:
    if STATE.exists():
        return json.loads(STATE.read_text())
    return {"open": {}, "peak": None}


def save_state(s: dict) -> None:
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(s, indent=1, default=str))


def size_multiplier(eq: float, peak: float) -> float:
    """The adopted budget-linear rule, `core/chosen.py["sizing"]`."""
    if not peak or peak <= 0:
        return 1.0
    dd = min((eq - peak) / peak, 0.0)
    cap = THUNDERBOLT.max_loss
    return float(np.clip((cap + dd) / cap, CHOSEN["sizing"]["floor_mult"], 1.0))


def market(host: str, side: str, qty: float, tag: str,
           reduce_only: bool = False) -> dict:
    """One netted market order. Bybit is in one-way mode, so this moves the
    single position rather than opening another one."""
    return signed(host, "/v5/order/create", {
        "category": CATEGORY, "symbol": SYMBOL, "side": side,
        "orderType": "Market", "qty": f"{qty:.3f}",
        "timeInForce": "IOC", "reduceOnly": reduce_only,
        "orderLinkId": f"h027-{tag}-{int(time.time() * 1000) % 10**9}",
    }, post=True)


def set_backstop(host: str, level: float | None) -> dict | None:
    """A native stop on the NET position, at the widest live leg's level.

    It is a disconnect backstop, not the strategy's stop: the legs have
    different stops and the exchange can only hold one, so the exchange holds
    the loosest of them and this bot enforces the rest.
    """
    if level is None:
        return None
    return signed(host, "/v5/position/trading-stop", {
        "category": CATEGORY, "symbol": SYMBOL, "positionIdx": 0,
        "stopLoss": f"{level:.2f}", "slTriggerBy": "LastPrice"}, post=True)


def due_exits(df: pd.DataFrame, legs: dict) -> list[tuple[str, dict, str]]:
    """Legs whose own stop was touched or whose horizon has expired.

    The stop is checked against the HIGH/LOW of every bar since entry, which is
    the same rule the kernel applies, and the horizon against wall-clock hours.
    """
    out = []
    now = df.index[-1]
    for tag, leg in legs.items():
        since = df[df.index > pd.Timestamp(leg["at"])]
        hit = False
        if len(since):
            hit = (since.low.min() <= leg["stop"] if leg["side"] == "Buy"
                   else since.high.max() >= leg["stop"])
        aged = (now - pd.Timestamp(leg["at"])).total_seconds() / 3600 >= leg["hold_h"]
        if hit or aged:
            out.append((tag, leg, "stop" if hit else "horizon"))
    return out


# --------------------------------------------------------------------------- #
def once(a) -> None:
    host = DEMO_HOST
    df = bars()
    last = df.index[-1]
    weekend = last.dayofweek >= 5
    eq = equity(host)
    st = load_state()
    peak = max(st.get("peak") or eq, eq)
    st["peak"] = peak
    mult = size_multiplier(eq, peak)

    print(f"{datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC  {SYMBOL} 1h  "
          f"[{'DRY RUN' if not a.arm else 'ARMED - DEMO'}]")
    print(f"  last closed bar {last}  close {df.close.values[-1]:.2f}"
          f"{'   WEEKEND' if weekend else ''}")
    print(f"  equity ${eq:,.2f}  peak ${peak:,.2f}  "
          f"drawdown {(eq - peak) / peak * 100:+.2f}%  size x{mult:.2f}")

    live = positions(host)
    if live:
        for p in live:
            print(f"  OPEN {p['side']} {p['size']} XAU @ {p['avgPrice']}  "
                  f"stop {p.get('stopLoss') or 'none'}  "
                  f"uPnL {float(p.get('unrealisedPnl') or 0):+.2f}")

    if weekend and not a.weekends:
        print("  weekend bar - skipped. The backtest never saw one "
              "(median range 6.8bps against 35.1 on weekdays). --weekends to allow.")
        return

    # cold = this process has no book AND has never written one. A restart with
    # an existing book is not a cold start; a first-ever run is.
    cold = not st["open"] and not st.get("started")
    if cold:
        print("  COLD START - only fresh crosses are taken on this pass")
    sigs = vwap_signals(df, cold) + asia_signal(df, cold)
    if not sigs:
        print("  no signal on the last closed bar")
        return

    # ---- 1. close legs the rule says are finished --------------------- #
    delta = 0.0                       # net XAU to trade this pass, + = buy
    for tag, leg, why in due_exits(df, st["open"]):
        print(f"  EXIT {tag:6} {leg['side']} {leg['qty']:.3f} XAU - {why}")
        delta += -leg["qty"] if leg["side"] == "Buy" else leg["qty"]
        if a.arm:
            r = market(host, "Sell" if leg["side"] == "Buy" else "Buy",
                       leg["qty"], f"x-{tag}", reduce_only=True)
            print(f"      {'CLOSED' if r.get('retCode') == 0 else 'REJECTED ' + str(r.get('retMsg'))}")
            if r.get("retCode") != 0:
                continue
        st["open"].pop(tag, None)

    # ---- 2. open what fired ------------------------------------------- #
    opened: list[str] = []
    for s in sigs:
        if s.get("skipped"):
            print(f"  {'skipped':18} {s['tag']:6} "
                  f"{'BUY' if s['side'] > 0 else 'SELL':4} z={s['z']:+.2f}  "
                  f"{s['skipped']} - waiting for a fresh cross")
            continue
        risk_pct = s["risk_pct"] * mult
        qty = eq * risk_pct / s["risk_px"]
        qty = max(MIN_QTY, round(qty / QTY_STEP) * QTY_STEP)
        want = "Buy" if s["side"] > 0 else "Sell"
        print(f"  {s['signal']:18} {s['tag']:6} {want.upper():4} z={s['z']:+.2f}  "
              f"qty {qty:.3f} XAU (${qty * s['ref']:,.0f})  stop {s['stop']:.2f}  "
              f"risk ${eq * risk_pct:,.0f} ({risk_pct * 100:.2f}%)  "
              f"hold<= {s['max_hold_h']}h")
        if s["tag"] in st["open"]:
            print("      already open for this leg - skipped")
            continue
        # A DRY RUN MUST NOT REMEMBER ANYTHING. The first version recorded the
        # leg whether or not it armed, so the dry run filled the book with
        # positions that did not exist and the armed run that followed skipped
        # every one of them as "already open". State is written only when an
        # order is actually sent.
        if a.arm:
            opened.append(s["tag"])
            st["open"][s["tag"]] = {"at": str(last), "side": want, "qty": qty,
                                    "stop": s["stop"], "hold_h": s["max_hold_h"],
                                    "entry_ref": s["ref"]}
        delta += qty if s["side"] > 0 else -qty

    # ---- 3. one netted order, and a backstop on what is left ---------- #
    total_risk = sum(l["qty"] * abs(l["entry_ref"] - l["stop"]) for l in st["open"].values())
    print(f"  net this pass: {delta:+.3f} XAU   book: {len(st['open'])} legs, "
          f"risk at stops ${total_risk:,.0f} ({total_risk / eq * 100:.2f}% of equity)")
    if a.arm and abs(delta) >= MIN_QTY:
        r = market(host, "Buy" if delta > 0 else "Sell", abs(delta), "net")
        if r.get("retCode") == 0:
            print(f"      NET ORDER ok {r['result'].get('orderId')}")
        elif r.get("retCode") == 110123:
            print(f"      NET ORDER REJECTED: {r.get('retMsg')}")
            print("      XAUUSDT needs its Trading Terms accepted, and Bybit's "
                  "agreement endpoint refuses demo requests (10032).")
            print("      Either accept them on the LIVE account first, or run "
                  "this with --symbol XAUTUSDT, which needs no agreement.")
            for tag in opened:
                st["open"].pop(tag, None)
            save_state(st)
            return
        else:
            # THE ORDER DID NOT FILL, SO THE BOOK MUST NOT REMEMBER IT. Without
            # this rollback a rejected order leaves phantom legs that the next
            # pass skips as "already open" and that the exit logic will later
            # try to close - selling a position that was never bought.
            print(f"      NET ORDER REJECTED: {r.get('retMsg')}")
            for tag in opened:
                st["open"].pop(tag, None)
            print(f"      rolled back {len(opened)} leg(s) - nothing is open")
            save_state(st)
            return
    if a.arm and st["open"]:
        longs = [l for l in st["open"].values() if l["side"] == "Buy"]
        widest = (min(l["stop"] for l in longs) if longs
                  else max(l["stop"] for l in st["open"].values()))
        set_backstop(host, widest)
        print(f"      backstop stop-loss set at {widest:.2f}")
    if a.arm:
        st["started"] = st.get("started") or str(last)
        save_state(st)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--arm", action="store_true",
                    help="actually place orders on the DEMO account")
    ap.add_argument("--weekends", action="store_true",
                    help="allow signals on weekend bars (untested by the backtest)")
    ap.add_argument("--symbol", default=None,
                    help="XAUUSDT (needs the Trading Terms accepted on the LIVE "
                         "account) or XAUTUSDT (works on demo today)")
    ap.add_argument("--loop", type=int, default=0, metavar="SECONDS")
    a = ap.parse_args()
    if a.symbol:
        globals()["SYMBOL"] = a.symbol
    while True:
        try:
            once(a)
        except Exception as exc:                          # noqa: BLE001
            print(f"  ERROR {type(exc).__name__}: {exc}")
        if not a.loop:
            return 0
        time.sleep(a.loop)


if __name__ == "__main__":
    raise SystemExit(main())
