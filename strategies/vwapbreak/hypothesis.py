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

#: What the deep dive established, carried onto the page so the reasoning lives
#: next to the numbers instead of in a commit message.
NOTES = [
    "<b>The direction is FOLLOW, not fade.</b> Tested on identical bars, "
    "thresholds and holds, follow beat fade in <b>79 of 100 paired cells</b> — "
    "25 of 25 on ETH 4h and XAUUSD 1h. H-002's own blind walk-forward already "
    "agreed: it picks MODE_BREAK in 100 of 140 folds and MODE_FADE in 4. "
    "H-002 is named after a trade it does not make.",

    "<b>A fixed target was destroying the payoff.</b> Average R rose "
    "monotonically with reward:risk to the edge of every grid tried. Removing "
    "the target entirely moved XAUUSD 1h from <b>+0.155R to +0.684R</b> per "
    "trade. The shape is one winner in nine carried a long way, and a target "
    "cuts exactly the trades that pay.",

    "<b>The session-close exit was too early.</b> A four-day horizon beats it. "
    "H-002 closes at the session boundary and gives the move back.",

    "<b>It survives its own null.</b> The identical 375-cell search on "
    "phase-randomised markets found <b>0 hits in 1,125 cells</b> across three "
    "seeds; its fastest route to 60% pass was 30.8 days against the real 12.9.",

    "<b>Fewer, larger positions are faster.</b> A single configuration reaches "
    "66.6% pass in 21.0 days; a ten-deep book of the same signal takes 31.6 "
    "days. Ten correlated positions at 0.50% risk put 5% at risk against a "
    "<b>3% daily cap</b>, and 12.8% of accounts die on the daily limit alone.",

    "<b>Not yet at the goal.</b> The in-sample 61.9% pass in 12.9 days did NOT "
    "survive blind quarterly reselection — best blind is 66.6% in 21.0 days. "
    "Session and relative-volume filters are being tested now, with 'no filter' "
    "inside the grid so the selector can decline them.",
]

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
        manifest=MANIFEST, null_seeds=1, notes=NOTES)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
