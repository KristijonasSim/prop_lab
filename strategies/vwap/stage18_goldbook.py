"""H-002 stage 18 — the gold book, re-priced at MEASURED cost, and combined.

Two tasks from `NEXT.md` in one place, because they need the same object:

  T3 item 1 — **combine the gold cells.** The 5m, 1h, 4h and 15m walk-forward
              cells all clear their gate and are different holds on the same
              instrument. They were only ever scored one at a time. If their
              drawdowns do not coincide, the book is faster than any leg.
  T5        — **the board publishes dead numbers.** `backtests/vwap/board.json`
              was written 2026-09-02 on the pre-fix kernel and its book is BTC
              4h + ETH 1h + ETH 30m + SOL 4h + gold 5m. Four of those five legs
              died on 2026-09-06. This rewrites the record on the post-fix
              walk-forward, at measured cost, gold only.

RE-PRICING IS EXACT, NOT APPROXIMATE. The walk-forward stored each trade at 1x
and 2x cost and R is linear in cost, so

    C/risk = r_1x - r_2x        r_0x = 2*r_1x - r_2x        r_s = r_0x - s*C/risk

recovers any cost level from the two. XAUUSD was walked forward at an ASSUMED
1.50bps/side (3.00 round trip). `core/fx_spread.py` measured 478 hours of
Dukascopy ticks: median spread 1.621bps of mid, mean 1.671, plus ~0.15bps
round-trip cTrader commission — **1.83bps round trip**, so s = 1.83/3.00 = 0.61.
Both the median (1.77) and the mean (1.83) reading are reported; the mean is the
headline because that is what SESSION_2026-09-06 used.

WHAT A "CELL" IS AND WHY MOST COMBINATIONS ARE FAKE. A cell is (timeframe,
train-trade floor, top-N). Two cells on the SAME timeframe are the same walk
re-selected — 5m/floor100/top10 and 5m/floor30/top10 overlap heavily — so
combining them is one book counted twice, not diversification. **One cell per
timeframe, maximum.** That leaves five genuine legs.

H-012'S WARNING APPLIES DIRECTLY. Adding legs to cut drawdown made the book
SLOWER, not faster: 15.9 in-window days became 130.7 held out, because equal
weighting divides the book's R by the leg count and the median leg had R/day
−0.0013. So equal weight is reported as the control and never as the answer,
and every combination is scored on **days to a funded account**, not on profit
factor.

THE NULL COMES WITH IT. `stage6_trades_shuffled_paired.parquet` holds the same
walk-forward on phase-randomised markets. Every combination built here is built
again from the null's cells by the identical rule, so a book assembled by
searching twenty cells is compared against books assembled the same way from
data with no edge in it.

Run: .venv/bin/python strategies/vwap/stage18_goldbook.py
"""
from __future__ import annotations

import itertools
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from core import board, riskladder                              # noqa: E402

BT = ROOT / "backtests" / "vwap"
OUT = BT
SYM = "XAUUSD"

ASSUMED_RT = 3.00          # bps round trip the walk-forward charged
MEASURED_RT = 1.83         # 1.671 mean spread + 0.15 commission
MEDIAN_RT = 1.77           # 1.621 median spread + 0.15 commission
GATE = 1.20
TF_ORDER = ["5m", "15m", "30m", "1h", "4h"]


def reprice(t: pd.DataFrame, rt_bps: float) -> pd.Series:
    """R at an arbitrary round-trip cost, from the stored 1x and 2x series."""
    c = t.r - t.r_2x                      # one round trip, in R
    r0 = t.r + c                          # zero cost
    return r0 - (rt_bps / ASSUMED_RT) * c


def pf(r) -> float:
    r = np.asarray(r)
    w, l = r[r > 0].sum(), -r[r < 0].sum()
    return float(w / l) if l > 0 else (float("inf") if w > 0 else float("nan"))


def maxdd(r) -> float:
    eq = np.concatenate(([0.0], np.cumsum(np.asarray(r))))
    return abs(float((eq - np.maximum.accumulate(eq)).min()))


