"""What H-002's board record depends on. Read by the board stage, not by humans.

Item 1 of `STEPS_1_2_4.md`. `core/fingerprint.py` hashes everything named here
and writes the result into `backtests/vwap/board.json`; `core/build_scoreboard.py`
rehashes it at render time and flags the card if anything moved.

The rule for `KERNELS`: if editing the file could change a single trade, it
belongs here. Listing one file too many costs a rerun. Listing one too few is
how H-009 kept a score of 8.9 on a kernel that had already been found to look
ahead.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
S = ROOT / "strategies" / "vwap"
D = ROOT / "data"
BT = ROOT / "backtests" / "vwap"

# The board on disk is the GOLD book: XAUUSD 5m + 30m + 1h + 4h, walk-forward
# 2024-09 to 2026-05, at the MEASURED 1.83bps round trip. Crypto is not here; it
# died to the 2026-09-06 look-ahead fix.
TFS = {"5m": "5min", "30m": "30min", "1h": "1h", "4h": "4h"}

KERNELS = [
    S / "engine.py",              # the numba kernel: bands, entries, exits, costs
    S / "sweep.py",               # config expansion and the (n, 8) trade array
    S / "stage1_grid.py",         # ASSETS: the per-market cost triples
    S / "stage3_timeframes.py",   # load_tf + TFS: which bars a leg actually sees
    S / "stage6_walkforward.py",  # quarterly blind reselection - produced the trades
    S / "stage18_goldbook.py",    # repricing, cell/book construction, selection
    S / "stage20_deadfix.py",     # the two dead-bar fixes, and the board writer
    ROOT / "core" / "metrics.py", # resolution_estimate, used inside the sweep
]

# Trades stand, summary does not. See core/fingerprint.py for why these are a
# note and not a hard stale.
SCORING = [
    ROOT / "core" / "board.py",
    ROOT / "core" / "riskladder.py",
    # The evaluation rules themselves: profit target, daily cap, max loss. Change
    # these and every pass rate and expected-days number on the card moves.
    ROOT / "core" / "prop_rules.py",
]

DATA = [
    # raw bars, one file per traded leg
    *[D / f"XAUUSD_dukascopy_{rule}.parquet" for rule in TFS.values()],
    # the walk-forward output the board record was actually built from, and its
    # paired null. Fingerprinting the raw bars alone would miss a board rebuilt
    # from a stale trades file.
    BT / "stage6_trades_xauusd_deadfix.parquet",
    BT / "stage6_trades_xauusd_shuffled_paired_deadfix.parquet",
]

COSTS = {
    "rt_bps": 1.83,          # 1.671 mean spread + 0.15 commission, MEASURED
    "assumed_rt_bps": 3.00,  # what the walk-forward charged before repricing
    "gate_multiple": 2,      # every headline is quoted at 2x as well
    "basis": "478 sampled hours of Dukascopy XAUUSD ticks, core/fx_spread.py",
}

# The stage whose write_board call produces backtests/vwap/board.json.
# core/manifest_audit.py walks this file's import graph and fails if anything it
# reaches is missing from KERNELS - which is what stops a kernel from silently
# escaping the stale flag by not being listed.
WRITER = S / "stage20_deadfix.py"

# Every stage that produced something fingerprinted here. The writer reads a
# cached trades parquet and never imports the kernel, so walking the writer alone
# would miss the entire simulation.
ROOTS = [WRITER, S / "stage6_walkforward.py"]

MANIFEST = {"kernels": KERNELS, "scoring": SCORING,
            "data": DATA, "costs": COSTS}

# stage18_goldbook.py writes the SAME board record from the PRE-dead-bar-fix
# walk-forward. It is superseded by stage 20 and kept only so the before/after
# stays reproducible, so it declares the pre-fix trades file and not stage 20's
# kernel. Fingerprinting it with the deadfix inputs would be a false provenance -
# the point of this whole item is that a record says what actually produced it.
MANIFEST_PREFIX = {
    "kernels": [k for k in KERNELS if k.name != "stage20_deadfix.py"],
    "scoring": SCORING,
    "data": [*[D / f"XAUUSD_dukascopy_{rule}.parquet" for rule in TFS.values()],
             BT / "stage6_trades.parquet",
             BT / "stage6_trades_shuffled_paired.parquet"],
    "costs": COSTS | {"note": "pre-dead-bar-fix walk-forward"},
}
