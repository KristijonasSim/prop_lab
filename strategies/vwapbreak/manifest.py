"""What H-027's board record depends on. See core/fingerprint.py."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
S = ROOT / "strategies" / "vwapbreak"

KERNELS = [
    S / "strategy.py",
    ROOT / "strategies" / "vwap" / "sweep.py",      # vwap_series
    ROOT / "strategies" / "vwap" / "engine.py",     # imported by sweep
    ROOT / "core" / "markets.py",
    ROOT / "core" / "pipeline.py",
    ROOT / "core" / "nulls.py",
    ROOT / "core" / "metrics.py",
    ROOT / "core" / "strategy.py",
]
SCORING = [ROOT / "core" / "board.py", ROOT / "core" / "riskladder.py",
           ROOT / "core" / "prop_rules.py"]
DATA: list[Path] = []
COSTS = {"model": "core/markets.py, maker entry / taker exit",
         "gate_multiple": 2}

WRITER = S / "hypothesis.py"
ROOTS = [WRITER]
MANIFEST = {"kernels": KERNELS, "scoring": SCORING,
            "data": DATA, "costs": COSTS}