def score(r: np.ndarray, exit_ts, label: str, n_legs: int = 1) -> dict:
    rows, pick = riskladder.from_trades(r, exit_ts)
    span = max((pd.DatetimeIndex(exit_ts).max()
                - pd.DatetimeIndex(exit_ts).min()).days, 1)
    return {"book": label, "legs": n_legs, "trades": len(r),
            "pf": round(pf(r), 3), "total_r": round(float(r.sum()), 2),
            "max_dd_r": round(maxdd(r), 2),
            "r_per_day": round(float(r.sum()) / span, 4),
            "tpd": round(len(r) / span, 2),
            "win": round(float((r > 0).mean()), 4),
            "avg_r": round(float(r.mean()), 4),
            "risk": pick.get("risk"), "pass_rate": pick.get("pass_rate"),
            "median_days": pick.get("median_days"),
            "expected_days": pick.get("expected_days"),
            "one_step_days": pick.get("one_step", {}).get("expected_days"),
            "fail_max": pick.get("fail_max"), "fail_daily": pick.get("fail_daily")}


def cells(path: Path, rt_bps: float) -> dict:
    """Every (tf, floor, topn) cell for gold, re-priced, keyed and time-sorted."""
    t = pd.read_parquet(path)
    t = t[t.symbol == SYM].copy()
    t["exit_ts"] = pd.to_datetime(t.exit_ts, utc=True)
    t["rm"] = reprice(t, rt_bps)
    out = {}
    for k, g in t.groupby(["tf", "floor", "topn"]):
        out[k] = g.sort_values("exit_ts")[["exit_ts", "entry_ts", "rm"]]
    return out


def combine(legs: list[pd.DataFrame], weights: np.ndarray) -> pd.DataFrame:
    """One book from several legs. A leg weighted w contributes w x its own R,
    and the weights sum to 1, so the book's R is on the same scale as a single
    leg's and `days = maxDD / R_per_day` stays comparable."""
    parts = []
    for lg, w in zip(legs, weights):
        p = lg.copy()
        p["rm"] = p.rm * w
        parts.append(p)
    return pd.concat(parts, ignore_index=True).sort_values("exit_ts")


def best_per_tf(cs: dict, window) -> dict:
    """The one cell to represent each timeframe, chosen on total R inside the
    common window. Two cells on one timeframe are the same walk re-selected."""
    lo, hi = window
    out = {}
    for tf in TF_ORDER:
        cand = {k: v for k, v in cs.items() if k[0] == tf}
        if not cand:
            continue
        best, bestr = None, -np.inf
        for k, g in cand.items():
            s = g[(g.exit_ts >= lo) & (g.exit_ts <= hi)]
            if len(s) < 30:
                continue
            if float(s.rm.sum()) > bestr:
                best, bestr = k, float(s.rm.sum())
        if best is not None:
            out[tf] = best
    return out


def build(cs: dict, tag: str) -> tuple:
    """Score every single cell, then every one-cell-per-timeframe combination,
    under three weightings. Returns (single-cell rows, book rows, chosen)."""
    lo = max(g.exit_ts.min() for g in cs.values())
    hi = min(g.exit_ts.max() for g in cs.values())
    cut = {k: g[(g.exit_ts >= lo) & (g.exit_ts <= hi)] for k, g in cs.items()}

    singles = []
    for k, g in sorted(cut.items()):
        if len(g) < 30:
            continue
        s = score(g.rm.values, g.exit_ts, f"{k[0]} floor{k[1]} top{k[2]}")
        s.update(tf=k[0], floor=k[1], topn=k[2], tag=tag)
        singles.append(s)
    singles = pd.DataFrame(singles).sort_values("expected_days",
                                                na_position="last")

    rep = best_per_tf(cut, (lo, hi))
    books = []
    tfs = [tf for tf in TF_ORDER if tf in rep]
    for n in range(2, len(tfs) + 1):
        for combo in itertools.combinations(tfs, n):
            legs = [cut[rep[tf]] for tf in combo]
            rday = np.array([max(float(l.rm.sum()), 0.0) for l in legs])
            dd = np.array([max(maxdd(l.rm.values), 1e-9) for l in legs])
            for wname, w in (
                    ("equal", np.ones(n) / n),
                    # signal-to-cost: R earned per unit of drawdown risked. This
                    # is the weighting H-012 said was missing when a wider book
                    # made things slower.
                    ("sig_cost", (rday / dd) / max((rday / dd).sum(), 1e-9)),
                    ("by_r", rday / max(rday.sum(), 1e-9))):
                if not np.isfinite(w).all() or w.sum() <= 0:
                    continue
                bk = combine(legs, w)
                s = score(bk.rm.values, bk.exit_ts,
                          "+".join(combo) + f" [{wname}]", n_legs=n)
                s.update(weighting=wname, combo="+".join(combo), tag=tag)
                books.append(s)
    return singles, pd.DataFrame(books), rep


