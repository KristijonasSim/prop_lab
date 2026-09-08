"""Does the MA200 gate beat a gate that knows nothing? The control for ma_gate.py.

WHY THIS EXISTS. `ma_gate.py` showed the gate lifting XAUUSD 4h from 47.1% pass /
97.7 days to 64.9% / 75.5, and reaching 60% pass in 35.0 days where the ungated
strategy never reaches 60% at all. That gate was CHOSEN as the best of 25
candidates screened on the same three years it is now scored on. A selection step
that size buys a lift on its own, and this project has published exactly that
mistake before.

THE CONTROL. Keep the gate's shape and destroy its meaning. The real gate is a
persistent up/down sign that spends long runs on one side; a plain shuffle would
make it flicker every bar and reject nearly everything, which is not a fair
comparison but an easier one. So the sign series is BLOCK-shuffled at the length
of its own median run, which preserves both the duty cycle (how often it says
yes) and the persistence (how long it says it for), and destroys only the one
thing that matters: whether it is aligned with the price it is gating.

If a gate carrying no information does what the real one does, the real one is
search noise. H-009 was accepted on exactly this test - "a shuffled gate hurts".

Run: .venv/bin/python strategies/vwapbreak/research/gate_null.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from core.run_hypothesis import run_market, window                 # noqa: E402
from strategies.vwapbreak.research.ma_gate import MaSlopeGated     # noqa: E402
from strategies.vwapbreak.strategy import STRATEGY                 # noqa: E402

SYM = "XAUUSD"
#: 4h is where the gate did something. 1h is included because the gate made it
#: WORSE there (38.0 -> 64.9 days) and a control that only runs where the result
#: was good is not a control.
TFS = ("4h", "1h")
SEEDS = (0, 1, 2)
UNIVERSE = {"FX": ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD"],
            "Metals/Energy": ["XAUUSD", "XAGUSD", "WTI"],
            "Crypto": ["BTCUSDT", "ETHUSDT", "SOLUSDT"]}


def _median_run(sign: np.ndarray) -> int:
    """Median length of a constant run in a boolean series."""
    s = sign.astype(np.int8)
    change = np.flatnonzero(np.diff(s)) + 1
    runs = np.diff(np.r_[0, change, len(s)])
    runs = runs[runs > 0]
    return int(max(2, np.median(runs))) if len(runs) else 2


class ShuffledGate(MaSlopeGated):
    """The MA gate with its sign series block-shuffled. Same shape, no meaning."""

    name = "vwapbreak_gatenull"

    def __init__(self, seed: int, period: int = 200):
        super().__init__(period)
        self.seed = seed

    def features(self, df: pd.DataFrame):
        f = dict(STRATEGY.features(df))
        m = pd.Series(df.close.values).rolling(self.period,
                                               min_periods=self.period).mean().values
        rising = np.r_[np.nan, np.diff(m)]
        ok = np.isfinite(rising)
        sign = rising > 0
        if ok.sum() > 10:
            live = sign[ok]
            b = _median_run(live)
            n_blocks = int(np.ceil(len(live) / b))
            pad = n_blocks * b - len(live)
            blocks = np.concatenate([live, live[:pad]]).reshape(n_blocks, b)
            rng = np.random.default_rng(1000 + self.seed)
            rng.shuffle(blocks, axis=0)
            sign = sign.copy()
            sign[ok] = blocks.reshape(-1)[:len(live)]
        z = np.array(f["z"], dtype=float)
        block = ((sign & ok) & (z < 0)) | ((~sign & ok) & (z > 0)) | ~ok
        z[block] = np.nan
        f["z"] = z
        return f


def summarise(res: dict) -> dict:
    hit = [x for x in res.get("rules", []) if x.get("days60")]
    b = min(hit, key=lambda x: x["days60"]) if hit else None
    return {"pf_2x": res.get("pf_2x"), "pass_pct": res.get("pass_pct"),
            "days": res.get("days_to_pass"),
            "days60": b["days60"] if b else None,
            "pass60": b["pass60"] if b else None,
            # kept so the noise band can be read at ANY risk level, not only at
            # the rung the scorer picked. Kris trades at a risk he chooses.
            "ladder": res.get("ladder", []),
            "rules": res.get("rules", [])}


def main() -> int:
    syms = [s for v in UNIVERSE.values() for s in v]
    span = window(syms, ["1h", "4h"])
    print(f"window {span[0].date()} -> {span[1].date()}   "
          f"block-shuffled gate, {len(SEEDS)} seeds\n")

    out = {}
    for tf in TFS:
        arms = [("real gate", MaSlopeGated())]
        arms += [(f"shuffled gate seed {s}", ShuffledGate(s)) for s in SEEDS]
        for tag, strat in arms:
            res = run_market(strat, SYM, tf, pipe_kw={}, null_seeds=0, span=span)
            res.pop("_trades", None)
            s = summarise(res)
            out[f"{tf}|{tag}"] = s
            d60 = f"{s['days60']:.1f}" if s["days60"] else "never"
            days = f"{s['days']:.1f}" if s["days"] else "—"
            pf2 = f"{s['pf_2x']:.3f}" if s["pf_2x"] else "—"
            print(f"{tf:>3s}  {tag:22s}  PF@2x {pf2:>6s}  "
                  f"pass {s['pass_pct']:5.1f}%  days {days:>7s}"
                  f"  days@60% {d60:>7s}")

    dest = ROOT / "backtests" / "vwapbreak" / "gate_null.json"
    dest.write_text(json.dumps(out, indent=1, default=str))
    print(f"\nwrote {dest.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
