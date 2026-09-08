"""One interface over both kernels, so an invariant is written once.

Item 2 of `STEPS_1_2_4.md`. Every test in this directory runs against every
kernel through `KERNELS`. Adding a third hypothesis means adding an adapter
here, and it inherits the whole suite - which is also the shape item 4 turns
into `core/strategy.py`, so this is a rehearsal for that refactor, not throwaway.

The contract is `core/KERNEL_CONTRACT.md` section 1.1: an (n, 8) float array,
one row per trade, columns entry_i, exit_i, dir, entry_px, exit_px, r, reason,
and one kernel-specific eighth.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# Column indices are shared by both kernels for 0-6; only column 7 differs
# (vwap stores the session, ribbon the maximum favourable excursion).
T_ENTRY_I, T_EXIT_I, T_DIR, T_ENTRY_PX, T_EXIT_PX, T_R, T_REASON = range(7)


@dataclass(frozen=True)
class Kernel:
    name: str
    run: Callable[[pd.DataFrame, dict, float, float], np.ndarray]
    cfg: dict
    #: a second, deliberately different configuration - one test passing on one
    #: lucky parameter set is not evidence about the kernel
    cfg_alt: dict
    file: Path


# --------------------------------------------------------------------------- #
# vwap  (H-002)
# --------------------------------------------------------------------------- #
def _vwap_run(df: pd.DataFrame, cfg: dict, fee_bps: float, slip_bps: float):
    # Through the Strategy declaration (item 4), not around it: if the adapter
    # bypassed it, the interface would be untested decoration.
    from strategies.vwap.strategy import STRATEGY
    return STRATEGY.run(df, cfg, fee_bps, slip_bps)


VWAP = Kernel(
    name="vwap",
    run=_vwap_run,
    cfg=dict(mode=0, band_k=2.0, stop_k=1.0, warmup_bars=8, min_risk_bps=2.0),
    cfg_alt=dict(mode=1, band_k=1.5, stop_mode=1, stop_k=2.0, target_mode=1,
                 rr=2.0, max_hold_bars=24, warmup_bars=4, one_trade=1,
                 min_risk_bps=3.0),
    file=ROOT / "strategies" / "vwap" / "engine.py",
)


# --------------------------------------------------------------------------- #
# ribbon  (H-016)
# --------------------------------------------------------------------------- #
def _ribbon_run(df: pd.DataFrame, cfg: dict, fee_bps: float, slip_bps: float):
    from strategies.ribbon.strategy import STRATEGY
    return STRATEGY.run(df, cfg, fee_bps, slip_bps)


RIBBON = Kernel(
    name="ribbon",
    run=_ribbon_run,
    cfg=dict(),
    cfg_alt=dict(mode=1, entry_thr=0.6, require_flip=0, trail_mode=0,
                 trail_k=4.0, stop_k=1.5, rr=2.0, max_hold_bars=48,
                 flip_exit=0, dir_mode=1),
    file=ROOT / "strategies" / "ribbon" / "engine.py",
)

KERNELS = [VWAP, RIBBON]
IDS = [k.name for k in KERNELS]
