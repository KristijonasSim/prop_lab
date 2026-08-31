"""ORB deep test — stage 1: full parameter grid, IS window, cost ladder.

Base venue assumption: Binance USDT-M perpetual, taker 0.05%/side (5 bps) plus
2 bps slippage = 7 bps/side. Reported at 0x / 1x / 2x / 3x costs. The 0x run is
the diagnostic that separates "no edge" from "edge eaten by fees".
"""

from __future__ import annotations

import sys, time
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from core import data                              # noqa: E402
from strategies.orb.sweep import sweep, DEFAULTS    # noqa: E402

OUT = ROOT / "backtests" / "orb"
OUT.mkdir(parents=True, exist_ok=True)

IS_START, IS_END = "2018-01-01", "2024-01-01"
OOS_START, OOS_END = "2024-01-01", "2026-09-01"

FEE_BPS, SLIP_BPS = 5.0, 2.0     # per side, 1x

HOURS = [0, 4, 7, 8, 12, 13, 16, 20]
OR_BARS = [1, 2, 4, 8, 16]                 # 15m 30m 1h 2h 4h
HOLD_BARS = [8, 16, 32, 96]                # 2h 4h 8h 24h
ENTRY = [0, 1]                             # touch | close-confirm
STOPS = [(0, 0.0), (1, 0.0), (2, 1.0), (2, 2.0)]   # OR-opposite | OR-mid | ATR1 | ATR2
RR = [0.0, 1.0, 1.5, 2.0, 3.0]             # 0 = time exit only
FADE = [0, 1]


def build_grid() -> list[dict]:
    cfgs = []
    for hour in HOURS:
        for ob in OR_BARS:
            for hb in HOLD_BARS:
                if hb <= ob:
                    continue                # need room to trade after the range
                for em in ENTRY:
                    for sm, sa in STOPS:
                        for rr in RR:
                            for fd in FADE:
                                # An OR-edge stop is meaningless on a fade: the
                                # entry is already through that edge, so the stop
                                # lands a hair away. Fades get ATR stops only.
                                if fd == 1 and sm in (0, 1):
                                    continue
                                c = dict(DEFAULTS)
                                c.update(hour=hour, or_bars=ob, hold_bars=hb,
                                         entry_mode=em, stop_mode=sm,
                                         stop_atr_mult=sa, rr=rr, fade=fd)
                                cfgs.append(c)
    return cfgs


def main():
    df = data.load("BTC/USDT", "15m")
    is_df = df[(df.index >= IS_START) & (df.index < IS_END)]
    cfgs = build_grid()
    print(f"configs {len(cfgs)} | IS bars {len(is_df)} "
          f"{is_df.index[0].date()} -> {is_df.index[-1].date()}", flush=True)

    frames = []
    for mult in (0.0, 1.0, 2.0, 3.0):
        t = time.time()
        r = sweep(is_df, cfgs, fee_bps=FEE_BPS * mult, slip_bps=SLIP_BPS * mult,
                  label=f"IS_cost{mult:g}x")
        r["cost_mult"] = mult
        frames.append(r)
        print(f"  cost {mult:g}x done in {time.time()-t:.0f}s", flush=True)

    out = pd.concat(frames, ignore_index=True)
    out.to_csv(OUT / "stage1_is_grid.csv", index=False)
    print("saved", OUT / "stage1_is_grid.csv", len(out), "rows")


if __name__ == "__main__":
    main()
