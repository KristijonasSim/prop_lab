"""The traded strategy is FROZEN. This test is the lock.

Kris, 2026-09-09: *"make sure everything is committed and this strategy is saved
and won't change."*

`core/chosen.py` is what the board renders, what the Pine indicator ships, and
what a live account would trade. Everything else in this repo is research and is
expected to move; this is not. A configuration that drifts silently between the
day it was measured and the day it is traded makes every number attached to it
meaningless, and the drift is always accidental - somebody re-runs a study, likes
a row, and edits the file.

So the five settings, the risk, the market and the headline numbers are pinned
here as literals. Changing the strategy means changing this test IN THE SAME
COMMIT as the change, which makes the change visible in review instead of
invisible.

WHAT IS DELIBERATELY NOT PINNED: the caveats list and the alternatives table.
Those are commentary and should be free to improve.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.chosen import CHOSEN, SETTINGS                        # noqa: E402


def test_the_market_and_size_are_what_was_measured():
    assert CHOSEN["sid"] == "vwapbreak"
    assert CHOSEN["hid"] == "H-027"
    assert CHOSEN["market"] == "XAUUSD"
    assert CHOSEN["tf"] == "1h"
    assert CHOSEN["rule"] == "floor 30 / top 5"
    assert CHOSEN["risk_pct"] == 2.0
    assert CHOSEN["risk_each_pct"] == 0.4
    assert abs(CHOSEN["risk_each_pct"] * 5 - CHOSEN["risk_pct"]) < 1e-9


def test_the_five_settings_are_frozen():
    """Ranked on the twelve months to 2026-08-30. If these move, the numbers
    below stop describing them."""
    assert SETTINGS == [
        {"thr": 1.00, "stop_sig": 3.0, "max_hold": 384, "hour_lo": 0,
         "hour_hi": 0, "min_rvol": 0.0},
        {"thr": 1.50, "stop_sig": 4.0, "max_hold": 384, "hour_lo": 0,
         "hour_hi": 0, "min_rvol": 1.0},
        {"thr": 0.50, "stop_sig": 3.0, "max_hold": 384, "hour_lo": 0,
         "hour_hi": 0, "min_rvol": 1.0},
        {"thr": 0.75, "stop_sig": 4.0, "max_hold": 384, "hour_lo": 7,
         "hour_hi": 16, "min_rvol": 1.0},
        {"thr": 1.50, "stop_sig": 4.0, "max_hold": 384, "hour_lo": 0,
         "hour_hi": 0, "min_rvol": 0.0},
    ]
    assert CHOSEN["trained_to"] == "2026-08-30"
    assert CHOSEN["refresh_on"] == "2026-12-01"


def test_the_headline_numbers_are_the_measured_ones():
    m = CHOSEN["measured"]
    assert m["pass_pct"] == 59.8
    assert m["days_to_pass"] == 21.7
    assert m["days_band"] == [16.8, 31.4]
    assert m["trades_per_day"] == 0.93
    assert m["win_pct"] == 20.3
    assert m["blown_pct"] == 33.9


def test_the_indicator_ships_exactly_these_settings():
    """The Pine a person pastes into TradingView has to be the strategy, not a
    near miss. This is the check that would have caught a defaults drift."""
    import json

    from core import pine

    rec = json.loads((ROOT / "backtests" / "vwapbreak" /
                      "hypothesis.json").read_text())
    p = pine.for_record(rec)
    assert p is not None
    for i, cfg in enumerate(SETTINGS, start=1):
        assert p["params"][f"THR{i}"] == f"{cfg['thr']:g}"
        assert p["params"][f"STOP{i}"] == f"{cfg['stop_sig']:g}"
        assert p["params"][f"HOLD{i}"] == str(int(cfg["max_hold"]))
        assert p["params"][f"HLO{i}"] == str(int(cfg["hour_lo"]))
        assert p["params"][f"HHI{i}"] == str(int(cfg["hour_hi"]))
        assert p["params"][f"RVOL{i}"] == f"{cfg['min_rvol']:g}"
    assert "{{" not in p["text"]
    assert "indicator(" in p["text"] and "strategy(" not in p["text"]
