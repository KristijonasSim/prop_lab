"""Step 8 deep dive + book, re-run on the 24h-capped survivors (`improve24.py`).

Same pre-registered tests as `deepdive.py` and `book5.py`, nothing changed but
the cap and the five names, which are the five that beat the luck check under
it. Kris, 2026-10-09.

    python -m factory.step8_24
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from factory import book5, deepdive, improve, queue  # noqa: E402

improve.MAX_HOURS = 24
improve.OUT = queue.DIR / "improve24.json"
deepdive.OUT = queue.DIR / "deepdive24.json"
book5.DEEP = deepdive.OUT
book5.OUT = queue.DIR / "book5_24.json"
book5.EXTRA = ()
book5.OUT2 = queue.DIR / "book5_24_round2.json"
deepdive.PICKS = tuple(r["name"] for r in json.loads(improve.OUT.read_text())
                       if r["null_final"]["real"])

if __name__ == "__main__":
    deepdive.main()
    print("\n=== BOOK ===", flush=True)
    book5.main()
    print("\n=== BOOK ROUND 2 (caps, older years) ===", flush=True)
    book5.round2()
