"""H-027 VWAP band breakout — blind walk-forward, the whole hypothesis in one file.

The in-sample search found XAUUSD 1h at 61.9% pass in 12.9 days, and the paired
null found NOTHING in 1,125 cells (its fastest route to 60% was 30.8 days against
the real 12.9). That is the search cleared. It is not the strategy cleared: the
configuration was chosen with knowledge of the window it was scored on.

This runs it the honest way - configuration re-chosen blind inside each quarter's
training window, never carried into the test quarter, on the same three-year span
as every other hypothesis.

Run: .venv/bin/python strategies/vwapbreak/hypothesis.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from core.run_hypothesis import run                            # noqa: E402
from strategies.vwapbreak.manifest import MANIFEST             # noqa: E402
from strategies.vwapbreak.strategy import STRATEGY             # noqa: E402

UNIVERSE = {
    "FX": ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD"],
    "Metals/Energy": ["XAUUSD", "XAGUSD", "WTI"],
    "Crypto": ["BTCUSDT", "ETHUSDT", "SOLUSDT"],
}
TIMEFRAMES = ["1h", "4h"]


def main() -> int:
    run(STRATEGY,
        sid="vwapbreak", hid="H-027",
        name="VWAP band breakout",
        tagline="Follow the band break, no target, four-day horizon. The deep "
                "dive's answer to what H-002 was actually trading.",
        universe=UNIVERSE, tfs=TIMEFRAMES,
        manifest=MANIFEST, null_seeds=1)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
