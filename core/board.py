"""One board record per hypothesis, in one shape.

`core/build_scoreboard.py` reads only these files. Keeping the shape in a single
writer means a new hypothesis cannot half-implement it: hand `write_board` a
stitched walk-forward trade series and it gets the same prop simulation, the
same risk ladder and the same comparable score as everything already on the
board.

The split that matters: `measured` holds the inputs that do NOT depend on risk
per trade (profit factor, cost robustness, null margin, consistency, Sharpe),
and the ladder holds the ones that do (pass rate, breach rates, days, drawdown).
The board scores every ladder level by combining the two.
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core import riskladder as RL                        # noqa: E402

BT = ROOT / "backtests"


def pf_of(r: np.ndarray) -> float:
    w, l = r[r > 0].sum(), -r[r < 0].sum()
    return float(w / l) if l > 0 else (math.inf if w > 0 else float("nan"))


def stitched_fields(r: np.ndarray, entry_ts, exit_ts, risk: float) -> dict:
    """Every field CLAUDE.md marks mandatory, on a stitched walk-forward series."""
    exit_ts = pd.DatetimeIndex(exit_ts)
    entry_ts = pd.DatetimeIndex(entry_ts)
    span = max((exit_ts[-1] - exit_ts[0]).total_seconds() / 86400.0, 1e-9)
    eq = np.concatenate(([0.0], np.cumsum(r)))
    dd_r = float((eq - np.maximum.accumulate(eq)).min())
    daily = pd.Series(r * risk, index=exit_ts).resample("1D").sum()
    sd = daily.std(ddof=1)
    hold = (exit_ts.values - entry_ts.values).astype("timedelta64[s]").astype(float)
    return {
        "pf": round(pf_of(r), 3),
        "trades": int(len(r)),
        "trades_per_day": round(len(r) / span, 3),
        "trades_per_week": round(7 * len(r) / span, 2),
        "avg_hold_h": round(float(np.mean(hold)) / 3600.0, 2),
        "win_rate": round(float((r > 0).mean()), 4),
        "avg_r": round(float(r.mean()), 4),
        "total_r": round(float(r.sum()), 2),
        "max_dd_r": round(dd_r, 2),
        "sharpe": round(float(daily.mean() / sd * math.sqrt(365)), 3) if sd else 0.0,
    }


def leg_payload(tr, *, picked, cap: int | None = 8, start=None,
                tf_label: str | None = None) -> dict:
    """Per-leg out-of-sample trades, so the board page can rebuild the book.

    The one thing people misread about this board is whose profit factor they
    are looking at: it is the whole book's, never a single market's. Shipping
    the trades lets the page answer that directly - tick a leg off and every
    number recomputes from the rest.

    `tr` needs the columns `sym`, `tf`, `exit_ts`, `r`, `r_2x`, with `r` being
    each leg's own R multiple, NOT yet divided by the number of legs. The page
    divides by however many are ticked, which is what equal weight means here.

    Every leg is cut to the SAME window, so any subset the trader ticks is
    measured over identical dates. `start` fixes that window explicitly (the
    H-002 book uses the first quarter its FX legs have); left out, it is the
    latest first-trade across the legs, which is the earliest date on which the
    whole set can be compared.

    `cap` bounds how many legs are offered. A walk-forward over 44 combinations
    is a wall, not a tool, and its trades run to megabytes on the page - so the
    board's own picks are always kept and the rest are the best remaining by
    profit factor at DOUBLE cost. Pass None to keep them all.
    """
    tr = tr.copy()
    tr["exit_ts"] = pd.to_datetime(tr.exit_ts, utc=True)
    if tf_label is not None:
        tr["tf"] = tf_label
    keys = list(dict.fromkeys(zip(tr.sym, tr.tf)))
    picked = [tuple(x) for x in picked]

    if cap is not None and len(keys) > cap:
        rank = {k: pf_of(g.r_2x.values)
                for k, g in tr.groupby(["sym", "tf"], sort=False)}
        rest = sorted((k for k in keys if k not in picked),
                      key=lambda k: -(rank.get(k) if rank.get(k) == rank.get(k) else -1))
        keys = picked + rest[:max(cap - len(picked), 0)]

    tr = tr[[(a, b) in keys for a, b in zip(tr.sym, tr.tf)]]
    if start is None:
        # Anchored on the legs the BOARD chose, not on every leg offered. Anchor
        # it on all of them and adding one late-starting candidate silently
        # shortens the window, so ticking the board's own book back on would
        # print a different profit factor from the one the board reports - the
        # page would appear to contradict itself.
        anchor = [k for k in keys if k in picked] or keys
        start = max(g.exit_ts.min() for k, g in tr.groupby(["sym", "tf"], sort=False)
                    if k in anchor)
    start = pd.Timestamp(start)
    start = start.tz_localize("UTC") if start.tzinfo is None else start.tz_convert("UTC")
    tr = tr[tr.exit_ts >= start].sort_values("exit_ts")
    if tr.empty:
        raise ValueError("no trades inside the common window")

    idx = {k: i for i, k in enumerate(keys)}
    day0 = tr.exit_ts.iloc[0].normalize()
    days = (tr.exit_ts.dt.normalize() - day0).dt.days.astype(int)
    items = []
    for a, b in keys:
        g = tr[(tr.sym == a) & (tr.tf == b)]
        span = max((g.exit_ts.iloc[-1] - g.exit_ts.iloc[0]).days, 1) if len(g) else 1
        items.append({"sym": a, "tf": b, "asset": a[:3], "n": int(len(g)),
                      "pf": round(pf_of(g.r.values), 3) if len(g) else None,
                      "pf2x": round(pf_of(g.r_2x.values), 3) if len(g) else None,
                      "tpd": round(len(g) / span, 3)})
    return {
        "start": str(day0.date()), "end": str(tr.exit_ts.iloc[-1].date()),
        "n_days": int(days.max()) + 1,
        "keys": [f"{a} {b}" for a, b in keys], "items": items,
        "picked": [idx[k] for k in picked if k in idx],
        # [leg index, day index, R, R at 2x cost]
        "trades": [[int(a), int(b), round(float(c), 4), round(float(d), 4)]
                   for a, b, c, d in zip([idx[(x, y)] for x, y in zip(tr.sym, tr.tf)],
                                         days, tr.r.values, tr.r_2x.values)],
    }


def write_board(*, sid: str, hid: str, name: str, tagline: str, period: str,
                report: str, candidate: str,
                r: np.ndarray, entry_ts, exit_ts,
                r_2x: np.ndarray | None = None, n_books: int = 1,
                null_margin: float = 0.0, consistency: float = 0.0,
                beats_null: bool = False,
                grid: dict | None = None, todo: list | None = None,
                note: str | None = None, legs: dict | None = None,
                markets: dict | None = None) -> dict:
    """`r` is the stitched out-of-sample trade series - walk-forward output, not
    a fitted backtest. Anything else is not comparable to what is already here
    and should not be put on the board."""
    order = np.argsort(pd.DatetimeIndex(exit_ts).values, kind="stable")
    r = np.asarray(r)[order]
    exit_ts = pd.DatetimeIndex(exit_ts)[order]
    entry_ts = pd.DatetimeIndex(entry_ts)[order]
    if r_2x is not None:
        r_2x = np.asarray(r_2x)[order]

    rows, pick = RL.from_trades(r, exit_ts)
    fields = stitched_fields(r, entry_ts, exit_ts, pick["risk"])
    # A book of N sub-strategies each sized 1/N produces N times the trade rows,
    # each worth 1/N of an R. Reporting only the total makes a book look far
    # busier than the mechanic actually is, and hides that R per day - the thing
    # that sets time-to-pass - has not moved at all.
    fields["n_books"] = int(n_books)
    fields["tpd_per_book"] = round(fields["trades_per_day"] / max(n_books, 1), 3)
    fields["r_per_day"] = round(fields["avg_r"] * fields["trades_per_day"], 4)

    rec = {
        "id": sid, "hid": hid, "name": name, "tagline": tagline,
        "period": period, "report": report, "candidate": candidate,
        "fields": fields,
        "pf_2x": (round(pf_of(r_2x), 3) if r_2x is not None else None),
        "measured": {
            "wf_pf": fields["pf"],
            "wf_pf_2x": (round(pf_of(r_2x), 3) if r_2x is not None else None),
            "null_margin": round(float(null_margin), 4),
            # Explicit, not inferred from the margin: "measured and lost" and
            # "never measured" both give a margin of 0 and both must fail the gate.
            "beats_null": bool(beats_null),
            "consistency": round(float(consistency), 4),
            "pf": fields["pf"],
            "sharpe": fields["sharpe"],
        },
        # Which evaluation structure the ladder's headline numbers are on.
        # Two-step (8% then 5%) since 2026-09-01; every row also carries its
        # one-step values under `one_step`.
        "structure": "two_step",
        "ladder": rows, "pick": pick,
        "grid": grid or {}, "todo": todo or [], "note": note,
        # Optional per-leg trade series, so the page can recompute the book from
        # any subset of markets the trader picks. Only hypotheses whose book is
        # actually several markets have one; see strategies/vwap/stage11_board.py
        # for the shape. Without it the page shows the legs as a static list.
        "legs": legs,
        # What this hypothesis actually trades, stated rather than left to be
        # inferred from a sentence. `traded` is the book the score was measured
        # on, one entry per market/timeframe; `searched` names the universe the
        # configuration was chosen from, which is usually far wider and is the
        # thing that makes a single survivor unimpressive.
        "markets": markets,
    }
    out = BT / sid / "board.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(rec, indent=1))
    print(f"  wrote {out}")
    print(f"    {name}: PF {fields['pf']}  {fields['trades']} trades  "
          f"{fields['trades_per_day']}/day across {n_books} sub-strategies "
          f"({fields['tpd_per_book']}/day each)  R/day {fields['r_per_day']:+.4f}")
    one = pick.get("one_step", {})
    print(f"    pick {pick['risk']*100:.2f}% risk  TWO-STEP pass {pick['pass_rate']*100:.1f}%  "
          f"killed {(pick['fail_max']+pick['fail_daily'])*100:.1f}%  "
          f"median {pick['median_days']} d  expected {pick['expected_days']} d"
          f"   (one-step was {one.get('expected_days')} d)")
    return rec
