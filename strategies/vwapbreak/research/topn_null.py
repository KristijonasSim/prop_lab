"""H-050 — is the top-N speedup an EDGE, or is it portfolio arithmetic?

THE CLAIM UNDER TEST. `TOPN_WIDE.md` records the fastest number this project has
ever produced: gold 1h at floor 100 / top 20 reaches **8.9 expected days with a
band of 8-13**, against the shipped floor 30 / top 5 at 15.3 [13-22]. The bands
do not touch, five of five markets improve, and the ladder is monotone across
five levels of N in both halves of an out-of-sample split.

**8.9 days is inside the 5-14 day pace target this project has failed to reach
for six weeks.** It is also, by its own admission, owed a paired null - every arm
in that file is real-data only. This is that null, plus the decomposition that
should have come first.

WHY A DECOMPOSITION COMES BEFORE A NULL. `core/pipeline.py` line ~307 does this
when it assembles a book of N configurations:

    rs.append(r1 / n)     # equal weight, so a book of N is comparable to one

**Every leg's R is divided by N.** The headline is `days = |maxDD_R| /
R_per_day`, so N enters it twice:

  * `R_per_day` - N legs at 1/N each. If the legs all trade the same edge this
    is roughly UNCHANGED as N grows: an average, not a sum.
  * `|maxDD_R|`  - N imperfectly correlated legs at 1/N each. This SHRINKS,
    by about 1/sqrt(N_effective). Pure variance reduction.

So a falling `days` is what portfolio arithmetic produces on its own, from any
set of imperfectly correlated legs, **including legs with no edge at all.** That
is the same shape as the daily-loss guard (H-041), whose falling blow-up column
turned out to be the risk rung, and as the shuffled MA200 gate that reached 60%
pass in 14.5 days from noise. `CLAUDE.md` already carries the rule: *a falling
column is arithmetic and is never evidence.*

THE TWO PRE-REGISTERED CRITERIA, written before the run.

  1. **DECOMPOSITION.** If `R_per_day` is flat or FALLING in N while `|maxDD_R|`
     falls, the speedup is variance reduction and not captured signal. A real
     improvement would show MORE R per day from more settings, not merely a
     smoother path to the same R.

  2. **THE PAIRED NULL.** The same ladder on a block-shuffled gold series, which
     has the bar structure and none of the edge. If the null's `|maxDD_R|` falls
     with N at the same rate as the real data's, the variance reduction carries
     no information about this market and the ladder shape is generic.

**AND WHAT WOULD SAVE IT.** Neither criterion kills the TRADE if it fails. A
smoother path to the same R is worth having - it is exactly what the risk ladder
buys, and this project already trades a five-deep book for that reason. What the
criteria settle is whether `TOPN_WIDE.md` found an EDGE, which decides whether it
belongs on the board as a discovery or in `core/chosen.py` as a position-sizing
choice. Those are different claims and only one of them has been made so far.

NOTE ON PROVENANCE. The script that produced `topn_wide.json`,
`topn_universe.json` and their logs is **not in the repository** - nothing under
`strategies/` or `core/` references those filenames. The 8.9-day headline
therefore had no reproducible code behind it until this file. The ladder here is
rebuilt from `core/pipeline.Pipeline` directly, so it is the kernel's own
numbers and not a reconstruction of someone's notes.

Run:  .venv/bin/python strategies/vwapbreak/research/topn_null.py
      .venv/bin/python strategies/vwapbreak/research/topn_null.py --seeds 10
      .venv/bin/python strategies/vwapbreak/research/topn_null.py --sym EURUSD
"""
from __future__ import annotations

import argparse
import json
import os
import sys

import numpy as np
import pandas as pd

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))
sys.path.insert(0, REPO)

from core.markets import COSTS, EXEC_MODE, TF_BPH, load          # noqa: E402
from core.pipeline import Market, Pipeline                       # noqa: E402
from core.riskladder import from_trades                          # noqa: E402
from core.run_hypothesis import _FixedGrid                       # noqa: E402
from strategies.vwapbreak.strategy import VwapBreakStrategy      # noqa: E402

OUT = os.path.join(REPO, "backtests", "vwapbreak")

FLOORS = (30, 100)
TOPN = (1, 3, 5, 10, 15, 20)


