"""Pull the feeds for a wide crypto universe, not just the original three coins.

H-017 reached 28.5 expected days against a 14-day target, and the one lever
that still scales is leg count: K grows as sqrt(N) with a measured exponent of
0.441, and the book runs eleven coins. Binance's public archive carries the
same 5-minute metrics and perp klines for **69 USDT-M perps with history back
to 2021**, so the universe was never eleven - it was eleven because that is
what someone happened to download.

This fetches the remaining ones through `core.binance_metrics`, which already
handles the archive's quirks (the millisecond-to-microsecond stamp switch, the
monthly files lagging weeks behind, resuming a killed run from the cache).

Coins are chosen for LISTING AGE, not for current volume: the fit window starts
in 2021 and a 2025 listing contributes nothing to it. Tokenised equities and
recent memecoins are excluded for the same reason, however liquid they are now.

Run: .venv/bin/python core/wide_universe.py [N_PARALLEL]
"""
from __future__ import annotations

import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core import binance_metrics as bm                              # noqa: E402

FIRST = date(2021, 12, 1)         # where the existing eleven coins begin
KLINE_FIRST = "2021-12"

#: The eleven already on disk.
HAVE = ["ADAUSDT", "AVAXUSDT", "BNBUSDT", "BTCUSDT", "DOGEUSDT", "DOTUSDT",
        "ETHUSDT", "LINKUSDT", "LTCUSDT", "SOLUSDT", "XRPUSDT"]

#: Thirty more, all listed well before the fit window opens and all verified
#: present in the archive on 2022-01-15.
ADD = ["MATICUSDT", "UNIUSDT", "ATOMUSDT", "ETCUSDT", "BCHUSDT", "FILUSDT",
       "TRXUSDT", "XLMUSDT", "VETUSDT", "EOSUSDT", "THETAUSDT", "AAVEUSDT",
       "ALGOUSDT", "AXSUSDT", "SANDUSDT", "MANAUSDT", "NEARUSDT", "FTMUSDT",
       "EGLDUSDT", "HBARUSDT", "XTZUSDT", "CHZUSDT", "ZECUSDT", "DASHUSDT",
       "COMPUSDT", "SUSHIUSDT", "CRVUSDT", "SNXUSDT", "GRTUSDT", "RUNEUSDT"]


def one(sym: str) -> str:
    try:
        m = bm.fetch(sym, first=FIRST)
        k = bm.klines(sym, "5m", first=KLINE_FIRST)
        return (f"{sym}: metrics {len(m):,}, perp {len(k):,}"
                if len(m) and len(k) else f"{sym}: EMPTY")
    except Exception as e:                                      # noqa: BLE001
        return f"{sym}: FAILED {type(e).__name__} {e}"


def main() -> int:
    n_par = int(sys.argv[1]) if len(sys.argv) > 1 else 5
    todo = [s for s in ADD if s not in HAVE]
    print(f"{len(todo)} coins to fetch, {n_par} at a time "
          f"({bm.WORKERS} threads each)\n", flush=True)
    with ThreadPoolExecutor(n_par) as ex:
        futs = {ex.submit(one, s): s for s in todo}
        for i, fu in enumerate(as_completed(futs), 1):
            print(f"[{i}/{len(todo)}] {fu.result()}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
