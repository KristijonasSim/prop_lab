"""ORB stage 14 — the board record, scored the same way as every other idea.

Stage 12 walk-forwarded the filtered family and threw the trades away, keeping
only per-quarter summaries. The strategy board needs the trade series itself:
without it ORB can only be scored on a fitted configuration while H-002 is
scored on walk-forward output, which is not a fair comparison and flatters ORB.

So this re-runs the same walk-forward, keeps the trades and their timestamps,
and hands them to core/board.py. Identical folds, identical grid, identical
selection rule as stage 12 - the only change is that nothing is discarded.
"""
from __future__ import annotations

import sys, time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from core import board                                            # noqa: E402
from core import data as crypto_data                              # noqa: E402
from strategies.orb.sweep import sweep, features, run_one         # noqa: E402
from strategies.orb.engine import T_R, T_ENTRY_I, T_EXIT_I        # noqa: E402
from strategies.orb.stage7_assets import ASSETS                   # noqa: E402
from strategies.orb.stage12_wf_filtered import build, MIN_TRAIN_TRADES  # noqa: E402

FEE, SLIP, MINRISK = ASSETS["BTCUSDT"]


def _fold(args):
    """One quarter: choose on the train slice, trade the test slice."""
    t0s, = args
    t0 = pd.Timestamp(t0s)
    df = crypto_data.load("BTC/USDT", "15m")
    df = df[df.index >= "2018-01-01"]
    train = df[(df.index >= t0 - pd.DateOffset(months=12)) & (df.index < t0)]
    test = df[(df.index >= t0) & (df.index < t0 + pd.DateOffset(months=3))]
    if len(train) < 1000 or len(test) < 500:
        return None

    cfgs = build()
    r = sweep(train, cfgs, fee_bps=FEE, slip_bps=SLIP)
    elig = r[(r.trades >= MIN_TRAIN_TRADES) & r.pf.notna()]
    if elig.empty:
        return None
    best = elig.sort_values("pf", ascending=False).iloc[0]
    cfg = {k: best[k] for k in cfgs[0]}

    feats = features(test)
    tr = run_one(test, feats, cfg, FEE, SLIP)
    tr2 = run_one(test, feats, cfg, FEE * 2, SLIP * 2)     # the 2x cost check
    if len(tr) == 0:
        return {"quarter": str(t0.date()), "train_pf": float(best.pf),
                "r": [], "r2": [], "entry": [], "exit": []}
    return {
        "quarter": str(t0.date()), "train_pf": float(best.pf),
        "r": tr[:, T_R].tolist(),
        "r2": tr2[:, T_R].tolist() if len(tr2) == len(tr) else tr[:, T_R].tolist(),
        "entry": [str(x) for x in test.index[tr[:, T_ENTRY_I].astype(int)]],
        "exit": [str(x) for x in test.index[tr[:, T_EXIT_I].astype(int)]],
    }


def main():
    starts = pd.date_range("2019-01-01", "2026-07-01", freq="3MS", tz="UTC")
    print(f"{len(starts)} quarters", flush=True)

    folds = []
    t0 = time.time()
    with ProcessPoolExecutor(max_workers=10) as ex:
        futs = {ex.submit(_fold, (str(s),)): s for s in starts}
        for fu in as_completed(futs):
            f = fu.result()
            if f:
                folds.append(f)
                print(f"[{time.time()-t0:.0f}s] {f['quarter']}  "
                      f"train {f['train_pf']:.2f}  {len(f['r'])} test trades", flush=True)
    folds.sort(key=lambda f: f["quarter"])

    r = np.concatenate([f["r"] for f in folds if f["r"]])
    r2 = np.concatenate([f["r2"] for f in folds if f["r2"]])
    entry = pd.to_datetime(sum([f["entry"] for f in folds], []), utc=True)
    exit_ = pd.to_datetime(sum([f["exit"] for f in folds], []), utc=True)

    q_above = sum(1 for f in folds if f["r"] and board.pf_of(np.array(f["r"])) > 1)
    consistency = q_above / max(len(folds), 1)

    # ORB's cost ladder: how many of 8,160 configurations per instrument clear
    # PF 1.20 as cost rises. This is its equivalent of the VWAP gate grid.
    import json
    rep = json.loads((ROOT / "backtests" / "orb" / "report_data.json").read_text())
    by_sym: dict[str, dict] = {}
    for row in rep.get("assets", {}).get("ladder", []):
        by_sym.setdefault(row["symbol"], {})[row["cost"]] = row["gate"]
    grid_rows = []
    for sym, costs in by_sym.items():
        grid_rows.append({"label": sym,
                          "cols": [costs.get(c) for c in ("0x", "1x", "2x", "3x")],
                          "worst": costs.get("2x", 0),
                          "clears": bool(costs.get("2x", 0))})
    grid_rows.sort(key=lambda x: (-(x["cols"][1] or 0), x["label"]))

    board.write_board(
        sid="orb", hid="H-001", name="Opening Range Breakout",
        tagline="Range of the first N minutes after a session open, traded on the break.",
        markets={"traded": [{"sym": "BTCUSDT", "tf": "15m", "asset": "BTC"}],
                 "searched": "BTC 15m-4h, then 9 FX / metal / index markets",
                 "note": "Also failed on real Gold, Silver and Nasdaq futures, on "
                         "every timeframe and both session clocks."},
        period="BTCUSDT 15m, walk-forward 2019-01 → 2026-08, 31 quarters",
        report="https://claude.ai/code/artifact/a38e8a90-fc1a-4133-afc1-da3a826ae370",
        candidate="Filtered ORB family, config re-chosen blind every quarter",
        r=r, r_2x=r2, entry_ts=entry, exit_ts=exit_, n_books=1,
        null_margin=0.0, beats_null=False,   # never beat its own null on any market
        consistency=consistency,
        grid={
            "title": "Configurations clearing PF 1.20, as cost rises",
            "note": ("Out of 8,160 per instrument. The <strong>2×</strong> column decides — "
                     "costs are an assumption until a firm is picked, and nothing survives "
                     "doubling them."),
            "cols": ["0x cost", "1x cost", "2x cost", "3x cost"],
            "label": "Instrument", "rows": grid_rows, "integer": True,
        },
        todo=[
            {"t": "Full parameter grid", "w": "13 of 32,640 clear PF 1.20 at real cost, none robust.", "done": True},
            {"t": "Zero-fee diagnostic", "w": "Median PF 0.960 with fees stripped to zero — no edge for cheaper execution to rescue.", "done": True},
            {"t": "Out of sample", "w": "Gold loses every winner; GBPUSD's survivors are one cluster on the worst anchor.", "done": True},
            {"t": "Walk-forward, 31 quarters", "w": "Unfiltered PF 0.781. Filtered family reaches 1.165 — a real lift, still under the 1.20 gate.", "done": True},
            {"t": "8-instrument FX universe", "w": "69 of 65,280 clear at 1x, zero at 2x, every best config breaches the 8% cap.", "done": True},
            {"t": "Prop challenge simulation", "w": "Run on walk-forward output across the full risk ladder.", "done": True},
            {"t": "US equity cross-section", "w": "The published edge picks the top 20 of 7,000 stocks daily. Untested, and not reproducible on a single symbol.", "done": False},
        ],
        note=("Rejected. The scope of that rejection is single-symbol crypto, FX and metals — "
              "the published ORB edge is a US-equity cross-section, which no single-symbol "
              "sweep can reproduce, so it remains untested rather than disproved. The numbers "
              "here are the best honest version: the filtered family, chosen blind each quarter."),
    )


if __name__ == "__main__":
    main()
