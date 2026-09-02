"""H-007 stage 1 — full cross-sectional grid, real data and paired-shuffle null.

Every configuration is run twice: once on the real panel and once on a panel
where each coin has been paired-shuffled (`shuffle_market_paired` — each bar
keeps its own volume, only the sequence is destroyed). Each coin gets its own
seed, so the null also destroys the cross-coin co-movement that a five-name
spread lives on. Reading the null as a distribution, not a single number, is a
rule this repo learned the hard way; NSEEDS shuffles are run.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from core import data as crypto_data                                 # noqa: E402
from strategies.vwap.stage3_timeframes import (shuffle_market_paired,  # noqa: E402
                                               null_seed)
from strategies.xsec import xsec                                     # noqa: E402

OUT = ROOT / "backtests" / "xsec"
OUT.mkdir(parents=True, exist_ok=True)

COINS = {"BTCUSDT": "BTC/USDT", "ETHUSDT": "ETH/USDT", "SOLUSDT": "SOL/USDT",
         "BNBUSDT": "BNB/USDT", "XRPUSDT": "XRP/USDT"}
START, END = "2020-08-12", "2026-09-01"

# Binance spot taker 5bps + 2bps slippage, per side.
COST_BPS = 7.0

LOOKBACKS = [3, 6, 12, 24, 48]
KS = [1, 2]
# hold = H rebalance periods. Rebalancing every bar pays the round trip far too
# often; longer holds are the only way the ranking gets a fair test at cost.
HOLDS = {"1h": [1, 4, 12], "4h": [1, 3, 6], "1d": [1, 3, 7]}
NSEEDS = 5


def load_panel(shuffle_seed: int | None = None) -> dict[str, dict[str, pd.DataFrame]]:
    """Returns {tf: aligned panel}. Shuffle is applied to the 15m bars, once,
    before resampling, so every timeframe sees the same null."""
    raw = {}
    for sym, ccxt_sym in COINS.items():
        d = crypto_data.load(ccxt_sym, "15m")
        d = d[(d.index >= START) & (d.index < END)]
        if shuffle_seed is not None:
            d = shuffle_market_paired(d, seed=null_seed(sym, shuffle_seed, "h006"))
        raw[sym] = d
    return {tf: xsec.panel({s: xsec.resample(raw[s], rule) for s in raw})
            for tf, (rule, _bpd) in xsec.TFS.items()}


def grid():
    for signal in xsec.SIGNALS:
        for tf in xsec.TFS:
            for L in LOOKBACKS:
                for k in KS:
                    for mode in xsec.MODES:
                        if mode == "spread" and 2 * k > len(COINS):
                            continue
                        for H in HOLDS[tf]:
                            yield dict(signal=signal, tf=tf, L=L, k=k,
                                       mode=mode, H=H)


def run_all(panels, tag: str) -> pd.DataFrame:
    rows = []
    for cfg in grid():
        pan = panels[cfg["tf"]]
        bars_per_day = xsec.TFS[cfg["tf"]][1]
        tr = xsec.run(pan, signal=cfg["signal"], L=cfg["L"], H=cfg["H"], k=cfg["k"],
                      mode=cfg["mode"], cost_bps=COST_BPS)
        s = xsec.summarise(tr, hold_hours=24.0 / bars_per_day * cfg["H"])
        if not s:
            continue
        rows.append({**cfg, "tag": tag, **s})
    return pd.DataFrame(rows)


def main():
    print("loading real panel ...")
    real = run_all(load_panel(), "real")
    real.to_csv(OUT / "stage1_real.csv", index=False)
    print(f"real: {len(real)} configs")

    nulls = []
    for seed in range(NSEEDS):
        print(f"null seed {seed} ...")
        nulls.append(run_all(load_panel(shuffle_seed=seed), f"null{seed}"))
    null = pd.concat(nulls, ignore_index=True)
    null.to_csv(OUT / "stage1_null.csv", index=False)

    gate = 1.20
    print("\n" + "=" * 70)
    print(f"configs clearing PF {gate} at 2x cost")
    print(f"  real          {int((real.pf_2x >= gate).sum())} of {len(real)}")
    for seed in range(NSEEDS):
        n = null[null.tag == f"null{seed}"]
        print(f"  null seed {seed}   {int((n.pf_2x >= gate).sum())} of {len(n)}")
    print(f"\nbefore costs (0x) — does the ranking have ANY edge?")
    print(f"  best real PF@0x   {real.pf_0x.max():.3f}   median {real.pf_0x.median():.3f}")
    print(f"  best null PF@0x   {null.pf_0x.max():.3f}   median {null.pf_0x.median():.3f}")
    print(f"  real configs PF@0x > 1.0:  {int((real.pf_0x > 1.0).sum())} of {len(real)}")
    print(f"  null configs PF@0x > 1.0:  {int((null.pf_0x > 1.0).sum())} of {len(null)}"
          f"  ({100*float((null.pf_0x > 1.0).mean()):.1f}%)")
    print(f"\nbest real PF@2x  {real.pf_2x.max():.3f}")
    print(f"best null PF@2x  {null.pf_2x.max():.3f}")
    print(f"median real PF   {real.pf.median():.3f}")
    print(f"median null PF   {null.pf.median():.3f}")


if __name__ == "__main__":
    main()
