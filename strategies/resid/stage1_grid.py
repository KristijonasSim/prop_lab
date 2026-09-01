"""H-008 stage 1 — full grid with a paired-shuffle null.

The null matters more here than anywhere else in the repo. H-005 was rejected
precisely because a fade rule is EASIER to satisfy on shuffled data than on real
data — a permuted series reverts around its extremes more readily than a real
trending one. So a residual-fade result that does not clearly beat its own null
means nothing, and five seeds are run so the null is read as a distribution.

The shuffle is applied per coin at 15m before resampling, with a different seed
per coin, which also destroys the cross-coin co-movement the beta is computed
from — exactly the structure this hypothesis claims to exploit.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from core import data as crypto_data                                 # noqa: E402
from strategies.vwap.stage3_timeframes import shuffle_market_paired  # noqa: E402
from strategies.xsec.xsec import panel                               # noqa: E402
from strategies.resid import resid                                   # noqa: E402

OUT = ROOT / "backtests" / "resid"
OUT.mkdir(parents=True, exist_ok=True)

SYMS = {"BTCUSDT": "BTC/USDT", "ETHUSDT": "ETH/USDT", "SOLUSDT": "SOL/USDT",
        "BNBUSDT": "BNB/USDT", "XRPUSDT": "XRP/USDT"}
COINS = ["ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]     # BTC is the factor
START, END = "2020-08-12", "2026-09-01"

COST_BPS = 7.0          # Binance spot taker 5bps + 2bps slippage, per side

BETA_WINS = [50, 100, 200]
LOOKBACKS = [2, 4, 8, 16]
Z_THRS = [1.5, 2.0, 2.5, 3.0]
HOLDS = [1, 2, 4]
NSEEDS = 5


def load_panels(shuffle_seed: int | None = None):
    raw = {}
    for sym, ccxt_sym in SYMS.items():
        d = crypto_data.load(ccxt_sym, "15m")
        d = d[(d.index >= START) & (d.index < END)]
        if shuffle_seed is not None:
            d = shuffle_market_paired(d, seed=abs(hash((sym, shuffle_seed, "h008"))) % 2**31)
        raw[sym] = d
    return {tf: panel({s: resid.resample(raw[s], rule) for s in raw})
            for tf, (rule, _bpd) in resid.TFS.items()}


def grid():
    for tf in resid.TFS:
        for bw in BETA_WINS:
            for L in LOOKBACKS:
                for z in Z_THRS:
                    for H in HOLDS:
                        for hedged in (True, False):
                            yield dict(tf=tf, beta_win=bw, L=L, z_thr=z,
                                       H=H, hedged=hedged)


def run_all(panels, tag: str) -> pd.DataFrame:
    rows = []
    for cfg in grid():
        pan = panels[cfg["tf"]]
        bpd = resid.TFS[cfg["tf"]][1]
        tr = resid.run(pan, COINS, beta_win=cfg["beta_win"], L=cfg["L"],
                       H=cfg["H"], z_thr=cfg["z_thr"], hedged=cfg["hedged"],
                       cost_bps=COST_BPS)
        s = resid.summarise(tr, hold_hours=24.0 / bpd * cfg["H"], n_books=len(COINS))
        if not s:
            continue
        rows.append({**cfg, "tag": tag, **s})
    return pd.DataFrame(rows)


def main():
    print("real grid ...")
    real = run_all(load_panels(), "real")
    real.to_csv(OUT / "stage1_real.csv", index=False)
    print(f"real: {len(real)} configs")

    nulls = []
    for seed in range(NSEEDS):
        print(f"null seed {seed} ...")
        nulls.append(run_all(load_panels(shuffle_seed=seed), f"null{seed}"))
    null = pd.concat(nulls, ignore_index=True)
    null.to_csv(OUT / "stage1_null.csv", index=False)

    gate = 1.20
    print("\n" + "=" * 70)
    print("BEFORE COSTS (0x) — is the residual reverting at all?")
    print(f"  real  median {real.pf_0x.median():.3f}   best {real.pf_0x.max():.3f}"
          f"   >1.0: {100*float((real.pf_0x > 1).mean()):.1f}%")
    print(f"  null  median {null.pf_0x.median():.3f}   best {null.pf_0x.max():.3f}"
          f"   >1.0: {100*float((null.pf_0x > 1).mean()):.1f}%")

    print(f"\nconfigs clearing PF {gate} at 2x cost")
    print(f"  real          {int((real.pf_2x >= gate).sum())} of {len(real)}")
    ns = []
    for seed in range(NSEEDS):
        n = null[null.tag == f"null{seed}"]
        c = int((n.pf_2x >= gate).sum())
        ns.append(c)
        print(f"  null seed {seed}   {c} of {len(n)}")
    print(f"  null mean {np.mean(ns):.1f}")

    print(f"\nbest real PF@2x  {real.pf_2x.max():.3f}")
    print(f"best null PF@2x  {null.pf_2x.max():.3f}")
    print(f"median real PF   {real.pf.median():.3f}   median null PF {null.pf.median():.3f}")

    print("\nhedged vs unhedged (real, median):")
    print(real.groupby('hedged')[['pf_0x', 'pf', 'pf_2x', 'tpd']].median().round(3))


if __name__ == "__main__":
    main()
