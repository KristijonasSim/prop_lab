"""Every manifest must name everything its result depends on.

`core/fingerprint.py` hashes what a manifest DECLARES. A kernel left out of the
manifest therefore never trips the stale flag, and the card stays green while
the result rots - the same failure the fingerprint was built to stop, one level
up. `core/manifest_audit.py` walks the import graph and this test enforces it.

On its first run the audit found `core/prop_rules.py` undeclared by both
hypotheses - it holds the profit target and the loss caps, so changing it moves
every pass rate on the board - and found that H-016 reaches H-002's kernel
through `strategies/ribbon/sweep.py`. Two records that read as independent on
the board are not.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core import manifest_audit as MA                          # noqa: E402

SIDS = sorted(p.parent.name for p in (ROOT / "backtests").glob("*/board.json"))


@pytest.mark.parametrize("sid", SIDS or ["<none>"])
def test_manifest_declares_every_reachable_module(sid):
    if sid == "<none>":
        pytest.skip("no board records on disk")
    r = MA.audit(sid)
    assert not r.get("error"), r["error"]
    assert not r["missing"], (
        f"strategies/{sid}/manifest.py does not declare: "
        f"{', '.join(r['missing'])}. A change to any of these would NOT flag "
        f"the board card stale. Add them to KERNELS or SCORING, or add them to "
        f"core/manifest_audit.py::IGNORE with a reason.")


@pytest.mark.parametrize("sid", SIDS or ["<none>"])
def test_manifest_files_all_exist(sid):
    if sid == "<none>":
        pytest.skip("no board records on disk")
    mod = __import__(f"strategies.{sid}.manifest", fromlist=["MANIFEST"])
    man = mod.MANIFEST
    missing = [str(p) for group in ("kernels", "scoring", "data")
               for p in man.get(group, []) if not Path(p).is_file()]
    assert not missing, (
        f"strategies/{sid}/manifest.py names files that do not exist: "
        f"{missing}. A missing declared file hashes to None and reads as a hard "
        f"stale forever.")
