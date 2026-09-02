"""H-013 stage 3 — the premium as a SECOND gate on H-009.

Stage 2 rejected H-013 as a standalone strategy: at every hold and every cost
level the block-shuffle null cleared the gate as often as the real signal and
its best config scored higher. That is the same verdict H-006 got, and H-006's
resolution is instructive - the signal was real, the STRATEGY was dead, and its
value was realised by using it to veto another strategy's trades. That produced
H-009, the top of the board.

So this asks the only question left that the stage-1 evidence supports:

    H-009 already keeps a trade only when the CROWD is on the other side.
    Does keeping it only when the PREMIUM also disagrees make it better?

The two are near-orthogonal by measurement (Spearman -0.05/-0.12/-0.16 against
crowd_z), so this is a second opinion, not a louder version of the first.

Direction. Stage 1 says a rich perp is followed by weakness, so the gate keeps a
LONG only when the premium is low or falling, and a SHORT only when it is high
or rising - the mirror of H-009's crowd rule.

Everything here is a POST-FILTER on trades that already exist at real prices, so
no fill assumption changes. It can only remove trades, never add them, which is
the same limitation H-009 carries and is stated in its notes.

Gate threshold is fixed at zero, not searched, for the same reason H-009 fixed
it: a searched threshold on 859 trades is a fitted number.

Run: .venv/bin/python strategies/basis/stage3_gate.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from strategies.basis import basis as bs                      # noqa: E402

FEEDS = ROOT / "data" / "feeds"
OUT = ROOT / "backtests" / "basis"
TRADES = ROOT / "backtests" / "gated_vwap" / "stage6_trades.parquet"
CRYPTO = {"BTCUSDT", "ETHUSDT", "SOLUSDT"}
NSEEDS = 5


def pf(r):
    w, l = r[r > 0].sum(), -r[r < 0].sum()
    return float(w / l) if l > 0 else float("nan")


def maxdd(r):
    e = np.cumsum(r)
    return float((e - np.maximum.accumulate(e)).min())


def stats(d, col="r_2x"):
    r = d[col].values
    if len(r) < 20:
        return {}
    span = max((d.exit_ts.max() - d.entry_ts.min()).days, 1)
    dd = maxdd(r)
    return {"trades": len(r), "pf": round(pf(d.r.values), 4),
            "pf_2x": round(pf(r), 4), "total_r": round(float(r.sum()), 1),
            "maxdd_r": round(dd, 2),
            "ret_dd": round(float(r.sum()) / abs(dd), 2) if dd else np.nan,
            "r_per_day": round(float(r.sum()) / span, 4),
            "tpd": round(len(r) / span, 3)}


def gate_series(sym: str, kind: str, win: int) -> pd.Series:
    df = bs.load(sym, FEEDS)
    return bs.signal_series(df, kind, 48, win)


def main():
    t = pd.read_parquet(TRADES)
    t = t[t.gated].copy() if t.gated.any() else t.copy()
    t["entry_ts"] = pd.to_datetime(t.entry_ts, utc=True)
    t["exit_ts"] = pd.to_datetime(t.exit_ts, utc=True)
    base = t.copy()
    print(f"H-009 book as it stands: {len(base)} trades "
          f"{base.entry_ts.min():%Y-%m} -> {base.exit_ts.max():%Y-%m}")
    print(f"  {stats(base)}\n")

    for kind, win in (("prem_z", 288), ("prem_z", 864), ("dprem", 0), ("lead", 0)):
        keep = pd.Series(True, index=t.index)
        cover = 0
        for sym in sorted(set(t.symbol) & CRYPTO):
            try:
                s = gate_series(sym, kind, win)
            except FileNotFoundError:
                continue
            m = t.symbol == sym
            # As-of join, and the offset matters: the signal indexed at bar T
            # covers [T, T+5m) and is only OBSERVABLE at T+5m, so the index is
            # advanced by one bar before the join. Without that the gate reads a
            # bar that had not finished when the trade was entered. merge_asof
            # rather than reindex because several legs enter on the same stamp.
            sd = s.dropna()
            obs = pd.DataFrame({"obs_ts": sd.index + pd.Timedelta(minutes=5),
                                "v": sd.values}).sort_values("obs_ts")
            left = (t.loc[m, ["entry_ts"]].rename_axis("tid").reset_index()
                     .sort_values("entry_ts"))
            j = pd.merge_asof(left, obs, left_on="entry_ts", right_on="obs_ts",
                              direction="backward",
                              tolerance=pd.Timedelta(days=1))
            v = j.set_index("tid").reindex(t.index[m]).v.values
            d = t.loc[m, "direction"].values
            # long only when the perp is CHEAP/cheapening, short only when rich
            ok = np.where(d > 0, v < 0, v > 0)
            ok = np.where(np.isnan(v), True, ok)     # no feed = leave the trade
            keep.loc[t.index[m]] = ok
            cover += int(m.sum())
        on = t[keep]
        off = t[~keep]
        a, b = stats(base), stats(on)
        print(f"gate = {kind} (win {win}) — covers {cover} crypto trades, "
              f"keeps {len(on)}/{len(base)} ({len(on)/len(base):.0%})")
        print(f"  gate off  PF2x {a['pf_2x']:.3f}  maxDD {a['maxdd_r']:.2f}R  "
              f"totR {a['total_r']:.1f}  ret/DD {a['ret_dd']:.1f}  "
              f"R/day {a['r_per_day']:.4f}")
        if b:
            print(f"  gate on   PF2x {b['pf_2x']:.3f}  maxDD {b['maxdd_r']:.2f}R  "
                  f"totR {b['total_r']:.1f}  ret/DD {b['ret_dd']:.1f}  "
                  f"R/day {b['r_per_day']:.4f}")
        if len(off) >= 20:
            c = stats(off)
            print(f"  REMOVED   PF2x {c['pf_2x']:.3f}  totR {c['total_r']:.1f} "
                  f"({len(off)} trades) — the gate is only real if what it "
                  f"throws away is worse than what it keeps")
        print()


if __name__ == "__main__":
    main()
