"""Run the pre-existing indicator parity check as part of the suite.

`strategies/ribbon/test_parity.py` recomputes ribbon's twenty moving averages the
slow, literal way - one bar at a time, straight from the Pine source - and
asserts the fast convolution implementation agrees. It is a good check and it
predates this suite by weeks.

It was also a SCRIPT, with a `main()` and no test functions, so `pytest` never
collected it and nothing ran it unless someone chose to. It is named
`test_parity.py`, which made it look covered. That is worse than not having it:
`core/verification.py` reported ribbon's indicators as tested when nothing had
run them.

Wrapped rather than rewritten, so the original stays runnable on its own.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "strategies" / "ribbon" / "test_parity.py"


def test_ribbon_indicators_match_the_literal_pine_reading():
    if not SCRIPT.exists():
        pytest.skip("strategies/ribbon/test_parity.py is gone")
    p = subprocess.run([sys.executable, str(SCRIPT)], cwd=ROOT,
                       capture_output=True, text=True, timeout=900)
    assert p.returncode == 0, (
        f"ribbon indicator parity FAILED (exit {p.returncode}).\n"
        f"{p.stdout[-2000:]}\n{p.stderr[-1000:]}")
