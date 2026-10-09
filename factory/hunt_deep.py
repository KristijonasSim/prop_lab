"""Deep dive on the hunt's REAL ideas - the same pre-registered tests as
`deepdive.py` (markets >= 4/6, older years as a note, years, costs, entry vs
random) under the 24h cap, plus the older-years pace that killed the book.

    python -m factory.hunt_deep
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from factory import book5, deepdive, improve, queue  # noqa: E402

improve.MAX_HOURS = 24
TAG = f"_{sys.argv[1].replace('.', '')}" if sys.argv[1:] else ""
improve.MIN_TPD = float(sys.argv[1]) if sys.argv[1:] else 1.0
improve.LIST = queue.DIR / f"hunt{TAG}_list.json"
improve.OUT = queue.DIR / f"hunt{TAG}.json"
deepdive.OUT = queue.DIR / f"hunt{TAG}_deep.json"
deepdive.PICKS = tuple(r["name"] for r in json.loads(improve.OUT.read_text())
                       if r["null_final"]["real"])

if __name__ == "__main__":
    deepdive.main()
    book5.DEEP = deepdive.OUT
    import pandas as pd
    from factory import cells
    for l in book5.legs():
        d = cells.load(l["market"], l["tf"])
        o = cells.holdout(l["market"], l["tf"])
        o = o[o.index < d.index[0]]
        print(f"older pace {l['name'][:40]:40}", book5.pace(book5._trades_full(l, frame=o)[["t", "r"]]))
        print(f"now   pace {l['name'][:40]:40}", book5.pace(book5._trades_full(l)[["t", "r"]]))
