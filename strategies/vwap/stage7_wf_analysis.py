"""H-002 VWAP stage 7 — what the walk-forward actually says.

Stage 6 produced 44 market x timeframe combinations under 4 selection rules =
176 stitched out-of-sample series. Reading the best cell off that grid would be
the same mistake the whole walk-forward exists to avoid: it is a search over 176
results. So this stage scores the grid three ways that a lucky cell cannot pass.

1. **Cross-rule robustness.** A combination is only carried forward if it clears
   the gate under ALL FOUR selection rules — both trade-count floors and both
   single-best and top-ten. A real edge should not care much which of these is
   used; a lucky cell will fall over as soon as the rule changes.

2. **The full mandatory field set** on the stitched series, including the
   resolution estimate, which is the phase gate.

3. **The prop-challenge simulation run on walk-forward output** rather than on
   fitted configurations. Stage 4's pass rates were measured on configs chosen
   with hindsight; these are not.

A combined multi-market book is also rebuilt from walk-forward trades. It is
scored on the window every leg shares (2024-09 onward), because BTC has 30
quarters of history and the FX/metals legs only have 7 — stitching those spans
together would let BTC's longer record carry legs that were never tested on it.
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from core.metrics import resolution_estimate                  # noqa: E402
from strategies.vwap.stage1_grid import OUT                   # noqa: E402
from strategies.vwap.stage4_profiles import run_accounts, curve_stats  # noqa: E402
from core import board                                        # noqa: E402
from core import riskladder as RL                             # noqa: E402

GATE_PF = 1.20
RISK = 0.0075                 # the mid risk level stage 4 used, held fixed here
COMMON_START = "2024-09-01"   # first quarter every FX/metal leg has


def pf(r):
    w, l = r[r > 0].sum(), -r[r < 0].sum()
    return float(w / l) if l > 0 else (np.inf if w > 0 else np.nan)


def full_fields(r, entry_ts, exit_ts, risk=RISK) -> dict:
    """Every field CLAUDE.md requires, on a stitched R series."""
    span = (exit_ts.iloc[-1] - exit_ts.iloc[0]).total_seconds() / 86400.0
    eq = np.concatenate(([0.0], np.cumsum(r)))
    dd_r = float((eq - np.maximum.accumulate(eq)).min())
    daily = pd.Series(r * risk, index=exit_ts).resample("1D").sum()
    dtt, dtb, p_pass = resolution_estimate(daily)
    sd = daily.std(ddof=1)
    hold = (exit_ts.values - entry_ts.values).astype("timedelta64[s]").astype(float)
    return {
        "pf": round(pf(r), 3),
        "trades": int(len(r)),
        "trades_per_day": round(len(r) / max(span, 1e-9), 3),
        "trades_per_week": round(7 * len(r) / max(span, 1e-9), 2),
        "avg_hold_h": round(float(np.mean(hold)) / 3600.0, 2),
        "win_rate": round(float((r > 0).mean()), 4),
        "avg_r": round(float(r.mean()), 4),
        "max_dd_r": round(dd_r, 2),
        "max_dd_pct": round(dd_r * risk, 4),
        "sharpe": round(float(daily.mean() / sd * math.sqrt(365)), 3) if sd else 0.0,
        "days_to_target": round(dtt, 1) if np.isfinite(dtt) else np.inf,
        "days_to_breach": round(dtb, 1) if np.isfinite(dtb) else np.inf,
    }


def main():
    st = pd.read_csv(OUT / "stage6_stitched.csv")
    tr = pd.read_parquet(OUT / "stage6_trades.parquet")
    tr["entry_ts"] = pd.to_datetime(tr.entry_ts, utc=True)
    tr["exit_ts"] = pd.to_datetime(tr.exit_ts, utc=True)
    pd.set_option("display.width", 240)

    # ---- 1. cross-rule robustness -------------------------------------------
    piv = st.pivot_table(index=["symbol", "tf"], columns=["floor", "topn"],
                         values="pf")
    piv.columns = [f"f{f}_n{n}" for f, n in piv.columns]
    piv["worst"] = piv.min(axis=1)
    piv["median"] = piv.median(axis=1)
    piv["quarters"] = st.groupby(["symbol", "tf"]).quarters.max()
    piv = piv.sort_values("worst", ascending=False)
    print("=== stitched walk-forward PF under each selection rule ===")
    print(piv.round(3).to_string())
    print(f"\nmedian across all 44 combinations x 4 rules: "
          f"{st.pf.median():.3f}   share above 1.0: {100*(st.pf > 1).mean():.1f}%")

    survivors = piv[piv.worst >= GATE_PF]
    print(f"\n{len(survivors)} combinations clear PF {GATE_PF} under ALL FOUR rules:")
    print(survivors.round(3).to_string() if len(survivors) else "  none")

    piv.round(4).to_csv(OUT / "stage7_robustness.csv")

    # ---- 2. mandatory fields on every combo x rule --------------------------
    rows = []
    for (sym, tf, fl, tn), g in tr.groupby(["symbol", "tf", "floor", "topn"]):
        g = g.sort_values("exit_ts")
        f = full_fields(g.r.values, g.entry_ts, g.exit_ts)
        f2 = {"pf_2x": round(pf(g.r_2x.values), 3)}
        q = st[(st.symbol == sym) & (st.tf == tf) &
               (st.floor == fl) & (st.topn == tn)]
        rows.append({"symbol": sym, "tf": tf, "floor": fl, "topn": tn,
                     "quarters": int(q.quarters.iloc[0]),
                     "q_above_1": int(q.q_above_1.iloc[0]), **f, **f2})
    fields = pd.DataFrame(rows).sort_values("pf", ascending=False)
    fields.to_csv(OUT / "stage7_fields.csv", index=False)
    print("\n=== mandatory fields, top 12 by stitched PF ===")
    print(fields.head(12).to_string(index=False))

    # ---- 3. prop simulation on walk-forward output --------------------------
    print("\n=== prop challenge on WALK-FORWARD trades (not fitted configs) ===")
    prop = []
    for _, r0 in fields.iterrows():
        if r0.pf < GATE_PF or r0.trades < 100:
            continue
        g = tr[(tr.symbol == r0.symbol) & (tr.tf == r0.tf) &
               (tr.floor == r0.floor) & (tr.topn == r0.topn)].sort_values("exit_ts")
        daily = pd.Series(g.r.values, index=g.exit_ts).resample("1D").sum()
        for risk in (0.005, 0.0075, 0.01, 0.02):
            acc = run_accounts(daily, risk)
            yrs = (g.exit_ts.iloc[-1] - g.exit_ts.iloc[0]).days / 365.25
            cs = curve_stats(g.r.values, g.exit_ts, risk, max(yrs, 1e-9))
            prop.append({"symbol": r0.symbol, "tf": r0.tf, "floor": r0.floor,
                         "topn": r0.topn, "risk": risk, "pf": r0.pf,
                         "tpd": r0.trades_per_day, **cs, **acc})
    pdf = pd.DataFrame(prop)
    if len(pdf):
        pdf.to_csv(OUT / "stage7_prop.csv", index=False)
        print(pdf[["symbol", "tf", "floor", "topn", "risk", "pf", "tpd", "cagr",
                   "max_dd", "pass_rate", "fail_max", "fail_daily",
                   "median_days_pass"]].to_string(index=False))
    else:
        print("  nothing cleared the gate with enough trades to simulate")

    # ---- 4. a multi-market book, on the window every leg shares -------------
    print(f"\n=== equal-weight book of surviving legs, from {COMMON_START} ===")
    book_rows = []
    for (fl, tn), _ in st.groupby(["floor", "topn"]):
        legs = piv[piv.worst >= GATE_PF].index.tolist()
        if not legs:
            continue
        sel = tr[(tr.floor == fl) & (tr.topn == tn) &
                 (tr.exit_ts >= COMMON_START)]
        sel = sel[pd.MultiIndex.from_frame(sel[["symbol", "tf"]]).isin(legs)]
        if sel.empty:
            continue
        sel = sel.sort_values("exit_ts")
        n_leg = sel.groupby(["symbol", "tf"]).ngroups
        r = sel.r.values / n_leg           # equal weight, so R stays comparable
        f = full_fields(r, sel.entry_ts, sel.exit_ts)
        daily = pd.Series(r, index=sel.exit_ts).resample("1D").sum()
        for risk in (0.0075, 0.01, 0.015):
            acc = run_accounts(daily, risk)
            book_rows.append({"floor": fl, "topn": tn, "legs": n_leg,
                              "risk": risk, **f, **acc})
    bdf = pd.DataFrame(book_rows)
    if len(bdf):
        bdf.to_csv(OUT / "stage7_book.csv", index=False)
        print(bdf[["floor", "topn", "legs", "risk", "pf", "trades",
                   "trades_per_day", "max_dd_r", "sharpe", "pass_rate",
                   "fail_max", "median_days_pass"]].to_string(index=False))
    else:
        print("  no surviving legs to combine")




# ---------------------------------------------------------------------------
# Risk ladder for the strategy board.
#
# Risk per trade is the only free lever left once the configuration is chosen
# blind, and it moves speed and survival in opposite directions. Fixing it at
# one value and reporting the result as "the" answer hides that trade-off - and
# hides the fact that the arbitrary choice may not even be the best one. So the
# board gets the whole ladder plus an explicitly-stated pick.
# ---------------------------------------------------------------------------

def book_trades(tr: pd.DataFrame, legs, floor: int, topn: int) -> pd.DataFrame:
    sel = tr[(tr.floor == floor) & (tr.topn == topn) & (tr.exit_ts >= COMMON_START)]
    sel = sel[[(s, t) in legs for s, t in zip(sel.symbol, sel.tf)]]
    return sel.sort_values("exit_ts")


def write_board_json():
    """The board record. Written through core/board.py so H-002 gets exactly the
    same prop simulation, risk ladder and scoring inputs as every other idea -
    nothing here is hand-copied, and nothing is H-002-specific."""
    st = pd.read_csv(OUT / "stage6_stitched.csv")
    tr = pd.read_parquet(OUT / "stage6_trades.parquet")
    tr["entry_ts"] = pd.to_datetime(tr.entry_ts, utc=True)
    tr["exit_ts"] = pd.to_datetime(tr.exit_ts, utc=True)

    piv = st.pivot_table(index=["symbol", "tf"], columns=["floor", "topn"], values="pf")
    worst = piv.min(axis=1)
    legs = []
    for sym, tf in worst[worst >= GATE_PF].index:
        rec = tr[(tr.symbol == sym) & (tr.tf == tf) & (tr.exit_ts >= COMMON_START)]
        if len(rec) and rec.r.sum() > 0:          # drop the pre-2024-only regimes
            legs.append((sym, tf))

    # Null margin: how many combinations clear the gate under every selection
    # rule on real data, against how many do on shuffled data.
    # Prefer the PAIRED null when it exists. It keeps each bar's volume with its
    # own return, so a participation filter cannot win merely by having a
    # volume/return relationship that the null lacks - and every survivor here
    # was chosen with a participation filter. It is the harder benchmark:
    # 11 gate-clearing cells against the independent null's 6.
    nullp = OUT / "stage6_stitched_shuffled_paired.csv"
    if not nullp.exists():
        nullp = OUT / "stage6_stitched_shuffled.csv"
    real_s = int((worst >= GATE_PF).sum())
    null_s = 0
    if nullp.exists():
        n = pd.read_csv(nullp)
        np_piv = n.pivot_table(index=["symbol", "tf"], columns=["floor", "topn"], values="pf")
        null_s = int((np_piv.min(axis=1) >= GATE_PF).sum())
    null_margin = 0.0 if not real_s else max(0.0, (real_s - null_s) / real_s)

    # Consistency: share of quarters above breakeven across the surviving legs.
    fold = pd.read_parquet(OUT / "stage6_folds.parquet")
    fl = fold[[(s0, t0) in legs for s0, t0 in zip(fold.symbol, fold.tf)]]
    consistency = float((fl.test_pf > 1).mean()) if len(fl) else 0.0

    # ------------------------------------------------------------------
    # Leg selection. Clearing the gate at 1x is NOT sufficient - the project's
    # rule is PF >= 1.20 at DOUBLE cost, because costs are an assumption until a
    # firm is picked. Selecting on 1x alone let four legs into the book that
    # individually collapse at 2x (BTC 15m 1.067, BTC 1h 1.017, BTC 30m 0.939,
    # gold 30m 1.025). The book got faster and stopped being robust, which is
    # the wrong trade. Only 3 of the 63 possible subsets hold at 2x.
    #
    # `topn` is also constrained. A top-10 book means running 10 configurations
    # per market simultaneously; with six legs that is sixty parallel strategies,
    # which is a research estimator for averaging selection noise, not a trading
    # plan. topn=1 is preferred and the top-10 variant is recorded alongside it.
    # ------------------------------------------------------------------
    import itertools
    GATE_2X = 1.20

    def score(sub, floor, topn):
        sel = book_trades(tr, list(sub), floor, topn)
        if sel.empty:
            return None
        r = sel.r.values / len(sub)
        r2 = sel.r_2x.values / len(sub)
        _rows, pk = RL.from_trades(r, sel.exit_ts)
        if pk["expected_days"] is None:
            return None
        return {"sub": list(sub), "floor": floor, "topn": topn, "sel": sel,
                "pf_2x": board.pf_of(r2), "days": pk["expected_days"]}

    cands = []
    for k in range(1, len(legs) + 1):
        for sub in itertools.combinations(legs, k):
            for floor in (100, 30):
                for topn in (1, 10):
                    c = score(sub, floor, topn)
                    if c and c["pf_2x"] >= GATE_2X:
                        cands.append(c)
    if not cands:
        print("no subset holds PF 1.20 at 2x cost - nothing to put on the board")
        return
    # tradeable first (topn == 1), then fewest expected days
    cands.sort(key=lambda c: (c["topn"] != 1, c["days"]))
    best = cands[0]
    legs, floor, topn, sel = best["sub"], best["floor"], best["topn"], best["sel"]
    n_legs = len(legs)
    print(f"  leg selection: {len(cands)} subsets hold 1.20 at 2x cost; chose "
          f"{' + '.join(f'{a} {b}' for a, b in legs)} "
          f"(floor {floor}, top {topn}, PF@2x {best['pf_2x']:.3f})")

    grid_rows = [{
        "label": f'{r0["symbol"]} {r0["tf"]}',
        "cols": [r0.get("r30_1"), r0.get("r30_10"), r0.get("r100_1"), r0.get("r100_10")],
        "worst": r0["worst"], "clears": bool(r0["survivor"]),
    } for r0 in json.loads((OUT / "report_data.json").read_text())["wf_grid"]]

    board.write_board(
        sid="vwap", hid="H-002", name="VWAP",
        tagline="Five model families around the volume-weighted average price.",
        period="FX & metals 2023-09 → 2026-08 · BTC from 2017",
        report="https://claude.ai/code/artifact/cb748842-7d3b-45f7-9d69-827e00ba82f4",
        candidate=(" + ".join(f"{a} {b}" for a, b in legs)
                   + ", equal weight, config re-chosen blind each quarter"),
        r=sel.r.values / n_legs, r_2x=sel.r_2x.values / n_legs,
        n_books=n_legs * topn,
        entry_ts=sel.entry_ts, exit_ts=sel.exit_ts,
        null_margin=null_margin, beats_null=(real_s > null_s),
        consistency=consistency,
        grid={
            "title": "Every market × timeframe, under all four ways of choosing",
            "note": ("The <strong>worst</strong> column is how the combination does under "
                     "the least favourable of the four selection rules. That is the number "
                     "that decides, not the best one."),
            "cols": ["floor 30 / best", "floor 30 / top 10",
                     "floor 100 / best", "floor 100 / top 10"],
            "label": "Market", "rows": grid_rows,
        },
        todo=[
            {"t": "Fill realism", "w": "Whether the result needs a limit fill nobody can guarantee.", "done": True},
            {"t": "Cost stress to 2x and 3x", "w": "Whether the edge is bigger than the spread difference between an ECN and a prop firm.", "done": True},
            {"t": "Null benchmark", "w": "Whether the profit factor beats what the same search finds in data with no edge in it.", "done": True},
            {"t": "Walk-forward", "w": "Chosen blind every quarter. Fails as a family at median 0.909; two legs hold.", "done": True},
            {"t": "Null benchmark on the walk-forward", "w": "Whether 4 survivors out of 44 beats what shuffled data gives. It gives 1.", "done": True},
            {"t": "Prop challenge on walk-forward output", "w": "Pass and breach rates across the full risk ladder, on blind-chosen configs.", "done": True},
            {"t": "NautilusTrader cross-check", "w": "Whether an independent matching engine agrees with the kernel.", "done": False},
            {"t": "Silver (XAGUSD)", "w": "Downloaded, 81,984 bars. Has not been through any stage.", "done": False},
        ],
    )


if __name__ == "__main__":
    main()
    write_board_json()
