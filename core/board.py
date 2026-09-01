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


def write_board(*, sid: str, hid: str, name: str, tagline: str, period: str,
                report: str, candidate: str,
                r: np.ndarray, entry_ts, exit_ts,
                r_2x: np.ndarray | None = None, n_books: int = 1,
                null_margin: float = 0.0, consistency: float = 0.0,
                beats_null: bool = False,
                grid: dict | None = None, todo: list | None = None,
                note: str | None = None) -> dict:
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
        "ladder": rows, "pick": pick,
        "grid": grid or {}, "todo": todo or [], "note": note,
    }
    out = BT / sid / "board.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(rec, indent=1))
    print(f"  wrote {out}")
    print(f"    {name}: PF {fields['pf']}  {fields['trades']} trades  "
          f"{fields['trades_per_day']}/day across {n_books} sub-strategies "
          f"({fields['tpd_per_book']}/day each)  R/day {fields['r_per_day']:+.4f}")
    print(f"    pick {pick['risk']*100:.2f}% risk  pass {pick['pass_rate']*100:.1f}%  "
          f"killed {(pick['fail_max']+pick['fail_daily'])*100:.1f}%  "
          f"median {pick['median_days']} d  expected {pick['expected_days']} d")
    return rec