def decompose(g: pd.DataFrame) -> dict:
    """The headline split into the two things N acts on, separately."""
    t = g.sort_values("exit_ts")
    r = t.r.values
    if len(r) < 20:
        return {}
    eq = np.concatenate(([0.0], np.cumsum(r)))
    dd_r = float((eq - np.maximum.accumulate(eq)).min())
    span = (t.exit_ts.max() - t.exit_ts.min()).total_seconds() / 86400.0
    span = max(span, 1e-9)
    rpd = float(r.mean()) * len(r) / span
    ladder, pick = from_trades(r, t.exit_ts)
    return {"trades": int(len(r)), "r_per_day": rpd, "dd_r": dd_r,
            "ratio_days": abs(dd_r) / rpd if rpd > 0 else np.nan,
            "expected_days": pick["expected_days"],
            "pass_pct": round(pick["pass_rate"] * 100, 1),
            "risk_pct": round(pick["risk"] * 100, 2),
            "avg_r": float(r.mean())}


def ladder(trades: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for (fl, tn), g in trades.groupby(["floor", "topn"]):
        d = decompose(g)
        if d:
            rows.append({"floor": int(fl), "topn": int(tn), **d})
    return pd.DataFrame(rows)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sym", default="XAUUSD")
    ap.add_argument("--tf", default="1h")
    ap.add_argument("--seeds", type=int, default=5)
    args = ap.parse_args()

    df = load(args.sym, args.tf)
    c = COSTS[args.sym]
    fee, slip = c.per_side(EXEC_MODE)
    bph = TF_BPH[args.tf]
    pad = int(max(20, round(24 * 4 * bph)) * 2)
    m = Market(sym=args.sym, tf=args.tf, df=df, fee_bps=fee, slip_bps=slip,
               pad_bars=pad)

    strat = VwapBreakStrategy()
    g = [dict(x) for x in strat.grid(args.tf)]
    for x in g:
        x["min_risk_bps"] = c.min_risk_bps

    # the kernel's own wrapper, not a copy of it - a re-implementation here
    # would be one more place for the two to drift apart
    p = Pipeline(_FixedGrid(strat, g), floors=FLOORS, topn=TOPN)

    print(f"{args.sym} {args.tf}  {df.index[0].date()} -> {df.index[-1].date()}"
          f"  cost {c.round_trip(EXEC_MODE):.2f}bps {EXEC_MODE}")
    print(f"grid {len(g)} configs, floors {FLOORS}, topn {TOPN}\n")

    print("walk-forward on the real series ...", flush=True)
    real = ladder(p.walk_forward(m).trades)

    print(f"walk-forward on {args.seeds} paired-shuffle nulls ...", flush=True)
    nulls = []
    for s in range(args.seeds):
        n = p.walk_forward(m, shuffled="paired", tag=f"tn{s}")
        L = ladder(n.trades)
        L["seed"] = s
        nulls.append(L)
        print(f"  seed {s + 1}/{args.seeds}", flush=True)
    nul = pd.concat(nulls) if nulls else pd.DataFrame()

    os.makedirs(OUT, exist_ok=True)
    real.to_csv(os.path.join(OUT, f"topn_null_real_{args.sym}.csv"), index=False)
    nul.to_csv(os.path.join(OUT, f"topn_null_shuffled_{args.sym}.csv"),
               index=False)

    for fl in FLOORS:
        r = real[real.floor == fl].sort_values("topn")
        if r.empty:
            continue
        print(f"\n{'=' * 94}\nfloor {fl} — THE DECOMPOSITION "
              f"(criterion 1)\n{'=' * 94}")
        print(f"{'topN':>5} {'trades':>7} {'R/day':>9} {'vs N=1':>8} "
              f"{'|maxDD_R|':>10} {'vs N=1':>8} {'dd/rpd':>8} "
              f"{'exp days':>9} {'pass%':>6}")
        b = r.iloc[0]
        for _, x in r.iterrows():
            print(f"{int(x.topn):5d} {int(x.trades):7d} {x.r_per_day:9.4f} "
                  f"{x.r_per_day / b.r_per_day:7.2f}x {abs(x.dd_r):10.2f} "
                  f"{abs(x.dd_r) / abs(b.dd_r):7.2f}x {x.ratio_days:8.1f} "
                  f"{x.expected_days if x.expected_days else float('nan'):9.1f} "
                  f"{x.pass_pct:6.1f}")

        if not nul.empty:
            nn = nul[nul.floor == fl].groupby("topn").agg(
                rpd=("r_per_day", "median"), dd=("dd_r", "median"),
                trades=("trades", "median")).sort_index()
            if not nn.empty:
                nb = nn.iloc[0]
                print(f"\nfloor {fl} — THE PAIRED NULL, median of "
                      f"{args.seeds} block-shuffled seeds (criterion 2)")
                print(f"{'topN':>5} {'null R/day':>11} {'vs N=1':>8} "
                      f"{'null |maxDD|':>13} {'vs N=1':>8}   "
                      f"{'REAL |maxDD| vs N=1':>21}")
                for tn, x in nn.iterrows():
                    rr = r[r.topn == tn]
                    rv = (abs(rr.iloc[0].dd_r) / abs(b.dd_r)) if len(rr) else np.nan
                    print(f"{int(tn):5d} {x.rpd:11.4f} {x.rpd / nb.rpd:7.2f}x "
                          f"{abs(x.dd):13.2f} {abs(x.dd) / abs(nb.dd):7.2f}x   "
                          f"{rv:20.2f}x")

    # ---- the verdicts, against the criteria written before the run
    print(f"\n{'=' * 94}\nTHE TWO CRITERIA\n{'=' * 94}")
    for fl in FLOORS:
        r = real[real.floor == fl].sort_values("topn")
        if len(r) < 3:
            continue
        b = r.iloc[0]
        hi = r.iloc[-1]
        rpd_lift = hi.r_per_day / b.r_per_day
        dd_cut = abs(hi.dd_r) / abs(b.dd_r)
        print(f"\nfloor {fl}: N=1 -> N={int(hi.topn)}")
        print(f"  R per day  x{rpd_lift:.2f}   |maxDD_R|  x{dd_cut:.2f}   "
              f"expected days {b.expected_days} -> {hi.expected_days}")
        if rpd_lift <= 1.05:
            print("  **CRITERION 1 FAILED — R per day did not rise. The speedup "
                  "is variance\n  reduction, not captured signal.**")
        else:
            print(f"  CRITERION 1 PASSED — R per day rose {rpd_lift:.2f}x.")
        if not nul.empty:
            # PER SEED, not on the pooled median. The question is how often a
            # shuffled market cuts its drawdown at least as hard as the real one
            # did, and a median cannot answer that - it is one draw's worth of
            # information presented as if it were the distribution.
            sub = nul[nul.floor == fl]
            cuts = []
            for sd, gs in sub.groupby("seed"):
                gs = gs.sort_values("topn")
                if len(gs) >= 3 and abs(gs.iloc[0].dd_r) > 0:
                    cuts.append(abs(gs.iloc[-1].dd_r) / abs(gs.iloc[0].dd_r))
            if cuts:
                cuts = np.array(cuts)
                beat = int((cuts <= dd_cut).sum())
                pval = (beat + 1) / (len(cuts) + 1)
                print(f"  null |maxDD_R| cut across {len(cuts)} seeds: "
                      f"median x{np.median(cuts):.2f}, "
                      f"range x{cuts.min():.2f}-x{cuts.max():.2f}")
                print(f"  seeds cutting at least as hard as the real x"
                      f"{dd_cut:.2f}: {beat}/{len(cuts)}  ->  p = {pval:.3f}")
                if pval > 0.05:
                    print("  **CRITERION 2 FAILED — a shuffled market cuts its "
                          "drawdown with N just\n  as hard. The variance "
                          "reduction is generic arithmetic.**")
                else:
                    print("  CRITERION 2 PASSED — the real ladder cuts drawdown "
                          "faster than the null.")

    json.dump({"real": real.to_dict("records"),
               "null_median": (nul.groupby(["floor", "topn"]).median(
                   numeric_only=True).reset_index().to_dict("records")
                   if not nul.empty else [])},
              open(os.path.join(OUT, f"topn_null_{args.sym}.json"), "w"),
              indent=1)
    print(f"\nwritten: {OUT}/topn_null_{args.sym}.json")


if __name__ == "__main__":
    main()
