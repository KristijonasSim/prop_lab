"""H-047 stage 2 - is there a TAIL? The H-008 test, applied to this hypothesis.

Stage 1 measured quintiles and found a real signal under the cost bar. A
quintile is the mean over the widest 20% of moves; a strategy trades the tail.
This asks whether the tail is any better, and it is the test that killed H-008:
if a 4-sigma move reverts no harder than a 1.5-sigma one, there is nothing here
that a narrower entry can reach.

THE READOUT IS ONE POSITION'S RETURN, not a spread. `-sign(z) x forward` in bps
is what the fade earns on the bar it fires, so it can be compared with a round
trip directly and without halving anything.

Run:  .venv/bin/python strategies/partrev/stage2_tail.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from core.markets import load                                   # noqa: E402
from core.run_hypothesis import window                          # noqa: E402
from core.universe import STANDARD                              # noqa: E402
from strategies.partrev.stage1_response import (NT, TF, rt_bps, table)

OUT = ROOT / "backtests" / "partrev"
HORIZONS = (6, 12)
NDEC = 10
TAIL = 0.01
N_NULL = 500
SEED = 20260915


def fade_bps(z: np.ndarray, fwd: np.ndarray) -> float:
    """What one faded position earns, in bps, before costs."""
    return float((-np.sign(z) * fwd).mean())


def null_fade(z: np.ndarray, fwd: np.ndarray, h: int, seeds: int = N_NULL) -> np.ndarray:
    """Blocks of length h, so the overlap in `fwd` survives and the pairing does not."""
    n = len(fwd)
    L = max(h, 1)
    nb = n // L
    if nb < 10:
        return np.full(seeds, np.nan)
    base = fwd[:nb * L].reshape(nb, L)
    tail = fwd[nb * L:]
    s = -np.sign(z)
    rng = np.random.default_rng(SEED)
    out = np.empty(seeds)
    for i in range(seeds):
        f = np.concatenate([base[rng.permutation(nb)].ravel(), tail])
        out[i] = float((s * f).mean())
    return out


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    t0, t1 = window(STANDARD, [TF])
    rec: dict = {"window": [str(t0.date()), str(t1.date())], "tf": TF,
                 "horizons": list(HORIZONS), "tail": TAIL, "markets": {}}
    rising, clears = {h: 0 for h in HORIZONS}, {h: 0 for h in HORIZONS}

    for sym in STANDARD:
        d = load(sym, TF)
        d = d[(d.index >= t0) & (d.index <= t1)]
        rt2 = 2.0 * rt_bps(sym)
        rec["markets"][sym] = {"rt_2x": round(rt2, 3)}
        print(f"\n=== {sym}   2x round trip {rt2:.2f}bps ===")
        for h in HORIZONS:
            t = table(d, h)
            ter = pd.qcut(t.rv.rank(method="first"), NT, labels=False)
            thin = t[ter == 0]
            z, f = thin.z.to_numpy(), thin.fwd.to_numpy()
            az = np.abs(z)
            dec = pd.qcut(pd.Series(az).rank(method="first"), NDEC, labels=False).to_numpy()
            by = [fade_bps(z[dec == g], f[dec == g]) for g in range(NDEC)]
            cut = np.quantile(az, 1 - TAIL)
            m = az >= cut
            tail_bps = fade_bps(z[m], f[m])
            nd = null_fade(z[m], f[m], h)
            p = float((nd >= tail_bps).mean())
            # "rising" = the top three deciles average above the bottom three,
            # and the top decile above the median decile. Two conditions, so a
            # single noisy decile cannot carry it.
            rise = (np.mean(by[-3:]) > np.mean(by[:3])) and (by[-1] > by[NDEC // 2])
            ok = tail_bps > rt2
            rising[h] += bool(rise)
            clears[h] += bool(ok)
            print(f"  h={h:2d}  deciles of |z|: " + " ".join(f"{x:+.2f}" for x in by))
            print(f"        top {TAIL:.0%} (n={int(m.sum())}): {tail_bps:+.2f}bps "
                  f"vs bar {rt2:.2f}  p={p:.3f}   rising={'YES' if rise else 'no'}"
                  f"  clears={'YES' if ok else 'no'}")
            rec["markets"][sym][f"h{h}"] = {
                "deciles": [round(x, 3) for x in by], "n_tail": int(m.sum()),
                "tail_bps": round(tail_bps, 3), "p": p,
                "rising": bool(rise), "clears": bool(ok),
                "tail_over_bar": round(tail_bps / rt2, 3)}

    print("\n=== GATE, against the addendum in PREREG.md ===")
    best = max(HORIZONS, key=lambda h: (rising[h], clears[h]))
    for h in HORIZONS:
        print(f"  h={h:2d}: rising on {rising[h]}/6, tail clears 2x cost on {clears[h]}/6")
    alive = rising[best] >= 4 and clears[best] >= 4
    print(f"\nH-047: {'ALIVE - build it' if alive else 'DEAD at gate 1'}")
    rec |= {"rising": rising, "clears": clears, "alive": bool(alive)}
    (OUT / "stage2.json").write_text(json.dumps(rec, indent=1, default=float))
    print(f"wrote {OUT / 'stage2.json'}")


if __name__ == "__main__":
    main()
