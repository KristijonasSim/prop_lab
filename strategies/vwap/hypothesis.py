"""H-002 VWAP mean reversion / breakout — one file, the whole hypothesis.

THE SHAPE EVERY HYPOTHESIS TAKES FROM NOW ON. There are no stage scripts here.
`strategies/vwap/strategy.py` says what the strategy IS; this says what to run it
on; `core/run_hypothesis.py` does the rest — blind quarterly walk-forward, the
paired null it has to beat, the risk ladder under the firm's real rules, and the
page. The old H-002 needed 25 hand-written files to reach the same place.

ENTRIES ARE RESTING LIMIT ORDERS, EXITS ARE MARKET ORDERS. A stop-loss cannot be
a limit order, so one side is maker and one is taker; `core/markets.py` charges
the average. On BTC that assumption is measured rather than hoped — H-023 put
through-given-touch at 99.8-100% with adverse selection ~0. On ETH, SOL and
XAUUSD it is an extrapolation and is labelled as one.

Run: .venv/bin/python strategies/vwap/hypothesis.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from core.run_hypothesis import run                            # noqa: E402
from strategies.vwap.manifest import MANIFEST                  # noqa: E402
from strategies.vwap.strategy import STRATEGY                  # noqa: E402

#: One row per asset class on the board. Within a class the best market is
#: promoted — best by DAYS TO PASS, which is the phase gate, not by profit
#: factor. The others stay visible on the row so the choice can be audited.
UNIVERSE = {
    "FX": ["EURUSD", "GBPUSD", "USDJPY"],
    "Gold": ["XAUUSD"],
    "Crypto": ["BTCUSDT", "ETHUSDT", "SOLUSDT"],
}

#: 1h and 4h. Not 5m/15m on this first run: the point is to prove the pipeline
#: end to end, and the fine timeframes multiply runtime by ~12 for no extra
#: information about whether the machinery works.
TIMEFRAMES = ["1h", "4h"]


def main() -> int:
    run(STRATEGY,
        sid="vwap", hid="H-002",
        name="VWAP mean reversion / breakout",
        tagline="Five model families around the volume-weighted average price, "
                "re-chosen blind every quarter.",
        universe=UNIVERSE, tfs=TIMEFRAMES,
        manifest=MANIFEST,
        null_seeds=1)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
