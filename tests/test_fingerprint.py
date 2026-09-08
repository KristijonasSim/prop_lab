"""core/fingerprint.py: does the stale flag actually fire, and only when it should.

Was `core/fingerprint_selftest.py`, written before pytest existed in this repo.
Moved here unchanged in substance when item 2 installed the frame.

The flag is only worth having if BOTH halves hold: it fires when a kernel moves,
and it stays quiet when nothing that matters moved. A flag that cries wolf is
turned off by the second week, which is how the project ended up with a hand-typed
`SUPERSEDED` note in the first place.
"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core import fingerprint as F                              # noqa: E402


@pytest.fixture
def work(tmp_path_factory):
    """Fixtures must live inside the repo: `check` resolves recorded paths
    against ROOT, so a /tmp path would not round-trip."""
    d = ROOT / "_fp_test_tmp"
    if d.exists():
        shutil.rmtree(d)
    d.mkdir()
    yield d
    shutil.rmtree(d, ignore_errors=True)


def _bars(n: int, start="2024-01-01") -> pd.DataFrame:
    idx = pd.date_range(start, periods=n, freq="1h", tz="UTC")
    return pd.DataFrame({"open": 1.0, "high": 1.0, "low": 1.0,
                         "close": 1.0, "volume": 1.0}, index=idx)


@pytest.fixture
def fp(work):
    kern, score, data = work / "kernel.py", work / "scoring.py", work / "feed.parquet"
    kern.write_text("x = 1\n")
    score.write_text("y = 1\n")
    _bars(100).to_parquet(data)
    return F.make(kernels=[kern], scoring=[score], data=[data],
                  costs={"rt_bps": 1.83}), kern, score, data


def test_unchanged_is_ok(fp):
    f, *_ = fp
    assert F.check(f)["state"] == "ok"


def test_kernel_edit_is_a_hard_stale(fp):
    f, kern, _, _ = fp
    kern.write_text("x = 2\n")
    r = F.check(f)
    assert r["state"] == "stale" and r["stale"] is True
    assert "kernel.py" in r["detail"]


def test_scoring_edit_is_a_note_not_a_stale(fp):
    """The trades still stand; only the stored summary was recomputed elsewhere.
    One tier would flag every card on a cosmetic edit to core/board.py."""
    f, _, score, _ = fp
    score.write_text("y = 2\n")
    r = F.check(f)
    assert r["state"] == "note" and r["stale"] is False


def test_appended_data_is_a_note(fp):
    """The feeds grow every day by design."""
    f, _, _, data = fp
    _bars(150).to_parquet(data)
    r = F.check(f)
    assert r["state"] == "note" and r["stale"] is False


def test_rewritten_history_is_a_hard_stale(fp):
    """Same filename, different history - a different input in disguise."""
    f, _, _, data = fp
    _bars(150, start="2023-06-01").to_parquet(data)
    assert F.check(f)["stale"] is True


def test_truncated_data_is_a_hard_stale(fp):
    f, _, _, data = fp
    _bars(50).to_parquet(data)
    assert F.check(f)["stale"] is True


def test_a_deleted_kernel_is_named(fp):
    f, kern, _, _ = fp
    kern.unlink()
    r = F.check(f)
    assert r["stale"] is True and "kernel.py" in r["detail"]


def test_mtime_alone_does_not_trip_it(fp):
    """A fresh git clone rewrites every mtime. Hashing mtime would stale a repo
    where literally nothing moved."""
    f, kern, _, _ = fp
    before = F.file_sha(kern)
    kern.touch()
    assert F.file_sha(kern) == before
    assert F.check(f)["state"] == "ok"


def test_cost_change_is_detected(fp):
    f, *_ = fp
    assert F.costs_changed(f, {"rt_bps": 1.83}) is False
    assert F.costs_changed(f, {"rt_bps": 3.00}) is True


def test_no_fingerprint_reports_unfingerprinted_not_ok():
    """A record written before provenance existed must not read as verified."""
    r = F.check(None)
    assert r["state"] == "unfingerprinted"
    assert r["stale"] is False


@pytest.mark.parametrize("sid", ["vwap", "ribbon"])
def test_live_board_records_are_fingerprinted_and_current(sid):
    p = ROOT / "backtests" / sid / "board.json"
    if not p.exists():
        pytest.skip(f"no board record for {sid}")
    b = json.loads(p.read_text())
    assert b.get("fingerprint"), f"{sid}/board.json carries no fingerprint"
    r = F.check(b["fingerprint"])
    assert r["state"] == "ok", (
        f"{sid} board record is {r['state']}: {r['detail']}. Rerun its board "
        f"stage - see strategies/{sid}/manifest.py for which one that is.")
