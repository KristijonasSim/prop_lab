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
    # ---------- stage 6/7: the walk-forward ----------
    d.update(collect_wf())
    return d


def collect_wf() -> dict:
    """Stage 6 walk-forward and its null, plus the stage 7 robustness read.

    Everything here is out of sample by construction: the configuration and the
    filter were chosen on the train slice of each fold and never saw the quarter
    they traded."""
    d: dict = {}
    real_p, null_p = OUT / "stage6_stitched.csv", OUT / "stage6_stitched_shuffled.csv"
    if not real_p.exists():
        return d
    r = pd.read_csv(real_p)
    n = pd.read_csv(null_p) if null_p.exists() else None

    def worst_by_combo(df):
        piv = df.pivot_table(index=["symbol", "tf"], columns=["floor", "topn"], values="pf")
        return piv, piv.min(axis=1)

    piv_r, worst_r = worst_by_combo(r)
    d["wf_summary"] = {
        "cells": int(len(r)),
        "combos": int(piv_r.shape[0]),
        "median": round(float(r.pf.median()), 3),
        "best": round(float(r.pf.max()), 3),
        "gate": int((r.pf >= 1.2).sum()),
        "gate2x": int((r.pf_2x >= 1.2).sum()),
        "above1": round(float((r.pf > 1).mean()), 4),
        "survivors": int((worst_r >= 1.2).sum()),
    }
    if n is not None:
        piv_n, worst_n = worst_by_combo(n)
        d["wf_null"] = {
            "cells": int(len(n)),
            "median": round(float(n.pf.median()), 3),
            "best": round(float(n.pf.max()), 3),
            "gate": int((n.pf >= 1.2).sum()),
            "gate2x": int((n.pf_2x >= 1.2).sum()),
            "above1": round(float((n.pf > 1).mean()), 4),
            "survivors": int((worst_n >= 1.2).sum()),
        }

    # per-combination grid: PF under each selection rule, worst across all four
    rows = []
    for (sym, tf), g in r.groupby(["symbol", "tf"]):
        cell = {f"r{int(x.floor)}_{int(x.topn)}": round(float(x.pf), 3)
                for x in g.itertuples()}
        nb = None
        if n is not None:
            gn = n[(n.symbol == sym) & (n.tf == tf)]
            nb = round(float(gn.pf.max()), 3) if len(gn) else None
        rows.append({
            "symbol": nm(sym), "tf": tf,
            "quarters": int(g.quarters.max()),
            **cell,
            "worst": round(float(g.pf.min()), 3),
            "best": round(float(g.pf.max()), 3),
            "null_best": nb,
            "survivor": bool(g.pf.min() >= 1.2),
        })
    rows.sort(key=lambda x: -x["worst"])
    d["wf_grid"] = rows

    # ---------- the legs that survive, and the recency split ----------
    tp = OUT / "stage6_trades.parquet"
    if tp.exists():
        tr = pd.read_parquet(tp)
        tr["exit_ts"] = pd.to_datetime(tr.exit_ts, utc=True)
        tr["entry_ts"] = pd.to_datetime(tr.entry_ts, utc=True)

        def pf_of(a):
            w, l = a[a > 0].sum(), -a[a < 0].sum()
            return float(w / l) if l > 0 else float("nan")

        legs = []
        for (sym, tf), _ in r[r.set_index(["symbol", "tf"]).index.isin(
                worst_r[worst_r >= 1.2].index)].groupby(["symbol", "tf"]):
            g = r[(r.symbol == sym) & (r.tf == tf)]
            b = g.loc[g.pf.idxmax()]
            t = tr[(tr.symbol == sym) & (tr.tf == tf) &
                   (tr.floor == b.floor) & (tr.topn == b.topn)].sort_values("exit_ts")
            recent = t[t.exit_ts >= "2024-09-01"]
            span = (t.exit_ts.iloc[-1] - t.exit_ts.iloc[0]).total_seconds() / 86400.0
            hold = (t.exit_ts.values - t.entry_ts.values).astype(
                "timedelta64[s]").astype(float).mean() / 3600.0
            legs.append({
                "symbol": nm(sym), "tf": tf,
                "rule": f"floor {int(b.floor)}, top {int(b.topn)}",
                "quarters": int(b.quarters), "q_above_1": int(b.q_above_1),
                "trades": int(b.trades), "pf": round(float(b.pf), 3),
                "pf2x": round(float(b.pf_2x), 3),
                "win": round(float(b.win), 4),
                "avg_r": round(float(t.r.mean()), 4),
                "hold": round(float(hold), 1),
                "tpd": round(len(t) / max(span, 1e-9), 3),
                "recent_r": round(float(recent.r.sum()), 1) if len(recent) else None,
                "recent_pf": (round(pf_of(recent.r.values), 3) if len(recent) else None),
                "keep": bool(len(recent) and recent.r.sum() > 0),
            })
        legs.sort(key=lambda x: (not x["keep"], -x["pf"]))
        d["wf_legs"] = legs

        # BTC 4h year by year - the longest blind record in the project
        b4 = tr[(tr.symbol == "BTCUSDT") & (tr.tf == "4h") &
                (tr.floor == 100) & (tr.topn == 1)].sort_values("exit_ts")
        if len(b4):
            b4 = b4.assign(yr=b4.exit_ts.dt.year)
            d["wf_btc_years"] = [
                {"year": int(y), "trades": int(len(g)),
                 "pf": round(pf_of(g.r.values), 3),
                 "total_r": round(float(g.r.sum()), 1)}
                for y, g in b4.groupby("yr")]

        # The book uses only survivors that are still positive on the recent
        # window. BTC 30m and 1h clear the gate over thirty quarters purely on
        # pre-2024 performance, and including them drags the book to breakeven.
        keep = []
        for sym, tf in worst_r[worst_r >= 1.2].index:
            rec = tr[(tr.symbol == sym) & (tr.tf == tf) &
                     (tr.exit_ts >= "2024-09-01")]
            if len(rec) and rec.r.sum() > 0:
                keep.append((sym, tf))
        d["wf_book_legs"] = [f"{nm(a)} {b}" for a, b in keep]
        book = []
        for fl, tn in [(100, 1), (100, 10), (30, 1), (30, 10)]:
            sel = tr[(tr.floor == fl) & (tr.topn == tn) & (tr.exit_ts >= "2024-09-01")]
            sel = sel[[(x, y) in keep for x, y in zip(sel.symbol, sel.tf)]]
            if sel.empty:
                continue
            sel = sel.sort_values("exit_ts")
            nl = sel.groupby(["symbol", "tf"]).ngroups
            rr = sel.r.values / nl
            eq = np.concatenate(([0.0], np.cumsum(rr)))
            span = (sel.exit_ts.iloc[-1] - sel.exit_ts.iloc[0]).total_seconds() / 86400.0
            book.append({
                "rule": f"floor {fl}, top {tn}", "legs": int(nl),
                "trades": int(len(rr)), "pf": round(pf_of(rr), 3),
                "pf2x": round(pf_of(sel.r_2x.values / nl), 3),
                "tpd": round(len(rr) / max(span, 1e-9), 2),
                "max_dd": round(float((eq - np.maximum.accumulate(eq)).min()) * 0.0075, 4),
            })
        d["wf_book"] = book

    # prop simulation run on walk-forward output, not on fitted configs
    pp = OUT / "stage7_prop.csv"
    if pp.exists():
        pr = pd.read_csv(pp)
        pr = pr[pr.risk == 0.0075].sort_values("pf", ascending=False)
        d["wf_prop"] = [{
            "symbol": nm(x.symbol), "tf": x.tf,
            "rule": f"floor {int(x.floor)}, top {int(x.topn)}",
            "pf": round(float(x.pf), 3), "tpd": round(float(x.tpd), 2),
            "cagr": round(float(x.cagr), 4), "max_dd": round(float(x.max_dd), 4),
            "pass_rate": round(float(x.pass_rate), 4),
            "fail_max": round(float(x.fail_max), 4),
            "median_days": (float(x.median_days_pass)
                            if pd.notna(x.median_days_pass) else None),
        } for x in pr.head(8).itertuples()]
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
    print(" walk-forward:", data.get("wf_summary"))
    print(" null:", data.get("wf_null"))
