"""H-002 declared against `core.strategy.Strategy`. Item 4, step 2.

A DECLARATION, NOT A REWRITE. Every line of arithmetic still lives in
`engine.py` and `sweep.py`; this file only says "the vwap hypothesis is a
Strategy, and here is where each piece of it is". `tests/test_golden.py` pins
the trade lists precisely so a port like this cannot quietly change one.

vwap was ported first because it is the better-evidenced kernel: it is the only
one that has been through NautilusTrader trade by trade.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from core.strategy import Strategy                             # noqa: E402,F401
from strategies.vwap import sweep as VS                        # noqa: E402
from strategies.vwap.stage3_timeframes import TFS, build_grid  # noqa: E402


class VwapStrategy:
    """Five model families around the volume-weighted average price."""

    name = "vwap"
    #: what column 7 of the trade array means for this kernel
    extra_column = "sess"

    def features(self, df: pd.DataFrame):
        """(atr, rvol, atr_rank, ema). Backward-looking only - `rvol` and
        `atr_rank` carry their own `.shift(1)` at construction, which is why a
        filter may read them at `entry_i` and nothing else."""
        return VS.features(df)

    def grid(self, tf: str = "1h") -> list[dict]:
        """Every configuration, sized per timeframe so a hold horizon in hours
        means the same thing on 5m as on 4h."""
        return build_grid(TFS[tf][1])

    def new_cache(self) -> dict:
        """The anchored VWAP is shared by every configuration on the same bars.
        `Pipeline` builds one of these per fold slice and hands it back on every
        call, so the VWAP is computed once per anchor instead of once per config."""
        return {"vw_cache": {}}

    def run(self, df: pd.DataFrame, cfg: dict,
            fee_bps: float, slip_bps: float,
            feats=None, vw_cache: dict | None = None) -> np.ndarray:
        """One configuration on one market. `vw_cache` is threaded through
        because the anchored VWAP is shared across configurations and rebuilding
        it per config is most of the sweep's cost."""
        full = dict(VS.DEFAULTS) | cfg
        return VS.run_one(df, feats if feats is not None else self.features(df),
                          {} if vw_cache is None else vw_cache,
                          full, fee_bps, slip_bps)


STRATEGY = VwapStrategy()