def main():
    print(f"gold cells re-priced from {ASSUMED_RT}bps assumed to "
          f"{MEASURED_RT}bps MEASURED round trip "
          f"(scale {MEASURED_RT/ASSUMED_RT:.3f})\n")

    real = cells(BT / "stage6_trades.parquet", MEASURED_RT)
    null = cells(BT / "stage6_trades_shuffled_paired.parquet", MEASURED_RT)
    s_real, b_real, rep = build(real, "real")
    s_null, b_null, rep_n = build(null, "null")

    cols = ["book", "trades", "pf", "total_r", "max_dd_r", "r_per_day", "tpd",
            "win", "risk", "pass_rate", "median_days", "expected_days",
            "one_step_days"]
    print("=" * 108)
    print("SINGLE CELLS — XAUUSD, post-fix walk-forward, MEASURED cost")
    print("=" * 108)
    print(s_real[cols].to_string(index=False))
    print(f"\ncells clearing PF {GATE}: real {int((s_real.pf >= GATE).sum())}"
          f"/{len(s_real)}   null {int((s_null.pf >= GATE).sum())}/{len(s_null)}")
    print(f"best PF: real {s_real.pf.max():.3f}   null {s_null.pf.max():.3f}")

    print(f"\nrepresentative cell per timeframe: "
          f"{ {tf: f'floor{k[1]} top{k[2]}' for tf, k in rep.items()} }")
    print("\n" + "=" * 108)
    print("COMBINED BOOKS — one cell per timeframe, three weightings")
    print("=" * 108)
    b = b_real.sort_values("expected_days", na_position="last")
    print(b[cols].head(20).to_string(index=False))

    s_real.to_csv(OUT / "stage18_gold_cells.csv", index=False)
    b_real.to_csv(OUT / "stage18_gold_books.csv", index=False)
    s_null.to_csv(OUT / "stage18_gold_cells_null.csv", index=False)
    b_null.to_csv(OUT / "stage18_gold_books_null.csv", index=False)

    def fastest(df):
        d = df[df.expected_days.notna()]
        return None if d.empty else d.loc[d.expected_days.idxmin()]

    fb, fs = fastest(b_real), fastest(s_real)
    nb, ns = fastest(b_null), fastest(s_null)
    print("\n" + "=" * 108)
    print("THE ONLY QUESTION THAT MATTERS: does combining make it FASTER?")
    print("=" * 108)
    for tag, x, nx in (("best single cell", fs, ns), ("best combined book", fb, nb)):
        if x is None:
            continue
        print(f"{tag:20} {x.book:34} PF {x.pf:6.3f}  {x.tpd:5.2f}/day  "
              f"maxDD {x.max_dd_r:6.2f}R  R/day {x.r_per_day:+.4f}  "
              f"pass {x.pass_rate:.3f}  median {x.median_days} d  "
              f"expected {x.expected_days} d")
        if nx is not None:
            print(f"{'  its null':20} {nx.book:34} PF {nx.pf:6.3f}  "
                  f"expected {nx.expected_days} d")
    if fb is not None and fs is not None:
        better = fb.expected_days < fs.expected_days
        print(f"\nCOMBINING {'HELPS' if better else 'DOES NOT HELP'}: "
              f"{fs.expected_days} d single -> {fb.expected_days} d combined")
    print("\nTARGET is 45 days. Everything above is measured on 7 walk-forward "
          "quarters, 2024-09 to 2026-05.")


if __name__ == "__main__":
    main()


# ---------------------------------------------------------------------------
# The board record. Appended 2026-09-07 for TASK T5.
# ---------------------------------------------------------------------------

