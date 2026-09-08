"""What H-016's board record depends on. Same contract as strategies/vwap/manifest.py.

Item 1 of `STEPS_1_2_4.md`. See `core/fingerprint.py` for the two tiers and why
a data file that grew is a note while one that was rewritten is a hard stale.

WHICH STAGE WRITES THE BOARD. `stage11_reprice.py --board` does, not
`stage10_board.py`. Stage 10 runs the walk-forward and writes
`stage10_trades.parquet`; stage 11 re-prices those trades at the MEASURED gold
spread, drops the silver leg, and writes the record that is on the board today.
Running stage 10 alone overwrites that record with the superseded four-leg book
that still contains silver - which is on the do-not-trade list in CLAUDE.md.
Both manifests exist below so each stage fingerprints what it actually used.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
S = ROOT / "strategies" / "ribbon"
D = ROOT / "data"
BT = ROOT / "backtests" / "ribbon"

# The live record: XAUUSD 15m + 30m + 1h, one config per timeframe, walk-forward
# 2024-10 to 2026-06. `sweep.load_tf` maps these labels onto the dukascopy cache.
TFS = {"15m": "15min", "30m": "30min", "1h": "1h"}

# Stage 10 searched both metals across four timeframes before stage 11 cut silver.
SEARCHED = {"XAUUSD", "XAGUSD"}
SEARCHED_TFS = {"15m": "15min", "30m": "30min", "1h": "1h", "4h": "4h"}

KERNELS = [
    S / "engine.py",              # the numba kernel
    S / "ribbon.py",              # RibbonParams + features (the 20 MAs)
    S / "sweep.py",               # grid, COSTS, load_tf, the paired null
    S / "stage6_walkforward.py",  # quarterly blind reselection
    S / "stage10_board.py",       # the walk-forward that produced the trades
    S / "stage11_reprice.py",     # measured repricing, silver dropped, board writer
    ROOT / "core" / "metrics.py",
    # REAL cross-hypothesis dependency, found by core/manifest_audit.py:
    # ribbon/sweep.py imports ASSETS from vwap/stage1_grid.py and the timeframe
    # loader from vwap/stage3_timeframes.py, and vwap/sweep.py pulls in
    # vwap/engine.py. Editing H-002's kernel can therefore move H-016's numbers.
    ROOT / "strategies" / "vwap" / "stage1_grid.py",
    ROOT / "strategies" / "vwap" / "stage3_timeframes.py",
    ROOT / "strategies" / "vwap" / "sweep.py",
    ROOT / "strategies" / "vwap" / "engine.py",
]

# Trades stand, summary does not. See core/fingerprint.py for why these are a
# note and not a hard stale.
SCORING = [
    ROOT / "core" / "board.py",
    ROOT / "core" / "riskladder.py",
    ROOT / "core" / "prop_rules.py",
]

DATA = [
    *[D / f"XAUUSD_dukascopy_{rule}.parquet" for rule in TFS.values()],
    BT / "stage10_trades.parquet",   # the trades stage 11 re-prices
    BT / "stage6_stitched.csv",      # the paired-null table stage 11 reads
]

# Stage 11 charges a MEASURED spread per symbol rather than sweep.COSTS. Gold got
# 1.6x cheaper and silver 2.0x more expensive, which is what killed the silver
# leg for the second time.
COSTS = {
    "model": "bps per side, measured from Dukascopy ticks (core/fx_spread.py)",
    "XAUUSD": 0.915,
    "assumed": "sweep.COSTS[sym] = (fee_bps, slip_bps, min_risk_bps); "
               "XAUUSD was (1.00, 0.50, 3.0)",
    "gate_multiple": 2,
}

# The stage whose write_board call produces backtests/ribbon/board.json - stage
# 11, not stage 10. core/manifest_audit.py walks its import graph.
WRITER = S / "stage11_reprice.py"

# Stage 11 re-prices stage 10's cached trades and reads stage 6's stitched null
# table, so all three are roots of the provenance chain.
ROOTS = [WRITER, S / "stage10_board.py", S / "stage6_walkforward.py"]

MANIFEST = {"kernels": KERNELS, "scoring": SCORING,
            "data": DATA, "costs": COSTS}

# stage10_board.py writes the SUPERSEDED four-leg book (3 gold + silver) at
# ASSUMED cost. Kept so the before/after stays reproducible; fingerprinted with
# its own inputs so the record can never claim stage 11's provenance.
MANIFEST_STAGE10 = {
    "kernels": [k for k in KERNELS if k.name != "stage11_reprice.py"],
    "scoring": SCORING,
    "data": [D / f"{sym}_dukascopy_{rule}.parquet"
             for sym in sorted(SEARCHED) for rule in SEARCHED_TFS.values()],
    "costs": {"model": "sweep.COSTS, ASSUMED not measured",
              "note": "superseded by stage11_reprice.py"},
}
