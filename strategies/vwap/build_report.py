"""Build the H-002 VWAP results page from the stage CSVs.

Regenerate after any re-run: .venv/bin/python strategies/vwap/build_report.py
Writes backtests/vwap/report.html — publish that as the artifact.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
OUT = ROOT / "backtests" / "vwap"

FAM = {0: "trend", 1: "band fade", 2: "band break", 3: "reclaim", 4: "pullback"}
ORDER = ["XAUUSD", "USDJPY", "EURUSD", "GBPUSD", "AUDUSD", "USDCHF",
         "USDCAD", "NZDUSD", "BTCUSDT"]
NICE = {"XAUUSD": "Gold", "BTCUSDT": "Bitcoin"}
CFGKEY = ["anchor_hour", "anchor_minute", "mode", "fill_mode", "band_k", "stop_mode",
          "stop_k", "target_mode", "rr", "max_hold_bars", "min_rvol",
          "min_atr_rank", "max_atr_rank"]


def _read(stem: Path) -> pd.DataFrame:
    """Prefer the parquet: the CSVs of these sweeps run past GitHub's 100 MB
    file ceiling, so only the parquet is committed."""
    q = stem.with_suffix(".parquet")
    if q.exists():
        return pd.read_parquet(q)
    return pd.read_csv(stem.with_suffix(".csv"), low_memory=False)


def nm(s):
    return NICE.get(s, s)


def anchor_label(r) -> str:
    if r["anchor_hour"] == -1:
        return f"rolling {int(r['anchor_minute'])} bars"
    return f"{int(r['anchor_hour']):02d}:{int(r['anchor_minute']):02d} UTC"


def collect() -> dict:
    d: dict = {}

    # ---------- stage 4: challenge profiles ----------
    pj = OUT / "profiles.json"
    if pj.exists():
        d["profiles"] = json.loads(pj.read_text())
    ps = OUT / "portfolio_scaling.json"
    if ps.exists():
        d["scaling"] = json.loads(ps.read_text())
    pc = OUT / "corr.json"
    if pc.exists():
        d["corr"] = json.loads(pc.read_text())

    # ---------- stage 1: the fill test ----------
    s1 = _read(OUT / "stage1_grid")
    k1 = s1[(s1.cost_mult == 1) & (s1.trades >= 100)]
    band = k1[k1["mode"].isin([1, 2])]          # only the families that enter at a band
    fill = []
    for sym in ORDER:
        g = band[band.symbol == sym]
        if not len(g):
            continue
        lim, hon = g[g.fill_mode == 0], g[g.fill_mode == 1]
        fill.append({
            "symbol": nm(sym),
            "limit_best": round(float(lim.pf.max()), 3),
            "limit_gate": int((lim.pf >= 1.2).sum()),
            "limit_trades": int(lim.trades.median()),
            "honest_best": round(float(hon.pf.max()), 3),
            "honest_gate": int((hon.pf >= 1.2).sum()),
            "honest_trades": int(hon.trades.median()),
        })
    d["fill"] = fill
    d["fill_totals"] = {
        "limit_gate": int((k1[k1.fill_mode == 0].pf >= 1.2).sum()),
        "honest_gate": int((k1[k1.fill_mode == 1].pf >= 1.2).sum()),
        "configs": int(len(s1) // s1.cost_mult.nunique()),
        "backtests": int(len(s1)),
    }

    # ---------- stage 2: honest fills, best per market, cost stress ----------
    s2 = _read(OUT / "stage2_paper")
    s2["family"] = s2["mode"].map(FAM)
    a1 = s2[(s2.cost_mult == 1) & (s2.trades >= 100)]
    a2 = s2[s2.cost_mult == 2][["symbol"] + CFGKEY + ["pf"]].rename(columns={"pf": "pf2x"})
    a0 = s2[s2.cost_mult == 0][["symbol"] + CFGKEY + ["pf"]].rename(columns={"pf": "pf0x"})
    m = a1.merge(a2, on=["symbol"] + CFGKEY, how="left").merge(
        a0, on=["symbol"] + CFGKEY, how="left")

    best = []
    for sym in ORDER:
        g = m[m.symbol == sym]
        if not len(g):
            continue
        b = g.loc[g.pf.idxmax()]
        best.append({
            "symbol": nm(sym), "family": b.family, "anchor": anchor_label(b),
            "band": round(float(b.band_k), 1),
            "trades": int(b.trades), "tpd": round(float(b.trades_per_day), 2),
            "pf": round(float(b.pf), 3),
            "pf2x": round(float(b.pf2x), 3) if pd.notna(b.pf2x) else None,
            "win": round(float(b.win_rate), 3),
            "avg_r": round(float(b.avg_r), 3),
            "hold": round(float(b.avg_hold_h), 1),
            "sharpe": round(float(b.sharpe), 2),
            "resolve": (round(float(b.days_to_target), 0)
                        if np.isfinite(b.days_to_target) else None),
            "gate": int((g.pf >= 1.2).sum()),
            "gate2x": int((g.pf2x >= 1.2).sum()),
        })
    d["best"] = best
    d["stage2"] = {
        "configs": int(len(a1)),
        "gate": int((m.pf >= 1.2).sum()),
        "gate2x": int((m.pf2x >= 1.2).sum()),
        "median2x_of_gate": round(float(m[m.pf >= 1.2].pf2x.median()), 3),
        "over16": int((m.pf >= 1.6).sum()),
    }

    # ---------- family comparison ----------
    fam = []
    for name, g in a1.groupby("family"):
        fam.append({"family": name, "configs": int(len(g)),
                    "median": round(float(g.pf.median()), 3),
                    "best": round(float(g.pf.max()), 3),
                    "gate": int((g.pf >= 1.2).sum()),
                    "tpd": round(float(g.trades_per_day.median()), 2)})
    d["families"] = sorted(fam, key=lambda r: -r["median"])

    # ---------- stage 3: timeframe x null benchmark ----------
    p3q, p3 = OUT / "stage3_timeframes.parquet", OUT / "stage3_timeframes.csv"
    if p3q.exists() or p3.exists():
        # pandas reads the literal string "null" as NaN, which silently emptied
        # the entire null benchmark. Keep the column as written.
        s3 = (pd.read_parquet(p3q) if p3q.exists()
              else pd.read_csv(p3, keep_default_na=False, na_values=[""], low_memory=False))
        s3["trades"] = pd.to_numeric(s3.trades, errors="coerce")
        s3["pf"] = pd.to_numeric(s3.pf, errors="coerce")
        s3["trades_per_day"] = pd.to_numeric(s3.trades_per_day, errors="coerce")
        s3 = s3[(s3.trades >= 100) & s3.pf.notna()]
        rows = []
        for (sym, tf), g in s3.groupby(["symbol", "tf"]):
            r, n = g[g.kind == "real"], g[g.kind.isin(["null", "shuffled"])]
            if not len(r) or not len(n):
                continue
            rows.append({
                "symbol": nm(sym), "tf": tf,
                "real_best": round(float(r.pf.max()), 3),
                "real_16": int((r.pf >= 1.6).sum()),
                "null_best": round(float(n.pf.max()), 3),
                "null_16": int((n.pf >= 1.6).sum()),
                "edge": round(float(r.pf.max() - n.pf.max()), 3),
                "beats": bool(r.pf.max() > n.pf.max() and (r.pf >= 1.6).sum() > (n.pf >= 1.6).sum()),
                "tpd": round(float(r.loc[r.pf.idxmax(), "trades_per_day"]), 2),
            })
        order_tf = {"5m": 0, "15m": 1, "30m": 2, "1h": 3, "4h": 4}
        rows.sort(key=lambda r: (ORDER.index([k for k, v in NICE.items()
                                              if v == r["symbol"]] [0] if r["symbol"] in NICE.values()
                                             else r["symbol"]), order_tf.get(r["tf"], 9)))
        d["tfnull"] = rows
        d["tfnull_summary"] = {
            "combos": len(rows),
            "beat": sum(1 for r in rows if r["beats"]),
            "null_over16": sum(r["null_16"] for r in rows),
            "real_over16": sum(r["real_16"] for r in rows),
            "null_best": round(max(r["null_best"] for r in rows), 3),
        }
    return d


if __name__ == "__main__":
    data = collect()
    (OUT / "report_data.json").write_text(json.dumps(data, indent=1))
    tpl = (Path(__file__).parent / "report_template.html").read_text()
    (OUT / "report.html").write_text(tpl.replace("/*__DATA__*/", json.dumps(data)))
    print("wrote report.html")
    print(" fill totals:", data["fill_totals"])
    print(" stage2:", data["stage2"])
    print(" tfnull:", data.get("tfnull_summary"))
