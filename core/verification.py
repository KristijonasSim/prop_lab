"""The verification gate. A hypothesis cannot hold a real board score until the
checks pass, in code.

Item 2 of `STEPS_1_2_4.md`. The root cause of every "it worked, then it was a
bug" event in this project is that results are published before they are
verified:

    now:      kernel -> sweep -> walk-forward -> BOARD -> (verify, ad hoc, later)
    should:   kernel -> VERIFY -> sweep -> walk-forward -> BOARD

H-009 reached board score **8.9 without ever being checked by a second engine**,
and nothing in the system stopped it. `core/scorecard.py` had an evidence
*weight*, but a weight is not a gate: a strong profit factor could always buy
its way past thin evidence.

This module runs the invariant suite for one hypothesis and writes
`backtests/<sid>/verification.json`. `core/scorecard.py` reads it and caps the
total at 3.0 when any check has not passed.

A SKIP IS NOT A PASS. A test that did not run has verified nothing, so a check
whose tests were all skipped fails the gate. That is how H-016 is scored for
never having been through a second engine: the test exists, it skips with a
reason, and the gate reads the skip.

EVERY PASS IS STAMPED WITH THE FINGERPRINT IT WAS EARNED ON. A pass on a kernel
that has since changed is not a pass, so `core/build_scoreboard.py` discards
verification whose fingerprint no longer matches the record it is attached to.
This is where item 1 pays for itself a second time.

SLOW CHECKS ARE EXCLUDED BY DEFAULT, and the file says so. `-k vwap` would
otherwise select the full NautilusTrader cross-check across five timeframes,
including 5m gold at ~270,000 bars - a gate nobody will run is a gate that does
not exist. The fast run verifies the 4h cross-check; CI runs the full one
nightly. `--slow` includes everything, and `verification.json` records which
depth was used so a pass cannot claim more than it did.

Run: .venv/bin/python core/verification.py            # every hypothesis, fast
     .venv/bin/python core/verification.py vwap       # just one
     .venv/bin/python core/verification.py --slow     # include the full cross-check
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core import fingerprint as FP                             # noqa: E402

BT = ROOT / "backtests"
PY_BIN = ROOT / ".venv" / "bin" / "python"

#: name -> (test file, what a failure means)
CHECKS: dict[str, tuple[str, str]] = {
    "lookahead": (
        "tests/test_no_lookahead.py",
        "Truncate the series; every already-closed trade must be identical. "
        "This is the test that would have caught the three look-aheads that "
        "killed every crypto result in the project."),
    "degenerate": (
        "tests/test_degenerate.py",
        "Zero-volume bars, flat OHLC, zero sigma, one bar, empty series. Both "
        "2026-09-07 bugs were degenerate-input bugs."),
    "costs": (
        "tests/test_costs.py",
        "Profit factor must fall as cost rises, and R must be affine in the "
        "cost multiple - the identity every MEASURED-cost board number uses."),
    "golden": (
        "tests/test_golden.py",
        "A pinned trade list. Any kernel edit that moves a trade has to be "
        "explained in the commit rather than discovered weeks later."),
    "second_engine": (
        "tests/test_second_engine.py",
        "Trade-by-trade agreement with NautilusTrader. An event-driven engine "
        "holds no array it could index into, so it cannot reproduce a "
        "look-ahead. This is the check that has actually found bugs."),
    "manifest": (
        "tests/test_manifests.py",
        "Everything this result depends on is declared, so the stale flag can "
        "see it. An undeclared kernel never trips the flag."),
    "fingerprint": (
        "tests/test_fingerprint.py",
        "The board record carries a fingerprint and it still matches the files "
        "on disk."),
    "parity": (
        "tests/test_ribbon_parity.py",
        "Ribbon's twenty moving averages recomputed the slow literal way from "
        "the Pine source. Existed for weeks as a SCRIPT that pytest never "
        "collected, so nothing ran it."),
}

#: Checks that only some hypotheses have. A check here that matches no tests is
#: recorded "n/a" and does not fail the gate; one that DOES match must still
#: pass. Ribbon's Pine parity check has no vwap equivalent and inventing one so
#: the table looks symmetrical would be theatre.
#:
#: Everything NOT listed here is required of every hypothesis, and "no tests
#: matched" fails - that is the point. A hypothesis with no look-ahead test has
#: not been shown to be free of look-ahead.
OPTIONAL = {"parity"}

#: Checks that are measurements rather than tests, read from the board record.
BOARD_CHECKS = {
    "paired_null": (
        "measured.beats_null",
        "The identical search run on phase-randomised data must find LESS than "
        "the real market did. Twelve hypotheses have died to this and one "
        "(H-005) cleared the gate 1,702 times against its null's 19,062."),
}


def _run_pytest(test_file: str, kexpr: str, slow: bool = False) -> dict:
    """One check, via junit-xml so skips are visible. Exit code alone cannot
    tell 'passed' from 'every test skipped', and that difference is the whole
    point of the gate."""
    with tempfile.TemporaryDirectory() as td:
        xml = Path(td) / "r.xml"
        cmd = [str(PY_BIN), "-m", "pytest", test_file, "-k", kexpr,
               "-q", "--tb=no", "-p", "no:cacheprovider",
               f"--junit-xml={xml}"]
        if not slow:
            # Deselected, not skipped: a deselected test never appears in the
            # report, so it cannot be miscounted as a skip and fail the gate.
            cmd += ["-m", "not slow"]
        proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True,
                              timeout=3600)
        if not xml.exists():
            return {"passed": False, "ran": 0,
                    "detail": f"pytest produced no report (exit {proc.returncode})"}
        root = ET.parse(xml).getroot()
        cases = root.iter("testcase")
        n = failed = skipped = 0
        why: list[str] = []
        for c in cases:
            n += 1
            if c.find("failure") is not None or c.find("error") is not None:
                failed += 1
                why.append(f"FAILED {c.get('name')}")
            elif c.find("skipped") is not None:
                skipped += 1
                s = c.find("skipped")
                why.append(f"SKIPPED {c.get('name')}: {s.get('message', '')[:160]}")
    ran = n - skipped
    passed = bool(ran) and failed == 0 and skipped == 0
    if n == 0:
        detail = "no tests matched this hypothesis"
    elif passed:
        detail = f"{ran} passed"
    else:
        detail = "; ".join(why[:3]) or f"{failed} failed of {n}"
    return {"passed": passed, "ran": ran, "skipped": skipped,
            "failed": failed, "detail": detail}


def verify(sid: str, slow: bool = False) -> dict:
    """Run every check for one hypothesis and write its verification.json."""
    board = BT / sid / "board.json"
    rec = json.loads(board.read_text()) if board.exists() else {}
    fp = rec.get("fingerprint")

    results: dict[str, dict] = {}
    for name, (test_file, why) in CHECKS.items():
        print(f"  {sid} · {name} ...", end=" ", flush=True)
        r = _run_pytest(test_file, sid, slow=slow)
        r["why"] = why
        if name in OPTIONAL and r.get("ran", 0) == 0 and not r.get("skipped"):
            r["passed"] = True
            r["na"] = True
            r["detail"] = "n/a - this hypothesis has no such check"
        results[name] = r
        print(("N/A " if r.get("na") else "PASS") if r["passed"]
              else f"NOT PASSED — {r['detail']}")

    for name, (field, why) in BOARD_CHECKS.items():
        obj: object = rec
        for part in field.split("."):
            obj = (obj or {}).get(part) if isinstance(obj, dict) else None
        ok = obj is True
        results[name] = {"passed": ok, "why": why,
                         "detail": f"{field} = {obj!r}"}
        print(f"  {sid} · {name} ... {'PASS' if ok else 'NOT PASSED'}")

    out = {
        "sid": sid,
        "when": __import__("pandas").Timestamp.utcnow().isoformat(),
        # The fingerprint this evidence was earned on. build_scoreboard discards
        # the whole file when the record's fingerprint no longer matches, because
        # a pass on a kernel that has since changed is not a pass.
        "kernel_hash": (fp or {}).get("kernel_hash"),
        # Which depth this evidence was earned at. A fast pass on second_engine
        # means the 4h configurations agree, not all five timeframes, and the
        # record must not imply otherwise.
        "depth": "slow" if slow else "fast",
        "checks": results,
        "all_passed": all(r["passed"] for r in results.values()),
        "failed": sorted(k for k, r in results.items() if not r["passed"]),
    }
    p = BT / sid / "verification.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(out, indent=1))
    print(f"  wrote {p.relative_to(ROOT)}  "
          f"{'ALL PASSED' if out['all_passed'] else 'FAILED: ' + ', '.join(out['failed'])}")
    return out


def load(sid: str, fp: dict | None) -> dict | None:
    """Read a hypothesis's verification, discarding it if it was earned on a
    kernel that has since changed."""
    p = BT / sid / "verification.json"
    if not p.exists():
        return None
    v = json.loads(p.read_text())
    want = (fp or {}).get("kernel_hash")
    if want and v.get("kernel_hash") and v["kernel_hash"] != want:
        return {"sid": sid, "all_passed": False, "stale_evidence": True,
                "failed": ["*"], "checks": v.get("checks", {}),
                "when": v.get("when")}
    return v


def main() -> int:
    slow = "--slow" in sys.argv
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    sids = args or sorted(p.parent.name for p in BT.glob("*/board.json"))
    bad = 0
    for sid in sids:
        print(f"\nverifying {sid}  ({'full' if slow else 'fast'} depth)")
        if not verify(sid, slow=slow)["all_passed"]:
            bad += 1
    print(f"\n{len(sids) - bad} of {len(sids)} hypotheses pass every check")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