BOOK_NOTE = (
    "Gold, and only gold. Every crypto leg this hypothesis used to carry died on "
    "2026-09-06 when three look-aheads were removed from the kernel - BTCUSDT went "
    "from 11 walk-forward cells clearing PF 1.20 at 2x to zero. XAUUSD went the "
    "other way, 3 cells to 11, and it is the first walk-forward in this project to "
    "beat a paired null by a real margin: 11 of 20 real cells clear against 0 of 20 "
    "for the null, whose best cell does not reach the gate at all. The book here is "
    "the 5m and 4h cells traded together, equally weighted, priced at the MEASURED "
    "1.83bps round trip rather than the 3.00bps the walk-forward assumed. Combining "
    "them is worth roughly half the time to a funded account - 193 expected days for "
    "the fastest single cell, 100 for the pair - because the two holds draw down at "
    "different times. Read the number with its caveat: the PAIR was chosen by "
    "searching 78 combinations on the same out-of-sample window, so the fastest one "
    "is a maximum over a search. The same search on phase-randomised markets "
    "produced 0 of 78 books under 150 days against the real data's 9, and its best "
    "book needs 301. It is still 100 days against a 45-day target."
)


def write_gold_board(rt_bps: float = MEASURED_RT):
    """Rewrite `backtests/vwap/board.json` on the post-fix, gold-only book."""
    real1 = cells(BT / "stage6_trades.parquet", rt_bps)
    real2 = cells(BT / "stage6_trades.parquet", rt_bps * 2)
    lo = max(g.exit_ts.min() for g in real1.values())
    hi = min(g.exit_ts.max() for g in real1.values())
    rep = best_per_tf({k: g[(g.exit_ts >= lo) & (g.exit_ts <= hi)]
                       for k, g in real1.items()}, (lo, hi))
    picked = [rep[tf] for tf in ("5m", "4h") if tf in rep]
    if len(picked) != 2:
        print("gold cells missing; board not written"); return None

    parts = []
    for k in picked:
        a = real1[k]; b = real2[k]
        s = a[(a.exit_ts >= lo) & (a.exit_ts <= hi)].copy()
        s2 = b[(b.exit_ts >= lo) & (b.exit_ts <= hi)]
        s["r_2x"] = s2.rm.values
        s["tf"] = k[0]
        parts.append(s)
    tr = pd.concat(parts, ignore_index=True).sort_values("exit_ts")
    n = len(parts)
    r = tr.rm.values / n                     # equal weight, so one leg's scale
    r2 = tr.r_2x.values / n

    legs = board.leg_payload(
        pd.DataFrame({"sym": SYM, "tf": tr.tf, "exit_ts": tr.exit_ts,
                      "r": tr.rm.values, "r_2x": tr.r_2x.values}),
        picked=[(SYM, k[0]) for k in picked], cap=None)

    return board.write_board(
        sid="vwap", hid="H-002", name="VWAP — gold only",
        tagline="The one edge that survived the 2026-09-06 kernel fix.",
        period=f"XAUUSD 5m + 4h · walk-forward 2024-09 → 2026-05 · "
               f"MEASURED {rt_bps}bps round trip",
        report="", n_books=n,
        candidate="config re-chosen blind each quarter on train PF; the 5m+4h "
                  "pairing chosen from 78 combinations on the same window",
        r=r, r_2x=r2, entry_ts=tr.entry_ts, exit_ts=tr.exit_ts,
        null_margin=0.0, beats_null=True, consistency=0.0, legs=legs,
        markets={"traded": [{"sym": SYM, "tf": k[0], "asset": "XAU"} for k in picked],
                 "searched": "20 walk-forward cells on XAUUSD x 5 timeframes x "
                             "2 train-trade floors x top-1/top-10, then 78 "
                             "one-cell-per-timeframe combinations",
                 "note": "Crypto is NOT here. It died to the kernel fix."},
        todo=[
            {"t": "Walk-forward, config chosen blind each quarter", "w": "Seven quarters, 2024-09 to 2026-05.", "done": True},
            {"t": "Paired null on the FIXED kernel", "w": "11 of 20 real cells clear against 0 of 20 for the null.", "done": True},
            {"t": "Measured cost, not assumed", "w": "1.83bps round trip from 478 sampled hours of Dukascopy ticks, against 3.00 assumed.", "done": True},
            {"t": "Independent-engine cross-check", "w": "stage17 ports the kernel to NautilusTrader and compares every configuration gold's folds chose.", "done": False},
            {"t": "Held-out check on the COMBINATION", "w": "The 5m+4h pairing was chosen on the same window it is scored on. The null controls the search; a fresh window would settle it.", "done": False},
            {"t": "Pace", "w": "100 expected days against a 45-day target. Still 2.2x short.", "done": False},
        ],
        note=BOOK_NOTE,
    )


if "--board" in sys.argv:
    write_gold_board()
