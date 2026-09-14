"""What the two hand-closed books would have done if the rule had run them.

Kris closed the demo account's two winning books himself - 2026-09-12 12:41 at
+$136.51 and 2026-09-14 11:16 at +$284.52 - and asked what would have happened
otherwise. This walks each leg forward under the rule that opened it and nothing
else: exit when the bar's high touches the leg's own stop, or at the 384-hour
horizon, whichever comes first.

WHERE THE BARS COME FROM. Bybit, not Dukascopy. The research cache ends
2026-08-31 and both books are from September, so the venue's own 1h candles are
the only honest source - and they are the prices these fills actually happened
against.

WHAT THIS CANNOT SETTLE. Two books is two books. It says what happened on these
trades, not what the rule is worth; `exitshape.py` and eleven years of gold are
what speak to that. A counterfactual on the trades you remember is the most
selective sample there is, which is exactly why the answer is reported whichever
way it comes out.

Run on the VM:  ~/prop_lab/.venv/bin/python ~/prop_lab/live/counterfactual.py
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("bybit_demo", ROOT / "live" / "bybit_demo.py")
B = importlib.util.module_from_spec(spec)
spec.loader.exec_module(B)

#: The two books, as the bot's own state file recorded them at the time.
BOOKS = {
    "trade 6 - closed by hand 2026-09-12 12:41, +$136.51": {
        "closed_at": "2026-09-12 12:41", "realised": 136.51, "exit_px": 4356.63,
        "legs": [("vwap1", 0.513, 4423.94), ("vwap2", 0.385, 4436.90),
                 ("vwap3", 0.513, 4423.94), ("vwap4", 0.385, 4436.90),
                 ("vwap5", 0.385, 4436.90), ("asia", 1.488, 4452.11)],
        "entry_ts": "2026-09-10 10:00", "entry_px": 4393.10,
    },
    "trade 8 - closed by hand 2026-09-14 11:16, +$284.52": {
        "closed_at": "2026-09-14 11:16", "realised": 284.52, "exit_px": 4300.06,
        "legs": [("vwap1", 2.065, 4345.37), ("vwap2", 1.549, 4348.00),
                 ("vwap3", 2.065, 4345.37), ("vwap5", 1.549, 4348.00),
                 ("asia", 1.919, 4369.47), ("vwap4", 0.279, 4367.83)],
        "entry_ts": "2026-09-14 02:00", "entry_px": 4332.35,
    },
}
HOLD_H = 384


def bars() -> pd.DataFrame:
    """Every 1h candle Bybit will give us, oldest first."""
    out = []
    end = None
    for _ in range(4):
        p = {"category": B.CATEGORY, "symbol": B.SYMBOL, "interval": "60", "limit": 1000}
        if end:
            p["end"] = end
        r = B.public("/v5/market/kline", p)
        rows = r.get("result", {}).get("list", [])
        if not rows:
            break
        out.extend(rows)
        end = int(rows[-1][0]) - 1
    df = pd.DataFrame(out, columns=["ts", "open", "high", "low", "close", "volume", "to"])
    df = df.astype({c: float for c in ("open", "high", "low", "close", "volume")})
    df["ts"] = pd.to_datetime(df.ts.astype("int64"), unit="ms", utc=True)
    return df.drop_duplicates("ts").set_index("ts").sort_index()


def walk(df: pd.DataFrame, entry_ts: str, entry_px: float,
         legs: list, closed_at: str) -> list[dict]:
    """Each SHORT leg forward from entry: stop on a high touch, else horizon."""
    # THE SIGNAL BAR IS NOT THE FILL BAR. `at` in the state file is the last
    # CLOSED bar when the bot decided; the order goes in at the next bar's open.
    # Walking from the signal bar let trade 8's legs "stop out" on the 02:00 bar
    # - a bar whose high happened before the position existed. That is a
    # look-ahead in the counterfactual, and it inverted the answer.
    t0 = pd.Timestamp(entry_ts, tz="UTC") + pd.Timedelta(hours=1)
    w = df[df.index >= t0]
    horizon = t0 + pd.Timedelta(hours=HOLD_H)
    out = []
    for tag, qty, stop in legs:
        exit_ts, exit_px, why = None, None, None
        for ts, b in w.iterrows():
            if ts > horizon:
                exit_ts, exit_px, why = ts, b.open, "horizon"
                break
            if b.high >= stop:                      # short: the stop is above
                exit_ts, exit_px, why = ts, stop, "stop"
                break
        if exit_ts is None:                          # still running
            exit_ts, exit_px, why = w.index[-1], w.close.iloc[-1], "STILL OPEN"
        out.append({"tag": tag, "qty": qty, "stop": stop, "exit_ts": str(exit_ts)[:16],
                    "exit_px": round(float(exit_px), 2), "why": why,
                    "pnl": round((entry_px - float(exit_px)) * qty, 2)})
    return out


def main() -> int:
    df = bars()
    print(f"Bybit {B.SYMBOL} 1h: {len(df)} bars, "
          f"{df.index[0]:%Y-%m-%d %H:%M} -> {df.index[-1]:%Y-%m-%d %H:%M} UTC")
    print(f"last close {df.close.iloc[-1]:.2f}\n")
    for lbl, t in (("since 09-10 11:00", "2026-09-10 11:00"),
                   ("since 09-14 03:00", "2026-09-14 03:00")):
        w = df[df.index >= pd.Timestamp(t, tz="UTC")]
        print(f"  highest high {lbl}: {w.high.max():.2f}   "
              f"lowest low: {w.low.min():.2f}")
    print()

    report = {}
    for name, bk in BOOKS.items():
        res = walk(df, bk["entry_ts"], bk["entry_px"], bk["legs"], bk["closed_at"])
        print("=" * 78)
        print(name)
        print(f"  entry {bk['entry_ts']} @ {bk['entry_px']:.2f}, "
              f"{sum(q for _, q, _ in bk['legs']):.3f} XAU short")
        print(f"  {'leg':7}{'qty':>7}{'stop':>10}{'would exit':>18}{'px':>10}"
              f"{'why':>12}{'P&L':>10}")
        for r in res:
            print(f"  {r['tag']:7}{r['qty']:>7.3f}{r['stop']:>10.2f}"
                  f"{r['exit_ts']:>18}{r['exit_px']:>10.2f}{r['why']:>12}{r['pnl']:>+10.2f}")
        rule = sum(r["pnl"] for r in res)
        print(f"\n  RULE would have made   {rule:+10.2f}  (gross, before fees)")
        print(f"  you actually made      {bk['realised']:+10.2f}  (net of fees)")
        print(f"  difference             {rule - bk['realised']:+10.2f}")
        report[name] = {"legs": res, "rule_gross": round(rule, 2),
                        "hand_net": bk["realised"],
                        "diff": round(rule - bk["realised"], 2)}

    dest = ROOT / "live" / "paper" / "counterfactual.json"
    dest.write_text(json.dumps(report, indent=1))
    print(f"\nwrote {dest.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
