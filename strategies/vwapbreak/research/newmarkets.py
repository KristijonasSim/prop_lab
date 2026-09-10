"""Six markets this project has never run H-027 on - three of them INDICES.

Kris, 2026-09-10: "i think later we could even do a basket of assets for example
6-7 assets". The current universe is four FX pairs, three metals/energy and three
coins, and `why.py` has just shown that the mechanism splits by ASSET CLASS: FX
and oil mean-revert after a VWAP band break, metals and crypto continue. The
class that should be most favourable to a follow-the-break rule - equity indices,
the most persistently trending liquid market there is - has never been tested,
and three of them were already in `data/` untouched.

    NAS100  SPX500  US30      index CFDs, 2023-09 -> 2026-08, same cache shape
    USDCHF  NZDUSD  USDCAD    the FX pairs the universe left out

WHAT IS RUN. Exactly the two diagnostics already run on the other twenty cells,
no more: the mechanism measurement from `why.py` (follow-through after a break,
with no strategy at all) and the single fixed configuration from `fixed.py` (the
strategy, no grid, no selection, with a bootstrap band on profit factor). No
walk-forward, no selection, so nothing here can be quoted as a result - it is a
screen that says whether a full run is worth the compute.

THE WINDOW IS THE ORIGINAL UNIVERSE'S. `run_hypothesis.window` sets the common
end to the EARLIEST last bar across the markets it is given, so adding markets
could shorten it and move every number the board has. The span is therefore
computed from the ten original symbols and then applied to these six.

COSTS ARE ASSUMED AND PESSIMISTIC - 1.8bps round trip on the indices against a
real Dukascopy spread nearer 0.7-1.2. A cell that clears here would clear at real
costs. See the note in `core/markets.py`.

Run: .venv/bin/python strategies/vwapbreak/research/newmarkets.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from core.markets import COSTS, EXEC_MODE, TF_BPH, load            # noqa: E402
from core.run_hypothesis import window                             # noqa: E402
from core.strategy import T_R                                      # noqa: E402
from strategies.vwapbreak.strategy import STRATEGY                 # noqa: E402
from strategies.vwapbreak.research.exits import UNIVERSE           # noqa: E402
from strategies.vwapbreak.research.fixed import ARMS, stats        # noqa: E402
from strategies.vwapbreak.research.why import row as why_row       # noqa: E402

NEW = {"Indices": ["NAS100", "SPX500", "US30"],
       "FX": ["USDCHF", "NZDUSD", "USDCAD"]}
TFS = ("1h", "4h")


def main() -> int:
    span = window([s for v in UNIVERSE.values() for s in v], list(TFS))
    print(f"window {span[0].date()} -> {span[1].date()}   (the original universe's)\n")

    print("MECHANISM - follow-through after a 1.0 sigma break, no strategy")
    print(f"{'market':9}{'tf':4}{'cost':>6}{'sigma':>7}{'s/cost':>7}"
          f"{'ft96h':>8}{'ft384h':>8}{'net384':>8}{'hit%':>6}{'VR':>7}")
    why_rows = []
    for group in NEW.values():
        for sym in group:
            for tf in TFS:
                r = why_row(sym, tf, span)
                why_rows.append(r)
                k = int(96 * TF_BPH[tf])
                print(f"{r['sym']:9}{r['tf']:4}{r['cost_rt_bps']:6.1f}"
                      f"{r['sigma_bps']:7.0f}{r['sigma_over_cost']:7.1f}"
                      f"{(r.get('ft_96h_bps') or 0):8.1f}"
                      f"{(r.get('ft_384h_bps') or 0):8.1f}"
                      f"{(r.get('ft_384h_net_bps') or 0):8.1f}"
                      f"{(r.get('ft_384h_hit') or 0):6.1f}"
                      f"{r.get(f'vr_{k}', float('nan')):7.2f}", flush=True)

    print("\nONE FIXED CONFIGURATION - thr 1.0, stop 8 sigma, hold 384h")
    print(f"{'market':9}{'tf':4}{'arm':12}{'trades':>7}{'win%':>7}{'avgR':>8}"
          f"{'PF2x':>7}{'band':>14}{'stop%':>7}")
    fixed_rows = []
    for group in NEW.values():
        for sym in group:
            for tf in TFS:
                df = load(sym, tf)
                df = df[(df.index >= span[0]) & (df.index <= span[1])]
                feats = STRATEGY.features(df)
                fee, slip = COSTS[sym].per_side(EXEC_MODE)
                for arm, a in ARMS.items():
                    cfg = {"thr": a["thr"], "stop_sig": a["stop_sig"],
                           "max_hold": max(2, int(round(a["hold_h"] * TF_BPH[tf]))),
                           "hour_lo": 0, "hour_hi": 0, "min_rvol": 0.0,
                           "min_risk_bps": COSTS[sym].min_risk_bps}
                    tr = STRATEGY.run(df, cfg, fee, slip, feats=feats)
                    tr2 = STRATEGY.run(df, cfg, fee * 2, slip * 2, feats=feats)
                    r = stats(tr, sym, tf, arm, tr2[:, T_R])
                    fixed_rows.append(r)
                    if r.get("pf") is None or arm != "traded":
                        continue
                    b = r["pf_2x_band"]
                    print(f"{sym:9}{tf:4}{arm:12}{r['trades']:7}{r['win_pct']:7.1f}"
                          f"{r['avg_r']:8.3f}{(r['pf_2x'] or 0):7.2f}"
                          f"{('%.2f-%.2f' % (b[0], b[1])):>14}"
                          f"{r['stopped_pct']:7.1f}", flush=True)

    dest = ROOT / "backtests" / "vwapbreak" / "newmarkets.json"
    dest.write_text(json.dumps({"why": why_rows, "fixed": fixed_rows},
                               indent=1, default=str))
    print(f"\nwrote {dest.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
