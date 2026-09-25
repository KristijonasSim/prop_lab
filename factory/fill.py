"""Top the queue up, in the order Kris set. This is what the VM runs.

    python -m factory.fill              top up to the default depth
    python -m factory.fill -n 500       ask for more
    python -m factory.queue             what is waiting

TradingView is drained first. When it has nothing left to give, the inventor
takes over and does not stop. Nothing here waits for a person, which was the
whole point of closing step 1.
"""
from __future__ import annotations

import argparse
import sys

from factory import queue
from factory.sources import invent, tradingview


def fill(target: int = 200, quiet: bool = False) -> dict:
    have = queue.status()["waiting"]
    want = max(0, target - have)
    report = {"already_waiting": have, "wanted": want,
              "tradingview": 0, "invent": 0, "skipped_pine": []}
    if want == 0:
        return report

    pine, skipped = tradingview.load()
    report["skipped_pine"] = skipped
    if pine:
        r = queue.add(pine, quiet=True)
        report["tradingview"] = r["added"]
        want -= r["added"]

    # The inventor never runs out, so it is asked last and asked for the rest.
    # `skip` walks forward through the grammar instead of re-offering the front
    # of the list, and `queue.add` drops anything already seen either way.
    if want > 0:
        tried = len(queue.fingerprints())
        made = invent.generate(want + tried, skip=0)
        r = queue.add(made, quiet=True)
        report["invent"] = r["added"]

    if not quiet:
        print(f"waiting before: {report['already_waiting']}")
        print(f"  tradingview:  +{report['tradingview']}")
        print(f"  invent:       +{report['invent']}")
        if skipped:
            print(f"  pine skipped: {len(skipped)}")
            for name, why in skipped[:5]:
                print(f"      {name}: {why}")
        print(f"waiting now:    {queue.status()['waiting']}")
    return report


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("-n", "--target", type=int, default=200,
                    help="keep at least this many ideas waiting")
    a = ap.parse_args(argv)
    fill(a.target)
    return 0


if __name__ == "__main__":
    sys.exit(main())
