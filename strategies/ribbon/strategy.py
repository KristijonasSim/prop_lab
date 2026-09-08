"""H-016 declared against `core.strategy.Strategy`. Item 4, step 3.

Same rule as `strategies/vwap/strategy.py`: a declaration, not a rewrite. The
arithmetic stays in `engine.py` and `ribbon.py`.

Ribbon leans harder on the shared suite than vwap does. Its own
`test_parity.py` covers the twenty moving averages and nothing else, and the
kernel has never been through a second engine - so the truncation, degenerate
and golden tests are most of the evidence there is about it.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from core.strategy import Strategy                             # noqa: E402,F401
from strategies.ribbon import sweep as RS                      # noqa: E402

#: The kernel takes every switch explicitly; a partial config is a bug, not a
#: default. These are the values the board's own legs were selected from.
BASE = dict(mode=0, entry_thr=0.8, require_flip=1, squeeze_n=0.0,
            min_strength=0.0, trail_mode=1, trail_k=8.0, stop_k=2.0,
            trail_start_r=0.0, rr=0.0, max_hold_bars=0, flip_exit=1,
            dir_mode=0, min_risk_bps=3.0)


class RibbonStrategy:
    """Twenty moving averages agreeing across timescales."""

    name = "ribbon"
    #: maximum favourable excursion, in R - the trailing stop's diagnostic
    extra_column = "mfe"

    def features(self, df: pd.DataFrame):
        """agree / prev_agree / nflat / strength / atr / live, plus the raw OHLC
        the kernel indexes directly."""
        return RS.ribbon_inputs(df)

    def grid(self, tf: str = "1h") -> list[dict]:
        return RS.build_grid(RS.TFS[tf][1])

    def new_cache(self) -> dict:
        """Nothing config-independent to reuse beyond `features`, which the
        pipeline already computes once per slice."""
        return {}

    def run(self, df: pd.DataFrame, cfg: dict,
            fee_bps: float, slip_bps: float, feats=None) -> np.ndarray:
        full = dict(BASE) | cfg
        inp = feats if feats is not None else self.features(df)
        return RS.run_one(inp, full, fee_bps, slip_bps,
                          full.get("min_risk_bps", 3.0))


STRATEGY = RibbonStrategy()
