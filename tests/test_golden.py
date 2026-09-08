"""Pinned trade lists. Any kernel edit that moves a trade has to say so.

The failure this prevents is the slow one. A kernel change that looks harmless
shifts a fill by one bar; nobody notices; three weeks later a board number is
different and the reason is gone. `git log` shows the edit but not its effect.

So: a fixed configuration on a fixed slice of real bars, its trade list stored on
disk, and a test that says the two must match. If a change is intended, the fix
is to regenerate and let the DIFF appear in the commit - which is a record of
what the change did, in trades, written at the moment it was made.

    Regenerate:  .venv/bin/python tests/test_golden.py --regenerate

Never regenerate to make a red test green. Read the diff first: this test firing
is the only warning the repo gives before a board number moves.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tests.kernels import IDS, KERNELS, T_ENTRY_I, T_EXIT_I, T_R   # noqa: E402

GOLDEN = Path(__file__).resolve().parent / "golden"
N_BARS = 4000
FEE, SLIP = 1.0, 0.5
SERIES = "XAUUSD_dukascopy_1h.parquet"


def _bars() -> pd.DataFrame:
    p = ROOT / "data" / SERIES
    if not p.exists():
        pytest.skip(f"{SERIES} not in the cache")
    return pd.read_parquet(p).sort_index().iloc[:N_BARS]


def _path(kernel, cfgname: str) -> Path:
    return GOLDEN / f"{kernel.name}_{cfgname}.npy"


def _cases():
    return [(k, c) for k in KERNELS for c in ("cfg", "cfg_alt")]


@pytest.mark.parametrize("kernel,cfgname",
                         _cases(),
                         ids=[f"{k.name}-{c}" for k, c in _cases()])
def test_trade_list_matches_the_pinned_one(kernel, cfgname):
    p = _path(kernel, cfgname)
    if not p.exists():
        pytest.skip(f"{p.name} not generated yet - run tests/test_golden.py "
                    f"--regenerate")
    want = np.load(p)
    got = kernel.run(_bars(), getattr(kernel, cfgname), FEE, SLIP)

    if len(want) != len(got):
        pytest.fail(
            f"{kernel.name} [{cfgname}]: {len(got)} trades against the pinned "
            f"{len(want)}. Total R {got[:, T_R].sum():.4f} against "
            f"{want[:, T_R].sum():.4f}. If the change was intended, regenerate "
            f"and put the reason in the commit message.")

    if not np.allclose(want, got, rtol=0, atol=1e-9, equal_nan=True):
        bad = np.where(~np.isclose(want, got, rtol=0, atol=1e-9,
                                   equal_nan=True).all(axis=1))[0]
        first = bad[0]
        pytest.fail(
            f"{kernel.name} [{cfgname}]: {len(bad)} of {len(want)} trades moved. "
            f"First at index {first}: entry bar "
            f"{want[first, T_ENTRY_I]:.0f}->{got[first, T_ENTRY_I]:.0f}, "
            f"exit bar {want[first, T_EXIT_I]:.0f}->{got[first, T_EXIT_I]:.0f}, "
            f"R {want[first, T_R]:.6f}->{got[first, T_R]:.6f}. "
            f"Total R {want[:, T_R].sum():.4f}->{got[:, T_R].sum():.4f}.")


def regenerate() -> int:
    GOLDEN.mkdir(exist_ok=True)
    bars = _bars()
    for kernel in KERNELS:
        for cfgname in ("cfg", "cfg_alt"):
            tr = kernel.run(bars, getattr(kernel, cfgname), FEE, SLIP)
            p = _path(kernel, cfgname)
            old = np.load(p) if p.exists() else None
            np.save(p, tr)
            msg = f"  {p.name}: {len(tr)} trades, total R {tr[:, T_R].sum():+.4f}"
            if old is not None:
                msg += (f"   (was {len(old)} trades, "
                        f"{old[:, T_R].sum():+.4f})")
            print(msg)
    print("\nregenerated. Read the diff before committing it.")
    return 0


if __name__ == "__main__":
    if "--regenerate" in sys.argv:
        raise SystemExit(regenerate())
    print(__doc__)
