"""H-017 stage 19 - the board record, on the blind configuration only.

Stage 13 wrote a board record from the 200-sub-strategy book that Kris
correctly rejected. Stage 18 replaced it with a configuration chosen entirely
inside the fit window - 14 legs at 0.50% risk - and measured blind on the test
half. That is the only version of H-017 with no hindsight in it, so it is the
one that goes on the board.

The board's `pick` will still choose its own risk level under the global
drawdown rule, and it will not choose 0.50%. Both numbers are recorded: the
board's conservative one in the ladder, and the 0.50% result in the note, so
the difference between "the sizing this project defaults to" and "the sizing
that actually passes evaluations fastest" is visible rather than buried.

Output: backtests/xpos/board.json
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from core import board                                              # noqa: E402
from strategies.xpos.stage16_kris_shape import maxdd, pf            # noqa: E402
from strategies.xpos.stage18_nested import (allin, build, gated,    # noqa: E402
                                            rank_legs)

OUT = ROOT / "backtests" / "xpos"
NLEGS, RISK = 14, 0.005


def main() -> int:
    t = pd.read_parquet(OUT / "stage14_trades.parquet")
    t["entry_ts"] = pd.to_datetime(t.entry_ts, utc=True)
    t["exit_ts"] = pd.to_datetime(t.exit_ts, utc=True)
    t = t[t.topn == 1].sort_values("exit_ts")
    g = gated(t)
    mid = g.exit_ts.quantile(0.5)
    keys = rank_legs(g[g.exit_ts <= mid])[:NLEGS]
    second = g[g.exit_ts > mid]
    s, dv = build(second, keys, mid, g.exit_ts.max())
    a = allin(dv, RISK)

    r2 = s.r_2x.values
    dd = maxdd(r2)

    # Stage 18's two nulls, on the identical blind configuration. The
    # leg-selection null is the harder of the two and is the one scored: real
    # 30.3 days all-in against a mean of 43.3. Its BEST seed reaches 29.0, so
    # the real result sits inside the null's range even while beating its
    # centre - which is why the margin is taken on the mean and the best-seed
    # caveat is carried in `todo` rather than rounded away.
    NULL_RANDOM_LEGS, NULL_SHUFFLED_GATE = 43.3, 52.3
    real_days = a["allin_days"]
    null_margin = max(0.0, (NULL_RANDOM_LEGS - real_days) / NULL_RANDOM_LEGS)
    beats = real_days < NULL_RANDOM_LEGS and real_days < NULL_SHUFFLED_GATE

    # Consistency: the share of test quarters whose own profit factor is above
    # breakeven, the same statistic every other board record carries.
    q = s.assign(qq=pd.PeriodIndex(s.exit_ts, freq="Q"))
    qpf = [pf(gq.r_2x.values) for _, gq in q.groupby("qq") if len(gq) >= 20]
    consistency = float(np.mean([x > 1 for x in qpf if np.isfinite(x)])) if qpf else 0.0
    print(f"nulls: real {real_days} d vs random-legs {NULL_RANDOM_LEGS} d, "
          f"shuffled-gate {NULL_SHUFFLED_GATE} d -> margin {null_margin:.3f}")
    print(f"consistency: {sum(x > 1 for x in qpf)}/{len(qpf)} test quarters "
          f"above breakeven")
    print(f"{len(s)} test-window trades on {len(keys)} legs, "
          f"PF@2x {pf(r2):.3f}, maxDD {dd:.1f}R")
    print(f"at {RISK*100:.2f}% risk: pass {a['pass_rate']*100:.1f}%, "
          f"median {a['median_days']} d, all-in {a['allin_days']} d")

    board.write_board(
        sid="xpos", hid="H-017",
        name="VWAP mean reversion / breakout",
        tagline="H-002's kernel on all eleven coins the Binance metrics "
                "archive covers, one configuration per leg, each gated by "
                "H-009's crowd rule. Chosen blind on an earlier half; the "
                "fastest book here, and still short of the target.",
        period=f"{s.exit_ts.min():%Y-%m} to {s.exit_ts.max():%Y-%m}, "
               f"walk-forward, everything chosen on an earlier half",
        report="strategies/xpos/notes.md",
        candidate="fastest in the project but half the accounts die, and "
                  "nothing here has been paper-traded",
        r=s.r.values, r_2x=r2,
        entry_ts=s.entry_ts.values, exit_ts=s.exit_ts.values,
        n_books=len(keys),
        null_margin=null_margin, beats_null=beats, consistency=consistency,
        markets={"traded": [{"sym": a_, "tf": b_, "asset": a_[:3]}
                            for a_, b_ in keys],
                 "searched": "11 USDT-M perps x 5 timeframes x 7,776 "
                             "configurations, walk-forward, then leg count "
                             "and risk chosen inside the fit window"},
        note=f"The ladder below sizes so the whole equity curve fits the 8% "
             f"cap. At {RISK*100:.2f}% risk - the level chosen blind in the "
             f"fit window, which the ladder refuses because the curve draws "
             f"{abs(dd)*RISK*100:.0f}% - the test half gives "
             f"{a['pass_rate']*100:.0f}% pass, a median of {a['median_days']} "
             f"days and {a['allin_days']} days all-in including retries, "
             f"against H-009's 48.7. Kris's objection to the earlier "
             f"200-sub-strategy version was correct and is what produced this "
             f"one: one configuration per leg, {len(s)/max((s.exit_ts.max()-s.entry_ts.min()).days,1):.1f} "
             f"trades a day, $20.71 average on $50 risked.",
        todo=["Median 19.5 days blind against a 7-14 day target - not met.",
              "Half the accounts die at this sizing; fine at $32 a go, not "
              "fine if a firm limits retries.",
              "The random-leg null reaches 43.3 days all-in with a best seed "
              "of 29.0 against the real 30.3 - leg SELECTION is only weakly "
              "better than picking at random, and that is the thinnest "
              "margin here.",
              "The curve draws over 50% at 0.50% risk, so this sizing passes "
              "an evaluation and would destroy the funded seat afterwards. "
              "Post-funding sizing is unsolved.",
              "Crypto perps only, 14bps round trip assumed, never "
              "paper-traded."])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
