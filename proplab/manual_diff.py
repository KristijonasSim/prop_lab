"""Compare hand-traded results against the mechanical rules.

The interesting case is a discretionary trader who is profitable on a setup
whose mechanical version is not. The difference is information, and it lives in
one of three places:

  SKIPPED    - signals the rules fired and the human declined. If the skipped
               ones lose on average, the filter is the edge.
  EXTRA      - trades the human took with no mechanical signal. The rules are
               missing a setup the human can see.
  MATCHED    - same setup, different execution. Entry timing, exit timing and
               hold length are compared trade by trade.

This does not prove a discretionary edge exists: trades recalled or marked
after the fact are selected by hindsight. It is only worth trusting on trades
recorded prospectively, ideally with bar replay and no peeking. What it does do
is turn "I trade it better" into a specific, testable difference.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

REQUIRED = {"entry_time", "side"}


def load_manual(path: str | Path, tz: str = "America/New_York") -> pd.DataFrame:
    """Read a hand-kept trade log. Times may be local (tz) or carry an offset."""
    df = pd.read_csv(path)
    df.columns = [c.strip().lower().replace(" ", "_") for c in df.columns]
    missing = REQUIRED - set(df.columns)
    if missing:
        raise ValueError(f"manual trade log needs columns {sorted(missing)}; "
                         f"found {sorted(df.columns)}")
    for col in ("entry_time", "exit_time"):
        if col in df:
            ts = pd.to_datetime(df[col], errors="coerce")
            df[col] = (ts.dt.tz_localize(tz).dt.tz_convert("UTC")
                       if ts.dt.tz is None else ts.dt.tz_convert("UTC"))
    df["side"] = df["side"].str.strip().str.lower()
    return df.sort_values("entry_time").reset_index(drop=True)


def mechanical_trades(result) -> pd.DataFrame:
    rows = [{
        "entry_time": pd.Timestamp(t.entry_time),
        "exit_time": pd.Timestamp(t.exit_time),
        "side": "long" if t.direction == 1 else "short",
        "entry_price": t.entry_price, "exit_price": t.exit_price,
        "net_pnl": t.net_pnl, "bars_held": t.bars_held,
    } for t in result.trades]
    return pd.DataFrame(rows)


def compare(manual: pd.DataFrame, mech: pd.DataFrame,
            tolerance_hours: float = 8.0) -> dict:
    """Match on the same session and direction, within `tolerance_hours`."""
    man = manual.copy()
    mec = mech.copy()
    man["_day"] = man["entry_time"].dt.date
    mec["_day"] = mec["entry_time"].dt.date
    man["_matched"] = -1
    mec["_matched"] = -1

    for i, m in man.iterrows():
        cand = mec[(mec["_day"] == m["_day"]) & (mec["side"] == m["side"])
                   & (mec["_matched"] < 0)]
        if cand.empty:
            continue
        delta = (cand["entry_time"] - m["entry_time"]).abs()
        j = delta.idxmin()
        if delta[j] <= pd.Timedelta(hours=tolerance_hours):
            man.at[i, "_matched"] = j
            mec.at[j, "_matched"] = i

    matched = man[man["_matched"] >= 0]
    extra = man[man["_matched"] < 0]
    skipped = mec[mec["_matched"] < 0]

    rows = []
    for _, m in matched.iterrows():
        k = mec.loc[m["_matched"]]
        rows.append({
            "day": str(m["_day"]), "side": m["side"],
            "entry_delta_min": round(
                (m["entry_time"] - k["entry_time"]).total_seconds() / 60, 1),
            "exit_delta_min": (round(
                (m["exit_time"] - k["exit_time"]).total_seconds() / 60, 1)
                if "exit_time" in m and pd.notna(m.get("exit_time")) else None),
            "manual_pnl": m.get("net_pnl"),
            "mechanical_pnl": round(k["net_pnl"], 2),
        })
    detail = pd.DataFrame(rows)

    def total(df, col="net_pnl"):
        return round(float(df[col].sum()), 2) if col in df and len(df) else None

    return {
        "n_manual": int(len(man)),
        "n_mechanical": int(len(mec)),
        "n_matched": int(len(matched)),
        "n_skipped_by_hand": int(len(skipped)),
        "n_taken_without_signal": int(len(extra)),
        "skipped_mechanical_pnl": total(skipped),
        "matched_mechanical_pnl": total(mec[mec["_matched"] >= 0]),
        "manual_total_pnl": total(man),
        "skipped": skipped.drop(columns=["_day", "_matched"], errors="ignore"),
        "extra": extra.drop(columns=["_day", "_matched"], errors="ignore"),
        "matched_detail": detail,
        "reading": _reading(len(skipped), total(skipped), detail),
    }


def _reading(n_skipped: int, skipped_pnl, detail: pd.DataFrame) -> str:
    parts = []
    if n_skipped and skipped_pnl is not None:
        if skipped_pnl < 0:
            parts.append(
                f"The {n_skipped} signals declined by hand would have lost "
                f"{abs(skipped_pnl):.0f} between them - the filtering is doing "
                f"real work, and identifying WHAT is being filtered is the "
                f"whole prize.")
        else:
            parts.append(
                f"The {n_skipped} declined signals would have MADE "
                f"{skipped_pnl:.0f}. The selection is costing money, so the edge "
                f"is elsewhere - most likely in the exits.")
    if len(detail) and detail["exit_delta_min"].notna().any():
        med = detail["exit_delta_min"].median()
        if med < -20:
            parts.append(f"Exits are typically {abs(med):.0f} minutes EARLIER "
                         f"than the mechanical end-of-session flatten, which is "
                         f"a testable rule on its own.")
        elif med > 20:
            parts.append(f"Exits are typically {med:.0f} minutes later than the "
                         f"mechanical flatten.")
    if not parts:
        parts.append("Not enough overlap to read a pattern yet.")
    return " ".join(parts)


TEMPLATE = """entry_time,exit_time,side,entry_price,exit_price,net_pnl,note
2026-06-02 10:15,2026-06-02 11:30,short,68556.1,68100.0,,skipped the 11:15 one, range too wide
"""


def write_template(path: str | Path) -> Path:
    path = Path(path)
    path.write_text(TEMPLATE)
    return path
