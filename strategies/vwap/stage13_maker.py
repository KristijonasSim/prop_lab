"""H-023 stage 13 — the same VWAP configs priced as a maker instead of a taker.

Stage 12 measured the thing this repo assumed and never checked: on BTCUSDT
USDT-M 15m bars, a resting limit that gets TOUCHED is traded strictly THROUGH
99.8% of the time, and the forward return after a through-fill is within
0.08bps of the return after a touch. The wick-touch fear that set the whole
board's cost policy does not hold on this instrument.

That licenses a question the board has never asked. Every one of the 2,584 fold
configurations behind H-002/H-009/H-017 is `fill_mode=1`: signal on a closed
bar, market order on the next open, 5bps taker + 2bps slippage each side, 14bps
the round trip. A resting limit at the band is 2bps a side and no slippage,
because you set the price. Four regimes, THE SAME CONFIGS in each, so the lift
is a paired difference and not a new fit:

  A  board      fill_mode=1, 5.0 + 2.0    14bps round trip - what the board uses
  B  limit@tkr  fill_mode=0, 5.0 + 2.0    isolates the better ENTRY PRICE alone
  C  mixed      fill_mode=0, 4.5 + 0.0     9bps - maker in, taker out
  D  maker      fill_mode=0, 2.0 + 0.0     4bps - both sides passive

B is the control that separates the two effects. A limit at the band fills at a
better price AND at a lower fee; without B the two are confounded and the whole
gain could be re-priced entry rather than saved cost.

THE FALSIFICATION CONTROL, and it is the point of the mode split. A resting
limit is the natural way to enter a FADE (mode 1) or a PULLBACK (mode 4) - you
want price to come to you. It is structurally wrong for a BREAKOUT (mode 2),
where the entry is above the market and has to cross. So mode 2 is run
alongside, and it must NOT improve. If maker pricing lifts breakouts as much as
fades, the lift is an artefact of the fill logic and not a real saving.

Scope, stated up front: BTCUSDT only. That is the one market where stage 12
verified the fill assumption on ticks, and quoting this on ETH, SOL or gold
without the same tick check would be exactly the unverified assumption this
whole stage exists to remove.

Run: .venv/bin/python strategies/vwap/stage13_maker.py
"""
from __future__ import annotations

import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from strategies.vwap.sweep import sweep, features, DEFAULTS          # noqa: E402
from strategies.vwap.stage3_timeframes import (load_tf, ANCHORS,     # noqa: E402
                                               FILTERS, TFS)

OUT = ROOT / "backtests" / "queue"
OUT.mkdir(parents=True, exist_ok=True)

SYM = "BTCUSDT"
USE_TFS = ("1h", "4h")
# A representative filter subset, not all seven. This stage measures a PAIRED
# difference - the same config priced four ways - so the lift is identified by
# the pairing, not by grid size. Dropping 15m and four filters takes the run
# from ~70 minutes to ~10 without changing what is being compared.
USE_FILTERS = ("none", "rvol>2.0", "ATRrank>0.5")
# 1 = FADE and 4 = PULLBACK are limit-friendly. 2 = BREAK is the control that
# must not benefit: you cannot rest a buy limit above the market.
MODES = (1, 4, 2)
MODENAME = {1: "fade", 4: "pullback", 2: "break(control)"}

REGIMES = {
    #             fill_mode  fee   slip   round-trip bps
    "A_board":    (1,        5.0,  2.0),      # 14
    "B_limit@tkr":(0,        5.0,  2.0),      # 14, better entry price only
    "C_mixed":    (0,        4.5,  0.0),      # 9
    "D_maker":    (0,        2.0,  0.0),      # 4
}
GATE = 1.20


def build_grid(bars_per_hour: float, modes=MODES) -> list[dict]:
    """The stage-3 grid, restricted to the modes this stage is about."""
    hold_bars = [0] + [max(1, int(round(h * bars_per_hour))) for h in (4, 12)]
    roll = max(20, int(round(24 * 4 * bars_per_hour)))
    cfgs = []
    for ah, am in ANCHORS:
        am2 = roll if ah == -1 else am
        for mode in modes:
            band_ks = [2.0] if mode in (0, 4) else [1.5, 2.0, 2.5]
            targets = [0, 3] if mode in (0, 3, 4) else [0, 1, 2, 3]
            stops = ([(0, 6.0), (1, 6.0)] if mode == 0
                     else [(0, 0.5), (0, 1.0), (1, 1.0), (1, 2.0)])
            for bk in band_ks:
                for sm, sk in stops:
                    for tm in targets:
                        for rr in ([1.0, 2.0, 3.0] if tm == 3 else [0.0]):
                            for hb in hold_bars:
                                for fname in USE_FILTERS:
                                    fover = FILTERS[fname]
                                    c = dict(DEFAULTS)
                                    c.update(anchor_hour=ah, anchor_minute=am2,
                                             mode=mode, band_k=bk,
                                             stop_mode=sm, stop_k=sk,
                                             target_mode=tm, rr=rr,
                                             max_hold_bars=hb,
                                             warmup_bars=max(2, int(bars_per_hour * 2)))
                                    c.update(fover)
                                    c["filter"] = fname
                                    cfgs.append(c)
    return cfgs


