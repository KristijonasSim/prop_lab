"""STEP 8 AGAIN, WITH EVERY TRADE CAPPED AT 24 HOURS.

Kris, 2026-10-09, on seeing a 259h average hold: *"i thought that those
strategies will have maximum 24h hold its not even day trading"*. Round 1's
exit grid allowed 480 bars - 80 days on 4h - which breaks the project's own
phase rule (intraday to a few days). Everything in `improve.py` is re-run
unchanged except that no trade may live longer than 24 hours, the ORIGINAL
included (so a lift measures tuning, not the cap). The AI pass is skipped:
round 1's model variants won 2 of 27 and neither was real.

    python -m factory.improve24        # improve24.json, IMPROVE24.md
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from factory import improve, queue  # noqa: E402

improve.MAX_HOURS = 24
improve.OUT = queue.DIR / "improve24.json"
improve.TABLE = queue.DIR / "IMPROVE24.md"
improve.CACHE = queue.DIR / "improve_cache"

if __name__ == "__main__":
    improve.cmd_grid()
    improve.cmd_null()
    improve.cmd_table()
