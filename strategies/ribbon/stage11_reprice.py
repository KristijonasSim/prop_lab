"""H-016 stage 11 — the ribbon book at MEASURED cost, and silver's second death.

TASK T3 item 2 from `NEXT.md`: "re-price EVERYTHING at measured cost. Only
XAUUSD and EURUSD have been re-priced so far. The correction was worth 0.33 of
profit factor and 60 days on gold. Every other board number is still on an
assumption."

H-016 is the other record on the board and it was never re-priced. Its book is
three XAUUSD legs and one **XAGUSD** leg, and the two metals move in opposite
directions when the assumption is replaced by a measurement:

| symbol | assumed bps/side | measured bps/side | effect |
|---|---|---|---|
| XAUUSD | 1.50 | **0.915** | 1.6x cheaper — the book gets better |
| XAGUSD | 2.25 | **4.554** | **2.0x more expensive** — the leg gets worse |

`core/fx_spread.py` sampled Dukascopy ticks: XAUUSD median spread 1.621bps of
mid (mean 1.671), XAGUSD **9.108bps**. Half of each is the crossing cost per
side; gold adds ~0.075bps/side of cTrader commission.

SILVER IS ALREADY DEAD ON OTHER EVIDENCE and this is the second cause. The
post-fix paired null gives XAGUSD **2 real cells clearing against its null's 2**
— not distinguishable from noise — while gold gives 11 against 0. Being priced
at half its true spread on top of that is not a marginal correction.

RE-PRICING IS EXACT. Every trade is stored at 1x and 2x cost, and R is linear in
cost, so `C/risk = r_1x − r_2x` recovers the zero-cost series and any other
level from it. No re-simulation, no new fills, no new assumptions.

Run: .venv/bin/python strategies/ribbon/stage11_reprice.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from core import riskladder                                     # noqa: E402
from strategies.ribbon.sweep import COSTS                       # noqa: E402

BT = ROOT / "backtests" / "ribbon"

# measured bps PER SIDE: half the sampled spread, plus commission where it applies
MEASURED = {"XAUUSD": 0.915, "XAGUSD": 4.554, "EURUSD": 0.137}


def assumed(sym: str) -> float:
    fee, slip, _ = COSTS[sym]
    return fee + slip


def reprice(g: pd.DataFrame, sym: str) -> pd.Series:
    c = g.r - g.r_2x                       # one round trip, in R
    r0 = g.r + c
    return r0 - (MEASURED[sym] / assumed(sym)) * c


def pf(r) -> float:
    r = np.asarray(r)
    w, l = r[r > 0].sum(), -r[r < 0].sum()
    return float(w / l) if l > 0 else (float("inf") if w > 0 else float("nan"))


def maxdd(r) -> float:
    eq = np.concatenate(([0.0], np.cumsum(np.asarray(r))))
    return abs(float((eq - np.maximum.accumulate(eq)).min()))


def score(r, exit_ts, label, legs=1) -> dict:
    rows, pick = riskladder.from_trades(np.asarray(r), exit_ts)
    span = max((pd.DatetimeIndex(exit_ts).max()
                - pd.DatetimeIndex(exit_ts).min()).days, 1)
    return {"book": label, "legs": legs, "trades": len(r),
            "pf": round(pf(r), 3), "total_r": round(float(np.sum(r)), 2),
            "max_dd_r": round(maxdd(r), 2),
            "r_per_day": round(float(np.sum(r)) / span, 4),
            "tpd": round(len(r) / span / max(legs, 1), 2),
            "risk": pick.get("risk"), "pass_rate": pick.get("pass_rate"),
            "median_days": pick.get("median_days"),
            "expected_days": pick.get("expected_days"),
            "one_step_days": pick.get("one_step", {}).get("expected_days")}


def book(t: pd.DataFrame, keys, label, col) -> dict:
    """`keys` are (symbol, timeframe, rule). The RULE matters: the board's book
    is four `single` legs, and the `top10` variant of the same market and
    timeframe is a different, far busier series. Mixing them silently changes
    the book being scored."""
    parts = [t[(t.sym == s) & (t.tf == tf) & (t.rule == rule)]
             for s, tf, rule in keys]
    parts = [p for p in parts if len(p)]
    if not parts:
        return {}
    n = len(parts)
    lo = max(p.exit_ts.min() for p in parts)
    hi = min(p.exit_ts.max() for p in parts)
    cut = [p[(p.exit_ts >= lo) & (p.exit_ts <= hi)] for p in parts]
    r = np.concatenate([c[col].values / n for c in cut])
    ts = pd.DatetimeIndex(np.concatenate([c.exit_ts.values for c in cut]))
    o = np.argsort(ts.values, kind="stable")
    return score(r[o], ts[o], label, legs=n)


def main():
    t = pd.read_parquet(BT / "stage10_trades.parquet")
    t["exit_ts"] = pd.to_datetime(t.exit_ts, utc=True)
    t["rm"] = np.nan
    for sym, g in t.groupby("sym"):
        t.loc[g.index, "rm"] = reprice(g, sym).values

    print("PER LEG — assumed against measured")
    print(f"{'leg':22} {'trades':>7} {'PF asm':>8} {'PF msr':>8} "
          f"{'R asm':>8} {'R msr':>8} {'delta':>8}")
    rows = []
    for (sym, tf, rule), g in t.groupby(["sym", "tf", "rule"]):
        a, m = pf(g.r.values), pf(g.rm.values)
        rows.append({"sym": sym, "tf": tf, "rule": rule, "trades": len(g),
                     "pf_assumed": round(a, 3), "pf_measured": round(m, 3),
                     "r_assumed": round(float(g.r.sum()), 2),
                     "r_measured": round(float(g.rm.sum()), 2),
                     "assumed_bps_side": assumed(sym),
                     "measured_bps_side": MEASURED[sym]})
        print(f"{sym+' '+tf+' '+rule:22} {len(g):7d} {a:8.3f} {m:8.3f} "
              f"{g.r.sum():8.2f} {g.rm.sum():8.2f} {g.rm.sum()-g.r.sum():+8.2f}")
    pd.DataFrame(rows).to_csv(BT / "stage11_legs.csv", index=False)

    # exactly the four legs `backtests/ribbon/board.json` says it trades
    board_keys = [("XAGUSD", "30m", "single"), ("XAUUSD", "15m", "single"),
                  ("XAUUSD", "1h", "single"), ("XAUUSD", "30m", "single")]
    gold_keys = [("XAUUSD", "15m", "single"), ("XAUUSD", "1h", "single"),
                 ("XAUUSD", "30m", "single")]
    books = [
        book(t, board_keys, "board book (3 gold + silver), ASSUMED", "r"),
        book(t, board_keys, "board book (3 gold + silver), MEASURED", "rm"),
        book(t, gold_keys, "gold only (3 legs), ASSUMED", "r"),
        book(t, gold_keys, "gold only (3 legs), MEASURED", "rm"),
    ]
    b = pd.DataFrame([x for x in books if x])
    b.to_csv(BT / "stage11_books.csv", index=False)
    print(f"\n{'=' * 112}\nTHE BOOK\n{'=' * 112}")
    print(b[["book", "legs", "trades", "pf", "total_r", "max_dd_r", "r_per_day",
             "tpd", "risk", "pass_rate", "median_days", "expected_days",
             "one_step_days"]].to_string(index=False))

    ba, bm = b.iloc[0], b.iloc[1]
    ga, gm = b.iloc[2], b.iloc[3]
    print(f"\nre-pricing the BOARD book: PF {ba.pf} -> {bm.pf}, "
          f"expected days {ba.expected_days} -> {bm.expected_days}")
    print(f"dropping SILVER as well:   PF {bm.pf} -> {gm.pf}, "
          f"expected days {bm.expected_days} -> {gm.expected_days}")
    print("\nSilver was priced at 2.25bps/side and measures 4.554, and it "
          "loses to\nthis hypothesis's OWN null - see the table below.")


if __name__ == "__main__":
    main()


# ---------------------------------------------------------------------------
# The null, per metal, and the board rewrite. Appended 2026-09-07.
# ---------------------------------------------------------------------------

def null_table():
    """Real against the ribbon's OWN paired null, per metal.

    Worth doing separately rather than borrowing H-002's verdict on silver: the
    two hypotheses share a market and nothing else, so H-002's null says nothing
    about this kernel. It happens to agree."""
    r = pd.read_csv(BT / "stage6_stitched.csv")
    rows = []
    for sym in ("XAUUSD", "XAGUSD"):
        x = r[r.symbol == sym]
        real = int((x.pf_2x >= 1.20).sum())
        nulls, best = [], []
        for i in range(3):
            n = pd.read_csv(BT / f"stage6_stitched_null{i}.csv")
            y = n[n.symbol == sym]
            nulls.append(int((y.pf_2x >= 1.20).sum()))
            best.append(float(y.pf_2x.max()))
        rows.append({"sym": sym, "cells": len(x), "real_clear": real,
                     "null_clear_mean": round(float(np.mean(nulls)), 2),
                     "null_clear": nulls, "real_best": round(float(x.pf_2x.max()), 3),
                     "null_best": round(max(best), 3),
                     "beats_null": real > float(np.mean(nulls))})
    return pd.DataFrame(rows)


BOOK_NOTE = (
    "Gold only, at measured cost. The board used to carry a fourth leg - XAGUSD "
    "30m - and it is gone for two independent reasons. Against this hypothesis's "
    "OWN paired null, silver clears PF 1.20 at 2x on 2 of 6 cells while the null "
    "clears 3.7 on average and reaches 2.549 against silver's real best of 2.113: "
    "it loses to its own null. And it was priced at 2.25bps per side when the "
    "measured spread is 4.554 - Dukascopy ticks, 330 sampled hours. Gold does the "
    "opposite on both counts: 5 of 8 real cells clear against the null's 1.0, and "
    "the measured 0.915bps per side is cheaper than the 1.50 assumed. "
    "THE UNCOMFORTABLE PART, stated rather than buried: removing silver makes this "
    "book SLOWER, 125.5 expected days to 151.1, even though profit factor rises "
    "from 1.855 to 2.068. The old 126.8-day headline was paid for by a leg that "
    "cannot be distinguished from noise. Re-pricing on its own is nearly a no-op "
    "(126.8 -> 125.5) because gold's gain and silver's loss cancel."
)


def write_ribbon_board(t: pd.DataFrame):
    from core import board
    keys = [("XAUUSD", "15m", "single"), ("XAUUSD", "1h", "single"),
            ("XAUUSD", "30m", "single")]
    parts = [t[(t.sym == s) & (t.tf == tf) & (t.rule == rl)] for s, tf, rl in keys]
    lo = max(p.exit_ts.min() for p in parts)
    hi = min(p.exit_ts.max() for p in parts)
    cut = [p[(p.exit_ts >= lo) & (p.exit_ts <= hi)].copy() for p in parts]
    n = len(cut)
    tr = pd.concat(cut, ignore_index=True).sort_values("exit_ts")
    # r_2x at measured cost: double the measured round trip, same linear rule
    c = tr.r - tr.r_2x
    r0 = tr.r + c
    scale = MEASURED["XAUUSD"] / assumed("XAUUSD")
    rm = r0 - scale * c
    rm2 = r0 - 2 * scale * c

    nt = null_table()
    real = int(nt[nt.sym == "XAUUSD"].real_clear.iloc[0])
    nullm = float(nt[nt.sym == "XAUUSD"].null_clear_mean.iloc[0])

    legpay = pd.DataFrame({"sym": tr.sym, "tf": tr.tf + " single",
                           "exit_ts": tr.exit_ts, "r": rm.values, "r_2x": rm2.values})
    return board.write_board(
        sid="ribbon", hid="H-016", name="Trend-following MA ribbon — gold only",
        tagline="Twenty moving averages agreeing across timescales. Beats its "
                "null on gold, loses to it on silver, and is still too slow.",
        period=f"XAUUSD 15m + 30m + 1h · walk-forward "
               f"{tr.exit_ts.min():%Y-%m} to {tr.exit_ts.max():%Y-%m} · "
               f"MEASURED {MEASURED['XAUUSD']*2:.2f}bps round trip",
        report="strategies/ribbon/notes.md",
        candidate="no — fails the phase gate at 151 expected days, and dropping "
                  "the null-failing silver leg made it slower, not faster",
        r=rm.values / n, r_2x=rm2.values / n,
        entry_ts=tr.entry_ts.values, exit_ts=tr.exit_ts.values, n_books=n,
        null_margin=0.0, beats_null=real > nullm, consistency=0.0,
        legs=board.leg_payload(legpay,
                               picked=[(s, f"{tf} single") for s, tf, _ in keys],
                               cap=None),
        markets={"traded": [{"sym": s, "tf": f"{tf} single", "asset": "XAU"}
                            for s, tf, _ in keys],
                 "searched": "12 markets x 5 timeframes x 660 configurations "
                             "(37,620 backtests), plus S&P 500, US30 and Nasdaq "
                             "- all three rejected",
                 "note": "Silver was dropped 2026-09-07: it loses to this "
                         "hypothesis's own null and was priced at half its "
                         "measured spread."},
        todo=[
            {"t": "Walk-forward against a paired null", "w": "Gold clears 5 of 8 cells against the null's 1.0. Silver clears 2 of 6 against 3.7 and is gone.", "done": True},
            {"t": "Measured cost", "w": "0.915bps/side from 478 sampled hours of Dukascopy ticks, against 1.50 assumed.", "done": True},
            {"t": "Phase gate", "w": "151 expected days against a 45-day target.", "done": False},
            {"t": "A gold bear market", "w": "The cache starts 2023-09 and holds one bull market. There is nothing else to test on.", "done": False},
            {"t": "Independent-engine cross-check", "w": "This kernel has never been run through a second engine.", "done": False},
        ],
        note=BOOK_NOTE,
    )


if "--board" in sys.argv:
    _t = pd.read_parquet(BT / "stage10_trades.parquet")
    _t["exit_ts"] = pd.to_datetime(_t.exit_ts, utc=True)
    _t["entry_ts"] = pd.to_datetime(_t.entry_ts, utc=True)
    _t["rm"] = np.nan
    for _s, _g in _t.groupby("sym"):
        _t.loc[_g.index, "rm"] = reprice(_g, _s).values
    print("\nREAL vs THIS HYPOTHESIS'S OWN NULL")
    print(null_table().to_string(index=False))
    write_ribbon_board(_t)