def run_tf(tf: str):
    """All four regimes at both cost levels for one timeframe."""
    try:
        df = load_tf(SYM, tf)
    except Exception as e:
        print(f"{tf}: {e}", flush=True)
        return []
    if len(df) < 3000:
        print(f"{tf}: only {len(df)} bars, skipped", flush=True)
        return []
    feats = features(df)
    cfgs = build_grid(TFS[tf][1])
    print(f"{SYM} {tf}: {len(df):,} bars, {len(cfgs)} configs x "
          f"{len(REGIMES)} regimes x 2 cost levels", flush=True)
    frames = []
    for rname, (fm, fee, slip) in REGIMES.items():
        for mult, mname in ((1, "1x"), (2, "2x")):
            use = [dict(c, fill_mode=fm) for c in cfgs]
            r = sweep(df, use, fee * mult, slip * mult, feats=feats,
                      label=f"{tf}|{rname}|{mname}")
            r["tf"], r["regime"], r["cost"] = tf, rname, mname
            frames.append(r)
            print(f"   {tf} {rname:12} {mname}  median PF {r.pf.median():5.3f}  "
                  f"best {r.pf.max():6.3f}  clears {GATE}: "
                  f"{int((r.pf >= GATE).sum()):4d}/{len(r)}", flush=True)
    return frames


def main():
    frames = []
    with ProcessPoolExecutor(max_workers=len(USE_TFS)) as ex:
        for got in ex.map(run_tf, USE_TFS):
            frames.extend(got)
    if not frames:
        sys.exit("no results")
    out = pd.concat(frames, ignore_index=True)
    out.to_parquet(OUT / "stage13_maker.parquet")

    # ---- the paired comparison. Same config, same timeframe, four regimes ----
    key = ["tf", "mode", "anchor_hour", "anchor_minute", "band_k", "stop_mode",
           "stop_k", "target_mode", "rr", "max_hold_bars", "filter"]
    at2x = out[out.cost == "2x"]
    piv = at2x.pivot_table(index=key, columns="regime", values="pf")
    piv = piv.dropna()

    print(f"\n{'=' * 88}\nPAIRED LIFT AT 2x COST — same configs, {len(piv)} of them\n{'=' * 88}")
    print(f"{'mode':16} {'n':>6} {'A board':>9} {'B lim@tkr':>10} "
          f"{'C mixed':>9} {'D maker':>9} {'D-A':>8} {'%better':>8}")
    for m in MODES:
        sub = piv.xs(m, level="mode") if "mode" in piv.index.names else piv
        if not len(sub):
            continue
        d_a = (sub["D_maker"] - sub["A_board"])
        print(f"{MODENAME[m]:16} {len(sub):6d} {sub['A_board'].median():9.3f} "
              f"{sub['B_limit@tkr'].median():10.3f} {sub['C_mixed'].median():9.3f} "
              f"{sub['D_maker'].median():9.3f} {d_a.median():8.3f} "
              f"{100 * (d_a > 0).mean():7.1f}%")

    print(f"\n-- configs clearing PF {GATE} at 2x cost, by mode and regime --")
    g = (at2x.assign(ok=at2x.pf >= GATE)
         .groupby(["mode", "regime"]).ok.sum().unstack().fillna(0).astype(int))
    g.index = [MODENAME.get(i, i) for i in g.index]
    print(g.to_string())

    print("\n-- best config per mode+regime at 2x cost (PF, trades/day, maxDD_R) --")
    b = (at2x.sort_values("pf", ascending=False)
         .groupby(["mode", "regime"])
         .first()[["pf", "trades_per_day", "max_dd_r", "total_r", "tf"]])
    b.index = pd.MultiIndex.from_tuples(
        [(MODENAME.get(m, m), r) for m, r in b.index], names=["mode", "regime"])
    print(b.round(3).to_string())
    print(f"\nwrote {OUT / 'stage13_maker.parquet'}")


if __name__ == "__main__":
    main()
