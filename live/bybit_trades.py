"""Every position the demo account has closed, from Bybit rather than from us.

WHY IT READS THE EXCHANGE AND NOT OUR OWN LOG. `live/paper/bybit_cron.log` says
what the bot DECIDED; this says what actually happened to the money, including
the trades nobody's code placed - two of the three real ones so far were closed
by hand from the Bybit UI or by the exchange's own backstop, and neither appears
as an exit in our log.

Read-only. It places nothing and cancels nothing.

Run on the VM:  ~/prop_lab/.venv/bin/python ~/prop_lab/live/bybit_trades.py
"""
from __future__ import annotations

import datetime as dt
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "live" / "paper" / "trades.jsonl"

spec = importlib.util.spec_from_file_location("bybit_demo", ROOT / "live" / "bybit_demo.py")
B = importlib.util.module_from_spec(spec)
spec.loader.exec_module(B)


def fetch() -> list[dict]:
    r = B.signed(B.DEMO_HOST, "/v5/position/closed-pnl",
                 {"category": B.CATEGORY, "limit": 100})
    rows = r.get("result", {}).get("list", [])
    rows.sort(key=lambda x: int(x["createdTime"]))
    return rows


def ts(ms: str) -> str:
    return dt.datetime.fromtimestamp(int(ms) / 1000, dt.timezone.utc).isoformat(timespec="seconds")


def main() -> int:
    rows = fetch()
    if not rows:
        print("no closed positions")
        return 0

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")

    tot = 0.0
    hdr = (f"{'#':>2} {'closed (UTC)':17} {'sym':9} {'side':5} {'qty':>8} "
           f"{'entry':>10} {'exit':>10} {'net':>9} {'fees':>7} {'cum':>9}")
    print(hdr)
    print("-" * len(hdr))
    for i, r in enumerate(rows, 1):
        p = float(r["closedPnl"])
        f = float(r["openFee"]) + float(r["closeFee"])
        tot += p
        print(f"{i:>2} {ts(r['updatedTime'])[5:16]:17} {r['symbol']:9} {r['side']:5} "
              f"{float(r['qty']):>8.3f} {float(r['avgEntryPrice']):>10.2f} "
              f"{float(r['avgExitPrice']):>10.2f} {p:>+9.2f} {f:>7.2f} {tot:>+9.2f}")

    fees = sum(float(r["openFee"]) + float(r["closeFee"]) for r in rows)
    wins = [r for r in rows if float(r["closedPnl"]) > 0]
    print(f"\n{len(rows)} closed   net {tot:+.2f}   fees {fees:.2f} "
          f"({fees / abs(tot) * 100:.0f}% of net)   winners {len(wins)}/{len(rows)}")
    print(f"equity now {B.equity(B.DEMO_HOST):,.2f}")
    print(f"\nwrote {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
