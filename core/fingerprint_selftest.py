"""Self-check for core/fingerprint.py. No pytest yet - that is item 2.

Runs on throwaway files in a temp directory, so it touches nothing in the repo.
When item 2 installs pytest these become `tests/test_fingerprint.py` more or less
unchanged; until then this is the thing that proves the flag actually fires.

Run: .venv/bin/python core/fingerprint_selftest.py
"""
from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core import fingerprint as F                              # noqa: E402

FAILED: list[str] = []


def check(name: str, got, want):
    ok = got == want
    print(f"  {'PASS' if ok else 'FAIL'}  {name}: {got!r}"
          + ("" if ok else f"  (expected {want!r})"))
    if not ok:
        FAILED.append(name)


def bars(n: int, start="2024-01-01") -> pd.DataFrame:
    idx = pd.date_range(start, periods=n, freq="1h", tz="UTC")
    return pd.DataFrame({"open": 1.0, "high": 1.0, "low": 1.0,
                         "close": 1.0, "volume": 1.0}, index=idx)


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="fpselftest_"))
    # `check` resolves paths against ROOT, so the fixtures have to live inside it.
    work = ROOT / "_fp_selftest_tmp"
    if work.exists():
        shutil.rmtree(work)
    work.mkdir()
    try:
        kern = work / "kernel.py"
        score = work / "scoring.py"
        data = work / "feed.parquet"
        kern.write_text("x = 1\n")
        score.write_text("y = 1\n")
        bars(100).to_parquet(data)

        fp = F.make(kernels=[kern], scoring=[score], data=[data],
                    costs={"rt_bps": 1.83})

        print("\nunchanged")
        check("state", F.check(fp)["state"], "ok")

        print("\nkernel edited -> hard stale")
        kern.write_text("x = 2\n")
        r = F.check(fp)
        check("state", r["state"], "stale")
        check("stale", r["stale"], True)
        kern.write_text("x = 1\n")

        print("\nscoring layer edited -> note, trades still stand")
        score.write_text("y = 2\n")
        r = F.check(fp)
        check("state", r["state"], "note")
        check("stale", r["stale"], False)
        score.write_text("y = 1\n")

        print("\ndata APPENDED -> note")
        bars(150).to_parquet(data)
        r = F.check(fp)
        check("state", r["state"], "note")
        check("stale", r["stale"], False)

        print("\ndata REWRITTEN from a different start -> hard stale")
        bars(150, start="2023-06-01").to_parquet(data)
        r = F.check(fp)
        check("state", r["state"], "stale")
        check("stale", r["stale"], True)

        print("\ndata TRUNCATED -> hard stale")
        bars(50).to_parquet(data)
        check("state", F.check(fp)["state"], "stale")
        bars(100).to_parquet(data)

        print("\nkernel deleted -> hard stale")
        kern.unlink()
        r = F.check(fp)
        check("state", r["state"], "stale")
        check("names the file", "kernel.py" in r["detail"], True)
        kern.write_text("x = 1\n")

        print("\ncost assumption changed")
        check("same costs", F.costs_changed(fp, {"rt_bps": 1.83}), False)
        check("different costs", F.costs_changed(fp, {"rt_bps": 3.00}), True)

        print("\nno fingerprint at all")
        r = F.check(None)
        check("state", r["state"], "unfingerprinted")
        check("not hard stale", r["stale"], False)

        print("\nmtime alone must NOT trip it (a git clone rewrites every mtime)")
        before = F.file_sha(kern)
        kern.touch()
        check("hash unchanged", F.file_sha(kern), before)
        check("state", F.check(fp)["state"], "ok")

        print("\nlive board records")
        import json
        for sid in ("vwap", "ribbon"):
            p = ROOT / "backtests" / sid / "board.json"
            if not p.exists():
                continue
            b = json.loads(p.read_text())
            check(f"{sid} fingerprinted", bool(b.get("fingerprint")), True)
            check(f"{sid} state", F.check(b.get("fingerprint"))["state"], "ok")
    finally:
        shutil.rmtree(work, ignore_errors=True)
        shutil.rmtree(tmp, ignore_errors=True)

    print()
    if FAILED:
        print(f"{len(FAILED)} FAILED: {', '.join(FAILED)}")
        return 1
    print("all checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
